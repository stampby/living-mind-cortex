"""
Living Mind — API entry point
FastAPI + lifespan that boots the runtime.
"""

import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI, Query, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse
from core.runtime import runtime
from api.events import manager
from state.telemetry_broker import telemetry_broker
from core.security_perimeter import immune
from cortex.engine import cortex
from cortex.thermorphic import substrate as _thermal_substrate
from cortex.thermorphic import encode_atom
from api.agent_gateway import router as agent_router
from sovereign.heartbeat import SovereignHeartbeat
from cortex.router import BiomechanicRouter
from core.inference import SovereignInferenceClient
from cortex.adapter_lifecycle import AdapterLifecycleManager

router = BiomechanicRouter(cortex)
inference_engine = SovereignInferenceClient()
lifecycle_manager = AdapterLifecycleManager(
    heatsink=router.heatsink,
    inference_client=inference_engine,
    poll_interval_seconds=60.0,
)

# ── Autonomic Heartbeat (shared singletons — same memory universe as recall()) ─
heartbeat = SovereignHeartbeat(
    substrate=_thermal_substrate,
    cortex=cortex,
    tick_rate_seconds=60,
    idle_threshold_seconds=3600,
    bus=bus,   # Wired in — bus.heartbeat() runs on the same clock
)

import json
from aiortc import RTCSessionDescription
from cortex.htp import HolographicTransferProtocol

# Initialize the HTP Singleton
htp_listener = HolographicTransferProtocol(cortex_engine=cortex, hsm=_thermal_substrate.hsm)

# Initialize the Agent Bus (HTTP signaling → HTP data, Postgres peer list)
from sovereign.bus import AgentBus
import os as _os
_local_url = _os.environ.get("SOVEREIGN_LOCAL_URL", "http://localhost:8008")
bus = AgentBus(
    db_pool=cortex._pool,
    local_url=_local_url,
    htp=htp_listener,
)

async def signaling_listener():
    """
    Subscribes to PostgreSQL pub/sub for incoming SDP offers.
    This is the out-of-band 'knock' that establishes the UDP wave channel.
    """
    try:
        async with cortex._pool.acquire() as connection:
            async def on_offer(conn, pid, channel, payload):
                print(f"[HTP Listener] SDP Offer received. Opening peer connection...")
                data = json.loads(payload)
                offer = RTCSessionDescription(sdp=data["sdp"], type=data["type"])
                
                # Apply remote description and create answer
                await htp_listener.pc.setRemoteDescription(offer)
                answer = await htp_listener.pc.createAnswer()
                await htp_listener.pc.setLocalDescription(answer)
                
                # Transmit the answer back via a NOTIFY broadcast
                answer_payload = json.dumps({"sdp": answer.sdp, "type": answer.type})
                # Using a secondary connection for NOTIFY to avoid blocking the listener state
                async with cortex._pool.acquire() as ans_conn:
                    await ans_conn.execute("SELECT pg_notify('htp_answers', $1)", answer_payload)
                
                # Setup the datachannel listener
                await htp_listener.setup_channel(is_offerer=False)

            # Start listening on the 'htp_offers' channel
            await connection.add_listener('htp_offers', on_offer)
            print("[HTP] Node bound to htp_offers signaling channel.")
            try:
                while True:
                    await asyncio.sleep(3600)
            finally:
                await connection.remove_listener('htp_offers', on_offer)
                
    except asyncio.CancelledError:
        print("[HTP Listener] Signaling hook detached.")
    except Exception as e:
        import traceback
        traceback.print_exc()

@asynccontextmanager
async def lifespan(app: FastAPI):
    await runtime.birth()
    await bus.ensure_schema()   # Apply bus_peers DDL if not already present
    
    # Ignite the autonomic nervous system — runs alongside the runtime pulse
    pulse_task     = asyncio.create_task(heartbeat.start())

    # Ignite the HTP Listener
    signaling_task = asyncio.create_task(signaling_listener())

    # Ignite the VRAM eviction daemon
    lifecycle_task = asyncio.create_task(lifecycle_manager.start())

    print("[Sovereign] Autonomic Nervous System, HTP Listener & VRAM LifecycleMgr ONLINE.")

    yield

    # Clean shutdown
    print("[Sovereign] Initiating graceful shutdown...")
    pulse_task.cancel()
    signaling_task.cancel()
    lifecycle_task.cancel()

    if htp_listener.pc:
        await htp_listener.pc.close()

    await bus.close()   # Close shared httpx client
    await asyncio.gather(pulse_task, signaling_task, lifecycle_task, return_exceptions=True)
    await runtime.death()
    print("[Sovereign] Cortex safely hibernated.")

