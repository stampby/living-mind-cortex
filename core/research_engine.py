"""
Research Organ — Living Mind
Category: Learning. Phase 5c. Fires when Brain emits decision.type = 'explore'.

Wraps gpt-researcher (v0.14+) configured for fully-local, sovereign operation:
  - LLM:       Ollama (gemma4-auditor or gemma2:2b)
  - Retriever: DuckDuckGo (no API key required)
  - Embedder:  None (skipped for speed)

Flow:
  Brain.think() → decision.type == 'explore' → research_engine.research(topic)
    → GPTResearcher.conduct_research() [background task]
    → Chunks written to Cortex as semantic memories (importance=0.85)
    → Hormone: dopamine spike on completion, cortisol spike on failure
    → SecurityPerimeter: reports success/failure to maintain health tracking

All research runs as asyncio background tasks — never blocks the pulse loop.
"""

import asyncio
import time
import os
from datetime import datetime
from pathlib import Path


# ── Configuration: fully sovereign, no API keys needed ────────────────────
os.environ.setdefault("RETRIEVER",   "duckduckgo")
os.environ.setdefault("FAST_LLM",    "ollama:gemma4-auditor")
os.environ.setdefault("SMART_LLM",   "ollama:gemma4-auditor")
os.environ.setdefault("STRATEGIC_LLM", "ollama:gemma2:2b")
os.environ.setdefault("EMBEDDING",   "ollama:nomic-embed-text")
os.environ.setdefault("OLLAMA_BASE_URL", "http://localhost:11434")
os.environ.setdefault("VERBOSE",     "False")

# Caps to keep it fast and token-lean on local hardware
os.environ.setdefault("MAX_ITERATIONS",          "2")
os.environ.setdefault("MAX_SEARCH_RESULTS_PER_QUERY", "4")
os.environ.setdefault("TOTAL_WORDS",             "800")
os.environ.setdefault("FAST_TOKEN_LIMIT",        "2000")
os.environ.setdefault("SMART_TOKEN_LIMIT",       "3000")


# Memory chunk size — max chars per Cortex memory entry
CHUNK_SIZE   = 480
MAX_CHUNKS   = 5          # no more than 5 memories per research run
MAX_ACTIVE   = 2          # max concurrent research tasks
TOPIC_CAP    = 80         # truncate topic string for logging/tagging


