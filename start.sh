#!/usr/bin/env bash
# Agentforge dev server launcher
# Usage: ./start.sh
# Stop: Ctrl+C (stops both backend and frontend)
#
# ┌──────────────┬────────────────────────────────────────────────────────┐
# │  Process     │  Virtualenv / runtime                                  │
# ├──────────────┼────────────────────────────────────────────────────────┤
# │  server      │  Python 3.12 venv                                      │
# │              │  Path: <repo>/server/.venv                             │
# │              │  Run:  server/.venv/bin/uvicorn  main:app              │
# │              │  pip:  server/.venv/bin/pip                            │
# ├──────────────┼────────────────────────────────────────────────────────┤
# │  frontend    │  System Node.js (no separate venv)                     │
# │              │  Packages: <repo>/ui/node_modules  (npm run dev)       │
# └──────────────┴────────────────────────────────────────────────────────┘

set -e

ROOT="$(cd "$(dirname "$0")" && pwd)"
BACKEND="$ROOT/server"
UI="$ROOT/ui"

# ─── Colors ───────────────────────────────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
BOLD='\033[1m'
RESET='\033[0m'

log()  { echo -e "${CYAN}[agentforge]${RESET} $*"; }
ok()   { echo -e "${GREEN}[✓]${RESET} $*"; }
warn() { echo -e "${YELLOW}[!]${RESET} $*"; }
err()  { echo -e "${RED}[✗]${RESET} $*"; }

# ─── cleanup: stop both processes on Ctrl+C ──────────────────────────────────
BACKEND_PID=""
UI_PID=""

cleanup() {
  echo ""
  log "Shutting down…"
  [ -n "$BACKEND_PID" ] && kill "$BACKEND_PID" 2>/dev/null || true
  [ -n "$UI_PID" ]      && kill "$UI_PID"      2>/dev/null || true
  wait "$BACKEND_PID" "$UI_PID" 2>/dev/null || true
  ok "Done."
  exit 0
}
trap cleanup INT TERM

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# [Process 1] Backend
#   Virtualenv : $BACKEND/.venv   (Python 3.12)
#   python   : $BACKEND/.venv/bin/python
#   pip      : $BACKEND/.venv/bin/pip
#   uvicorn  : $BACKEND/.venv/bin/uvicorn
#   Dependencies : $BACKEND/pyproject.toml  (fastapi, uvicorn, langgraph, langchain-*)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
BACKEND_VENV="$BACKEND/.venv"
BACKEND_PYTHON="$BACKEND_VENV/bin/python"
BACKEND_UVICORN="$BACKEND_VENV/bin/uvicorn"

echo -e "${BOLD}[server]${RESET} venv → ${CYAN}$BACKEND_VENV${RESET}"

if ! command -v uv &> /dev/null; then
  err "uv is not installed. Please install it: curl -LsSf https://astral.sh/uv/install.sh | sh"
  exit 1
fi

if [ ! -d "$BACKEND_VENV" ]; then
  log "No Python venv → creating: $BACKEND_VENV (using uv)"
  uv venv --python 3.12 "$BACKEND_VENV"
  ok "venv created"
else
  # Recreate the venv if the shebang broke after a directory move/rename
  # (uv venv doesn't install pip by default, so check via the uvicorn script)
  VENV_PYTHON_SHEBANG=$(head -1 "$BACKEND_VENV/bin/uvicorn" 2>/dev/null | sed 's/#!//')
  if [ -n "$VENV_PYTHON_SHEBANG" ] && [ ! -f "$VENV_PYTHON_SHEBANG" ]; then
    warn "venv shebang path is broken ($VENV_PYTHON_SHEBANG) → recreating venv"
    rm -rf "$BACKEND_VENV"
    uv venv --python 3.12 "$BACKEND_VENV"
    ok "venv recreated"
  fi
fi

log "Installing/updating backend dependencies (uv pip install)…"
(cd "$BACKEND" && uv pip install --python "$BACKEND_VENV" -e ".[dev]" -q)
ok "Backend deps ready"

# .env check
if [ ! -f "$BACKEND/.env" ]; then
  warn "server/.env missing → copying .env.example"
  cp "$BACKEND/.env.example" "$BACKEND/.env"
  warn "Set ANTHROPIC_API_KEY in $BACKEND/.env."
fi

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# [Process 2] Frontend
#   Runtime  : system Node.js  (no separate Python/virtualenv)
#   Packages : $UI/node_modules   (npm install)
#   Run      : npm run dev  (Vite dev server)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
echo -e "${BOLD}[frontend]${RESET} node_modules → ${GREEN}$UI/node_modules${RESET}"

if [ ! -d "$UI/node_modules" ]; then
  log "Installing frontend dependencies…"
  (cd "$UI" && npm install --silent)
  ok "Frontend deps ready"
fi

# ─── Port conflict check ──────────────────────────────────────────────────────
check_port() {
  if lsof -i ":$1" -sTCP:LISTEN -t &>/dev/null; then
    err "Port $1 is already in use. Stop the process or change the port."
    exit 1
  fi
}
check_port 8000
check_port 5137

# ─── LAN IP detection (for pointing other devices on the same network) ───────
LAN_IP=$(ip -4 route get 1.1.1.1 2>/dev/null | awk '{for(i=1;i<=NF;i++) if($i=="src") {print $(i+1); exit}}') || true

# ─── Start backend ────────────────────────────────────────────────────────────
# venv: $BACKEND_VENV  /  executable: $BACKEND_UVICORN
log "Starting backend → http://localhost:8000"
log "  venv    : $BACKEND_VENV"
log "  uvicorn : $BACKEND_UVICORN"
(cd "$BACKEND" && "$BACKEND_UVICORN" main:app --reload --host 0.0.0.0 --port 8000 --log-level warning) \
  2>&1 | sed $'s/^/\033[0;36m[server]\033[0m /' &
BACKEND_PID=$!

# Backend health check (up to 10s)
log "Waiting for backend…"
for i in $(seq 1 20); do
  if curl -sf http://localhost:8000/api/models > /dev/null 2>&1; then
    ok "Backend ready (http://localhost:8000)"
    break
  fi
  sleep 0.5
  if [ $i -eq 20 ]; then
    warn "Backend health check timed out — continuing with frontend startup."
  fi
done

# ─── Start frontend ───────────────────────────────────────────────────────────
# Node.js system runtime / packages: $UI/node_modules
log "Starting frontend → http://0.0.0.0:5137 (exposed on LAN)"
log "  node_modules : $UI/node_modules"
(cd "$UI" && npm run dev -- --host 0.0.0.0 --port 5137) \
  2>&1 | sed $'s/^/\033[0;32m[frontend]\033[0m /' &
UI_PID=$!

# ─── Run summary ──────────────────────────────────────────────────────────────
echo ""
echo -e "${BOLD}  Process      Virtualenv / runtime${RESET}"
echo   "  ──────────  ──────────────────────────────────────────────────"
echo -e "  ${CYAN}server${RESET}      Python 3.12  $BACKEND_VENV"
echo -e "  ${GREEN}frontend${RESET}    Node.js      $UI/node_modules (0.0.0.0:5137)"
echo ""
ok "Servers running. Browser: ${GREEN}http://localhost:5137${RESET}"
echo ""
echo "  Backend  → http://localhost:8000"
echo "  Frontend → http://localhost:5137"
if [ -n "$LAN_IP" ]; then
  echo "  LAN      → http://$LAN_IP:5137"
fi
echo ""
echo "  Ctrl+C to stop all."
echo ""

# If either one dies, cleanup
wait "$BACKEND_PID" "$UI_PID"
cleanup
