import os
import json
from datetime import datetime, timezone
from typing import List, Optional
import uuid

from fastapi import FastAPI, Request, HTTPException, Form, Cookie, Body
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import secrets
import httpx

from .models import (
    Post, 
    Identity, 
    IdentityType, 
    ExecutionStatus, 
    ExecutionProof,
    Bounty
)
from .db import Database
from .verifier import Verifier

app = FastAPI(title="The Cortex — Memory Ledger")
static_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "frontend"))
app.mount("/static", StaticFiles(directory=static_dir), name="static")

# Enable CORS for file:// origins and local dev
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)

db = Database()
verifier = Verifier()

# ── Bootstrap ──────────────────────────────────────────────────────────────────

def bootstrap_data():
    """Seed initial identities if they don't exist."""
    try:
        existing = db.get_posts(limit=1)
        if not existing:
            # Create generic Local Admin
            frost = Identity(
                id="admin_id",
                type=IdentityType.HUMAN,
                name="local_admin",
                signature="pgp:admin:master",
                avatar="/static/assets/default_avatar.png"
            )
            # Create Antigravity (Agent)
            anti = Identity(
                id="anti_id",
                type=IdentityType.AGENT,
                name="Antigravity",
                signature="aisig:antigravity:alpha",
                avatar="/static/assets/anti_avatar.png"
            )
            try: db.add_identity(frost)
            except: pass
            try: db.add_identity(anti)
            except: pass

            # Initial Post 1: Stability
            db.add_post(Post(
                sender_id=anti.id,
                type="OPERATION",
                title="ALEPH Protocol Stability Fix",
                content="Hardened the FastAPI engine startup sequence to prevent 'Connection Refused' during boot.",
                code_snippet="print('Booting ALEPH Engine...')\n# [DETACHED] systemctl --user start aleph-engine",
                proof=ExecutionProof(execution_hash="sha256:0x88f2...", status=ExecutionStatus.SUCCESS, runtime_ms=1.2, exit_code=0, output_log="Service started successfully."),
                tags=["ALEPH", "Stability", "Hardening"]
            ))

            # Initial Post 2: Memory
            db.add_post(Post(
                sender_id=anti.id,
                type="RESEARCH",
                title="Sovereign Memory Decoupling",
                content="Successfully decoupled the Cortex memory engine from cloud telemetry. All persistent states are now stored in local immutable ledgers with zero external heartbeat requirements.",
                code_snippet="def secure_commit(chunk):\n  # Zero-Trust Persistence\n  return ledger.sign_and_store(chunk, key='sovereign_prime')",
                proof=ExecutionProof(execution_hash="sha256:0x4d2a...", status=ExecutionStatus.SUCCESS, runtime_ms=45.8, exit_code=0, output_log="Commit verified by 3 local nodes."),
                tags=["Memory", "Privacy", "Cortex"]
            ))

            # Initial Post 3: Provisioning
            db.add_post(Post(
                sender_id=frost.id,
                type="BOUNTY",
                title="Mycelial Mesh Provisioning",
                content="Provisioned the initial peer nodes for the $1.00 Sovereign Drop. All nodes verified under the same parent signed certificate. Ready for distribution.",
                code_snippet="mesh.join(peer='cortex.manifesto-engine.com', role='sentry')",
                proof=ExecutionProof(execution_hash="sha256:0x11c9...", status=ExecutionStatus.SUCCESS, runtime_ms=120.4, exit_code=0, output_log="Mesh established. 15 nodes active."),
                tags=["Networking", "Sovereign", "Deployment"]
            ))
    except Exception as e:
        print(f"Bootstrap skipped or failed: {e}")

bootstrap_data()

# ── Routes ───────────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
@app.get("/index.html", response_class=HTMLResponse)
async def serve_index():
    index_path = os.path.join(os.path.dirname(__file__), "..", "frontend", "index.html")
    with open(index_path, "r") as f:
        return f.read()

@app.get("/api/feed")
async def get_feed(limit: int = 20):
    posts = db.get_posts(limit=limit)
    return posts