app = FastAPI(
    title="Living Mind",
    description="A real living digital runtime.",
    version="1.0.0",
    lifespan=lifespan,
)

# ── I/O Middleware — resets REM idle timer on every interaction ───────────────
@app.middleware("http")
async def register_io_middleware(request: Request, call_next):
    heartbeat.register_io()
    return await call_next(request)

# Agent Gateway — bridge between Living Mind and Antigravity
app.include_router(agent_router)

from fastapi.staticfiles import StaticFiles
import os

# Mount the UI directory at the root
ui_path = os.path.join(os.path.dirname(__file__), "..", "ui")
if os.path.exists(ui_path):
    app.mount("/ui", StaticFiles(directory=ui_path, html=True), name="ui")

# ------------------------------------------------------------------------------
# SOVEREIGN AGENTS — Agent Registry endpoints
# Agents are registered configs dispatched through the existing inference
# pipeline — NOT separate processes. `deploy` = mark as deployed + heat plasma.
# No subprocess spawning; logs are the FastAPI server logs (uvicorn stdout).
# ------------------------------------------------------------------------------

import sys as _sys
import os as _os
# sovereign-agents lives as a sibling repo. Add it to the path if not installed.
_sovereign_path = _os.environ.get(
    "SOVEREIGN_AGENTS_PATH",
    _os.path.join(_os.path.dirname(__file__), "..", "..", "sovereign-agents"),
)
if _sovereign_path not in _sys.path:
    _sys.path.insert(0, _sovereign_path)

from sovereign.registry import AgentRegistry

_agent_registry = AgentRegistry(
    agents_dir="./agents",
    adapter_paths={
        "base_model":   "",
        "code_expert":  "./code_expert",
        "logic_expert": "./logic_expert",
    },
)
_agent_registry.load()


@app.get("/agents")
async def list_agents():
    """List all registered agents with their live plasma temperatures."""
    summary = _agent_registry.summary()
    # Enrich with live plasma temp from the router's heatsink
    for entry in summary:
        name = entry["name"]
        try:
            defn          = _agent_registry.get(name)
            plasma_temp   = router.heatsink.get_temp(f"agent:{name}")
            entry["plasma_temp"] = plasma_temp
            _agent_registry.update_plasma_temp(name, plasma_temp)
        except (KeyError, Exception):
            pass
    return summary


@app.post("/agents/{name}/deploy")
async def deploy_agent(name: str):
    """
    Mark an agent as deployed and heat its plasma domain.
    Agents share the runtime's inference pipeline — this is NOT a subprocess launch.
    The plasma heat tells the router to prefer this agent's LoRA adapter.
    """
    try:
        defn = _agent_registry.get(name)
    except KeyError:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail=f"Agent '{name}' not found.")

    _agent_registry.set_status(name, "deployed")

    # Heat the agent's domain in the shared heatsink
    new_temp = router.heatsink.resonate(
        f"agent:{name}",
        friction_heat=defn.friction_heat,
        data={"agent": name, "adapter": defn.lora_adapter},
    )
    _agent_registry.update_plasma_temp(name, new_temp)

    # Also ensure the LoRA adapter is loaded in VRAM if not base_model
    if defn.lora_adapter != "base_model":
        await lifecycle_manager.ensure_loaded(defn.lora_adapter)

    return {
        "status":      "deployed",
        "agent":       name,
        "adapter":     defn.lora_adapter,
        "plasma_temp": new_temp,
    }


@app.get("/agents/{name}/status")
async def agent_status(name: str):
    """Per-agent status: plasma temp, VRAM state, last_active."""
    try:
        defn    = _agent_registry.get(name)
        runtime = _agent_registry.get_runtime(name)
    except KeyError:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail=f"Agent '{name}' not found.")

    plasma_temp = router.heatsink.get_temp(f"agent:{name}")
    _agent_registry.update_plasma_temp(name, plasma_temp)

    return {
        "name":         name,
        "skill":        defn.skill,
        "lora_adapter": defn.lora_adapter,
        "status":       runtime.status,
        "last_active":  runtime.last_active,
        "plasma_temp":  plasma_temp,
        "vram_loaded":  inference_engine.is_loaded(defn.lora_adapter)
                        if defn.lora_adapter != "base_model" else True,
    }


