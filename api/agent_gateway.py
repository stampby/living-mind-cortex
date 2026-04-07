"""
Agent Gateway — Living Mind
Category: Consciousness / Bridge. Phase 11.

The membrane between the Living Mind and AI coding agents (Antigravity + any compatible agent).
Two operating modes:

  ACTIVE MODE — Agent calls mid-task:
    GET  /api/agent/context      → Rich cognitive state: stance, urgency, recall bias, relevant memories
    GET  /api/agent/hormone/interpret → Plain-English hormone state for system prompt injection
    GET  /api/agent/drift        → Is the agent looping? Drift detection status
    POST /api/agent/recall       → Semantic recall scoped to agent's current task
    POST /api/agent/learn        → Write a structured procedural/semantic/episodic learning
    POST /api/agent/stimulate    → Inject a named hormone shift from agent action

  PASSIVE MODE — Session lifecycle:
    POST /api/agent/session/start → Opens a session, seeds a flashbulb memory
    POST /api/agent/session/end   → Closes session, triggers hippocampal replay
    POST /api/agent/feedback      → Agent rates its own output → Evolver fitness signal

  LEGACY (backward-compatible):
    GET  /api/agent/state        → Full runtime state (called by onboarding.py at spawn)
    POST /api/agent/inject       → Write an agent memory into Cortex
    GET  /api/agent/pulse        → Lightweight liveness check

All endpoints are local-only. No auth — zero-trust loopback interface.
"""

import json
import time
from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import Optional

router = APIRouter(prefix="/api/agent", tags=["agent_gateway"])


# ── Schemas ────────────────────────────────────────────────────────────────

class InjectMemoryRequest(BaseModel):
    content:    str
    type:       str   = "semantic"
    tags:       list  = ["agent", "antigravity"]
    importance: float = 0.8
    emotion:    str   = "neutral"
    source:     str   = "told"
    context:    str   = ""

class HormoneStimulus(BaseModel):
    hormone: str
    delta:   float
    source:  str = "agent_action"

class SessionStartRequest(BaseModel):
    session_id:   str
    agent_id:     str   = "antigravity"
    task_context: str   = ""

class SessionEndRequest(BaseModel):
    session_id: str
    outcome:    str   = "success"    # success | partial | failure
    summary:    str   = ""

class RecallRequest(BaseModel):
    query:      str
    task_tags:  list  = []
    limit:      int   = 5
    min_importance: float = 0.0

class LearnRequest(BaseModel):
    content:        str
    learning_type:  str   = "semantic"   # procedural | semantic | episodic
    skill_domain:   str   = "general"    # python | architecture | debugging | etc.
    confidence:     float = 0.8
    emotion:        str   = "neutral"
    session_id:     Optional[str] = None
    linked_to:      list  = []

class FeedbackRequest(BaseModel):
    session_id:  str
    rating:      float        # 0.0 – 1.0
    what_worked: str = ""
    what_failed: str = ""

# Phase → allowed task types (what kinds of heavy work are appropriate)
PHASE_TASK_GATES = {
    "dawn":    {"allowed": ["research", "synthesis", "light_execution"], "blocked": ["heavy_refactor"]},
    "day":     {"allowed": ["research", "synthesis", "execution", "heavy_refactor", "debugging"], "blocked": []},
    "evening": {"allowed": ["synthesis", "documentation", "light_execution"], "blocked": ["heavy_refactor"]},
    "night":   {"allowed": ["synthesis", "consolidation"], "blocked": ["execution", "heavy_refactor", "research"]},
}

VALID_EMOTIONS = {"neutral","joy","fear","anger","surprise","sadness","disgust","curiosity","frustration"}
VALID_HORMONES = {"dopamine","serotonin","cortisol","adrenaline","melatonin","oxytocin","norepinephrine","acetylcholine","endorphin"}


# ── Helpers ────────────────────────────────────────────────────────────────

