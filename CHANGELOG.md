# Changelog

All notable changes to Living Mind Cortex are documented here.  
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

---

## [2.0.0] — 2026-04-07

### 🎯 Focus: Enterprise Agent Cognitive Substrate

This release transforms Living Mind Cortex from a standalone autonomous organism into a **full cognitive substrate for enterprise AI coding agents**. The system now operates in two simultaneous modes: active real-time cognitive integration during agent sessions, and passive overnight evolution based on session outcomes.

### Added

#### Agent Cognitive Loop Protocol (`api/agent_gateway.py`)
Full bidirectional integration layer for coding agents. 8 new endpoints:
- `GET /api/agent/context` — cognitive stance, urgency, creative pressure, phase gate, relevant memories
- `GET /api/agent/hormone/interpret` — plain-English hormone state for system prompt injection
- `GET /api/agent/drift` — metacognition drift detection status
- `POST /api/agent/session/start` — auto session management (closes previous session)
- `POST /api/agent/session/end` — close session, trigger hippocampal replay queue
- `POST /api/agent/recall` — semantic memory search scoped to agent task context
- `POST /api/agent/learn` — write structured procedural/semantic/episodic learnings
- `POST /api/agent/feedback` — rate session output as Evolver fitness signal

#### Evolutionary Meta-Layer (`core/evolver.py`) — *new file*
Three-vector self-evolution running nightly inside the Dream state:
- **Vector A (Phase Mutation)** — mutates pulse frequencies in `runtime.phase_config`
- **Vector B (Hormone Genome)** — evolves baselines and decay curves based on session ratings
- **Vector C (Quantum Selection)** — 40% probability of selecting more novel variant when fitness delta < 0.05
- Agent-centric fitness oracle: `0.4×session_rating + 0.3×success_rate + 0.2×coherence + 0.1×energy`
- Every accepted mutation checkpointed to `lineage_snapshots` DB table

#### Metacognition Overseer (`core/metacognition.py`) — *new file*
Agent-specific drift detection firing every 6 pulses:
- `hormone_imbalance` — freeze state (cortisol > 0.6, dopamine < 0.4) → dopamine correction
- `skill_loop` — same domain tag failing repeatedly → hormone pattern break
- `research_starvation` — research engine idle > 20 pulses → curiosity burst
- LLM self-reflection memory written on every detection event
- Exposes `drift_status()` for `GET /api/agent/drift`

#### Interoception Engine (`state/interoception.py`) — *new file*
True internal body simulation with three signals fed into the hormone bus every pulse:
- `energy_budget` — drains on LLM work, restores during night/idle phases
- `pain` — spikes on failures, quarantine events, agent session failures
- `cognitive_load` — normalized research queue depth
- Low energy → melatonin rise + acetylcholine fade (the organism gets "foggy when tired")
- High pain → cortisol + adrenaline cascade

#### Neurotransmitter Orchestra v2.0 (`state/telemetry_broker.py`)
Two new hormones added to `HormoneState`:
- **Acetylcholine** (`baseline=0.55`) — attention/focus, decays when tired or in freeze state
- **Endorphin** (`baseline=0.30`) — flow state signal, spikes after successful deep work

Five cross-talk interaction rules between hormones:
- Freeze mode: cortisol > 0.6 AND dopamine < 0.4 → suppress acetylcholine
- Flow boost: endorphin > 0.55 AND dopamine > 0.70 → boost acetylcholine
- Cortisol cascade: cortisol > 0.7 → adrenaline spike
- Vigilance attention: norepinephrine > 0.65 → sharpen acetylcholine
- Sleep fog: melatonin > 0.5 → suppress acetylcholine

New `cognitive_stance()` method returns one of: `focused-analytical | flow | frozen | vigilant | winding-down | balanced`

Updated arousal calculation now weights acetylcholine (20%) and de-weights melatonin.
Updated valence calculation includes endorphin.

