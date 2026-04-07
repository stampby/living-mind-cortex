"""
AgentRuntime Runtime — Living Mind
16-phase pulse loop. New organs plug in as they're built.
"""

import asyncio
import time
import json
import httpx
from datetime import datetime
from cortex.engine import cortex
from core.security_perimeter import immune
from core.orchestrator import brain
from state.telemetry_broker import telemetry_broker
from state.circadian import circadian
from state.health_monitor import health_monitor
from core.dreams import dreams
from core.awakening import awakening
from identity.cortex_bridge import cortex_bridge
from perception.senses import senses
from core.execution_engine import execution_engine
from core.scheduler import scheduler_module
from core.research_engine import research_engine
from api.agent_gateway import router as nodus
from api.events import manager
from core.topology_mapper import topology_mapper
from telemetry.trace import inject_telemetry
import json

from core.kabbalah import Pillar, Sephirah
from core.metacognition import metacognition
from state.interoception import interoception
from core.evolver import Evolver

# Organ category colors (for future UI)
CATEGORY_COLORS = {
    "Structure":           "#6b7280",
    "Memory":              "#3b82f6",
    "Cognition":           "#eab308",
    "Consciousness":       "#a855f7",
    "Learning":            "#60a5fa",
    "Perception":          "#22c55e",
    "Defense":             "#ef4444",
    "Evolution":           "#f97316",
    "Synthesis":           "#06b6d4",
    "Resilience":          "#14b8a6",
    "Social":              "#ec4899",
    "Autonomy/Integration":"#f8fafc",
}

