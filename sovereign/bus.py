"""
sovereign/bus.py — Agent Bus
Sovereign Agents v1.0

P2P point-to-point agent communication layer.

Transport design (locked):
  - Signaling:  HTTP   — bus.connect() POSTs SDP offer to {peer_url}/htp/offer
  - Data:       WebRTC — HolographicTransferProtocol handles the channel after handshake
  - Persistence: PostgreSQL bus_peers table (local, not shared across machines)

Reconnect policy (locked):
  connect() always attempts the HTTP handshake — idempotent by upsert.
  No special reconnect path; a stale active row is overwritten on success.

heartbeat() wires into SovereignHeartbeat.tick() — one clock, not two.
bus.py itself does NOT spawn background tasks.

v1 scope: point-to-point only.
v2: add broker column + mesh topology on top of the existing bus_peers table.

Authentication: v2 concern. See FIXME below.
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import TYPE_CHECKING

try:
    import httpx
    _HTTPX = True
except ImportError:
    _HTTPX = False

if TYPE_CHECKING:
    import asyncpg
    from cortex.htp import HolographicTransferProtocol

log = logging.getLogger("AgentBus")

# FIXME(v2): All bus connections are currently unauthenticated.
# A peer that knows the /htp/offer URL can connect freely.
# v2 should add a pre-shared token or mTLS before this is exposed
# on any non-localhost network interface.

PING_TIMEOUT_SECONDS = 5.0
CONNECT_TIMEOUT_SECONDS = 8.0
HEARTBEAT_INTERVAL_SECONDS = 60  # Matches SovereignHeartbeat tick rate

# bus_peers schema — applied by install.sh / schema migration
BUS_PEERS_DDL = """
CREATE TABLE IF NOT EXISTS bus_peers (
    id          SERIAL PRIMARY KEY,
    name        TEXT NOT NULL DEFAULT '',
    url         TEXT NOT NULL UNIQUE,
    last_seen   TIMESTAMPTZ DEFAULT now(),
    status      TEXT DEFAULT 'active'
        CHECK (status IN ('active', 'unreachable', 'evicted'))
);
"""


class AgentBus:
    """
    Local-first agent communication bus.

    Injected dependencies (do not instantiate inside this class):
      db_pool  — shared asyncpg pool from the FastAPI lifespan
      local_url — this node's public /htp/offer URL (stored in bus_peers
                  so remote nodes can call back)
      htp      — existing HolographicTransferProtocol instance from api/main.py

    Usage (from api/main.py lifespan)::

        bus = AgentBus(
            db_pool=cortex._pool,
            local_url="http://my-node:8008",
            htp=htp_listener,
        )
        await bus.ensure_schema()
        # Then pass bus into SovereignHeartbeat.tick() for periodic heartbeat.
    """

    def __init__(
        self,
        db_pool: "asyncpg.Pool",
        local_url: str,
        htp: "HolographicTransferProtocol",
    ) -> None:
        self._pool     = db_pool
        self._local    = local_url.rstrip("/")
        self._htp      = htp
        self._client: httpx.AsyncClient | None = None

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    async def ensure_schema(self) -> None:
        """Apply bus_peers DDL if the table doesn't already exist."""
        async with self._pool.acquire() as conn:
            await conn.execute(BUS_PEERS_DDL)
        log.info("[Bus] bus_peers schema ready.")

    def _http(self) -> httpx.AsyncClient:
        """Lazily create a shared httpx client (reused across calls)."""
        if not _HTTPX:
            raise RuntimeError("httpx is required for AgentBus. pip install httpx")
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(timeout=CONNECT_TIMEOUT_SECONDS)
        return self._client

    async def close(self) -> None:
        """Clean up the HTTP client on shutdown."""
        if self._client and not self._client.is_closed:
            await self._client.aclose()

    # ── Public API ────────────────────────────────────────────────────────────

    async def connect(self, peer_url: str, peer_name: str = "") -> bool:
        """
        Initiate a P2P connection to a remote Cortex node.

        Always attempts the HTTP handshake — idempotent by upsert.
        A stale 'active' row is overwritten on success; a failed row
        is marked 'unreachable' without raising.

        Returns True if the WebRTC channel is established.
        """
        peer_url = peer_url.rstrip("/")
        log.info("[Bus] Connecting to peer: %s", peer_url)

        try:
            # Step 1: Generate SDP offer from the local HTP peer connection
            offer = await self._htp.pc.createOffer()
            await self._htp.pc.setLocalDescription(offer)

            # Step 2: POST SDP offer to the remote node's /htp/offer endpoint
            payload = {
                "sdp":       offer.sdp,
                "type":      offer.type,
                "origin":    self._local,   # so the remote knows who to call back
            }
            resp = await self._http().post(
                f"{peer_url}/htp/offer",
                json=payload,
                timeout=CONNECT_TIMEOUT_SECONDS,
            )
            resp.raise_for_status()
            answer_data = resp.json()

            # Step 3: Apply SDP answer from the remote node
            from aiortc import RTCSessionDescription
            answer = RTCSessionDescription(
                sdp=answer_data["sdp"],
                type=answer_data["type"],
            )
            await self._htp.pc.setRemoteDescription(answer)
            await self._htp.setup_channel(is_offerer=True)

            # Step 4: Upsert peer as active
            await self._upsert_peer(peer_url, peer_name or peer_url, "active")
            log.info("[Bus] ✓ Connected to %s", peer_url)
            return True

        except Exception as exc:
            log.warning("[Bus] Connect to '%s' failed: %s", peer_url, exc)
            await self._upsert_peer(peer_url, peer_name or peer_url, "unreachable")
            return False

    async def disconnect(self, peer_url: str) -> None:
        """Mark a peer as evicted and close the HTP channel."""
        peer_url = peer_url.rstrip("/")
        await self._set_status(peer_url, "evicted")
        # Close the WebRTC channel if this peer owns it
        if self._htp.channel and self._htp.channel.readyState == "open":
            self._htp.channel.close()
        log.info("[Bus] Disconnected from %s", peer_url)

    async def broadcast(self, domain: str, payload: dict) -> None:
        """
        Send a memory event to all active peers concurrently.
        On send failure: mark peer unreachable, do not raise.
        """
        active = await self._active_peers()
        if not active:
            return

        message = json.dumps({"domain": domain, **payload}).encode()

        async def _send(peer: dict) -> None:
            try:
                if self._htp.channel and self._htp.channel.readyState == "open":
                    self._htp.channel.send(message)
                else:
                    log.warning("[Bus] Channel not open — marking %s unreachable.", peer["url"])
                    await self._set_status(peer["url"], "unreachable")
            except Exception as exc:
                log.warning("[Bus] Broadcast to '%s' failed: %s", peer["url"], exc)
                await self._set_status(peer["url"], "unreachable")

        await asyncio.gather(*[_send(p) for p in active], return_exceptions=True)

    async def sync_memory(self, peer_url: str, memory_ids: list[str]) -> int:
        """
        Request specific memories from a peer and inject them locally.
        Skips nodes that already exist locally (checked by entanglement hash).
        Returns number of nodes successfully injected.
        """
        peer_url = peer_url.rstrip("/")
        try:
            resp = await self._http().post(
                f"{peer_url}/htp/memory/sync",
                json={"memory_ids": memory_ids, "origin": self._local},
                timeout=CONNECT_TIMEOUT_SECONDS,
            )
            resp.raise_for_status()
            nodes = resp.json().get("nodes", [])
        except Exception as exc:
            log.warning("[Bus] sync_memory from '%s' failed: %s", peer_url, exc)
            return 0

        injected = 0
        for node in nodes:
            # Skip if already exists — check by entanglement hash
            eid = node.get("entanglement_id")
            if eid and await self._node_exists(eid):
                continue
            try:
                await self._htp.cortex.remember(
                    content=node["content"],
                    type=node.get("type", "semantic"),
                    importance=node.get("importance", 0.5),
                    tags=node.get("tags", []),
                    emotion=node.get("emotion", "neutral"),
                    source="htp_sync",
                    context=f"Synced from {peer_url}",
                )
                injected += 1
            except Exception as exc:
                log.warning("[Bus] Failed to inject node %s: %s", eid, exc)

        log.info("[Bus] sync_memory: injected %d/%d nodes from %s", injected, len(nodes), peer_url)
        return injected

    async def heartbeat(self) -> None:
        """
        Ping all active peers. Mark unreachable if no response within timeout.
        Attempt a single reconnect on unreachable peers — not a retry loop.

        Called by SovereignHeartbeat.tick() — does NOT spawn its own task.
        """
        active = await self._active_peers()
        unreachable = await self._unreachable_peers()

        # Ping active peers
        for peer in active:
            alive = await self._ping(peer["url"])
            if not alive:
                log.warning("[Bus] Peer %s went unreachable.", peer["url"])
                await self._set_status(peer["url"], "unreachable")

        # Single reconnect attempt on unreachable peers
        for peer in unreachable:
            log.info("[Bus] Attempting reconnect to %s", peer["url"])
            success = await self.connect(peer["url"], peer.get("name", ""))
            if not success:
                log.warning("[Bus] Reconnect failed for %s — stays unreachable.", peer["url"])

    async def peers(self) -> list[dict]:
        """
        Return all rows from bus_peers.
        Used by GET /bus/peers endpoint.
        """
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT id, name, url, last_seen, status FROM bus_peers ORDER BY last_seen DESC"
            )
        return [dict(r) for r in rows]

    # ── Internal ──────────────────────────────────────────────────────────────

    async def _upsert_peer(self, url: str, name: str, status: str) -> None:
        """Insert or update a peer row — idempotent on url uniqueness."""
        async with self._pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO bus_peers (url, name, last_seen, status)
                VALUES ($1, $2, now(), $3)
                ON CONFLICT (url) DO UPDATE
                    SET name      = EXCLUDED.name,
                        last_seen = now(),
                        status    = EXCLUDED.status
                """,
                url, name, status,
            )

    async def _set_status(self, url: str, status: str) -> None:
        async with self._pool.acquire() as conn:
            await conn.execute(
                "UPDATE bus_peers SET status = $1, last_seen = now() WHERE url = $2",
                status, url,
            )

    async def _active_peers(self) -> list[dict]:
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT id, name, url FROM bus_peers WHERE status = 'active'"
            )
        return [dict(r) for r in rows]

    async def _unreachable_peers(self) -> list[dict]:
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT id, name, url FROM bus_peers WHERE status = 'unreachable'"
            )
        return [dict(r) for r in rows]

    async def _ping(self, url: str) -> bool:
        """GET {url}/status — returns True if the node responds in time."""
        try:
            resp = await self._http().get(
                f"{url}/status",
                timeout=PING_TIMEOUT_SECONDS,
            )
            return resp.status_code == 200
        except Exception:
            return False

    async def _node_exists(self, entanglement_id: str) -> bool:
        """Check if a memory node with this entanglement ID already exists locally."""
        async with self._pool.acquire() as conn:
            row = await conn.fetchval(
                "SELECT 1 FROM memories WHERE metadata->>'entanglement_id' = $1 LIMIT 1",
                entanglement_id,
            )
        return row is not None