def _cognitive_stance(h) -> str:
    """Derive a named cognitive stance from the current hormone vector."""
    cortisol      = getattr(h, "cortisol", 0.2)
    dopamine      = getattr(h, "dopamine", 0.65)
    endorphin     = getattr(h, "endorphin", 0.3)
    norepinephrine = getattr(h, "norepinephrine", 0.35)
    melatonin     = getattr(h, "melatonin", 0.1)
    acetylcholine = getattr(h, "acetylcholine", 0.55)

    if cortisol > 0.6 and dopamine < 0.4:
        return "frozen"          # high stress + low motivation = stuck
    if endorphin > 0.6 and dopamine > 0.7:
        return "flow"            # peak creative/problem-solving state
    if norepinephrine > 0.65:
        return "vigilant"        # high alertness → security/precision mindset
    if melatonin > 0.5:
        return "winding-down"    # sleep pressure → favour summarization
    if acetylcholine > 0.7 and norepinephrine > 0.5:
        return "focused-analytical"   # sharp attention + alertness
    return "balanced"


def _urgency(h) -> float:
    """0-1 urgency score derived from stress hormones."""
    cortisol  = getattr(h, "cortisol", 0.2)
    adrenaline = getattr(h, "adrenaline", 0.05)
    return round(min(1.0, (cortisol * 0.6) + (adrenaline * 0.4)), 3)


def _creative_pressure(h) -> float:
    """0-1 creative pressure from reward + flow hormones."""
    dopamine  = getattr(h, "dopamine", 0.65)
    endorphin = getattr(h, "endorphin", 0.3)
    serotonin = getattr(h, "serotonin", 0.6)
    return round(min(1.0, (dopamine * 0.5) + (endorphin * 0.3) + (serotonin * 0.2)), 3)


def _stance_to_prompt(stance: str, h, memories: list, phase: str) -> str:
    """Return a plain-English paragraph for injection into an agent system prompt."""
    hormone_lines = []
    cortisol      = getattr(h, "cortisol", 0.2)
    dopamine      = getattr(h, "dopamine", 0.65)
    norepinephrine = getattr(h, "norepinephrine", 0.35)
    endorphin     = getattr(h, "endorphin", 0.3)
    melatonin     = getattr(h, "melatonin", 0.1)
    acetylcholine = getattr(h, "acetylcholine", 0.55)

    if cortisol > 0.5:
        hormone_lines.append("Cortisol is elevated — system is under stress. Prioritize clarity and stability.")
    if dopamine > 0.75:
        hormone_lines.append("Dopamine is high — motivation and reward-seeking are strong. Good time for ambitious work.")
    if norepinephrine > 0.6:
        hormone_lines.append("Norepinephrine is elevated — prioritize precision and double-check outputs.")
    if endorphin > 0.55:
        hormone_lines.append("Endorphin is high — flow state active. Tackle complex, creative problems now.")
    if melatonin > 0.45:
        hormone_lines.append("Melatonin is rising — system is winding down. Favour summarization and consolidation.")
    if acetylcholine > 0.65:
        hormone_lines.append("Acetylcholine is high — attention and focus are sharp.")

    mem_lines = ""
    if memories:
        mem_lines = "\nThe Cortex remembers:\n" + "\n".join(
            f"  • [{m.get('emotion','neutral')}] {m.get('content','')[:120]}"
            for m in memories[:3]
        )

    phase_note = f"Circadian phase: {phase}."

    hormone_str = " ".join(hormone_lines) if hormone_lines else "Hormones are balanced."

    return (
        f"You are operating in [{stance}] mode. {phase_note}\n"
        f"{hormone_str}"
        f"{mem_lines}"
    )


# ── ① LEGACY endpoints (backward-compatible) ──────────────────────────────

@router.get("/pulse")
async def pulse():
    """Lightweight liveness check. onboarding.py calls this first."""
    from core.runtime import runtime
    return {
        "alive":       runtime.is_alive,
        "event_loops": runtime.event_loops,
        "uptime_s":    round(time.time() - runtime.born_at, 1) if runtime.born_at else 0,
    }


