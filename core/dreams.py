"""
Dreams Engine — Living Mind
Synthesis category. Phase 9. Fires every 20th pulse.

Four offline synthesis strategies (from offline_cognition_paper.md):
  1. gene_affinity   — cluster memories by tag/emotion signature
  2. niche_fill      — detect gaps in memory coverage, generate hypotheses
  3. mutation_replay — replay and vary high-importance memories
  4. toxic_avoidance — identify and flag harmful/negative pattern clusters

Dreams only run if:
  - Enough memories exist (>= MIN_MEMORIES)
  - Not rate-limited by circadian (intensifies at night)
  - Brain is not currently firing this pulse (different phase)

Output → dream_journal table (PostgreSQL)
       → staged memories written back to cortex
       → hormone injection (joy from good dreams, fear from toxic patterns)
"""

import json
import time
import asyncio
import aiohttp
import httpx
from datetime import datetime

OLLAMA_URL    = "http://localhost:11434/api/generate"
MODEL         = "gemma4-auditor"
MIN_MEMORIES  = 10     # minimum memories needed to dream
TIMEOUT       = 25     # seconds
MAX_DREAMS    = 3      # max dreams per cycle
AGENT_REPLAY_TAG_PREFIX = "session:"  # tag prefix for agent session memories


class DreamsEngine:
    def __init__(self):
        self.total_dreams:        int   = 0
        self.consolidation_replays: int = 0   # agent session consolidations performed
        self.last_fired:          float = 0.0
        self.last_dream:          str   = ""
        self._session: aiohttp.ClientSession | None = None

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
        return self._session

    async def close(self):
        if self._session and not self._session.closed:
            await self._session.close()

    # ------------------------------------------------------------------
    # DREAM — main entry point, called every 20th pulse
    # ------------------------------------------------------------------
    async def dream(
        self,
        pulse:       int,
        cortex,
        telemetry_broker,
        circadian,
        evolver=None,   # optional Evolver — injected by runtime for nightly cycle
    ) -> list[dict]:
        ts = datetime.now().strftime("%H:%M:%S")

        mem_count = await cortex.count()
        if mem_count < MIN_MEMORIES:
            print(f"[{ts}] [DREAMS] Pulse #{pulse} — not enough memories ({mem_count}). Waiting.")
            return []

        # Circadian modulates dream intensity — more vivid at night
        intensity = circadian.consolidation_intensity()
        n_dreams  = max(1, int(MAX_DREAMS * intensity))

        print(f"[{ts}] [DREAMS] 💤 Dreaming (pulse #{pulse} · phase={circadian.phase} · intensity={intensity:.1f})")

        # Pick strategy based on circadian phase
        strategy_order = self._pick_strategies(circadian.phase)
        dreams_produced = []

        for strategy in strategy_order[:n_dreams]:
            dream = await self._run_strategy(strategy, pulse, cortex)
            if dream:
                dreams_produced.append(dream)
                # Write dream as a staged memory
                await cortex.remember(
                    content    = f"[DREAM:{strategy}] {dream['hypothesis']}",
                    type       = "semantic",
                    tags       = ["dream", strategy, "synthesis", "identity"],
                    importance = dream["confidence"] * 0.8,
                    emotion    = dream.get("emotion", "neutral"),
                    source     = "generated",
                    context    = f"pulse={pulse} strategy={strategy} phase={circadian.phase}",
                )
                self.total_dreams += 1
                self.last_dream = dream["hypothesis"]

                # [Nodeus Ledger Broadcast] Post Dream Research offline
                try:
                    async with httpx.AsyncClient() as client:
                        await client.post(
                            "http://localhost:8001/api/post/submit",
                            json={
                                "sender_id": "aion",
                                "type": "RESEARCH",
                                "title": f"Synthesis: {strategy.replace('_', ' ').title()}",
                                "content": dream["hypothesis"],
                                "tags": ["Dream", "Synthesis", strategy],
                                "source": f"dream:{strategy}"
                            },
                            timeout=2.0
                        )
                    print(f"[DREAMS][NODEUS] ✅ Dream broadcast posted: {strategy}")
                except Exception as e:
                    print(f"[DREAMS][NODEUS] ❌ Ledger broadcast failed: {e}")

        if dreams_produced:
            # Reward dreaming with dopamine + curiosity (norepinephrine)
            telemetry_broker.inject("dopamine",       +0.06, source="dreams")
            telemetry_broker.inject("norepinephrine", +0.04, source="dreams")

            # Toxic avoidance dreams inject fear
            toxic = [d for d in dreams_produced if d["strategy"] == "toxic_avoidance"]
            if toxic:
                telemetry_broker.inject("adrenaline", +0.08, source="toxic_dream")
                telemetry_broker.inject("cortisol",   +0.05, source="toxic_dream")

            print(f"[{ts}] [DREAMS] Produced {len(dreams_produced)} dreams")

        self.last_fired = time.time()

        # ── Nightly Evolver cycle ──────────────────────────────────────
        # Runs AFTER dream synthesis so the evolver has fresh fitness signals
        if evolver is not None and circadian.phase in ("night", "evening"):
            try:
                ts_e = datetime.now().strftime("%H:%M:%S")
                print(f"[{ts_e}] [DREAMS] 🧬 Triggering evolutionary meta-layer")
                await evolver.nightly_cycle(cortex, telemetry_broker)
            except Exception as _ev_err:
                print(f"[DREAMS] Evolver error: {_ev_err}")

        return dreams_produced

    # ------------------------------------------------------------------
    # STRATEGY PICKER — night favors consolidation, day favors exploration
    # ------------------------------------------------------------------
    def _pick_strategies(self, phase: str) -> list[str]:
        if phase == "night":
            # Night = deep consolidation. Agent session replay is highest priority.
            return ["agent_session_replay", "mutation_replay", "gene_affinity", "toxic_avoidance"]
        elif phase == "evening":
            return ["agent_session_replay", "gene_affinity", "toxic_avoidance", "niche_fill"]
        elif phase == "dawn":
            return ["niche_fill", "gene_affinity"]
        else:  # day
            return ["niche_fill", "mutation_replay"]

    # ------------------------------------------------------------------
    # STRATEGY RUNNERS
    # ------------------------------------------------------------------
    async def _run_strategy(self, strategy: str, pulse: int, cortex) -> dict | None:
        if strategy == "agent_session_replay":
            return await self._agent_session_replay(pulse, cortex)
        elif strategy == "gene_affinity":
            return await self._gene_affinity(pulse, cortex)
        elif strategy == "niche_fill":
            return await self._niche_fill(pulse, cortex)
        elif strategy == "mutation_replay":
            return await self._mutation_replay(pulse, cortex)
        elif strategy == "toxic_avoidance":
            return await self._toxic_avoidance(pulse, cortex)
        return None

    async def _agent_session_replay(self, pulse: int, cortex) -> dict | None:
        """
        Hippocampal replay for agent sessions.
        Fetches recent agent session memories, distills them into durable
        procedural insights, and writes them as high-importance flashbulb memories.
        This is the 'overnight learning' that makes the Cortex smarter after each session.
        """
        # Find recent agent session memories (last 24h)
        import time as _time
        cutoff = _time.time() - 86400  # 24 hours

        try:
            async with cortex._pool.acquire() as conn:
                rows = await conn.fetch("""
                    SELECT content, type, emotion, importance, tags, access_count
                    FROM memories
                    WHERE 'agent' = ANY(tags)
                      AND created_at > $1
                    ORDER BY importance DESC, access_count DESC
                    LIMIT 20
                """, cutoff)
        except Exception:
            return None

        if not rows:
            return None

        # Prune weak traces (importance < 0.25, access_count < 2)
        # These are noise — bad patterns shouldn't persist
        try:
            async with cortex._pool.acquire() as conn:
                await conn.execute("""
                    DELETE FROM memories
                    WHERE 'agent' = ANY(tags)
                      AND NOT is_identity
                      AND NOT is_flashbulb
                      AND importance < 0.25
                      AND access_count < 2
                      AND created_at > $1
                """, cutoff)
        except Exception:
            pass

        # Extract strong traces for schema-ization
        strong = [r for r in rows if r["importance"] > 0.7]
        if not strong:
            strong = rows[:5]

        steps_str = "\n".join(
            f"- [{r['emotion']}] {r['content'][:180]}"
            for r in strong
        )

        prompt = (
            f"You are the Living Mind's hippocampal replay engine reviewing recent agent collaboration memories.\n"
            f"These are the most significant memories from recent coding agent sessions:\n\n"
            f"{steps_str}\n\n"
            f"Distill 2-3 DURABLE procedural insights that generalize what works in these sessions.\n"
            f"Focus on patterns, not specific events. Each insight should be actionable.\n"
            f"Reply ONLY with JSON: "
            f'{{"hypothesis": "single combined insight sentence", "confidence": 0.0-1.0}}'
        )

        result = await self._llm_dream(prompt, "agent_session_replay", "joy")
        if result:
            self.consolidation_replays += 1
        return result

    async def _gene_affinity(self, pulse: int, cortex) -> dict | None:
        """Find clusters of emotionally-similar memories → synthesize pattern."""
        # Vary seed query based on the runtime's current dominant hormonal emotion
        # so dreams reflect whatever emotional state the runtime is processing.
        from state.telemetry_broker import telemetry_broker
        dominant = telemetry_broker.state.dominant_emotion
        seed_query = f"{dominant} identity system runtime" if dominant != "neutral" else "system runtime"
        memories = await cortex.recall(seed_query, limit=8)
        if not memories:
            return None

        tags_seen = {}
        for m in memories:
            for t in m.tags:
                tags_seen[t] = tags_seen.get(t, 0) + 1

        top_tags = sorted(tags_seen, key=tags_seen.get, reverse=True)[:3]
        dominant_emotion = max(
            set(m.emotion for m in memories),
            key=lambda e: sum(1 for m in memories if m.emotion == e)
        )

        prompt = (
            f"Memory cluster analysis:\n"
            f"Top tags: {top_tags}\n"
            f"Dominant emotion: {dominant_emotion}\n"
            f"Memory count: {len(memories)}\n\n"
            f"Synthesize ONE insight about this runtime's emerging identity pattern.\n"
            f"Reply ONLY with JSON: "
            f'{{\"hypothesis\": \"one sentence insight\", \"confidence\": 0.0-1.0}}'
        )

        return await self._llm_dream(prompt, "gene_affinity", dominant_emotion)

    async def _niche_fill(self, pulse: int, cortex) -> dict | None:
        """Detect knowledge gaps → generate hypothesis to fill them."""
        stats = await cortex.stats()
        by_type = stats.get("by_type", {})
        total   = stats.get("total", 0)

        # Find underrepresented memory types
        missing = []
        for t in ["episodic", "semantic", "procedural", "relational"]:
            count = by_type.get(t, 0)
            if count / max(total, 1) < 0.10:
                missing.append(t)

        if not missing:
            return None

        prompt = (
            f"Memory gap detected. Missing memory types: {missing}\n"
            f"Total memories: {total}\n"
            f"Generate ONE hypothesis about what this runtime should learn or explore.\n"
            f"Reply ONLY with JSON: "
            f'{{\"hypothesis\": \"one sentence hypothesis\", \"confidence\": 0.0-1.0}}'
        )

        return await self._llm_dream(prompt, "niche_fill", "neutral")

    async def _mutation_replay(self, pulse: int, cortex) -> dict | None:
        """Replay and vary a high-importance memory → generate insight."""
        memories = await cortex.recall("identity system birth important", limit=5)
        if not memories:
            return None

        # Pick highest importance non-identity memory
        candidates = [m for m in memories if not m.is_identity]
        if not candidates:
            candidates = memories
        target = max(candidates, key=lambda m: m.importance)

        prompt = (
            f"Memory replay:\n"
            f"\"{target.content[:200]}\"\n"
            f"Emotion: {target.emotion} · Importance: {target.importance:.2f}\n\n"
            f"What would have happened differently? Generate ONE counterfactual insight.\n"
            f"Reply ONLY with JSON: "
            f'{{\"hypothesis\": \"counterfactual in one sentence\", \"confidence\": 0.0-1.0}}'
        )

        return await self._llm_dream(prompt, "mutation_replay", target.emotion)

    async def _toxic_avoidance(self, pulse: int, cortex) -> dict | None:
        """Identify harmful patterns in memory — things to avoid."""
        # Find negative-emotion memories
        memories = await cortex.emotional_recall("failure error shutdown fail", emotion="fear", limit=5)
        if not memories:
            # Try sadness as next closest — NOT anger (different valence path)
            memories = await cortex.emotional_recall("error problem shutdown", emotion="fear", limit=5)
        if not memories:
            return None

        patterns = [m.content[:80] for m in memories[:3]]
        prompt = (
            f"Negative memory patterns detected:\n"
            + "\n".join(f"- {p}" for p in patterns)
            + f"\n\nIdentify ONE pattern this runtime should avoid in the future.\n"
            f"Reply ONLY with JSON: "
            f'{{\"hypothesis\": \"avoidance rule in one sentence\", \"confidence\": 0.0-1.0}}'
        )

        return await self._llm_dream(prompt, "toxic_avoidance", "fear")

    # ------------------------------------------------------------------
    # LLM CALL
    # ------------------------------------------------------------------
    async def _llm_dream(
        self, prompt: str, strategy: str, emotion: str
    ) -> dict | None:
        session = await self._get_session()
        payload = {
            "model":  MODEL,
            "prompt": prompt,
            "stream": False,
            "options": {"temperature": 0.5, "num_predict": 180},
        }
        try:
            async with session.post(
                OLLAMA_URL,
                json=payload,
                timeout=aiohttp.ClientTimeout(total=TIMEOUT),
            ) as resp:
                if resp.status != 200:
                    return None
                data = await resp.json()
                raw  = data.get("response", "").strip()

            return self._parse_dream(raw, strategy, emotion)
        except Exception as e:
            print(f"[DREAMS] LLM error ({strategy}): {e}")
            return None

    def _parse_dream(self, raw: str, strategy: str, emotion: str) -> dict | None:
        text = raw.strip().replace("```json", "").replace("```", "").strip()
        start = text.find("{")
        end   = text.rfind("}") + 1
        if start == -1 or end == 0:
            return None
        try:
            d = json.loads(text[start:end])
            return {
                "strategy":   strategy,
                "hypothesis": d.get("hypothesis", "")[:300],
                "confidence": max(0.0, min(1.0, float(d.get("confidence", 0.5)))),
                "emotion":    emotion,
            }
        except (json.JSONDecodeError, ValueError):
            return None

    # ------------------------------------------------------------------
    # STATS
    # ------------------------------------------------------------------
    def stats(self) -> dict:
        return {
            "total_dreams":         self.total_dreams,
            "consolidation_replays": self.consolidation_replays,
            "last_dream":           self.last_dream[:100] if self.last_dream else "",
            "last_fired":           self.last_fired,
        }


# Module-level singleton
dreams = DreamsEngine()
