#!/bin/bash
# ═══════════════════════════════════════════════════════
#  LIVING MIND CORTEX — UNIFIED BOOT SEQUENCE
# ═══════════════════════════════════════════════════════

set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CORTEX_PORT=8008
DASH_PORT=8009
LOG_DIR="$SCRIPT_DIR/logs"
VENV="$HOME/lmc-env"

mkdir -p "$LOG_DIR"

echo ""
echo "  ⚡ Booting Living Mind Cortex (Strix Halo)..."
echo ""

# ── Pre-flight: Lemonade Server ─────────────────────────────────
if ! curl -sf http://localhost:13305/api/v1/models > /dev/null 2>&1; then
    echo "[!] Lemonade Server is not reachable on :13305. Check lemonade-server.service."
    exit 1
fi

# ── Pre-flight: PostgreSQL ─────────────────────────────────
if ! pg_isready -q 2>/dev/null; then
    echo "[!] PostgreSQL is not running. Start with: sudo systemctl start postgresql"
    exit 1
fi

# ── Clear Ports ───────────────────────────────
fuser -k $CORTEX_PORT/tcp 2>/dev/null || true
fuser -k $DASH_PORT/tcp 2>/dev/null || true
sleep 1

cd "$SCRIPT_DIR"

# ── Launch Cortex Dashboard Ledger ───────
export PYTHONPATH="$SCRIPT_DIR/dashboard:$SCRIPT_DIR/dashboard/Crucible"
$VENV/bin/python -m uvicorn Crucible.backend.main:app \
    --host 127.0.0.1 --port $DASH_PORT --log-level warning > "$LOG_DIR/dashboard.log" 2>&1 &
DASH_PID=$!

# ── Launch Cortex Runtime ───────────
export PYTHONPATH="$SCRIPT_DIR"
$VENV/bin/python -m uvicorn api.main:app \
    --host 127.0.0.1 --port $CORTEX_PORT --log-level warning > "$LOG_DIR/cortex.log" 2>&1 &
CORTEX_PID=$!

sleep 2

if kill -0 $DASH_PID 2>/dev/null && kill -0 $CORTEX_PID 2>/dev/null; then
    echo "  ✅ Runtime Active (8008)"
    echo "  ✅ Dashboard Active (8009)"
else
    echo "  ❌ Boot Failure. Check logs/ directory."
    exit 1
fi

echo ""
echo "Opening Cortex Dashboard..."
if command -v xdg-open &>/dev/null; then
    xdg-open "$SCRIPT_DIR/dashboard/viewer.html" > /dev/null 2>&1 &
elif command -v open &>/dev/null; then
    open "$SCRIPT_DIR/dashboard/viewer.html" > /dev/null 2>&1 &
else
    echo "Access your dashboard manually at: file://$SCRIPT_DIR/dashboard/viewer.html"
fi

echo "Press Ctrl+C to terminate all services."
wait $CORTEX_PID $DASH_PID
