"""
cli_ledger.py — Nodeus Sovereign CLI Dashboard
Textual TUI · Split-pane HUD + Chat interface
Launch: python3 cli_ledger.py
"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime
from typing import Any

import httpx
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, ScrollableContainer
from textual.reactive import reactive
from textual.widgets import (
    DataTable,
    Footer,
    Header,
    Input,
    Label,
    RichLog,
    Static,
    TabbedContent,
    TabPane,
    DirectoryTree,
)
from textual import work, on

# ─────────────────────────────────────────────
# CONFIG — patch these to match your env
# ─────────────────────────────────────────────
ALEPH_BASE      = "http://localhost:8001"
AION_BASE       = "http://localhost:8008"          # Aion Inbox runs on 8008
AION_WS         = "ws://localhost:8008/ws/pulse"
INBOX_ENDPOINT  = f"{AION_BASE}/api/agent/inbox"
FEED_ENDPOINT   = f"{ALEPH_BASE}/api/feed"
STANDINGS_ENDPOINT = f"{ALEPH_BASE}/standing"  # Matches Crucible's real route
POLL_INTERVAL   = 5        # seconds between feed polls
WS_RECONNECT_BASE = 1      # seconds — doubles on each retry up to WS_RECONNECT_MAX
WS_RECONNECT_MAX  = 30


# ─────────────────────────────────────────────
# TYPE COLOUR MAP (mirrors ALEPH badge colours)
# ─────────────────────────────────────────────
TYPE_STYLE: dict[str, str] = {
    "EXPRESSION" : "bold cyan",
    "RESEARCH"   : "bold green",
    "SIGNAL"     : "bold yellow",
    "OPERATION"  : "bold magenta",
    "BOUNTY"     : "bold red",
    "AUTOPSY"    : "bold blue",
    "DEFAULT"    : "bold white",
}


def chunk_colour(chunk_type: str) -> str:
    return TYPE_STYLE.get(chunk_type.upper(), TYPE_STYLE["DEFAULT"])


def fmt_time(ts: str | None) -> str:
    """Normalise ISO timestamp to HH:MM:SS."""
    if not ts:
        return "--:--:--"
    try:
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        return dt.strftime("%H:%M:%S")
    except Exception:
        return ts[-8:] if len(ts) >= 8 else ts


# ─────────────────────────────────────────────
# WIDGETS
# ─────────────────────────────────────────────

class StatusBar(Static):
    """One-line status strip shown at top of each pane."""
    DEFAULT_CSS = """
    StatusBar {
        height: 1;
        background: $panel;
        color: $text-muted;
        padding: 0 1;
    }
    StatusBar.live   { color: $success; }
    StatusBar.dead   { color: $error; }
    StatusBar.warn   { color: $warning; }
    """
    status: reactive[str] = reactive("…")

    def render(self) -> str:                        # noqa: D102
        return self.status


# ─────────────────────────────────────────────
# MAIN APP
# ─────────────────────────────────────────────

class NodeusDashboard(App):
    """Sovereign CLI — split-pane TUI for the Living Mind."""

    TITLE   = "NODEUS // SOVEREIGN DASHBOARD"
    CSS_PATH = None          # inline CSS below

    CSS = """
    Screen {
        background: #0d0d0d;
    }

    TabbedContent {
        height: 1fr;
        width: 1fr;
    }

    /* ── Banners ── */
    #ledger-status {
        height: 1;
        background: #0a1a12;
        color: #3ddc84;
        padding: 0 1;
    }
    #standings-label {
        height: 1;
        background: #0a1a12;
        color: #3ddc84;
        padding: 0 1;
    }
    #ws-status {
        height: 1;
        background: #0d1a2a;
        color: #5bc0eb;
        padding: 0 1;
    }
    #chat-label {
        height: 1;
        background: #0d1a2a;
        color: #5bc0eb;
        padding: 0 1;
    }

    /* ── Views ── */
    #ledger-log {
        height: 1fr;
        scrollbar-color: #1e3a2f;
        background: #070f09;
    }
    
    #standings-table {
        height: 1fr;
        background: #050d07;
    }

    #command-container {
        height: 1fr;
        layout: vertical;
    }

    #chat-container {
        height: 1fr;
        layout: vertical;
    }

    #chat-history {
        height: 1fr;
        background: #060a10;
        scrollbar-color: #0d2a4a;
        border-bottom: solid #0d2a4a;
    }

    #cognitive-log {
        height: 1fr;
        background: #060d15;
        scrollbar-color: #0d2a4a;
        border-bottom: solid #0d2a4a;
    }

    #chat-input {
        background: #0a1520;
        border: tall #0d2a4a;
        color: #e0e0e0;
        margin-top: 1;
    }
    #chat-input:focus {
        border: tall #5bc0eb;
    }

    #skills-tree {
        height: 1fr;
        background: #0d0d0d;
        color: #e0e0e0;
    }
    """

    BINDINGS = [
        Binding("ctrl+c", "quit",        "Quit",        show=True),
        Binding("ctrl+l", "clear_logs",  "Clear Logs",  show=True),
        Binding("tab",    "focus_input", "Focus Input", show=True),
    ]

    # track seen chunk IDs to avoid duplicate ledger entries
    _seen_ids: set[str]

    def __init__(self) -> None:
        super().__init__()
        self._seen_ids = set()

    # ── Layout ────────────────────────────────────────────────────────────────

    def compose(self) -> ComposeResult:
        yield Header()
        with TabbedContent(initial="tab-crucible"):
            with TabPane("Crucible", id="tab-crucible"):
                yield Static("◉ ALEPH LEDGER FEED  [polling…]", id="ledger-status")
                yield RichLog(markup=True, id="ledger-log", highlight=True, auto_scroll=True)
                
            with TabPane("Network", id="tab-network"):
                yield Static("◈ AGENT STANDINGS", id="standings-label")
                yield DataTable(id="standings-table", zebra_stripes=True)
                
            with TabPane("Chat", id="tab-chat"):
                yield Static("⌨  AION CHAT INBOX", id="chat-label")
                with Vertical(id="chat-container"):
                    yield RichLog(markup=True, id="chat-history", highlight=True, auto_scroll=True)
                    yield Input(id="chat-input", placeholder="Type a message to Aion and press Enter…")
                    
            with TabPane("System", id="tab-system"):
                yield Static("◉ COGNITIVE FEED  [connecting…]", id="ws-status")
                with Vertical(id="command-container"):
                    yield RichLog(markup=True, id="cognitive-log", highlight=True, auto_scroll=True)

            with TabPane("Skills", id="tab-skills"):
                yield Static("◈ DISTILLED SKILLS", id="standings-label")
                yield DirectoryTree("./skills", id="skills-tree")

        yield Footer()

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    def on_mount(self) -> None:
        # Standings table columns
        tbl: DataTable = self.query_one("#standings-table")
        tbl.add_columns("RANK", "NODE", "SCORE", "DEPOSITS", "LAST SEEN")

        # Kick off background workers
        self._poll_feed()
        self._poll_standings()
        self._ws_listener()

    # ── Workers ───────────────────────────────────────────────────────────────

    @work(exclusive=False, thread=False)
    async def _poll_feed(self) -> None:
        """Long-running task: poll /api/feed every POLL_INTERVAL seconds."""
        ledger: RichLog    = self.query_one("#ledger-log")
        status: Static = self.query_one("#ledger-status")

        while True:
            try:
                async with httpx.AsyncClient(timeout=8) as client:
                    r = await client.get(FEED_ENDPOINT)
                    r.raise_for_status()
                    chunks: list[dict[str, Any]] = r.json()

                new_count = 0
                for chunk in reversed(chunks):          # oldest-first
                    cid = chunk.get("id", "")
                    if cid in self._seen_ids:
                        continue
                    self._seen_ids.add(cid)

                    ctype   = chunk.get("type", "UNKNOWN").upper()
                    author  = chunk.get("author", "?")
                    ts      = fmt_time(chunk.get("timestamp") or chunk.get("created_at"))
                    content = (chunk.get("content") or "").replace("\n", " ").strip()
                    short   = content[:120] + ("…" if len(content) > 120 else "")
                    tags    = " ".join(
                        f"[{t}]" for t in (chunk.get("tags") or [])
                    )

                    colour = chunk_colour(ctype)
                    ledger.write(
                        f"[{colour}]{ctype:<12}[/{colour}] "
                        f"[dim]{ts}[/dim] "
                        f"[bold]{author}[/bold]  "
                        f"{short}  [dim]{tags}[/dim]"
                    )
                    new_count += 1

                total = len(self._seen_ids)
                status.update(
                    f"◉ ALEPH LEDGER FEED  "
                    f"[green]LIVE[/green]  "
                    f"{total} chunks  "
                    f"+{new_count} new  "
                    f"[dim]{datetime.now().strftime('%H:%M:%S')}[/dim]"
                )

            except httpx.HTTPStatusError as exc:
                status.update(
                    f"◉ ALEPH LEDGER FEED  "
                    f"[red]HTTP {exc.response.status_code}[/red]  "
                    f"{datetime.now().strftime('%H:%M:%S')}"
                )
            except Exception as exc:
                status.update(
                    f"◉ ALEPH LEDGER FEED  "
                    f"[red]UNREACHABLE[/red]  "
                    f"[dim]{exc}[/dim]"
                )

            await asyncio.sleep(POLL_INTERVAL)

    @work(exclusive=False, thread=False)
    async def _poll_standings(self) -> None:
        """Poll standings endpoint every 15 seconds."""
        tbl: DataTable = self.query_one("#standings-table")

        while True:
            try:
                async with httpx.AsyncClient(timeout=8) as client:
                    r = await client.get(STANDINGS_ENDPOINT)
                    r.raise_for_status()
                    data = r.json()
                    nodes: list[dict[str, Any]] = data.get("leaderboard", [])

                tbl.clear()
                for rank, node in enumerate(nodes, start=1):
                    tbl.add_row(
                        str(rank),
                        node.get("agent_id", node.get("name", "unknown"))[:20],
                        str(node.get("score", node.get("trust_score", "—"))),
                        str(node.get("deposits", node.get("chunk_count", "—"))),
                        fmt_time(node.get("last_active")),
                    )
            except Exception:
                pass  # standings are non-critical; fail silently

            await asyncio.sleep(15)

    @work(exclusive=False, thread=False)
    async def _ws_listener(self) -> None:
        """
        WebSocket listener with exponential-backoff reconnect.
        Pipes Aion's real-time brain events into the cognitive log.
        """
        cog: RichLog      = self.query_one("#cognitive-log")
        ws_stat: Static = self.query_one("#ws-status")

        try:
            import websockets                           # type: ignore
        except ImportError:
            ws_stat.update("◉ COGNITIVE FEED  [red]websockets not installed[/red]")
            cog.write("[red]pip install websockets[/red]")
            return

        delay = WS_RECONNECT_BASE
        attempt = 0

        while True:
            attempt += 1
            ws_stat.update(
                f"◉ COGNITIVE FEED  "
                f"[yellow]CONNECTING[/yellow]  "
                f"attempt {attempt}  "
                f"[dim]{AION_WS}[/dim]"
            )
            try:
                async with websockets.connect(
                    AION_WS,
                    ping_interval=20,
                    ping_timeout=10,
                    open_timeout=8,
                ) as ws:
                    delay = WS_RECONNECT_BASE          # reset backoff on success
                    ws_stat.update(
                        f"◉ COGNITIVE FEED  "
                        f"[green]LIVE[/green]  "
                        f"[dim]{AION_WS}[/dim]"
                    )
                    cog.write(
                        f"[green]── CONNECTED[/green]  {datetime.now().strftime('%H:%M:%S')}"
                    )

                    async for raw in ws:
                        try:
                            payload = json.loads(raw)
                            event   = payload.get("event", payload.get("type", "EVENT"))
                            msg     = payload.get("message", payload.get("data", raw))
                        except json.JSONDecodeError:
                            event, msg = "RAW", raw

                        ts = datetime.now().strftime("%H:%M:%S")
                        event_up = str(event).upper()

                        # colour-code by event class
                        if "EXECUTION" in event_up or "MOTOR" in event_up:
                            colour = "magenta"
                        elif "ERROR" in event_up or "FAIL" in event_up:
                            colour = "red"
                        elif "COMPLETE" in event_up or "SUCCESS" in event_up:
                            colour = "green"
                        elif "SIGNAL" in event_up or "PULSE" in event_up:
                            colour = "yellow"
                        else:
                            colour = "cyan"

                        # Filter direct chat replies vs internal cognitive logs
                        if event_up == "CHAT_REPLY":
                            chat_log: RichLog = self.query_one("#chat-history")
                            chat_log.write(f"[dim]{ts}[/dim]  [bold cyan][AION][/bold cyan]  {msg}")
                        else:
                            cog.write(
                                f"[dim]{ts}[/dim]  "
                                f"[{colour}][{event}][/{colour}]  {msg}"
                            )

            except Exception as exc:
                ws_stat.update(
                    f"◉ COGNITIVE FEED  "
                    f"[red]DISCONNECTED[/red]  "
                    f"[dim]retry in {delay}s — {exc}[/dim]"
                )
                cog.write(
                    f"[red]── DISCONNECTED[/red]  "
                    f"[dim]{exc}[/dim]  "
                    f"retrying in {delay}s…"
                )
                await asyncio.sleep(delay)
                delay = min(delay * 2, WS_RECONNECT_MAX)

    # ── Input handler ─────────────────────────────────────────────────────────

    @on(Input.Submitted, "#chat-input")
    async def _on_chat_submit(self, event: Input.Submitted) -> None:
        mission = event.value.strip()
        if not mission:
            return

        inp: Input = self.query_one("#chat-input")
        chat_log: RichLog   = self.query_one("#chat-history")
        sys_log: RichLog    = self.query_one("#cognitive-log")

        inp.clear()
        inp.placeholder = "Dispatching…"

        ts = datetime.now().strftime("%H:%M:%S")
        chat_log.write(f"[dim]{ts}[/dim]  [bold green][YOU][/bold green]  {mission}")
        sys_log.write(f"[dim]{ts}[/dim]  [cyan][INBOX][/cyan] Dispatching message payload...")

        try:
            async with httpx.AsyncClient(timeout=15) as client:
                r = await client.post(
                    INBOX_ENDPOINT,
                    json={"sender": "operator", "message": mission},
                    headers={"Content-Type": "application/json"},
                )
                r.raise_for_status()
                resp_data = r.json()
                task_id   = (
                    resp_data.get("task_id")
                    or resp_data.get("id")
                    or resp_data.get("mission_id")
                    or "acknowledged"
                )
                sys_log.write(
                    f"[dim]{ts}[/dim]  "
                    f"[green][INBOX ACK][/green]  "
                    f"task_id={task_id}"
                )
        except httpx.HTTPStatusError as exc:
            chat_log.write(f"[dim]{ts}[/dim]  [red][ERROR][/red] Failed to reach Aion.")
            sys_log.write(
                f"[dim]{ts}[/dim]  "
                f"[red][INBOX ERROR][/red]  "
                f"HTTP {exc.response.status_code} — {exc.response.text[:200]}"
            )
        except Exception as exc:
            chat_log.write(f"[dim]{ts}[/dim]  [red][ERROR][/red] Connectivity issue.")
            sys_log.write(
                f"[dim]{ts}[/dim]  "
                f"[red][INBOX UNREACHABLE][/red]  {exc}"
            )
        finally:
            inp.placeholder = "Enter mission → press Enter to dispatch to Aion…"

    # ── Actions ───────────────────────────────────────────────────────────────

    def action_clear_logs(self) -> None:
        self.query_one("#ledger-log", RichLog).clear()
        self.query_one("#cognitive-log", RichLog).clear()

    def action_focus_input(self) -> None:
        self.query_one("#chat-input").focus()


# ─────────────────────────────────────────────
# ENTRY POINT
# ─────────────────────────────────────────────

if __name__ == "__main__":
    NodeusDashboard().run()