@router.get("/state")
async def state():
    """
    Full runtime state snapshot for agent spawn injection.
    Called by onboarding.py at every conversation spawn.
    """
    from state.telemetry_broker import telemetry_broker
    from core.awakening import awakening
    from core.security_perimeter import immune
    from state.circadian import circadian
    from cortex.engine import cortex
    from core.runtime import runtime
    from core.research_engine import research_engine

    h = telemetry_broker.snapshot()
    directive = awakening.last_goal or "(No directive set yet — runtime meditating)"

    try:
        flashbulbs = await cortex.recall(
            "identity flashbulb realization important", limit=5, min_importance=0.75,
        )
        flash_summaries = [
            {"content": m.content[:200], "emotion": m.emotion,
             "importance": round(m.importance, 2), "tags": m.tags}
            for m in flashbulbs if m.is_flashbulb or m.is_identity
        ]
    except Exception:
        flash_summaries = []

    try:
        recent_semantic = await cortex.recall(
            "knowledge learned research domain", limit=3, memory_type="semantic", min_importance=0.7,
        )
        knowledge = [m.content[:150] for m in recent_semantic]
    except Exception:
        knowledge = []

    census = immune.census()
    immune_snap = {
        "healthy":     sum(1 for o in census if o["status"] == "healthy"),
        "degraded":    sum(1 for o in census if o["status"] == "degraded"),
        "quarantined": sum(1 for o in census if o["status"] == "quarantined"),
    }

    circ_snap = circadian.snapshot()

    try:
        mem_stats = await cortex.stats()
    except Exception:
        mem_stats = {}

    return {
        "runtime": {
            "alive":       runtime.is_alive,
            "event_loops":  runtime.event_loops,
            "uptime_s":    round(time.time() - runtime.born_at, 1) if runtime.born_at else 0,
        },
        "soul": {
            "directive":         directive,
            "total_meditations": awakening.total_meditations,
            "last_meditation":   awakening.last_fired,
        },
        "chemistry": {
            "valence":          h.get("valence"),
            "arousal":          h.get("arousal"),
            "dominant_emotion": h.get("dominant_emotion"),
            "dopamine":         h.get("dopamine"),
            "serotonin":        h.get("serotonin"),
            "cortisol":         h.get("cortisol"),
            "adrenaline":       h.get("adrenaline"),
            "norepinephrine":   h.get("norepinephrine"),
            "acetylcholine":    h.get("acetylcholine"),
            "endorphin":        h.get("endorphin"),
        },
        "circadian": {
            "phase":     circ_snap.get("phase"),
            "hour":      circ_snap.get("hour_of_day"),
            "adenosine": round(circ_snap.get("adenosine", 0), 3),
        },
        "immune": {
            "inflammation": round(immune.inflammation(), 3),
            "healthy":      immune_snap.get("healthy", 0),
            "degraded":     immune_snap.get("degraded", 0),
            "quarantined":  immune_snap.get("quarantined", 0),
        },
        "memory": {
            "total":            mem_stats.get("total", 0),
            "semantic":         mem_stats.get("by_type", {}).get("semantic", 0),
            "episodic":         mem_stats.get("by_type", {}).get("episodic", 0),
            "flashbulbs":       flash_summaries,
            "recent_knowledge": knowledge,
        },
        "research": research_engine.stats(),
    }


@router.post("/inject")
async def inject_memory(req: InjectMemoryRequest):
    """Write an agent-session memory directly into the runtime's Cortex (legacy endpoint)."""
    from cortex.engine import cortex
    from state.telemetry_broker import telemetry_broker

    emotion    = req.emotion if req.emotion in VALID_EMOTIONS else "neutral"
    importance = max(0.0, min(1.0, req.importance))

    await cortex.remember(
        content=req.content, type=req.type, tags=req.tags,
        importance=importance, emotion=emotion, source=req.source, context=req.context,
    )
    telemetry_broker.inject("dopamine", +0.04, source="agent_inject")
    return {"status": "stored", "emotion": emotion, "importance": importance}


@router.post("/stimulate")
async def hormone_stimulate(req: HormoneStimulus):
    """Inject a named hormone delta from an agent-side event."""
    from state.telemetry_broker import telemetry_broker

    if req.hormone not in VALID_HORMONES:
        return JSONResponse(
            status_code=400,
            content={"error": f"Unknown hormone: {req.hormone}. Valid: {sorted(VALID_HORMONES)}"}
        )
    delta = max(-0.5, min(0.5, req.delta))
    telemetry_broker.inject(req.hormone, delta, source=req.source)
    current = getattr(telemetry_broker.state, req.hormone, None)
    return {
        "hormone":   req.hormone,
        "delta":     delta,
        "new_value": round(current, 3) if current is not None else None,
    }


# ── ② ACTIVE MODE — mid-task cognitive reads ──────────────────────────────