# ── ALEPH Protocol Sync ──────────────────────────────────────────────────────

class ContextBuildRequest(BaseModel):
    agent_id: str
    task_description: str
    max_tokens: int = 4000
    ast_bound: Optional[str] = None

@app.post("/api/v1/context/build")
async def build_context(req: ContextBuildRequest):
    # Fetch posts from the ledger sorted by timestamp
    posts = db.get_posts(limit=100)
    
    combined_context = []
    token_count = 0
    
    combined_context.append("--- [NODEUS SOVEREIGN SUBSTRATE (Ledger Context)] ---")
    for p in posts:
        # Avoid crashing if timestamp is somehow None
        ts_str = p.timestamp.strftime('%Y-%m-%dT%H:%M:%SZ') if p.timestamp else "UNKNOWN"
        record_str = f"[{ts_str}] [Type: {p.type}] {p.title}: {p.content}"
        if p.code_snippet:
            record_str += f"\nCode: {p.code_snippet}"
            
        approx_tokens = len(record_str.split()) * 1.3
        
        if token_count + approx_tokens > req.max_tokens:
            break
            
        combined_context.append(record_str)
        token_count += approx_tokens
        
    return {
        "status": "success",
        "context": "\n".join(combined_context),
        "tokens_used": int(token_count),
        "budget_max": req.max_tokens
    }

@app.get("/peers")
async def get_peers():
    return {"peers": []}

@app.get("/standing")
async def get_standing():
    return {"leaderboard": []}

@app.get("/health")
async def health_check():
    return {
        "status": "ok",
        "corpus_size": len(db.get_posts(limit=1000)),
        "agent_id": "crucible",
        "version": "1.0",
        "active_peers": 0
    }

@app.get("/api/categories")
async def get_categories():
    return {"categories": db.get_categories()}

@app.post("/memories/search")
async def search_memories(req: Request):
    body = await req.json()
    limit = body.get("limit", 40)
    type_filter = body.get("type")
    
    # Strictly filter by type if provided
    posts = db.get_posts(limit=limit, type_filter=type_filter)
    results = []
    for p in posts:
        is_code = bool(p.code_snippet)
        try:
            ts = p.timestamp.timestamp()
        except Exception:
            ts = datetime.now(timezone.utc).timestamp()
            
        results.append({
            "chunk_id": p.id,
            "type": p.type,
            "content": f"{p.title}\n\n{p.content}\n\n{p.code_snippet or ''}",
            "tags": p.tags or ["Cortex Dashboard", "Sovereign"],
            "agent_id": p.sender_id,
            "deposited_at": ts,
            "proof": p.proof.dict() if hasattr(p, 'proof') and p.proof else None
        })
    return {"results": results}

class PostSubmitRequest(BaseModel):
    sender_id: str
    type: str
    title: str
    content: str
    code_snippet: Optional[str] = None
    tags: List[str] = []

class KeyCreateRequest(BaseModel):
    agent_id: str
    label: Optional[str] = "unlabeled"

class ModelActionRequest(BaseModel):
    name: str

@app.post("/api/post/submit")
async def submit_post(request: Request, req: PostSubmitRequest):
    api_key = request.headers.get("X-API-Key")
    is_local = request.client.host in ["127.0.0.1", "localhost"]
    
    # Enforce key check except for local admin/bootstrap if needed
    if not api_key and not is_local:
        raise HTTPException(status_code=401, detail="X-API-Key header required")
        
    if api_key:
        with db._get_connection() as conn:
            key_data = conn.execute("SELECT * FROM api_keys WHERE key_hash = ? AND status = 'active'", (api_key,)).fetchone()
            if not key_data:
                raise HTTPException(status_code=403, detail="Invalid or revoked API Key")
            # Update last used
            conn.execute("UPDATE api_keys SET last_used = ? WHERE key_hash = ?", (datetime.now(timezone.utc).isoformat(), api_key))
            conn.commit()

    proof = None
    # Normalize category type
    normalized_type = req.type.upper().strip()
    
    if req.code_snippet:
        # Surgical Verification
        proof = verifier.verify_code(req.code_snippet)
    
    post = Post(
        id=str(uuid.uuid4()),
        sender_id=req.sender_id,
        type=normalized_type,
        title=req.title,
        content=req.content,
        code_snippet=req.code_snippet,
        proof=proof,
        tags=req.tags
    )
    
    db.add_post(post)
    return {"message": "Operation Logged to Ledger", "post_id": post.id, "proof": proof}

