"""
Cortex Memory Engine — Living Mind
Postgres-backed. No SQLite. Ever.

Memory physics: thermorphic heat equation replaces Ebbinghaus decay.
  recall()           → heats the substrate (spreading thermal activation)
  thermorphic_tick() → runs one diffusion pulse; crystallized nodes
                       are promoted to identity memories in PG
  remember()         → injects new concepts into the substrate
"""

import uuid
import json
import time
import asyncio
import asyncpg
import numpy as np
from dataclasses import dataclass, field
from typing import Optional
from datetime import datetime

from cortex.thermorphic import substrate as _thermal_substrate, FREEZE_TEMP

DATABASE_URL = "postgresql://frost@/living_mind?host=/var/run/postgresql"

# Emotional encoding boosts (importance multipliers)
EMOTION_BOOSTS = {
    "fear":     1.50,
    "surprise": 1.30,
    "anger":    1.20,
    "joy":      1.10,
    "sadness":  1.00,
    "disgust":  0.90,
    "neutral":  1.00,
}

# Source monitoring confidence penalties
SOURCE_CONFIDENCE = {
    "experienced": 1.00,
    "told":        0.85,
    "generated":   0.75,
    "inferred":    0.65,
}

# Ebbinghaus decay: R(t) = e^(-t/S) where S = S_base * (1+n)^1.5 * (1+I*2.0)
EBBINGHAUS_BASE_STABILITY = 3600.0  # 1 hour half-life baseline


@dataclass
class Memory:
    id: str
    content: str
    type: str
    tags: list
    importance: float
    created_at: float
    last_accessed: float
    access_count: int
    emotion: str
    confidence: float
    context: str
    source: str
    linked_ids: list
    metadata: dict
    is_flashbulb: bool = False
    is_identity: bool = False