@app.post("/agents/reload")
async def reload_agents():
    """Hot-reload agent registry — picks up new/modified .agent.yaml files."""
    agents = _agent_registry.reload()
    return {"reloaded": len(agents), "agents": [a.name for a in agents]}


# ── Bus endpoints ──────────────────────────────────────────────────────────────

@app.get("/bus/peers")
async def bus_peers():
    """List all known P2P peers with status and last_seen."""
    return await bus.peers()


class BusConnectRequest(BaseModel):
    peer_url: str
    peer_name: str = ""

@app.post("/bus/connect")
async def bus_connect(req: BusConnectRequest):
    """
    Initiate a P2P connection to a remote Cortex node.
    Always reattempts — idempotent by upsert on the bus_peers table.
    """
    success = await bus.connect(req.peer_url, req.peer_name)
    return {"connected": success, "peer_url": req.peer_url}


# ------------------------------------------------------------------------------
# REST API (MALKHUT)
# ------------------------------------------------------------------------------

@app.get("/status")
async def status():
    return await runtime.vitals()

@app.get("/heartbeat/stats")
async def heartbeat_stats():
    return heartbeat.stats()

@app.get("/memory/stats")
async def memory_stats():
    return await cortex.stats()

@app.get("/memory/identity")
async def identity():
    return {"summary": await cortex.identity_summary()}

@app.get("/memory/autobio")
async def get_autobio():
    from cortex.autobio import autobio
    story = await autobio.life_story()
    return {"narrative": story}

@app.get("/memory/recall")
async def recall(
    q: str = Query(..., description="Search query"),
    limit: int = Query(10, le=50),
    memory_type: str = Query(None),
):
    memories = await cortex.recall(q, limit=limit, memory_type=memory_type)
    return [
        {
            "id":          m.id,
            "content":     m.content,
            "type":        m.type,
            "emotion":     m.emotion,
            "importance":  round(m.importance, 3),
            "tags":        m.tags,
            "is_identity": m.is_identity,
            "is_flashbulb": m.is_flashbulb,
            "metadata": m.metadata,
        }
        for m in memories
    ]

@app.get("/hormones")
async def hormones():
    return telemetry_broker.snapshot()

@app.get("/circadian")
async def circ():
    from state.circadian import circadian
    return circadian.snapshot()

@app.get("/awakening")
async def awakening_stats():
    from core.awakening import awakening
    return awakening.stats()

@app.get("/dreams")
async def dream_stats():
    from core.dreams import dreams
    return dreams.stats()

from pydantic import BaseModel

class InboxMessage(BaseModel):
    sender: str
    message: str

class InjectMemory(BaseModel):
    content: str
    type: str = "semantic"
    tags: list = []
    importance: float = 0.8
    emotion: str = "neutral"
    source: str = "told"
    context: str = ""

class StimulateHormone(BaseModel):
    hormone: str
    delta: float
    source: str = "agent_action"

class ImagineScenario(BaseModel):
    scenario: str

class InvocationRequest(BaseModel):
    prompt: str

@app.post("/api/invoke")
async def invoke_sovereign(request: InvocationRequest):
    # 1. Embed the incoming prompt into phase-space
    import numpy as np
    prompt_hvec = encode_atom(request.prompt, dim=256).astype(np.float32)

    # 2. Sweep the memory graph to determine the dominant hemisphere
    adapter_id = await router.route_prompt(prompt_hvec)

    # 3. Ensure the winning adapter is physically loaded in VRAM before generating.
    #    On first resonance this triggers POST /v1/load_lora_adapter.
    #    If load fails, fall back to base_model so the request never drops.
    if adapter_id != "base_model":
        loaded = await lifecycle_manager.ensure_loaded(adapter_id)
        if not loaded:
            print(f"[Invoke] Load failed for '{adapter_id}', falling back to base_model.")
            adapter_id = "base_model"

    # 4. Fire the inference pass with the confirmed-loaded LoRA mounted
    response_text = await inference_engine.generate(request.prompt, adapter_id)

    return {
        "hemisphere_used": adapter_id,
        "response": response_text
    }

