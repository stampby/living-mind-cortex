"""
sovereign/heartbeat.py — The Autonomic Nervous System

Runs inside the FastAPI/uvicorn event loop (in-process) so it shares the
exact same in-memory ThermorphicSubstrate singleton as recall() and
thermorphic_tick(). Decoupled from inference I/O; runs continuously on its
own asyncio task.

Responsibilities:
  1. HSM hologram rebuild after every tick (keeps the O(D) recall path current)
  2. Idle REM cycle — when I/O has been quiet > idle_threshold, trigger
     memory consolidation.

Phase 1 (live): cortex.consolidate() — episodic → semantic promotion
Phase 2 (live): process_hebbian_wiring() — co-access graph edges
Phase 3 (live): process_semantic_distillation() — LLM crystal synthesis
                with extractive fallback when Ollama is offline.

NOTE: thermal decay is already driven by runtime._pulse_loop via cortex.decay()
every 10 pulses. The heartbeat's job is HSM coherence and REM only.
"""

import asyncio
import logging
import aiohttp
from datetime import datetime, timezone

logger = logging.getLogger("SovereignHeartbeat")

OLLAMA_URL    = "http://localhost:11434/api/generate"
DISTILL_MODEL = "gemma4-auditor"
OLLAMA_TIMEOUT = aiohttp.ClientTimeout(total=45)


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
        bus=None,   # Optional AgentBus — injected to avoid circular imports
    ):
        self.substrate            = substrate
        self.cortex               = cortex
        self.tick_rate            = tick_rate_seconds
        self.idle_threshold       = idle_threshold_seconds
        self.last_io_timestamp    = datetime.now(timezone.utc)
        self.ticks                = 0
        self.rem_cycles           = 0
        self.crystals_formed      = 0
        self._running             = False
        self._session: aiohttp.ClientSession | None = None
        self._bus                 = bus   # AgentBus | None

    # ── Public API ─────────────────────────────────────────────────────────────

    async def start(self):
        """Ignite the heartbeat. Designed to run as an asyncio.create_task."""
        self._running = True
        self._session = aiohttp.ClientSession()
        ts = datetime.now(timezone.utc).isoformat(timespec="seconds")
        logger.info(f"[{ts}] 💓 Sovereign heartbeat ignited — tick: {self.tick_rate}s")
        print(f"[{ts}] 💓 Sovereign heartbeat ignited — tick: {self.tick_rate}s")

        try:
            while self._running:
                await asyncio.sleep(self.tick_rate)
                await self.tick()
        except asyncio.CancelledError:
            print("[HEARTBEAT] Autonomic pulse halted — clean shutdown.")
            if self._session and not self._session.closed:
                await self._session.close()
            raise

    async def tick(self):
        """One heartbeat cycle: HSM rebuild from current hot pool → idle check."""
        self.ticks += 1
        ts = datetime.now(timezone.utc).isoformat(timespec="seconds")

        try:
            hot_nodes = {
                nid: n for nid, n in self.substrate.nodes.items()
                if n.temperature > 0.12  # FREEZE_TEMP
            }
            self.substrate.hsm.update(hot_nodes)

            hot_count = len(hot_nodes)
            hsm_mag   = round(self.substrate.hsm.decode_magnitude(), 4)

            logger.info(f"[HEARTBEAT #{self.ticks}] hot={hot_count} hsm_magnitude={hsm_mag}")
            print(f"[{ts}] 💓 Tick #{self.ticks} | hot={hot_count} | hsm_mag={hsm_mag}")

            idle_seconds = (datetime.now(timezone.utc) - self.last_io_timestamp).total_seconds()
            if idle_seconds > self.idle_threshold:
                await self.trigger_rem_cycle()

            if self._bus is not None:
                try:
                    await self._bus.heartbeat()
                except Exception as bus_err:
                    logger.warning(f"[HEARTBEAT] Bus heartbeat error: {bus_err}")

        except Exception as e:
            logger.error(f"[HEARTBEAT] Tick error: {e}")
            print(f"[HEARTBEAT] ⚠️  Tick error: {e}")

    async def trigger_rem_cycle(self):
        """
        REM — Off-cycle memory consolidation.
        Three phases, each bounded and independently guarded.
        """
        self.rem_cycles += 1
        ts = datetime.now(timezone.utc).isoformat(timespec="seconds")
        print(f"[{ts}] 🌙 REM cycle #{self.rem_cycles} initiated...")
        logger.info(f"REM cycle #{self.rem_cycles} triggered after idle period.")

        try:
            # ── Phase 1: Episodic → Semantic consolidation ──────────────────
            consolidated = await self.cortex.consolidate()
            if consolidated:
                print(f"[REM P1] Consolidated {consolidated} episodic → semantic memories.")

            # ── Phase 2: Hebbian co-activation wiring ───────────────────────
            edges = await self.cortex.process_hebbian_wiring(window_seconds=3600)
            print(f"[REM P2] Hebbian wiring complete — {edges} edges upserted.")

            # ── Phase 3: Semantic Distillation ──────────────────────────────
            crystal = await self.process_semantic_distillation(
                cycle_number=self.rem_cycles,
                batch_size=10,
            )
            if crystal:
                print(f"[REM P3] Crystal formed: {crystal['summary_id']} "
                      f"({crystal['source_count']} nodes → 1) "
                      f"[{'LLM' if crystal['llm_used'] else 'extractive'}]")

            # Reset idle timer
            self.last_io_timestamp = datetime.now(timezone.utc)

        except Exception as e:
            logger.error(f"[HEARTBEAT/REM] Error during REM cycle: {e}")
            print(f"[HEARTBEAT/REM] ⚠️  REM error: {e}")

    # ── Phase 3: Semantic Distillation ─────────────────────────────────────────

    async def process_semantic_distillation(
        self,
        cycle_number: int,
        batch_size: int = 10,
    ) -> dict | None:
        """
        Crystallization: compress a cluster of cold, un-distilled memories into a
        single dense semantic crystal written back to PostgreSQL.

        Strategy:
          1. Fetch oldest cold memories not yet distilled (importance > 0.01)
          2. Synthesize via Ollama (gemma4-auditor) with 45s timeout
          3. Extractive fallback if Ollama is offline/slow
          4. Transactional write: insert crystal, archive sources, log lineage
        """
        async with self.cortex._pool.acquire() as conn:
            cold_nodes = await conn.fetch("""
                SELECT id, content, importance, type
                FROM memories
                WHERE importance > 0.01
                  AND last_accessed < extract(epoch from now()) - 86400
                  AND id NOT IN (
                      SELECT unnest(source_ids) FROM rem_distillations
                  )
                  AND type IN ('semantic', 'episodic')
                ORDER BY created_at ASC
                LIMIT $1
            """, batch_size)

        if not cold_nodes:
            print("[REM P3] No cold clusters require distillation.")
            return None

        source_ids   = [str(r["id"]) for r in cold_nodes]
        source_texts = [r["content"] for r in cold_nodes]

        print(f"[REM P3] Distilling {len(source_ids)} cold nodes...")

        # ── LLM synthesis (with extractive fallback) ─────────────────────────
        crystal_text, llm_used = await self._synthesize(source_texts)

        # ── Transactional write ───────────────────────────────────────────────
        import uuid as _uuid
        summary_id = str(_uuid.uuid4())

        async with self.cortex._pool.acquire() as conn:
            async with conn.transaction():
                # A. Insert the crystallized memory
                await conn.execute("""
                    INSERT INTO memories (
                        id, content, type, importance,
                        tags, emotion, confidence, source, context
                    ) VALUES (
                        $1::uuid, $2, 'semantic', 0.95,
                        ARRAY['crystal', 'rem', 'distilled'], 'neutral',
                        0.9, 'generated',
                        $3
                    )
                """,
                    summary_id,
                    f"[CRYSTAL] {crystal_text}",
                    f"rem_cycle={cycle_number} sources={len(source_ids)}"
                )

                # B. Archive source nodes — importance → 0.01 (preserved, not deleted)
                #    Tag with 'archived_rem' for reliable querying (avoids REAL float precision)
                await conn.execute("""
                    UPDATE memories
                    SET importance = 0.01,
                        tags = array_append(
                            array_append(tags, 'archived'),
                            'archived_rem'
                        )
                    WHERE id = ANY($1::uuid[])
                      AND NOT ('archived_rem' = ANY(tags))
                """, source_ids)

                # C. Log lineage
                await conn.execute("""
                    INSERT INTO rem_distillations
                        (source_ids, summary_id, rem_cycle)
                    VALUES ($1::uuid[], $2::uuid, $3)
                """, source_ids, summary_id, cycle_number)

        self.crystals_formed += 1

        return {
            "summary_id":   summary_id,
            "source_count": len(source_ids),
            "llm_used":     llm_used,
            "preview":      crystal_text[:120],
        }

    async def _synthesize(self, source_texts: list[str]) -> tuple[str, bool]:
        """
        Try Ollama synthesis; fall back to extractive summary if unavailable.
        Returns (crystal_text, llm_used).
        """
        prompt = (
            "Synthesize the following memory fragments into a single, dense semantic crystal. "
            "Preserve core technical facts, decisions, and outcomes. Strip conversational filler. "
            "Output only the synthesized text, no preamble.\n\n"
            + "\n".join(f"- {t}" for t in source_texts)
        )

        try:
            if self._session is None or self._session.closed:
                self._session = aiohttp.ClientSession()

            async with self._session.post(
                OLLAMA_URL,
                json={
                    "model":  DISTILL_MODEL,
                    "prompt": prompt,
                    "stream": False,
                    "options": {"temperature": 0.2, "num_predict": 300},
                },
                timeout=OLLAMA_TIMEOUT,
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    text = data.get("response", "").strip()
                    if text:
                        return text, True
        except Exception as e:
            logger.warning(f"[REM P3] Ollama unavailable ({e}), using extractive fallback.")

        # Extractive fallback: pick the two longest / most content-dense fragments
        ranked = sorted(source_texts, key=len, reverse=True)[:3]
        fallback = " | ".join(t.replace("\n", " ")[:120] for t in ranked)
        return f"[EXTRACTIVE] {fallback}", False

    def register_io(self):
        """Reset idle timer on every HTTP request / WebSocket message."""
        self.last_io_timestamp = datetime.now(timezone.utc)

    def stats(self) -> dict:
        idle_s = (datetime.now(timezone.utc) - self.last_io_timestamp).total_seconds()
        return {
            "ticks":          self.ticks,
            "rem_cycles":     self.rem_cycles,
            "crystals_formed": self.crystals_formed,
            "tick_rate_s":    self.tick_rate,
            "idle_s":         round(idle_s, 1),
            "hot_nodes":      len(self.substrate.hsm.active_hot_nodes),
            "hsm_magnitude":  round(self.substrate.hsm.decode_magnitude(), 4),
        }