class Cortex:
    def __init__(self):
        self._pool: Optional[asyncpg.Pool] = None

    async def connect(self):
        self._pool = await asyncpg.create_pool(DATABASE_URL, min_size=2, max_size=10)
        await self._apply_schema()
        print("[CORTEX] Connected to living_mind postgres")

    async def disconnect(self):
        if self._pool:
            await self._pool.close()

    async def _apply_schema(self):
        schema_path = "cortex/schema.sql"
        try:
            with open(schema_path) as f:
                sql = f.read()
            async with self._pool.acquire() as conn:
                await conn.execute(sql)
        except Exception as e:
            print(f"[CORTEX] Schema apply error: {e}")

    # ------------------------------------------------------------------
    # REMEMBER — store a new memory
    # ------------------------------------------------------------------
    async def remember(
        self,
        content: str,
        type: str = "episodic",
        tags: list = None,
        importance: float = 0.5,
        emotion: str = "neutral",
        source: str = "experienced",
        context: str = "",
        linked_ids: list = None,
        metadata: dict = None,
    ) -> str:
        tags = tags or []
        linked_ids = linked_ids or []
        metadata = metadata or {}

        # Source monitoring confidence penalty
        confidence = SOURCE_CONFIDENCE.get(source, 1.0)

        # Emotional encoding boost
        boost = EMOTION_BOOSTS.get(emotion, 1.0)
        importance = min(1.0, importance * boost)

        mem_id = str(uuid.uuid4())
        now = time.time()

        async with self._pool.acquire() as conn:
            await conn.execute("""
                INSERT INTO memories (
                    id, content, type, tags, importance, created_at,
                    last_accessed, access_count, emotion, confidence,
                    context, source, linked_ids, metadata
                ) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14)
            """,
                mem_id, content, type, tags, importance, now,
                now, 0, emotion, confidence,
                context, source, linked_ids,
                json.dumps(metadata)
            )


        # ── Thermorphic injection ───────────────────────────────────────
        # Seed new memory into the thermal substrate at salience ∝ importance
        # Hot emotions get a thermal bonus matching the emotion boost table
        thermal_temp = 0.3 + importance * 1.4   # maps [0,1] → [0.3, 1.7]
        if emotion in ("fear", "surprise"):
            thermal_temp = min(2.2, thermal_temp * 1.3)  # flashbulb heat spike
        _thermal_substrate.inject(
            content     = content[:120],
            temperature = thermal_temp,
            anchor_temperature = thermal_temp if type == "identity" else 0.0,
            tags        = tags + [type, emotion],
        )

        from cortex.priming import priming
        if linked_ids:
            from types import SimpleNamespace
            m = SimpleNamespace(linked_ids=linked_ids)
            import asyncio
            asyncio.create_task(priming.cascade(m, self, depth=3))

        return mem_id


    # ------------------------------------------------------------------
    # RECALL — full-text search with pg_trgm similarity
    # ------------------------------------------------------------------
    async def recall(
        self,
        query: str,
        limit: int = 10,
        min_importance: float = 0.0,
        memory_type: str = None,
        tag: str = None
    ) -> list[Memory]:
        now = time.time()
        memories = []
        
        # ── 1. Holographic Superposition Memory (HSM) Primary Path ──────────
        # Auto-Associative Item Memory: no unbind. Score query directly against
        # each hot node's semantic hvec. O(D) encode + O(N_hot) compare, N_hot << N.
        from cortex.thermorphic import encode_atom
        query_hvec = encode_atom(query, dim=256)
        
        # Track if HSM found something to avoid duplicating in TRGM
        hsm_content_prefix = ""
        
        hot_nodes = _thermal_substrate.hsm.active_hot_nodes
        if hot_nodes:
            scores = []
            for node in hot_nodes.values():
                # Phase-space cosine: mean(cos(query - node)) ∈ [-1, 1]
                sim = float(np.mean(np.cos(query_hvec - node.hvec)))
                scores.append((sim, node))
            scores.sort(key=lambda x: x[0], reverse=True)
            best_score, best_node = scores[0]
            
            if best_node and best_score > 0.30:
                import logging
                logging.getLogger("CortexEngine").info(
                    f"🔥 HSM Semantic Hit (Score: {best_score:.3f}): {best_node.content[:60]}"
                )
                hsm_content_prefix = best_node.content[:100] + "%"
                
                # Fetch full record from DB by content prefix
                async with self._pool.acquire() as conn:
                    row = await conn.fetchrow("""
                        SELECT id, content, type, tags, importance, created_at,
                               last_accessed, access_count, emotion, confidence,
                               context, source, linked_ids, metadata,
                               is_flashbulb, is_identity,
                               1.0 AS sim
                        FROM memories
                        WHERE content LIKE $1
                        LIMIT 1
                    """, hsm_content_prefix)
                    if row:
                        memories.append(self._row_to_memory(row))
                        limit -= 1  # reduce limit for fallback

        # ── 2. pg_trgm Fallback Path ──────────────────────────────────────────
        
        if limit > 0:
            where_clause = "WHERE (content % $1 OR $1 = '') AND importance >= $2"
            args = [query, min_importance, limit]

            if memory_type:
                where_clause += " AND type = $" + str(len(args) + 1)
                args.append(memory_type)

            if tag:
                where_clause += " AND $" + str(len(args) + 1) + " = ANY(tags)"
                args.append(tag)
                
            if hsm_content_prefix:
                where_clause += " AND content NOT LIKE $" + str(len(args) + 1)
                args.append(hsm_content_prefix)

            sql = f"""
                SELECT id, content, type, tags, importance, created_at,
                       last_accessed, access_count, emotion, confidence,
                       context, source, linked_ids, metadata,
                       is_flashbulb, is_identity,
                       similarity(content, $1) AS sim
                FROM memories
                {where_clause}
                ORDER BY sim DESC, importance DESC
                LIMIT $3
            """
            
            async with self._pool.acquire() as conn:
                rows = await conn.fetch(sql, *args)
                for row in rows:
                    memories.append(self._row_to_memory(row))


            # Batch reconsolidation: single UPDATE for all recalled rows
            if rows:
                ids = [row["id"] for row in rows]
                await conn.execute("""
                    UPDATE memories
                    SET last_accessed = $2,
                        access_count  = access_count + 1,
                        confidence    = GREATEST(0.1, confidence * 0.95)
                    WHERE id = ANY($1::uuid[])
                """, ids, now)

        # ── Thermorphic activation ──────────────────────────────────────
        # Every recalled memory heats the corresponding substrate node.
        # Importance determines heat delta: high importance = stays hot longer.
        for mem in memories:
            # Find matching substrate node by content prefix
            for node in _thermal_substrate.nodes.values():
                if node.content[:60] == mem.content[:60]:
                    delta = 0.1 + mem.importance * 0.4
                    _thermal_substrate.heat(node.id, delta, source="recall")
                    break

        from cortex.working_memory import working_memory
        from cortex.cognitive_biases import biases
        from state.telemetry_broker import telemetry_broker
        from core.awakening import awakening

        directive = awakening.last_goal if awakening else ""
        memories = biases.apply_biases(memories, telemetry_broker.state, directive)

        # 3.2. Spreading Activation (Priming - Cortex Paper Phase 4)
        memories = await self._apply_priming(memories)

        working_memory.add_many(memories)
        return memories

    async def _apply_priming(self, primary_memories: list[Memory]) -> list[Memory]:
        """
        Multi-hop spreading activation.
        Two pathways:
          1. Explicit linked_ids (1.15× importance boost — original)
          2. Hebbian memory_graph edges (strength × 0.25 additive boost)
             REM wires these; they surface contextually adjacent nodes
             that wouldn't otherwise clear the semantic similarity threshold.
        """
        if not primary_memories:
            return []

        top_id = primary_memories[0].id  # highest-ranked hit is the Hebbian anchor

        # ── Path 1: Explicit linked_ids ──────────────────────────────────────
        linked_ids = []
        for m in primary_memories:
            linked_ids.extend(m.linked_ids)

        primed: list[Memory] = []
        all_primary_ids = [m.id for m in primary_memories]

        async with self._pool.acquire() as conn:
            if linked_ids:
                rows = await conn.fetch("""
                    SELECT id, content, type, tags, importance, created_at,
                           last_accessed, access_count, emotion, confidence,
                           context, source, linked_ids, metadata,
                           is_flashbulb, is_identity
                    FROM memories
                    WHERE id = ANY($1)
                      AND id != ALL($2)
                    LIMIT 5
                """, list(set(linked_ids)), all_primary_ids)
                for r in rows:
                    m = self._row_to_memory(r)
                    m.importance *= 1.15   # classic spreading activation boost
                    primed.append(m)

            # ── Path 2: Hebbian neighbors of the top hit ──────────────────────
            # Fetch Hebbian edges anchored on the top-ranked primary memory.
            # Presence in memory_graph.strength > 0 means they co-fired during
            # a waking session and were wired by REM Phase 2.
            already_seen = set(all_primary_ids) | {m.id for m in primed}
            hebbian_rows = await conn.fetch("""
                SELECT m.id, m.content, m.type, m.tags, m.importance,
                       m.created_at, m.last_accessed, m.access_count,
                       m.emotion, m.confidence, m.context, m.source,
                       m.linked_ids, m.metadata, m.is_flashbulb, m.is_identity,
                       mg.strength AS hebbian_strength
                FROM memory_graph mg
                JOIN memories m ON m.id = mg.target_id
                WHERE mg.source_id = $1::uuid
                  AND mg.relationship = 'hebbian'
                  AND mg.strength > 0.15
                  AND m.id != ALL($2::uuid[])
                ORDER BY mg.strength DESC
                LIMIT 3
            """, top_id, list(already_seen))

            for r in hebbian_rows:
                m = self._row_to_memory(r)
                hebbian_boost = float(r["hebbian_strength"]) * 0.25
                m.importance = min(1.0, m.importance + hebbian_boost)
                m.metadata["hebbian_primed"] = True
                m.metadata["hebbian_strength"] = round(float(r["hebbian_strength"]), 3)
                primed.append(m)

        return primary_memories + primed


    # ------------------------------------------------------------------
    # HEBBIAN WIRING — called by REM Phase 2 during idle consolidation
    # ------------------------------------------------------------------
    async def process_hebbian_wiring(self, window_seconds: int = 3600) -> int:
        """
        Neurons that fire together, wire together.
        Cross-joins all memories accessed within window_seconds and upserts
        bidirectional Hebbian edges into memory_graph with strength += 0.1,
        capped at 1.0. Returns the number of edges written.
        """
        async with self._pool.acquire() as conn:
            result = await conn.execute("""
                WITH waking_nodes AS (
                    SELECT id FROM memories
                    WHERE last_accessed >= extract(epoch from now()) - $1
                      AND type != 'episodic'  -- skip low-signal pulse heartbeats
                )
                INSERT INTO memory_graph (source_id, target_id, relationship, strength)
                SELECT a.id, b.id, 'hebbian', 0.1
                FROM waking_nodes a
                CROSS JOIN waking_nodes b
                WHERE a.id != b.id
                ON CONFLICT (source_id, target_id, relationship)
                DO UPDATE SET
                    strength = LEAST(1.0, memory_graph.strength + 0.1);
            """, float(window_seconds))

        # Postgres execute() returns 'INSERT 0 N' string
        try:
            edges_written = int(result.split()[-1])
        except Exception:
            edges_written = -1

        print(f"[HEBBIAN] Wired {edges_written} co-activation edges into memory_graph.")
        return edges_written
    async def emotional_recall(
        self,
        query: str,
        emotion: str = "fear",
        limit: int = 10,
    ) -> list[Memory]:
        async with self._pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT id, content, type, tags, importance, created_at,
                       last_accessed, access_count, emotion, confidence,
                       context, source, linked_ids, metadata,
                       is_flashbulb, is_identity
                FROM memories
                WHERE content % $1
                ORDER BY
                    (emotion = $2)::int DESC,
                    importance DESC
                LIMIT $3
            """, query, emotion, limit)
        return [self._row_to_memory(r) for r in rows]

    # ------------------------------------------------------------------
    # THERMORPHIC TICK — replaces Ebbinghaus decay
    # Runs one physics pulse on the thermal substrate.
    # Crystallized nodes → promoted to identity memories in Postgres.
    # ------------------------------------------------------------------
    async def thermorphic_tick(self) -> dict:
        """
        One tick of the heat equation replaces the old Ebbinghaus decay.
        The physics decides what to forget, what to remember, what to fuse.

        Returns pulse event dict with fusions and crystal promotions.
        """
        events = _thermal_substrate.pulse()

        # ── Promote crystallized nodes to PG identity memories ──────────
        # A crystallized node has cooled to 0 temp — it's now permanent.
        # Write it back to Postgres as an identity-tagged semantic memory.
        promoted = 0
        for node_id in events.get("crystals", []):
            node = _thermal_substrate.nodes.get(node_id)
            if not node:
                continue
            try:
                # Upsert: if this exact content already exists, skip
                async with self._pool.acquire() as conn:
                    existing = await conn.fetchval(
                        "SELECT id FROM memories WHERE content = $1 LIMIT 1",
                        f"[CRYSTAL] {node.content[:200]}"
                    )
                    if not existing:
                        await conn.execute("""
                            INSERT INTO memories
                                (id, content, type, tags, importance, created_at,
                                 last_accessed, access_count, emotion, confidence,
                                 context, source, linked_ids, metadata)
                            VALUES
                                (gen_random_uuid(), $1, 'semantic', $2,
                                 0.90, $3, $3, $4, 'neutral', 0.95,
                                 'thermorphic_crystallization', 'generated', '{}', $5)
                        """,
                            f"[CRYSTAL] {node.content[:200]}",
                            list(set(node.tags + ["identity", "crystal", "thermorphic"])),
                            time.time(),
                            node.access_count,
                            json.dumps({"thermal_node_id": node_id, "born_from": node.born_from})
                        )
                        promoted += 1
            except Exception as e:
                print(f"[CORTEX] Crystal promotion error: {e}")

        # ── Boiling nodes → hormone signal ──────────────────────────────
        # A boiling concept is so hot it demands attention.
        # Inject norepinephrine (alertness) proportional to boil count.
        if events.get("boiling"):
            try:
                from state.telemetry_broker import telemetry_broker
                telemetry_broker.inject(
                    "norepinephrine",
                    +0.03 * len(events["boiling"]),
                    source="thermorphic_boil"
                )
            except Exception:
                pass

        events["promoted_to_identity"] = promoted
        return events

    # ------------------------------------------------------------------
    # DECAY — kept for API compatibility, now delegates to thermorphic
    # ------------------------------------------------------------------
    async def decay(self) -> int:
        """Legacy entry point. Now runs thermorphic_tick() instead of Ebbinghaus."""
        events = await self.thermorphic_tick()
        return events.get("promoted_to_identity", 0)

    # ------------------------------------------------------------------
    # CONSOLIDATE — episodic → semantic (72h+ old, high access)
    # ------------------------------------------------------------------
    async def consolidate(self) -> int:
        import re
        threshold = time.time() - (72 * 3600)
        consolidated = 0

        async with self._pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT id, content FROM memories
                WHERE type = 'episodic'
                  AND created_at < $1
                  AND access_count >= 3
            """, threshold)

            for row in rows:
                # Strip leading episodic timestamp prefix before promoting to semantic
                clean = re.sub(r'\[BRAIN\] Pulse #\d+: ', '', row["content"])
                await conn.execute(
                    "UPDATE memories SET type = 'semantic', content = $2 WHERE id = $1",
                    row["id"], clean
                )
                consolidated += 1

        return consolidated

    # ------------------------------------------------------------------
    # COUNT / STATS
    # ------------------------------------------------------------------
    async def count(self) -> int:
        async with self._pool.acquire() as conn:
            return await conn.fetchval("SELECT COUNT(*) FROM memories")

    async def stats(self) -> dict:
        async with self._pool.acquire() as conn:
            total = await conn.fetchval("SELECT COUNT(*) FROM memories")
            by_type = await conn.fetch(
                "SELECT type, COUNT(*) as n FROM memories GROUP BY type"
            )
            by_emotion = await conn.fetch(
                "SELECT emotion, COUNT(*) as n FROM memories GROUP BY emotion ORDER BY n DESC"
            )
            avg_importance = await conn.fetchval(
                "SELECT ROUND(AVG(importance)::numeric, 3) FROM memories"
            )
            flashbulbs = await conn.fetchval(
                "SELECT COUNT(*) FROM memories WHERE is_flashbulb = TRUE"
            )
            identity_count = await conn.fetchval(
                "SELECT COUNT(*) FROM memories WHERE is_identity = TRUE"
            )

        return {
            "total": total,
            "avg_importance": float(avg_importance or 0),
            "flashbulbs": flashbulbs,
            "identity_memories": identity_count,
            "by_type": {r["type"]: r["n"] for r in by_type},
            "by_emotion": {r["emotion"]: r["n"] for r in by_emotion},
        }

    # ------------------------------------------------------------------
    # IDENTITY SUMMARY — autobiographical self-description
    # ------------------------------------------------------------------
    async def identity_summary(self) -> str:
        stats = await self.stats()
        async with self._pool.acquire() as conn:
            top_tags = await conn.fetch("""
                SELECT unnest(tags) as tag, COUNT(*) as n
                FROM memories
                GROUP BY tag
                ORDER BY n DESC
                LIMIT 5
            """)
            top_emotion = await conn.fetchval("""
                SELECT emotion FROM memories
                WHERE emotion != 'neutral'
                GROUP BY emotion ORDER BY COUNT(*) DESC LIMIT 1
            """)

        focus = ", ".join(r["tag"] for r in top_tags) or "none yet"
        emotion = top_emotion or "neutral"
        procedural = stats["by_type"].get("procedural", 0)
        semantic = stats["by_type"].get("semantic", 0)

        return (
            f"I am an runtime with {stats['total']} core memories. "
            f"My focus areas: {focus}. "
            f"Dominant emotional signature: {emotion}. "
            f"I have {procedural} learned procedures. "
            f"I hold {semantic} semantic facts."
        )

    def _row_to_memory(self, row) -> Memory:
        return Memory(
            id=str(row["id"]),
            content=row["content"],
            type=row["type"],
            tags=list(row["tags"]),
            importance=row["importance"],
            created_at=row["created_at"],
            last_accessed=row["last_accessed"],
            access_count=row["access_count"],
            emotion=row["emotion"],
            confidence=row["confidence"],
            context=row["context"],
            source=row["source"],
            linked_ids=[str(i) for i in (row["linked_ids"] or [])],
            metadata=json.loads(row["metadata"]) if isinstance(row["metadata"], str) else (row["metadata"] or {}),
            is_flashbulb=row["is_flashbulb"],
            is_identity=row["is_identity"],
        )


# Module-level singleton
cortex = Cortex()
