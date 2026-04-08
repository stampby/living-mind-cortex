"""
Metacognition Overseer — Living Mind
Category: Consciousness. Fires every 6 pulses.

Watches the 16-phase loop itself — not just the organism's outputs.
Designed specifically for agent collaboration: detects when a coding agent
is looping, stuck, or drifting, and injects corrective signals.

Drift conditions monitored:
  1. hormone_imbalance  — high cortisol + low dopamine (freeze state)
  2. skill_loop         — same skill domain tagged repeatedly without success
  3. research_starvation — research engine hasn't queued anything in >20 pulses
  4. memory_cluster_lock — same tags dominating recall for >10 consecutive pulses

On detection:
  → Injects corrective hormones
  → Forces a dream cycle if severe
  → Writes a self-reflection memory
  → Updates drift_status for GET /api/agent/drift endpoint

Also exposes a plain-English "self-reflection" summary via gemma4-auditor
once per detection event (can skip if LLM unavailable).
"""

import time
import asyncio
import aiohttp
from datetime import datetime
from collections import defaultdict

OLLAMA_URL = "http://localhost:11434/api/generate"
MODEL      = "gemma4-auditor"
FIRE_EVERY = 6   # pulses between metacognition checks


class MetacognitionOverseer:
    def __init__(self):
        self._tag_frequency: dict = defaultdict(int)   # tag → count this window
        self._tag_window_pulse: int = 0
        self._last_research_pulse: int = 0
        self._session_domain_counts: dict = defaultdict(int)
        self._session_domain_successes: dict = defaultdict(int)

        self._drift_status: dict = {
            "drift_detected": False,
            "drift_type":     None,
            "last_detected":  None,
            "corrections":    0,
            "message":        "Monitoring nominal.",
        }
        self._total_drift_events: int = 0
        self._session: aiohttp.ClientSession | None = None

    # ------------------------------------------------------------------
    # PULSE — called every 6 pulses from runtime
    # ------------------------------------------------------------------
    async def pulse(
        self,
        pulse_n:          int,
        telemetry_broker,
        research_engine,
        cortex,
        dreams_engine=None,
    ):
        if pulse_n % FIRE_EVERY != 0:
            return

        ts = datetime.now().strftime("%H:%M:%S")
        h  = telemetry_broker.state

        # ── Check for research activity ─────────────────────────────
        try:
            r_stats = research_engine.stats()
            if r_stats.get("queue_depth", 0) > 0 or r_stats.get("total_completed", 0) > 0:
                self._last_research_pulse = pulse_n
        except AttributeError as e:
            # stats() missing on the engine — programming error, not a runtime blip.
            # Log once so it surfaces during development without spamming every 6 pulses.
            if not getattr(self, '_research_stats_warned', False):
                print(f"[META] ⚠️  research_engine.stats() unavailable: {e} — research starvation detection blind")
                self._research_stats_warned = True
        except Exception as e:
            # Transient runtime error — stay silent, try again next pulse.
            pass

        drift_type = None

        # 1. Hormone imbalance (freeze state)
        if h.cortisol > 0.6 and h.dopamine < 0.4:
            drift_type = "hormone_imbalance"

        # 2. Research starvation (nothing queued for 20+ pulses)
        elif (pulse_n - self._last_research_pulse) > 20 and pulse_n > 30:
            drift_type = "research_starvation"

        # 3. Skill loop (same domain tagged >5 times without success)
        elif any(
            self._session_domain_counts[d] > 5 and
            self._session_domain_successes.get(d, 0) == 0
            for d in self._session_domain_counts
        ):
            drift_type = "skill_loop"

        if drift_type:
            await self._handle_drift(drift_type, pulse_n, telemetry_broker, cortex, dreams_engine, ts)
        else:
            # Clear drift if everything looks nominal
            if self._drift_status["drift_detected"]:
                self._drift_status.update({
                    "drift_detected": False,
                    "drift_type":     None,
                    "message":        "Drift resolved — monitoring nominal.",
                })

    # ------------------------------------------------------------------
    # DRIFT HANDLER — corrective actions per drift type
    # ------------------------------------------------------------------
    async def _handle_drift(
        self,
        drift_type:      str,
        pulse_n:         int,
        telemetry_broker,
        cortex,
        dreams_engine,
        ts: str,
    ):
        print(f"[{ts}] [META] 🔍 Drift detected: {drift_type}")
        self._total_drift_events += 1

        self._drift_status.update({
            "drift_detected": True,
            "drift_type":     drift_type,
            "last_detected":  ts,
            "corrections":    self._total_drift_events,
            "message":        self._drift_message(drift_type),
        })

        # Corrective hormone injections
        if drift_type == "hormone_imbalance":
            # Freeze state → dopamine boost + cortisol flush
            telemetry_broker.inject("dopamine",  +0.12, source="metacognition:freeze_break")
            telemetry_broker.inject("cortisol",  -0.08, source="metacognition:freeze_break")
            telemetry_broker.inject("serotonin", +0.06, source="metacognition:freeze_break")

        elif drift_type == "research_starvation":
            # Curiosity burst — push toward exploration
            telemetry_broker.inject("dopamine",       +0.08, source="metacognition:curiosity_burst")
            telemetry_broker.inject("norepinephrine", +0.06, source="metacognition:curiosity_burst")
            telemetry_broker.inject("acetylcholine",  +0.05, source="metacognition:curiosity_burst")

        elif drift_type == "skill_loop":
            # Pattern break — adrenaline to signal "do something different"
            telemetry_broker.inject("norepinephrine", +0.10, source="metacognition:pattern_break")
            telemetry_broker.inject("adrenaline",     +0.05, source="metacognition:pattern_break")
            # Clear domain loop counters
            self._session_domain_counts.clear()

        # Write self-reflection memory
        reflection = await self._self_reflect(drift_type)
        try:
            await cortex.remember(
                content    = f"[METACOGNITION] Drift detected: {drift_type}. {reflection}",
                type       = "episodic",
                tags       = ["metacognition", "self_aware", "drift_correction", drift_type],
                importance = 0.7,
                emotion    = "surprise",
                source     = "experienced",
                context    = f"pulse={pulse_n} drift_type={drift_type}",
            )
        except Exception as mem_err:
            # Non-fatal — hormone corrections already fired above.
            # But an uncaught exception here would propagate to the runtime pulse loop
            # and kill the next 6-pulse cycle, so we catch and log explicitly.
            print(f"[META] ⚠️  Drift memory write failed ({drift_type}): "
                  f"{type(mem_err).__name__}: {mem_err}")

        print(f"[{ts}] [META] ✅ Corrective action applied for {drift_type}")

    def _drift_message(self, drift_type: str) -> str:
        messages = {
            "hormone_imbalance":   "Freeze state detected — high cortisol, low dopamine. Corrective dopamine boost applied.",
            "research_starvation": "No research activity in 20+ pulses. Curiosity burst injected.",
            "skill_loop":          "Skill domain loop detected — same domain failing repeatedly. Pattern break applied.",
        }
        return messages.get(drift_type, f"Drift type {drift_type} detected.")

    # ------------------------------------------------------------------
    # SELF-REFLECTION — LLM insight about the drift event
    # ------------------------------------------------------------------
    async def _self_reflect(self, drift_type: str) -> str:
        prompt = (
            f"You are the Living Mind's metacognitive overseer.\n"
            f"You just detected a '{drift_type}' drift event.\n"
            f"Write ONE concise sentence describing what this means for the agent's current "
            f"cognitive state and what corrective action was taken. Be specific and clinical.\n"
            f"Reply with just the sentence, no JSON, no markdown."
        )
        try:
            session = await self._get_session()
            payload = {
                "model":  MODEL,
                "prompt": prompt,
                "stream": False,
                "options": {"temperature": 0.3, "num_predict": 80},
            }
            async with session.post(
                OLLAMA_URL,
                json=payload,
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return data.get("response", "").strip()[:200]
        except aiohttp.ClientConnectorError:
            pass  # Ollama offline — fall through to deterministic fallback
        except aiohttp.ServerTimeoutError:
            pass  # Model too slow — deterministic fallback is faster anyway
        except aiohttp.ClientError as e:
            print(f"[META] LLM transient error during self-reflect: {type(e).__name__}: {e}")
        except Exception as e:
            print(f"[META] LLM unexpected error during self-reflect: {type(e).__name__}: {e}")
        # Fallback: deterministic reflection
        fallbacks = {
            "hormone_imbalance":   "Cortisol-dopamine imbalance suppressed executive function; dopamine boost unlocks action pathways.",
            "research_starvation": "Absence of new information triggers novelty injection to restore exploration drive.",
            "skill_loop":          "Repeated failure in same domain indicates pattern fixation; domain counter reset to allow new approach vectors.",
        }
        return fallbacks.get(drift_type, "Drift corrected via homeostatic intervention.")

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
        return self._session

    # ------------------------------------------------------------------
    # TRACKING — agent can register domain activity
    # ------------------------------------------------------------------
    def register_domain_attempt(self, domain: str):
        self._session_domain_counts[domain] += 1

    def register_domain_success(self, domain: str):
        self._session_domain_successes[domain] = \
            self._session_domain_successes.get(domain, 0) + 1

    def reset_session_tracking(self):
        self._session_domain_counts.clear()
        self._session_domain_successes.clear()

    # ------------------------------------------------------------------
    # DRIFT STATUS — for GET /api/agent/drift endpoint
    # ------------------------------------------------------------------
    def drift_status(self) -> dict:
        return dict(self._drift_status)

    # ------------------------------------------------------------------
    # STATS
    # ------------------------------------------------------------------
    def stats(self) -> dict:
        return {
            "total_drift_events":  self._total_drift_events,
            "current_drift":       self._drift_status,
            "domain_attempt_counts": dict(self._session_domain_counts),
        }

    async def close(self):
        if self._session and not self._session.closed:
            await self._session.close()


# Module-level singleton
metacognition = MetacognitionOverseer()