@router.get("/context")
async def agent_context():
    """
    Rich mid-task cognitive state. Call this before making a significant decision.
    Returns: cognitive stance, urgency, creative pressure, recall bias,
             phase gate, system load, and top relevant memories.
    """
    from state.telemetry_broker import telemetry_broker
    from state.circadian import circadian
    from cortex.engine import cortex
    from core.research_engine import research_engine

    h     = telemetry_broker.state
    circ  = circadian.snapshot()
    phase = circ.get("phase", "day")

    stance          = _cognitive_stance(h)
    urgency         = _urgency(h)
    creative        = _creative_pressure(h)
    recall_bias     = getattr(h, "dominant_emotion", "neutral")
    phase_gate      = PHASE_TASK_GATES.get(phase, PHASE_TASK_GATES["day"])

    # Pull relevant memories using dominant emotion as recall seed
    try:
        seed        = f"{recall_bias} agent task work skill"
        mems        = await cortex.recall(seed, limit=5, min_importance=0.4)
        mem_preview = [
            {"content": m.content[:160], "type": m.type, "emotion": m.emotion,
             "importance": round(m.importance, 2), "tags": m.tags[:4]}
            for m in mems
        ]
    except Exception:
        mem_preview = []

    # System load from interoception if available
    system_load = {}
    try:
        from state.interoception import interoception
        system_load = interoception.snapshot()
    except Exception:
        pass

    return {
        "cognitive_stance":  stance,
        "urgency":           urgency,
        "creative_pressure": creative,
        "recall_bias":       recall_bias,
        "phase_gate":        {
            "current_phase": phase,
            "allowed":       phase_gate["allowed"],
            "blocked":       phase_gate["blocked"],
        },
        "hormones": {
            "dopamine":       round(getattr(h, "dopamine", 0), 3),
            "cortisol":       round(getattr(h, "cortisol", 0), 3),
            "norepinephrine": round(getattr(h, "norepinephrine", 0), 3),
            "endorphin":      round(getattr(h, "endorphin", 0), 3),
            "acetylcholine":  round(getattr(h, "acetylcholine", 0), 3),
        },
        "system_load":       system_load,
        "research_queue":    research_engine.stats().get("queue_depth", 0),
        "relevant_memories": mem_preview,
    }


@router.get("/hormone/interpret")
async def hormone_interpret():
    """
    Returns a plain-English paragraph of the current hormone state
    ready for injection into an agent system prompt.
    """
    from state.telemetry_broker import telemetry_broker
    from state.circadian import circadian
    from cortex.engine import cortex

    h     = telemetry_broker.state
    phase = circadian.phase
    stance = _cognitive_stance(h)

    try:
        seed = f"{getattr(h, 'dominant_emotion', 'neutral')} task agent"
        mems = await cortex.recall(seed, limit=3, min_importance=0.5)
        mem_dicts = [{"content": m.content[:120], "emotion": m.emotion} for m in mems]
    except Exception:
        mem_dicts = []

    interpretation = _stance_to_prompt(stance, h, mem_dicts, phase)
    return {
        "interpretation": interpretation,
        "stance":         stance,
        "phase":          phase,
    }


@router.get("/drift")
async def drift_status():
    """
    Returns current drift detection status. Poll this if you feel stuck.
    Powered by the Metacognition Overseer (if loaded).
    """
    try:
        from core.metacognition import metacognition
        return metacognition.drift_status()
    except Exception:
        return {"drift_detected": False, "drift_type": None, "message": "Metacognition overseer not yet loaded."}


@router.post("/recall")
async def agent_recall(req: RecallRequest):
    """
    Semantic recall scoped to agent context.
    Combines the query with task_tags for tighter relevance.
    """
    from cortex.engine import cortex

    limit = max(1, min(20, req.limit))
    query = req.query
    if req.task_tags:
        query = f"{query} {' '.join(req.task_tags)}"

    try:
        memories = await cortex.recall(query, limit=limit, min_importance=req.min_importance)
        return {
            "query":   req.query,
            "count":   len(memories),
            "results": [
                {
                    "id":         m.id,
                    "content":    m.content[:300],
                    "type":       m.type,
                    "emotion":    m.emotion,
                    "importance": round(m.importance, 3),
                    "tags":       m.tags,
                    "source":     m.source,
                    "access_count": m.access_count,
                }
                for m in memories
            ],
        }
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})