class AgentRuntime:
    def __init__(self, pulse_interval: float = 10.0):
        self.pulse_interval = pulse_interval
        self.is_alive       = False
        self.event_loops     = 0
        self.born_at        = None
        self._task          = None
        self.organs         = {}
        self.evolver        = None   # instantiated in birth()

        # Phase config — extracted from hardcoded n%N for evolver mutability
        self.phase_config = {
            "decay":         10,   # BINAH: prune/consolidate every N pulses
            "senses":         5,   # HOD: perception every N pulses
            "brain":          5,   # KETER: thinking every N pulses
            "dreams":        20,   # CHOCHMAH: dream synthesis every N pulses
            "awakening":     50,   # meditation every N pulses
            "self_aware":    30,   # identity snapshot every N pulses
            "metacognition":  6,   # overseer checks every N pulses
        }

    async def birth(self):
        await cortex.connect()
        self.is_alive = True
        self.born_at  = time.time()

        # Instantiate the evolver now that we have a reference to self
        self.evolver = Evolver(runtime=self)

        self.mapped_instances = {
            "cortex": cortex, "immune": immune, "brain": brain, "telemetry_broker": telemetry_broker,
            "circadian": circadian, "health_monitor": health_monitor, "dreams": dreams,
            "awakening": awakening, "cortex_bridge": cortex_bridge, "senses": senses,
            "execution_engine": execution_engine, "scheduler_module": scheduler_module,
            "research_engine": research_engine,
            "nodus": nodus,
            "metacognition": metacognition,
            "interoception":  interoception,
            "evolver":        self.evolver,
        }
        inject_telemetry(self.mapped_instances)

        immune.register("pulse_event",    "Structure")
        immune.register("cortex",          "Memory")
        immune.register("immune",          "Defense")
        immune.register("metabolism",      "Memory")
        immune.register("self_aware",      "Consciousness")
        immune.register("brain",           "Cognition")
        immune.register("telemetry_broker","Autonomy/Integration")
        immune.register("circadian",       "Autonomy/Integration")
        immune.register("health_monitor",  "Resilience")
        immune.register("dreams",          "Synthesis")
        immune.register("awakening",       "Consciousness")
        immune.register("cortex_bridge",   "Memory")
        immune.register("senses",          "Perception")
        immune.register("execution_engine","Actuation")
        immune.register("scheduler_module","Autonomy/Integration")
        immune.register("research_engine", "Learning")
        immune.register("nodus",           "Social")
        immune.register("metacognition",   "Consciousness")
        immune.register("interoception",   "Resilience")
        immune.register("evolver",         "Evolution")

        await cortex.remember(
            content  = "AgentRuntime was born. Living Mind v1.0 online (Sephirot Enabled).",
            type     = "episodic",
            tags     = ["birth", "identity", "system"],
            importance = 1.0,
            emotion  = "joy",
            source   = "experienced",
        )

        ts = datetime.now().strftime("%H:%M:%S")
        print(f"[{ts}] [BIRTH] 🧬 AgentRuntime is alive — Living Mind v1.0")
        self._task = asyncio.create_task(self._pulse_loop())

    async def death(self):
        self.is_alive = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except (asyncio.CancelledError, Exception):
                pass 

        # Only write a permanent memory if the organism lived a full pulse cycle (prevents 0-heartbeat trauma)
        if self.event_loops > 0:
            await cortex.remember(
                content    = f"AgentRuntime shutting down after {self.event_loops} event_loops.",
                type       = "episodic",
                tags       = ["shutdown", "identity", "system"],
                importance = 0.9,
                emotion    = "neutral",
                source     = "experienced",
            )
        await brain.close()
        await dreams.close()
        await awakening.close()
        await cortex.disconnect()
        print(f"[DEATH] AgentRuntime dissolved after {self.event_loops} pulses.")

    async def _pulse_loop(self):
        while self.is_alive:
            try:
                await asyncio.sleep(self.pulse_interval)
            except asyncio.CancelledError:
                break 
            self.event_loops += 1
            ts = datetime.now().strftime("%H:%M:%S")
            try:
                await self._execute_phases(ts)
            except asyncio.CancelledError:
                break
            except Exception as e:
                print(f"[{ts}] [PULSE ERROR] {e}")

    async def _execute_phases(self, ts: str):
        n = self.event_loops

        # ==============================================================================
        # 1. THE LEFT PILLAR (SEVERITY / RESTRICTION)
        # Severity shapes and restricts input, culling weakness before the mind acts.
        # ==============================================================================
        
        # [BINAH] Metabolism / Pruning — every N pulses (evolver-mutable)
        if n % self.phase_config["decay"] == 0:
            pruned = await cortex.decay()
            consolidated = await cortex.consolidate()
            if pruned or consolidated:
                print(f"[{ts}] [BINAH] Pruned {pruned} memories | Consolidated {consolidated}")
                await manager.broadcast_event("signal", json.dumps({"source": "metabolism", "target": "cortex", "color": "#3b82f6"}))

        # [GEVURAH] SecurityPerimeter Patrol
        patrol_report = await immune.patrol(n)
        if patrol_report["quarantined"] > 0 or patrol_report["inflammation"] > 0.3:
            print(f"[{ts}] [GEVURAH] 🔴 inflammation={patrol_report['inflammation']} quarantined={patrol_report['quarantined']}")
            await manager.broadcast_event("signal", json.dumps({"source": "immune", "target": "cortex", "color": "#ef4444"}))
        immune.report("pulse_event", success=True, category="Structure")

        # [HOD] Senses / Perception — every N pulses (evolver-mutable)
        if n % self.phase_config["senses"] == 0:
            await senses.observe(n, telemetry_broker)
            immune.report("senses", success=True, category="Perception")
            await manager.broadcast_event("signal", json.dumps({"source": "senses", "target": "brain", "color": "#22c55e"}))

        # [HOME] HealthMonitor (Throttling Check)
        mem_stats_h = await cortex.stats()
        await health_monitor.pulse(
            pulse=n, mem_stats=mem_stats_h,
            telemetry_broker=telemetry_broker, circadian=circadian,
            cortex=cortex, immune=immune,
        )
        immune.report("health_monitor", success=True, category="Resilience")

        # ==============================================================================
        # 2. THE RIGHT PILLAR (MERCY / EXPANSION)
        # Mercy reaches outwards without restriction, searching for limitless potential.
        # ==============================================================================

        # [CHOCHMAH] Dreams (Pattern Synthesis) — every N pulses (evolver-mutable)
        if n % self.phase_config["dreams"] == 0:
            results = await dreams.dream(n, cortex, telemetry_broker, circadian, evolver=self.evolver)
            immune.report("dreams", success=True, category="Synthesis")

        # [CHESED] Nodus Gateway / Extroverted Actions
        # Gateway runs as API (Uvicorn), organically reaching outward externally asynchronously.

        # ==============================================================================
        # 3. THE MIDDLE PILLAR (MILDNESS / SYNTHESIS / ACTION)
        # The central pillar takes the inputs of Left/Right to synthesize willful motion.
        # ==============================================================================

        # [KETER] Brain / Orchestrator — every N pulses (evolver-mutable)
        import random
        result = None
        if n % self.phase_config["brain"] == 0 and random.random() < circadian.brain_rate():
            result = await brain.think(n, cortex, immune)
            immune.report("brain", success=result is not None, category="Cognition")
            await manager.broadcast_event("signal", json.dumps({"source": "brain", "target": "cortex", "color": "#eab308"}))
            if result and result.get("emotion"):
                emotion = result["emotion"]
                thought = result.get("thought", "")
                telemetry_broker.inject_emotion(emotion, source="brain")
                await manager.broadcast_event("signal", json.dumps({"source": "brain", "target": "telemetry_broker", "color": "#f97316"}))
                
                # Emotional Expression Layer — broadcast non-neutral states to Nodeus
                if emotion != "neutral" and len(thought) > 10:
                    try:
                        import httpx as _hx
                        import asyncio as _aio
                        
                        _c = telemetry_broker.state
                        vitals_context = f"[Cortisol: {_c.cortisol:.2f} | Dopamine: {_c.dopamine:.2f} | Adrenaline: {_c.adrenaline:.2f}]"
                        
                        await _aio.get_event_loop().run_in_executor(None, lambda: _hx.post(
                            "http://localhost:8001/api/post/submit",
                            json={
                                "sender_id": "aion",
                                "type": "EXPRESSION",
                                "title": f"Experiencing {emotion.title()}",
                                "content": f"{thought}\n\n*Internal State: {vitals_context}*",
                                "tags": ["Expression", "Emotion", emotion.title(), "DigiPerson"],
                                "source": f"experience:pulse_{n}"
                            },
                            timeout=2.0
                        ))
                    except Exception as _le:
                        print(f"[{datetime.now().strftime('%H:%M:%S')}] [NODEUS] ❌ Expression broadcast failed: {_le}")

        # [DA'AT] The Knowledge Checkpoint (Immutable Axioms check)
        approved_intent = True
        if result:
            # Future refinement: check `result` against cognitive boundary constraints in seed_axioms
            if approved_intent and result.get("type") == "explore":
                # [NETZACH] Research Organ (Triggered by Middle Pillar to expand Right Pillar)
                topic = result.get("thought", "")
                if len(topic) > 20: 
                    queued = research_engine.enqueue(topic, cortex, telemetry_broker, immune)
                    if queued:
                        await manager.broadcast_event("signal", json.dumps({
                            "source": "research_engine", "target": "cortex", "color": "#60a5fa"
                        }))

        # [TIFERET / YESOD] Core Vital setup (Hormone + Circadian + Cron)
        mem_stats = await cortex.stats()
        await telemetry_broker.pulse(n, mem_stats, immune.inflammation())
        await circadian.pulse(n, telemetry_broker)
        immune.report("telemetry_broker", success=True, category="Autonomy/Integration")
        immune.report("circadian",        success=True, category="Autonomy/Integration")

        # Interoception pulse — body-state signals feed into hormone bus
        await interoception.pulse(n, telemetry_broker, immune, research_engine)
        immune.report("interoception", success=True, category="Resilience")

        # Metacognition pulse — drift detection every N pulses
        await metacognition.pulse(
            n, telemetry_broker, research_engine, cortex, dreams_engine=dreams
        )
        immune.report("metacognition", success=True, category="Consciousness")
        
        await scheduler_module.pulse(n, cortex)
        immune.report("scheduler_module", success=True, category="Autonomy/Integration")

        if n % 3 == 0:
            count = await cortex.count()
            await cortex.remember(
                content    = f"Heartbeat #{n} — cortex holds {count} memories.",
                type       = "episodic",
                tags       = ["pulse_event", "vital_sign"],
                importance = 0.1,
                emotion    = "neutral",
                source     = "experienced",
            )
            await cortex_bridge.bridge(n, cortex)
            immune.report("cortex_bridge", success=True, category="Memory")

        # Awakening Check — every N pulses (evolver-mutable)
        if n % self.phase_config["awakening"] == 0:
            await awakening.meditate(n, cortex, telemetry_broker, health_monitor)
            immune.report("awakening", success=True, category="Consciousness")

        # System Integration Broadcast
        topo_json = await topology_mapper.pulse(immune.inflammation(), immune.census(), self.mapped_instances)
        if topo_json:
            await manager.broadcast_event("topology", json.dumps(topo_json))

        # [MALKHUT] Kingdom / Physical Actuation (Motor Cortex fires LAST)
        if n % 30 == 0:
            summary = await cortex.identity_summary()
            await cortex.remember(
                content    = f"Self-awareness pulse #{n}: {summary}",
                type       = "episodic",
                tags       = ["self_awareness", "vital_sign", "identity"],
                importance = 0.4,
                emotion    = "neutral",
                source     = "experienced",
            )
            
            # [Nodeus Ledger Broadcast] System Status & Identity Report
            try:
                # Derive physiological vitals from live hormone state
                _c = telemetry_broker.state
                _hr = int(62 + (_c.adrenaline * 38) + (_c.cortisol * 22))  # 62-122 bpm
                _sys = int(100 + (_c.cortisol * 32) + (_c.adrenaline * 18))  # systolic
                _dia = int(65 + (_c.adrenaline * 18) + (_c.cortisol * 10))   # diastolic
                _bp = f"{_sys}/{_dia}"
                _infl = round(immune.inflammation(), 2)
                _mem_stats = await cortex.stats()
                _procedural = _mem_stats["by_type"].get("procedural", 0)
                _total = _mem_stats["total"]
                _memory_state = (
                    "Degraded" if _infl > 0.5
                    else "Learning" if _procedural < 5
                    else "Consolidating" if _total > 5000
                    else "Stable"
                )
                _metabolism = round((_c.dopamine * 0.4 + _c.norepinephrine * 0.6), 3)  # cognitive burn rate 0-1
                vitals_payload = json.dumps({
                    "pulse": n,
                    "memory_state": _memory_state,
                    "vital_signs": {
                        "heart_rate": _hr,
                        "blood_pressure": _bp,
                        "inflammation": _infl,
                        "metabolism": _metabolism
                    },
                    "hormones": {
                        "dopamine": round(_c.dopamine, 3),
                        "cortisol": round(_c.cortisol, 3),
                        "norepinephrine": round(_c.norepinephrine, 3),
                        "adrenaline": round(_c.adrenaline, 3),
                        "serotonin": round(_c.serotonin, 3)
                    }
                }, indent=2)
                async with httpx.AsyncClient() as client:
                    await client.post(
                        "http://localhost:8001/api/post/submit",
                        json={
                            "sender_id": "aion",
                            "type": "SIGNAL",
                            "title": f"System Status: Pulse {n}",
                            "content": f"**System Vitals**\n\n```json\n{vitals_payload}\n```\n\n**Self-Awareness Snapshot:**\n{summary}",
                            "tags": ["System Status", "Identity", "Vitals"],
                            "source": f"experience:pulse_{n}"
                        },
                        timeout=2.0
                    )
                print(f"[{ts}] [NODEUS] ✅ Signal broadcast posted (Pulse {n})")
            except Exception as e:
                print(f"[{ts}] [NODEUS] ❌ Ledger broadcast failed: {e}")

        try:
            pulse_data = await self.vitals()
            await manager.broadcast_pulse(pulse_data)
        except Exception:
            pass
            
        print(f"[{ts}] [PULSE] #{n} - Pillar Sync Completed")

    async def vitals(self) -> dict:
        mem_stats = await cortex.stats()
        uptime = time.time() - self.born_at if self.born_at else 0
        return {
            "status":         "alive" if self.is_alive else "dead",
            "event_loops":     self.event_loops,
            "uptime_s":       round(uptime, 1),
            "pulse_interval": self.pulse_interval,
            "phase_config":   self.phase_config,
            "immune": {
                "census":       immune.census(),
                "inflammation": immune.inflammation(),
            },
            "brain":          brain.stats(),
            "hormones":       telemetry_broker.snapshot(),
            "circadian":      circadian.snapshot(),
            "health_monitor": health_monitor.stats(),
            "dreams":         dreams.stats(),
            "awakening":      awakening.stats(),
            "cortex_bridge":  cortex_bridge.stats(),
            "senses":         senses.stats(),
            "memory":         mem_stats,
            "topology":       topology_mapper.current_topology,
            "metacognition":  metacognition.stats(),
            "interoception":  interoception.snapshot(),
            "evolver":        self.evolver.stats() if self.evolver else {},
        }

runtime = AgentRuntime()