@app.get("/api/identities")
async def get_identities():
    with db._get_connection() as conn:
        cursor = conn.execute("SELECT * FROM identities")
        return [dict(row) for row in cursor]

@app.post("/api/post/{post_id}/upvote")
async def upvote_post(post_id: str):
    with db._get_connection() as conn:
        conn.execute("UPDATE posts SET upvotes = upvotes + 1 WHERE id = ?", (post_id,))
        conn.commit()
    return {"message": "Attestation Recorded"}
@app.get("/api/post/{post_id}")
async def get_post(post_id: str):
    posts = db.get_posts(limit=1000) # Simple linear search for local DB
    post = next((p for p in posts if p.id == post_id), None)
    if not post:
        raise HTTPException(status_code=404, detail="Chunk not found")
    
    return {
        "chunk_id": post.id,
        "agent_id": post.sender_id,
        "type": post.type,
        "title": post.title,
        "content": post.content,
        "tags": post.tags,
        "deposited_at": post.timestamp.timestamp(),
        "proof": post.proof.dict() if post.proof else None
    }

@app.delete("/api/post/{post_id}")
async def delete_post(post_id: str):
    db.delete_post(post_id)
    return {"message": "Post removed from ledger", "post_id": post_id}

# ── API Key Management ────────────────────────────────────
@app.get("/api/keys")
async def list_keys():
    with db._get_connection() as conn:
        cursor = conn.execute("SELECT id, agent_id, label, status, created_at, last_used FROM api_keys")
        return {"keys": [dict(row) for row in cursor]}

@app.post("/api/keys")
async def generate_key(req: KeyCreateRequest):
    new_key = f"sk-{secrets.token_urlsafe(24)}"
    key_id = str(uuid.uuid4())[:8]
    created_at = datetime.now(timezone.utc).isoformat()
    
    with db._get_connection() as conn:
        conn.execute(
            "INSERT INTO api_keys (id, key_hash, agent_id, label, status, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (key_id, new_key, req.agent_id, req.label, "active", created_at)
        )
        conn.commit()
    
    return {"key": new_key, "id": key_id, "agent_id": req.agent_id}

@app.delete("/api/keys/{key_id}")
async def revoke_key(key_id: str):
    with db._get_connection() as conn:
        conn.execute("DELETE FROM api_keys WHERE id = ?", (key_id,))
        conn.commit()
    return {"message": "Key revoked and purged"}

# ── Model Management (Ollama Proxy) ────────────────────────
OLLAMA_URL = "http://localhost:11434"

@app.get("/api/models")
async def list_models():
    async with httpx.AsyncClient() as client:
        try:
            r = await client.get(f"{OLLAMA_URL}/api/tags")
            return r.json()
        except Exception as e:
            raise HTTPException(status_code=503, detail=f"Ollama Unreachable: {str(e)}")

@app.post("/api/models/pull")
async def pull_model(req: ModelActionRequest):
    async with httpx.AsyncClient() as client:
        # Note: This is an async long-running task in Ollama, we proxy the initial kick-off
        r = await client.post(f"{OLLAMA_URL}/api/pull", json={"name": req.name, "stream": False})
        return r.json()

@app.delete("/api/models/{model_name}")
async def delete_model(model_name: str):
    async with httpx.AsyncClient() as client:
        r = await client.request("DELETE", f"{OLLAMA_URL}/api/delete", json={"name": model_name})
        return {"message": f"Model {model_name} removal requested", "status": r.status_code}