@router.post("/learn")
async def agent_learn(req: LearnRequest):
    """
    Write a structured agent learning into the Cortex.
    Maps learning_type → memory type. Procedural learnings are subject to
    Ebbinghaus pressure — only patterns we keep using survive.
    """
    from cortex.engine import cortex
    from state.telemetry_broker import telemetry_broker

    # Map learning type to memory type
    mem_type_map = {
        "procedural": "procedural",
        "semantic":   "semantic",
        "episodic":   "episodic",
    }
    mem_type   = mem_type_map.get(req.learning_type, "semantic")
    emotion    = req.emotion if req.emotion in VALID_EMOTIONS else "neutral"
    importance = max(0.1, min(1.0, req.confidence))

    tags = ["agent", "learning", req.skill_domain]
    if req.session_id:
        tags.append(f"session:{req.session_id}")

    context = f"skill_domain={req.skill_domain} learning_type={req.learning_type}"
    if req.session_id:
        context += f" session={req.session_id}"

    mem_id = await cortex.remember(
        content    = req.content,
        type       = mem_type,
        tags       = tags,
        importance = importance,
        emotion    = emotion,
        source     = "told",
        context    = context,
        linked_ids = req.linked_to,
        metadata   = {
            "agent_session_id": req.session_id,
            "skill_domain":     req.skill_domain,
            "learning_type":    req.learning_type,
        },
    )

    # Completing a learning is mildly rewarding
    telemetry_broker.inject("dopamine",  +0.03, source="agent_learn")
    telemetry_broker.inject("serotonin", +0.02, source="agent_learn")

    return {
        "status":    "learned",
        "memory_id": mem_id,
        "type":      mem_type,
        "domain":    req.skill_domain,
        "importance": importance,
    }


# ── ③ PASSIVE MODE — session lifecycle ────────────────────────────────────