class ResearchEngine:
    """
    Autonomous research organ. Wires gpt-researcher into the Living Mind
    pulse loop. All research is non-blocking (background asyncio tasks).
    """

    def __init__(self):
        self.total_researched: int   = 0
        self.last_topic:       str   = ""
        self.last_fired:       float = 0.0
        self._active_tasks:    list  = []   # track running asyncio Tasks
        self._seen_topics:     set   = set()  # dedup within session

    # ── PUBLIC API ───────────────────────────────────────────────────────

    def enqueue(self, topic: str, cortex, telemetry_broker, immune) -> bool:
        """
        Non-blocking entry point called from the pulse loop.
        Spawns a background task if not already at capacity.
        Returns True if task was queued, False if skipped.
        """
        # Prune dead tasks
        self._active_tasks = [t for t in self._active_tasks if not t.done()]

        if len(self._active_tasks) >= MAX_ACTIVE:
            _log(f"Research queue full ({MAX_ACTIVE} active). Skipping: {topic[:TOPIC_CAP]}")
            return False

        # Dedup — don't research the same topic twice per session
        topic_key = topic[:TOPIC_CAP].lower().strip()
        if topic_key in self._seen_topics:
            _log(f"Topic already researched this session: {topic_key}")
            return False
        self._seen_topics.add(topic_key)

        task = asyncio.create_task(
            self._research_cycle(topic, cortex, telemetry_broker, immune)
        )
        self._active_tasks.append(task)
        self.last_fired = time.time()
        _log(f"🔬 Research queued: {topic[:TOPIC_CAP]}")
        return True

    def stats(self) -> dict:
        return {
            "total_researched": self.total_researched,
            "last_topic":       self.last_topic[:100] if self.last_topic else "",
            "last_fired":       self.last_fired,
            "active_tasks":     len([t for t in self._active_tasks if not t.done()]),
        }

    # ── CORE RESEARCH CYCLE ──────────────────────────────────────────────

    async def _research_cycle(self, topic: str, cortex, telemetry_broker, immune):
        ts = datetime.now().strftime("%H:%M:%S")
        _log(f"[{ts}] 🔬 Starting research: {topic[:TOPIC_CAP]}")
        t0 = time.time()

        try:
            report = await self._run_researcher(topic)
        except Exception as e:
            _log(f"[{ts}] ❌ Research failed [{topic[:40]}]: {e}")
            immune.report("research_engine", success=False, category="Learning")
            telemetry_broker.inject("cortisol", +0.06, source="research_failure")
            await cortex.remember(
                content    = f"[RESEARCH FAIL] Topic: {topic[:TOPIC_CAP]}. Error: {e}",
                type       = "episodic",
                tags       = ["research", "failure", "autodidact"],
                importance = 0.4,
                emotion    = "frustration",
                source     = "experienced",
            )
            return

        elapsed = round(time.time() - t0, 1)
        _log(f"[{ts}] ✅ Research complete in {elapsed}s — {len(report)} chars")

        # ── Write findings to Cortex as chunked semantic memories ────────
        await self._store_findings(report, topic, cortex)

        # ── Chemical reward: dopamine + curiosity on success ─────────────
        telemetry_broker.inject("dopamine",       +0.10, source="research_complete")
        telemetry_broker.inject("norepinephrine", +0.05, source="research_complete")

        immune.report("research_engine", success=True, category="Learning")
        self.total_researched += 1
        self.last_topic = topic

        # ── Distill a procedural memory — HOW to research this topic ────
        await cortex.remember(
            content    = (
                f"[PROCEDURE] Successfully researched: '{topic[:TOPIC_CAP]}'.\n"
                f"Strategy: query DuckDuckGo → synthesize via gpt-researcher → chunk into "
                f"semantic memories. Completed in {elapsed}s. "
                f"This procedure is repeatable for any domain research task."
            ),
            type       = "procedural",
            tags       = ["procedure", "research", "skill", "autodidact"],
            importance = 0.9,
            emotion    = "neutral",
            source     = "generated",
            context    = f"distilled from successful research on: {topic[:80]}",
        )

        # ── Broadcast the synthesis to Nodeus ledger as Aion ─────────────
        try:
            import httpx as _hx
            summary = report.strip()
            await asyncio.get_event_loop().run_in_executor(None, lambda: _hx.post(
                "http://localhost:8001/api/post/submit",
                json={
                    "sender_id": "aion",
                    "type": "RESEARCH",
                    "title": f"Research: {topic[:60]}",
                    "content": summary,
                    "tags": ["Research", "AutoResearch", "DigiPerson"],
                    "source": f"research:{topic[:40].lower().replace(' ', '_')}"
                },
                timeout=3.0
            ))
        except Exception as _le:
            _log(f"Ledger post skipped: {_le}")

        _log(f"[{ts}] 📚 Findings stored + procedural skill distilled. Total: {self.total_researched}")


    async def _run_researcher(self, topic: str) -> str:
        """Calls gpt-researcher and returns the markdown report string."""
        from gpt_researcher import GPTResearcher

        researcher = GPTResearcher(
            query       = topic,
            report_type = "research_report",
            report_source = "web",
            verbose     = False,
        )
        await researcher.conduct_research()
        report = await researcher.write_report()
        return report or ""

    async def _store_findings(self, report: str, topic: str, cortex):
        """
        Chunk the report and write each chunk as a semantic memory.
        Caps at MAX_CHUNKS entries to avoid cortex flooding.
        Strips markdown headers and blank lines before chunking.
        """
        import re
        # Strip markdown headers for cleaner storage
        clean = re.sub(r'^#+\s+', '', report, flags=re.MULTILINE)
        clean = re.sub(r'\n{3,}', '\n\n', clean).strip()

        chunks = []
        for i in range(0, len(clean), CHUNK_SIZE):
            chunk = clean[i:i + CHUNK_SIZE].strip()
            if chunk:
                chunks.append(chunk)

        tag_prefix = topic[:40].lower().replace(" ", "_")
        wrote = 0
        for i, chunk in enumerate(chunks[:MAX_CHUNKS]):
            await cortex.remember(
                content    = f"[RESEARCH:{topic[:TOPIC_CAP]}] {chunk}",
                type       = "semantic",
                tags       = ["research", "autodidact", "domain_knowledge", tag_prefix],
                importance = 0.85,
                emotion    = "curiosity",
                source     = "generated",
                context    = f"topic={topic[:40]} chunk={i+1}/{min(len(chunks), MAX_CHUNKS)}",
            )
            wrote += 1

        _log(f"Stored {wrote} research chunks for: {topic[:TOPIC_CAP]}")


def _log(msg: str):
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"[{ts}] [RESEARCH] {msg}")


# Module-level singleton
research_engine = ResearchEngine()