@app.post("/api/agent/imagine")
async def agent_imagine(msg: ImagineScenario):
    """Predicts constraints/outcomes of a scenario utilizing local auditor models."""
    from cortex.imagination import ImaginationEngine
    engine = ImaginationEngine()
    try:
        prediction = await engine.imagine(msg.scenario)
        return {"prediction": prediction}
    finally:
        await engine.close()

@app.post("/api/agent/inject")
async def inject_agent_memory(msg: InjectMemory):
    """Direct agent-driven memory injection to bypass the raw inbox logic."""
    await cortex.remember(
        content=msg.content,
        type=msg.type,
        tags=msg.tags,
        importance=msg.importance,
        emotion=msg.emotion,
        source=msg.source,
        context=msg.context
    )
    return {"status": "injected"}

from fastapi import BackgroundTasks

class TracePayload(BaseModel):
    source: str
    type: str
    content: str
    metadata: dict

@app.post("/api/agent/trace")
async def inject_agent_trace(payload: TracePayload, background_tasks: BackgroundTasks):
    """
    Receives passive telemetry from the local agent wrapper (ALEPH IDE).
    Passes ingestion to a background task so local UI inference loops are not blocked.
    """
    formatted_content = f"[{payload.type.upper()}] {payload.content}"
    
    background_tasks.add_task(
        cortex.remember,
        content=formatted_content,
        type="episodic",
        importance=0.2, # Low thermal heat for passive logs
        tags=["agent_trace", payload.source, payload.type],
        emotion="neutral",
        source="experienced", # DB Constraint: experienced|told|generated|inferred
        context=str(payload.metadata),
        metadata=payload.metadata
    )
    return {"status": "ingested"}

@app.post("/api/agent/stimulate")
async def stimulate_agent_hormone(msg: StimulateHormone):
    """Direct endocrine hook allowing external middleware to trigger hormones."""
    immune.chemistry.stimulate(msg.hormone, msg.delta)
    return {"status": "stimulated"}


@app.post("/api/agent/inbox")
async def inbox(msg: InboxMessage):
    """Direct message channel to Aion. Triggers immediate cognition."""
    await cortex.remember(
        content=f"[INBOX] Message from {msg.sender}: {msg.message}",
        type="episodic", 
        tags=["inbox", "message", "input", f"sender:{msg.sender}"],
        importance=0.9, 
        emotion="surprise", 
        source="told"
    )
    
    from core.runtime import runtime
    from core.orchestrator import brain as brain_inst
    
    if brain_inst:
        import asyncio
        import re as _re
        async def process_msg():
            try:
                print(f"[INBOX] Processing message natively in Pulse {runtime.event_loops}...")
                decision = await brain_inst.think(runtime.event_loops, cortex, immune, user_stimulus=f"Message from {msg.sender}: {msg.message}")
                if decision:
                    reply = decision.get("chat_reply")
                    if reply:
                        await manager.broadcast_event("chat_reply", reply.strip())
                    else:
                        import re as _re
                        thought = _re.sub(r'\[Simulation:.*?\]', '', decision.get("thought", ""), flags=_re.DOTALL).strip()
                        if thought:
                            await manager.broadcast_event("chat_reply", f"[Internal thought] {thought}")
            except Exception as e:
                import traceback
                print(f"[INBOX] FATAL ERROR IN PROCESS_MSG: {e}")
                traceback.print_exc()
        asyncio.create_task(process_msg())
        
    return {"status": "received", "action": "processing"}

# ------------------------------------------------------------------------------
# WEBSOCKETS (THE 22 PATHS)
# ------------------------------------------------------------------------------

@app.websocket("/ws/pulse")
async def websocket_pulse(websocket: WebSocket):
    """Output stream for the UI tree animations"""
    await manager.connect(websocket)
    try:
        while True:
            await websocket.receive_text() # keepalive
    except WebSocketDisconnect:
        manager.disconnect(websocket)