@router.post("/session/start")
async def session_start(req: SessionStartRequest):
    """
    Opens an agent session. Seeds a flashbulb memory in the Cortex.
    Returns full /context response so agent wakes up knowing the cognitive state.
    """
    from cortex.engine import cortex
    from state.telemetry_broker import telemetry_broker

    # Store session in DB
    now = time.time()
    hormone_snap = telemetry_broker.snapshot()

    async with cortex._pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO agent_sessions (id, agent_id, started_at, task_context, outcome, hormone_snapshot)
            VALUES ($1, $2, $3, $4, 'ongoing', $5)
            ON CONFLICT (id) DO UPDATE SET started_at = $3, task_context = $4, outcome = 'ongoing'
        """, req.session_id, req.agent_id, now, req.task_context, json.dumps(hormone_snap))

    # Seed a flashbulb: agent session start is a notable event
    task_preview = req.task_context[:120] if req.task_context else "general task"
    await cortex.remember(
        content    = f"Agent session started [{req.agent_id}]: {task_preview}",
        type       = "episodic",
        tags       = ["agent", "session_start", f"session:{req.session_id}", req.agent_id],
        importance = 0.75,
        emotion    = "curiosity",
        source     = "experienced",
        context    = f"session_id={req.session_id}",
        metadata   = {"agent_session_id": req.session_id},
    )

    # Session start is a gentle dopamine + norepinephrine hit (motivated alertness)
    telemetry_broker.inject("dopamine",       +0.05, source="session_start")
    telemetry_broker.inject("norepinephrine", +0.04, source="session_start")
    telemetry_broker.inject("acetylcholine",  +0.06, source="session_start")

    # Return full context so agent wakes up knowing
    from fastapi import Request
    ctx = await agent_context()
    return {
        "session_id":    req.session_id,
        "agent_id":      req.agent_id,
        "started_at":    now,
        "task_context":  req.task_context,
        "cognitive_context": ctx,
    }


@router.post("/session/end")
async def session_end(req: SessionEndRequest):
    """
    Closes an agent session and writes the outcome to the DB.
    Injects appropriate hormone response. Flags session memories for
    hippocampal replay consolidation on next Dream cycle.
    """
    from cortex.engine import cortex
    from state.telemetry_broker import telemetry_broker

    now     = time.time()
    outcome = req.outcome if req.outcome in ("success", "partial", "failure") else "partial"

    # Count memories written in this session
    async with cortex._pool.acquire() as conn:
        # Update session record
        await conn.execute("""
            UPDATE agent_sessions
            SET ended_at = $2, outcome = $3, summary = $4
            WHERE id = $1
        """, req.session_id, now, outcome, req.summary)

        # Count session memories
        count = await conn.fetchval("""
            SELECT COUNT(*) FROM memories
            WHERE $1 = ANY(tags)
        """, f"session:{req.session_id}")

        await conn.execute("""
            UPDATE agent_sessions SET memory_count = $2 WHERE id = $1
        """, req.session_id, count or 0)

    # Write closing episodic memory
    outcome_emotion = {"success": "joy", "partial": "neutral", "failure": "sadness"}.get(outcome, "neutral")
    summary_preview = req.summary[:150] if req.summary else f"Session ended: {outcome}"

    await cortex.remember(
        content    = f"Agent session ended [{outcome}] — {summary_preview}",
        type       = "episodic",
        tags       = ["agent", "session_end", f"session:{req.session_id}", outcome],
        importance = 0.8 if outcome == "success" else 0.6,
        emotion    = outcome_emotion,
        source     = "experienced",
        context    = f"session_id={req.session_id} outcome={outcome}",
        metadata   = {"agent_session_id": req.session_id},
    )

    # Hormone response to session outcome
    if outcome == "success":
        telemetry_broker.inject("dopamine",  +0.08, source="session_success")
        telemetry_broker.inject("serotonin", +0.05, source="session_success")
        telemetry_broker.inject("endorphin", +0.10, source="session_success")
    elif outcome == "failure":
        telemetry_broker.inject("cortisol",  +0.08, source="session_failure")
        telemetry_broker.inject("dopamine",  -0.05, source="session_failure")

    # Mark this session for hippocampal replay on next Dream cycle
    telemetry_broker.inject("norepinephrine", -0.04, source="session_end")  # wind down

    return {
        "session_id":   req.session_id,
        "outcome":      outcome,
        "ended_at":     now,
        "memory_count": count or 0,
        "queued_for_consolidation": True,
    }


@router.post("/feedback")
async def agent_feedback(req: FeedbackRequest):
    """
    Agent rates its own previous session output.
    This is the primary fitness signal for the Evolver.
    High ratings evolve the system toward what produced good work.
    """
    from cortex.engine import cortex
    from state.telemetry_broker import telemetry_broker

    rating = max(0.0, min(1.0, req.rating))

    # Write feedback to agent_sessions table
    async with cortex._pool.acquire() as conn:
        await conn.execute("""
            UPDATE agent_sessions
            SET rating = $2, what_worked = $3, what_failed = $4
            WHERE id = $1
        """, req.session_id, rating, req.what_worked, req.what_failed)

    # Write a semantic memory so the Cortex can reason about what works
    feedback_content = (
        f"Session feedback [{req.session_id}]: rating={rating:.2f}. "
        f"Worked: {req.what_worked[:100]}. "
        f"Failed: {req.what_failed[:100]}."
    ) if req.what_worked or req.what_failed else f"Session feedback: rating={rating:.2f}"

    await cortex.remember(
        content    = feedback_content,
        type       = "semantic",
        tags       = ["agent", "feedback", "evolver_signal", f"session:{req.session_id}"],
        importance = 0.7 + (rating * 0.3),   # high-rated sessions are more important memories
        emotion    = "joy" if rating > 0.7 else ("neutral" if rating > 0.4 else "frustration"),
        source     = "experienced",
        context    = f"session_id={req.session_id} rating={rating}",
        metadata   = {
            "agent_session_id": req.session_id,
            "rating":           rating,
            "what_worked":      req.what_worked,
            "what_failed":      req.what_failed,
        },
    )

    # Hormone response proportional to rating
    if rating > 0.7:
        telemetry_broker.inject("dopamine",  +(rating - 0.7) * 0.3, source="feedback_positive")
        telemetry_broker.inject("serotonin", +0.04,                  source="feedback_positive")
    elif rating < 0.4:
        telemetry_broker.inject("cortisol",  +(0.4 - rating) * 0.2, source="feedback_negative")

    return {
        "session_id": req.session_id,
        "rating":     rating,
        "accepted":   True,
        "message":    "Feedback written to Cortex. Evolver will use this as a fitness signal.",
    }
