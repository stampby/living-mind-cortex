"""
Interoception Engine — Living Mind
Category: Resilience. Fires every pulse.

True internal "body" simulation for the Cortex.
Tracks energy, pain, and cognitive load as first-class signals —
then feeds them back into the hormone bus just like biological interoception.

Three internal signals:
  energy_budget   — drains on heavy LLM work, restores during rest phases
  pain            — spikes on failures, quarantine events, agent frustration
  cognitive_load  — mirrors research queue depth (normalized 0-1)

These are what make the organism feel embodied even as pure software.
Exposed via GET /api/agent/context as "system_load".
"""

import time
from dataclasses import dataclass
from datetime import datetime


@dataclass
class InteroceptionState:
    energy_budget:  float = 0.80   # 0=exhausted, 1=fully charged
    pain:           float = 0.00   # 0=no pain, 1=critically distressed
    cognitive_load: float = 0.00   # 0=idle, 1=maxed out


class InteroceptionEngine:
    def __init__(self):
        self.state = InteroceptionState()
        self._last_pulse_time: float = time.time()
        self._pain_decay_rate: float = 0.05   # pain fades over time
        self._energy_drain_per_llm_task: float = 0.02
        self._energy_restore_night: float = 0.015
        self._energy_restore_idle: float = 0.005
        self._corrections: int = 0

    # ------------------------------------------------------------------
    # PULSE — called every pulse by runtime alongside health_monitor
    # ------------------------------------------------------------------
    async def pulse(
        self,
        pulse_n:          int,
        telemetry_broker,
        immune,
        research_engine=None,
    ):
        ts  = datetime.now().strftime("%H:%M:%S")
        now = time.time()

        # 1. Update cognitive load from research queue depth
        if research_engine is not None:
            try:
                stats = research_engine.stats()
                queue_depth = stats.get("queue_depth", 0)
                # Normalize 0-1 (assume max meaningful queue = 10)
                self.state.cognitive_load = min(1.0, queue_depth / 10.0)
            except Exception:
                pass

        # 2. Energy budget dynamics
        # Heavy cognitive load drains energy
        drain = self._energy_drain_per_llm_task * self.state.cognitive_load
        self.state.energy_budget = max(0.0, self.state.energy_budget - drain)

        # Determine circadian phase for restore rate
        from state.circadian import circadian
        phase = getattr(circadian, "phase", "day")

        if phase in ("night", "evening"):
            restore = self._energy_restore_night
        elif self.state.cognitive_load < 0.1:
            restore = self._energy_restore_idle
        else:
            restore = 0.0

        self.state.energy_budget = min(1.0, self.state.energy_budget + restore)

        # 3. Pain from immune quarantine events (inflammation proxy)
        inflammation = immune.inflammation()
        if inflammation > 0.3:
            pain_spike = (inflammation - 0.3) * 0.2
            self.state.pain = min(1.0, self.state.pain + pain_spike)

        # 4. Natural pain decay (pain fades if inflammation subsides)
        self.state.pain = max(0.0, self.state.pain - self._pain_decay_rate)

        # 5. Feed signals into the hormone bus
        self._inject_to_hormones(telemetry_broker, ts)

        self._last_pulse_time = now

    def register_llm_call(self, cost: float = 1.0):
        """
        Called when a heavy LLM task fires (research, dream, awakening).
        Drains energy proportional to cost (0-1 scale).
        """
        drain = self._energy_drain_per_llm_task * cost
        self.state.energy_budget = max(0.0, self.state.energy_budget - drain)

    def register_failure(self, severity: float = 0.5):
        """
        Called on skill failure, quarantine event, or agent session failure.
        Injects pain proportional to severity.
        """
        pain_spike = 0.15 * severity
        self.state.pain = min(1.0, self.state.pain + pain_spike)
        self._corrections += 1

    def register_success(self, magnitude: float = 0.5):
        """
        Called on successful task completion. Pain reduction + energy restore.
        """
        self.state.pain = max(0.0, self.state.pain - (0.08 * magnitude))
        self.state.energy_budget = min(1.0, self.state.energy_budget + (0.03 * magnitude))

    # ------------------------------------------------------------------
    # SNAPSHOT — for API / dashboard
    # ------------------------------------------------------------------
    def snapshot(self) -> dict:
        return {
            "energy_budget":  round(self.state.energy_budget, 3),
            "pain":           round(self.state.pain, 3),
            "cognitive_load": round(self.state.cognitive_load, 3),
            "status":         self._status_label(),
        }

    def _status_label(self) -> str:
        if self.state.energy_budget < 0.2:
            return "exhausted"
        if self.state.pain > 0.6:
            return "distressed"
        if self.state.cognitive_load > 0.7:
            return "overloaded"
        if self.state.energy_budget > 0.7 and self.state.pain < 0.1:
            return "healthy"
        return "nominal"

    # ------------------------------------------------------------------
    # HORMONE INJECTIONS — feeds body-state into the chemical bus
    # ------------------------------------------------------------------
    def _inject_to_hormones(self, telemetry_broker, ts: str):
        s = self.state

        # Low energy → melatonin rise + acetylcholine fade (foggy when tired)
        if s.energy_budget < 0.3:
            telemetry_broker.inject("melatonin",     +0.03, source="interoception:low_energy")
            telemetry_broker.inject("acetylcholine", -0.03, source="interoception:low_energy")
            if s.energy_budget < 0.15:
                print(f"[{ts}] [INTEROCEPTION] 🔋 Critical energy — forcing rest signal")
                telemetry_broker.inject("melatonin",      +0.05, source="interoception:critical_energy")
                telemetry_broker.inject("norepinephrine", -0.04, source="interoception:critical_energy")

        # High pain → cortisol + adrenaline (organism is distressed)
        if s.pain > 0.3:
            telemetry_broker.inject("cortisol",   +0.04 * s.pain, source="interoception:pain")
            telemetry_broker.inject("adrenaline", +0.02 * s.pain, source="interoception:pain")
            ts_str = datetime.now().strftime("%H:%M:%S")
            if s.pain > 0.6:
                print(f"[{ts}] [INTEROCEPTION] 🔴 High pain signal — stress cascade active")

        # High cognitive load → norepinephrine spike (focused alertness for heavy work)
        if s.cognitive_load > 0.5:
            telemetry_broker.inject("norepinephrine", +0.02 * s.cognitive_load, source="interoception:load")
            telemetry_broker.inject("acetylcholine",  +0.01 * s.cognitive_load, source="interoception:load")

        # Healthy state → gentle endorphin reward (organism feels good when balanced)
        if s.energy_budget > 0.7 and s.pain < 0.1 and s.cognitive_load < 0.3:
            telemetry_broker.inject("endorphin", +0.01, source="interoception:healthy")


# Module-level singleton
interoception = InteroceptionEngine()