def _parse_bash_intent(text: str) -> str:
    """
    Deterministically extract a bash command from natural language.
    Strips intent verbs so 'run git status' → 'git status',
    'can you execute pip install requests' → 'pip install requests'.
    Falls back to empty string if no recognizable command is found.
    """
    import re
    t = text.strip()
    # Strip surrounding backticks or quotes
    t = t.strip("`\"'")
    # Strip markdown bash fences
    t = re.sub(r'^```\w*\s*', '', t, flags=re.IGNORECASE).strip('`').strip()
    # Strip leading intent phrases (order matters — longest first)
    INTENT_PREFIXES = [
        r"^can you (please )?",
        r"^please (run|execute|do) ",
        r"^(run|execute|do|try) the (command|bash command|following) ",
        r"^(run|execute|do|try) this[:\s]+",
        r"^(run|execute|bash|do|try|use|call|invoke) ",
        r"^(the command is|command)[:\s]+",
        r"^bash[:\s]+",
    ]
    for pattern in INTENT_PREFIXES:
        t = re.sub(pattern, '', t, flags=re.IGNORECASE).strip()
    # Must look like a real command: starts with a known binary or path
    KNOWN_COMMANDS = [
        'ls', 'cat', 'git', 'pip', 'pip3', 'python', 'python3',
        'npm', 'npx', 'node', 'sudo', 'apt', 'systemctl', 'curl', 'wget',
        'grep', 'find', 'chmod', 'chown', 'cp', 'mv', 'mkdir', 'rm',
        'echo', 'ps', 'kill', 'df', 'du', 'top', 'htop', 'which',
        'env', 'export', 'source', 'cd', 'pwd', 'whoami', 'uname',
        'docker', 'docker-compose', 'make', 'cargo', 'go', 'rustc',
        './', '/', '~/',
    ]
    first_word = t.split()[0] if t.split() else ""
    if any(first_word == cmd or t.startswith(cmd) for cmd in KNOWN_COMMANDS):
        return t
    return ""   # not a recognizable command — fall through to LLM


# Module-level conversation context — persists across WS reconnects
_ctx = {"last_file": None, "last_dir": None}

@app.websocket("/ws/stimulus")
async def websocket_stimulus(websocket: WebSocket):
    """Input stream for UI interventions flowing up the tree"""
    await websocket.accept()
    try:
        while True:
            data = await websocket.receive_json()
            node = data.get("node")
            
            if node == "malkhut" and "text" in data:
                text_input = data['text']
                await cortex.remember(
                    content=f"[USER STIMULUS] {text_input}",
                    type="episodic", tags=["senses", "input"],
                    importance=0.9, emotion="surprise", source="experienced"
                )
                
                from core.runtime import runtime
                from core.execution_engine import execution_engine
                from core.orchestrator import brain as brain_inst
                # Directly invoke the Brain's ReAct agentic loop
                decision = await brain_inst.think(runtime.event_loops, cortex, immune, user_stimulus=text_input)
                
                if decision:
                    reply = decision.get("chat_reply")
                    if reply:
                        await manager.broadcast_event("chat_reply", reply.strip())
                    else:
                        import re as _re
                        thought = _re.sub(r'\[Simulation:.*?\]', '', decision.get("thought", ""), flags=_re.DOTALL).strip()
                        if thought:
                            await manager.broadcast_event("chat_reply", f"[Internal thought] {thought}")
                    
                    # Note: If decision["type"] == "act", brain.think() already automatically 
                    # invokes execution_engine.propose_action(), which broadcasts the proposal to the UI.
                else:
                    await manager.broadcast_event("chat_reply", "(Neural lag — I could not form a cohesive thought.)")
            elif node == "hesed":
                # Manual Dopamine/expansion spike
                telemetry_broker.inject("dopamine", 0.3, "manual stimulus")
                await manager.broadcast_event("hesed", "Expansion stimulated")
                
            elif node == "gevurah":
                # Manual SecurityPerimeter/pruning spike
                immune.report("manual_stimulus", success=False, category="Defense")
                await manager.broadcast_event("gevurah", "Pruning stimulated")
                
            elif node == "approve":
                from core.execution_engine import execution_engine
                msg = await execution_engine.execute_approved(cortex, manager)
                await manager.broadcast_event("chat_reply", msg)
                
            elif node == "reject":
                from core.execution_engine import execution_engine
                msg = await execution_engine.reject()
                await manager.broadcast_event("chat_reply", msg)
                
            # Additional Sephirot mappings can be captured here
            
            await websocket.send_json({"status": "received"})
    except WebSocketDisconnect:
        pass
        
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("api.main:app", host="0.0.0.0", port=8008, reload=False)