#### Hippocampal Session Replay (`core/dreams.py`)
New `agent_session_replay` dream strategy (highest priority during `night`/`evening` phases):
- Fetches agent session memories from last 24h
- Prunes weak traces (importance < 0.25, access_count < 2)
- Distills strong traces into durable `procedural` memories via LLM
- Increments `consolidation_replays` counter in stats

#### Session Lifecycle Automation (`~/.gemini/memory/living_mind_client.py`)
Complete rewrite of the agent client with automated session management:
- `session_start()` — opens session, auto-closes previous one
- `session_end()` — closes session with outcome
- `close_stale_sessions()` — auto-closes sessions idle > 2 hours (runs at spawn)
- `learn()`, `recall()`, `get_context()`, `get_drift()`, `hormone_interpret()` — mid-task API
- Active session persisted to `~/.gemini/memory/active_session.json`
- Deterministic session_id derivation: `md5(hour + task_context)[:16]`

#### Database Schema (`cortex/schema.sql`)
Three additions (all idempotent — safe to run on existing databases):
- `agent_sessions` table — full research dataset (id, outcome, rating, hormone_snapshot, etc.)
- `lineage_snapshots` table — Evolver genome archive (phase_config, hormone_genome, fitness)
- `memories.counterfactual_of UUID` column — provenance graph fork tracking
- `memories.agent_session_id TEXT` column — links memories to the session that created them

#### Runtime Wiring (`core/runtime.py`)
- Phase frequencies extracted from hardcoded `n % N` into `self.phase_config` dict (Evolver-mutable)
- `Evolver` instantiated in `birth()`, registered as `"Evolution"` organ
- `interoception` registered as `"Resilience"` organ
- `metacognition` registered as `"Consciousness"` organ
- `dreams.dream()` now receives `evolver=self.evolver` to trigger nightly cycle
- `vitals()` now returns `phase_config`, `metacognition`, `interoception`, and `evolver` stats

#### Cortex Gateway Skill (`~/.gemini/.agents/skills/cortex-gateway/SKILL.md`)
Skill definition for AI agents specifying exactly when and how to use the Cortex client:
- When to call `get_context()`, `recall()`, `learn()`, `feedback()`
- Phase gate interpretation guide
- Rating scale (0.0–1.0) with honest calibration notes

### Changed
- `dreams.dream()` signature now accepts optional `evolver=None` parameter
- Night/evening strategy picker now prioritizes `agent_session_replay` over `mutation_replay`
- `dreams.stats()` now returns `consolidation_replays` count
- `identity/journal.json` reset to clean baseline (populated on first boot)
- `cortex/engine.py` DATABASE_URL uses generic username placeholder
- `dashboard/Crucible` references genericized

### Fixed
- Personal filesystem paths removed from all source files
- Pre-existing `test_circadian.py` import from wrong module path noted (not a regression)

---

## [1.0.0] — 2026-04-05

### Initial Release

- 16-phase deterministic pulse loop (Kabbalistic Sephirot ordering)
- PostgreSQL-backed Cortex memory engine with pg_trgm full-text search
- Ebbinghaus forgetting curves with flashbulb immunity
- 7-hormone telemetry bus (Dopamine, Serotonin, Cortisol, Adrenaline, Norepinephrine, Melatonin, Oxytocin)
- Circadian 4-phase clock (dawn/day/evening/night) with adenosine sleep pressure
- Dream synthesis engine (gene_affinity, niche_fill, mutation_replay, toxic_avoidance)
- Security perimeter / immune system with organ-level health monitoring
- Research engine (non-blocking DDG + Ollama background queries)
- Cognitive biases engine (Ebbinghaus + emotional salience scoring)
- Spreading activation / neural priming graph
- Working memory buffer (salience-gated, ephemeral)
- Real-time Svelte dashboard + 3D topology viewer
- Agent gateway with 4 initial endpoints (`/pulse`, `/state`, `/inject`, `/stimulate`)
- Evolution organ (skill distillation from successful mission trajectories)
- Imagination engine (counterfactual simulation sandbox)
- Homeostasis monitor with configurable set-points
- Session journal (wipe-proof session bridge)
