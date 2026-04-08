"""
cortex/adapter_lifecycle.py

AdapterLifecycleManager: The VRAM Eviction Daemon.

Runs as an asyncio background task. On every tick it:
  1. Calls heatsink.purge_frozen() to identify sublimated domains.
  2. For each cold domain: calls inference_client.unload_lora(domain).
     Only on confirmed HTTP 200 does it remove the plasma record.
  3. When a new domain is routed to for the first time, ensures its
     adapter is physically loaded before the generation pass fires.

Order of operations is strict:
  UNLOAD -> PURGE   (guaranteed by this manager)
  LOAD   -> ROUTE   (guaranteed by ensure_loaded())

If unload fails, the domain stays in the plasma registry so it's
still tracked — we don't silently lose VRAM accounting.
"""

import asyncio
import os
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from cortex.heatsink import ThermomorphicMemoryPlasma
    from core.inference import SovereignInferenceClient


# ── Path Registry ─────────────────────────────────────────────────────────────
# Maps domain_id -> filesystem path where the adapter weights live.
# Populate this from config / env at startup.

ADAPTER_PATHS: dict[str, str] = {
    "code_expert":  os.environ.get("LORA_PATH_CODE",  "./code_expert"),
    "logic_expert": os.environ.get("LORA_PATH_LOGIC", "./logic_expert"),
}

# Domains resurrected after a failed unload receive this temperature.
#
# Physics rationale:
#   - Must be above sublimation threshold (1.0K) so the record stays in registry.
#   - Must be above absolute_zero so get_temp() does NOT auto-evict immediately.
#   - Must be LOW enough that thermal_weight = 1.0 + (5.0 / 500.0) = 1.01x
#     barely amplifies routing scores — a ghost won't win the MoE race.
#   - At k=0.005: 5.0K × e^(-0.005 × 60) = 3.7K after first sweep tick.
#     Crosses 1.0K threshold in ln(5.0) / 0.005 ≈ 322 seconds (~5 sweeps).
#     That gives us 5 automatic retry windows before the ghost becomes permanent.
GHOST_SENTINEL_TEMP: float = 5.0


class AdapterLifecycleManager:
    """
    Background daemon to keep VRAM state synchronized with the plasma heatsink.
    Boot once per process in the FastAPI lifespan, same as the heartbeat.
    """

    def __init__(
        self,
        heatsink: "ThermomorphicMemoryPlasma",
        inference_client: "SovereignInferenceClient",
        poll_interval_seconds: float = 60.0,
    ):
        self.heatsink = heatsink
        self.client   = inference_client
        self.interval = poll_interval_seconds
        # Tracks domains whose vLLM unload failed: weights still in VRAM,
        # plasma record resurrected at GHOST_SENTINEL_TEMP.
        # Key = domain_id, Value = number of consecutive failed unload attempts.
        self._ghost_domains: dict[str, int] = {}

    async def start(self) -> None:
        """
        Long-running eviction loop. Cancel via asyncio task cancellation.
        """
        print(f"[LifecycleMgr] VRAM eviction daemon started "
              f"(poll interval: {self.interval}s).")
        
        # Initial sync to pick up resident adapters from previous runs
        await self.client.sync_loaded_adapters()

        try:
            while True:
                await asyncio.sleep(self.interval)
                await self._eviction_sweep()
        except asyncio.CancelledError:
            print("[LifecycleMgr] Eviction daemon halted.")

    async def _eviction_sweep(self) -> None:
        """
        Identify sublimated domains and evict their adapters from VRAM.

        Critical ordering:
          1. Snapshot temperatures BEFORE purge_frozen() auto-deletes records.
          2. Call unload_lora() against vLLM.
          3a. On success: record is gone, _ghost_domains cleared.
          3b. On failure: resurrect at GHOST_SENTINEL_TEMP so the ghost stays
              trackable and unroutable. Store retry count in _ghost_domains.

        Ghost scenario prevented:
          Without the pre-purge snapshot, a failed unload writes back at 1.0K
          which immediately re-crosses the sublimation threshold and auto-purges,
          leaving weights in VRAM with no plasma record — a permanent blind spot.
        """
        # ── 1. Snapshot pre-purge temperatures ────────────────────────────
        # get_temp() auto-deletes domains below 1.0K threshold. We must read
        # temperatures BEFORE calling purge_frozen() which triggers those deletes.
        candidate_temps: dict[str, float] = {}
        for domain_id in list(self.heatsink.domains):
            t = self.heatsink.get_temp(domain_id)  # may auto-delete
            if t <= self.heatsink.absolute_zero:    # already purged by get_temp
                candidate_temps[domain_id] = t
        # purge_frozen() now just returns what get_temp() already cleaned up
        frozen = self.heatsink.purge_frozen()
        if not frozen and not candidate_temps:
            return
        all_sublimated = list(set(list(frozen) + list(candidate_temps.keys())))

        if all_sublimated:
            print(f"[LifecycleMgr] Sweep found {len(all_sublimated)} "
                  f"sublimated domain(s): {all_sublimated}")

        # ── 2 & 3. Unload each sublimated domain ───────────────────────────
        for domain_id in all_sublimated:
            evicted = await self.client.unload_lora(domain_id)

            if evicted:
                # Confirmed gone from VRAM. Clear any ghost tracking.
                self._ghost_domains.pop(domain_id, None)
                print(f"[LifecycleMgr] '{domain_id}' fully evicted. VRAM reclaimed.")
            else:
                # ── Ghost prevention ────────────────────────────────────
                # Weights are still in VRAM. The plasma record was auto-purged.
                # Resurrect at GHOST_SENTINEL_TEMP so the domain stays in registry
                # and can't win routing (5.0K → 1.01x multiplier only).
                retry_count = self._ghost_domains.get(domain_id, 0) + 1
                self._ghost_domains[domain_id] = retry_count

                # Force-write back into heatsink bypassing resonate()'s add logic:
                # resonate() would add friction_heat ON TOP of current temp,
                # but the record was deleted. We need to set it to exactly GHOST_SENTINEL_TEMP.
                import time
                self.heatsink.domains[domain_id] = {
                    'temp':      GHOST_SENTINEL_TEMP,
                    'last_seen': time.time(),
                    'data':      None,
                }
                print(
                    f"[LifecycleMgr] GHOST WARNING: '{domain_id}' unload failed "
                    f"(attempt {retry_count}). Resurrected at {GHOST_SENTINEL_TEMP}K. "
                    f"Weights still in VRAM. Router blocked. Next sweep in ~{self.interval:.0f}s."
                )

    async def ensure_loaded(self, adapter_id: str) -> bool:
        """
        Called by the router on first resonance with a domain.
        Loads the adapter if it's not already in VRAM.

        Returns True if the adapter is ready to serve, False if load failed
        (caller should fall back to base_model generation).
        """
        if adapter_id == "base_model":
            return True  # Base substrate is always hot

        if self.client.is_loaded(adapter_id):
            return True  # Already resident — fast path

        path = ADAPTER_PATHS.get(adapter_id)
        if not path:
            print(f"[LifecycleMgr] ERROR: No path registered for adapter '{adapter_id}'.")
            return False

        return await self.client.load_lora(adapter_id, path)
