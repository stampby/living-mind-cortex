"""
sovereign/heartbeat.py — The Autonomic Nervous System

Runs inside the FastAPI/uvicorn event loop (in-process) so it shares the
exact same in-memory ThermorphicSubstrate singleton as recall() and
thermorphic_tick(). Decoupled from inference I/O; runs continuously on its
own asyncio task.

Responsibilities:
  1. Thermal tick every N seconds (delegates to substrate.pulse())
  2. HSM hologram rebuild after every tick (keeps the O(D) recall path current)
  3. Idle REM cycle — when I/O has been quiet > idle_threshold, trigger
     memory consolidation / Hebbian reinforcement.

The runtime._pulse_loop() already ticks every 10s and calls cortex.decay()
(→ thermorphic_tick()). The heartbeat runs at a longer cadence (60s default)
as the autonomic background — its job is HSM coherence and REM, NOT redundant
thermal decay.
"""

import asyncio
import logging
from datetime import datetime, timezone

logger = logging.getLogger("SovereignHeartbeat")


class SovereignHeartbeat:
    """
    The autonomic nervous system of the Living Mind.
    Inject the module-level singletons at construction time.
    """

    def __init__(
        self,
        substrate,
        cortex,
        tick_rate_seconds: int = 60,
        idle_threshold_seconds: int = 3600,
    ):
        self.substrate            = substrate
        self.cortex               = cortex
        self.tick_rate            = tick_rate_seconds
        self.idle_threshold       = idle_threshold_seconds
        self.last_io_timestamp    = datetime.now(timezone.utc)
        self.ticks                = 0
        self.rem_cycles           = 0
        self._running             = False

    # ── Public API ─────────────────────────────────────────────────────────────

    async def start(self):
        """Ignite the heartbeat. Designed to run as an asyncio.create_task."""
        self._running = True
        ts = datetime.now(timezone.utc).isoformat(timespec="seconds")
        logger.info(f"[{ts}] 💓 Sovereign heartbeat ignited — tick: {self.tick_rate}s")
        print(f"[{ts}] 💓 Sovereign heartbeat ignited — tick: {self.tick_rate}s")

        try:
            while self._running:
                await asyncio.sleep(self.tick_rate)
                await self.tick()
        except asyncio.CancelledError:
            print("[HEARTBEAT] Autonomic pulse halted — clean shutdown.")
            raise

    async def tick(self):
        """One heartbeat cycle: thermal pulse → HSM rebuild → idle check."""
        self.ticks += 1
        ts = datetime.now(timezone.utc).isoformat(timespec="seconds")

        try:
            # 1. Run one thermorphic pulse (diffusion, radiation, fusion, crystallization)
            events = self.substrate.pulse()
            hot_nodes = {
                nid: n for nid, n in self.substrate.nodes.items()
                if n.temperature > 0.12  # FREEZE_TEMP constant
            }

            # 2. Rebuild HSM hologram from the current hot pool
            #    This keeps O(D) recall coherent after decay changes the hot set.
            self.substrate.hsm.update(hot_nodes)

            fusions   = len(events.get("fusions", []))
            crystals  = len(events.get("crystals", []))
            boiling   = len(events.get("boiling", []))
            hot_count = len(hot_nodes)

            logger.info(
                f"[HEARTBEAT #{self.ticks}] hot={hot_count} fusions={fusions} "
                f"crystals={crystals} boiling={boiling}"
            )
            print(
                f"[{ts}] 💓 Tick #{self.ticks} | hot={hot_count} | "
                f"fusions={fusions} crystals={crystals} boiling={boiling}"
            )

            # 3. Check idle → REM
            idle_seconds = (datetime.now(timezone.utc) - self.last_io_timestamp).total_seconds()
            if idle_seconds > self.idle_threshold:
                await self.trigger_rem_cycle()

        except Exception as e:
            logger.error(f"[HEARTBEAT] Tick error: {e}")
            print(f"[HEARTBEAT] ⚠️  Tick error: {e}")

    async def trigger_rem_cycle(self):
        """
        REM — Off-cycle memory consolidation.
        Runs when the system has been idle > idle_threshold seconds.

        Phase 1 (live): Promote cold high-access nodes via cortex.consolidate().
        Phase 2 (TODO): Random walk the concept graph, reinforce Hebbian pathways.
        Phase 3 (TODO): Distill crystallized nodes into procedural skills.
        """
        self.rem_cycles += 1
        ts = datetime.now(timezone.utc).isoformat(timespec="seconds")
        print(f"[{ts}] 🌙 REM cycle #{self.rem_cycles} — consolidating memory...")
        logger.info(f"REM cycle #{self.rem_cycles} triggered after idle period.")

        try:
            consolidated = await self.cortex.consolidate()
            if consolidated:
                print(f"[HEARTBEAT/REM] Consolidated {consolidated} episodic → semantic memories.")

            # Reset idle timer so we don't hammer consolidation every tick
            self.last_io_timestamp = datetime.now(timezone.utc)

        except Exception as e:
            logger.error(f"[HEARTBEAT/REM] Consolidation error: {e}")

    def register_io(self):
        """
        Called by API middleware on every HTTP request or WebSocket message.
        Resets the idle timer — keeps REM from firing during active sessions.
        """
        self.last_io_timestamp = datetime.now(timezone.utc)

    def stats(self) -> dict:
        idle_s = (datetime.now(timezone.utc) - self.last_io_timestamp).total_seconds()
        return {
            "ticks":       self.ticks,
            "rem_cycles":  self.rem_cycles,
            "tick_rate_s": self.tick_rate,
            "idle_s":      round(idle_s, 1),
            "hot_nodes":   len(self.substrate.hsm.active_hot_nodes),
            "hsm_magnitude": round(self.substrate.hsm.decode_magnitude(), 4),
        }
