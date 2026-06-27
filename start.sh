#!/usr/bin/env bash
# Agentforge 개발 서버 통합 실행 스크립트
# 사용: ./start.sh
# 종료: Ctrl+C (백엔드+프론트 모두 종료됨)
#
# ┌──────────────┬────────────────────────────────────────────────────────┐
# │  프로세스    │  가상환경 / 런타임                                     │
# ├──────────────┼────────────────────────────────────────────────────────┤
# │  server      │  Python 3.12 venv                                      │
# │              │  경로: <repo>/server/.venv                             │
# │              │  실행: server/.venv/bin/uvicorn  main:app              │
# │              │  pip:  server/.venv/bin/pip                            │
# ├──────────────┼────────────────────────────────────────────────────────┤
# │  frontend    │  시스템 Node.js (별도 venv 없음)                       │
# │              │  패키지: <repo>/ui/node_modules  (npm run dev)         │
# └──────────────┴────────────────────────────────────────────────────────┘

set -e

ROOT="$(cd "$(dirname "$0")" && pwd)"
BACKEND="$ROOT/server"
UI="$ROOT/ui"

# ─── 색상 ─────────────────────────────────────────────────────────────────────
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

# ─── cleanup: Ctrl+C 시 두 프로세스 모두 종료 ────────────────────────────────
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
# [프로세스 1] 백엔드
#   가상환경 : $BACKEND/.venv   (Python 3.12)
#   python   : $BACKEND/.venv/bin/python
#   pip      : $BACKEND/.venv/bin/pip
#   uvicorn  : $BACKEND/.venv/bin/uvicorn
#   의존성   : $BACKEND/pyproject.toml  (fastapi, uvicorn, langgraph, langchain-*)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
BACKEND_VENV="$BACKEND/.venv"
BACKEND_PYTHON="$BACKEND_VENV/bin/python"
BACKEND_UVICORN="$BACKEND_VENV/bin/uvicorn"

echo -e "${BOLD}[server]${RESET} venv → ${CYAN}$BACKEND_VENV${RESET}"

if [ ! -d "$BACKEND_VENV" ]; then
  log "Python venv 없음 → 생성: $BACKEND_VENV"
  python3 -m venv "$BACKEND_VENV"
  "$BACKEND_PYTHON" -m ensurepip --upgrade 2>/dev/null || true
  ok "venv 생성 완료"
else
  # 디렉토리 이동/rename 후 shebang이 깨진 경우 venv 재생성
  VENV_PYTHON_SHEBANG=$(head -1 "$BACKEND_VENV/bin/pip" 2>/dev/null | sed 's/#!//')
  if [ -n "$VENV_PYTHON_SHEBANG" ] && [ ! -f "$VENV_PYTHON_SHEBANG" ]; then
    warn "venv shebang 경로 깨짐 ($VENV_PYTHON_SHEBANG) → venv 재생성"
    rm -rf "$BACKEND_VENV"
    python3 -m venv "$BACKEND_VENV"
    "$BACKEND_PYTHON" -m ensurepip --upgrade 2>/dev/null || true
    ok "venv 재생성 완료"
  fi
fi

log "백엔드 의존성 설치/업데이트 (${BACKEND_PYTHON} -m pip)…"
# pyproject.toml 에서 deps 읽어 설치 (패키지 빌드 없이 deps만)
# pip 바이너리 대신 python -m pip 사용 → venv 생성 직후도 항상 작동
DEPS=$(cd "$BACKEND" && "$BACKEND_PYTHON" -c "
import tomllib
with open('pyproject.toml', 'rb') as f:
    d = tomllib.load(f)
deps = d['project']['dependencies']
deps += d['project'].get('optional-dependencies', {}).get('dev', [])
print('\n'.join(deps))
")
echo "$DEPS" | xargs "$BACKEND_PYTHON" -m pip install -q
ok "백엔드 deps 준비"

# .env 체크
if [ ! -f "$BACKEND/.env" ]; then
  warn "server/.env 없음 → .env.example 복사"
  cp "$BACKEND/.env.example" "$BACKEND/.env"
  warn "ANTHROPIC_API_KEY를 $BACKEND/.env 에 설정하세요."
fi

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# [프로세스 2] 프론트엔드
#   런타임  : 시스템 Node.js  (별도 Python/가상환경 없음)
#   패키지  : $UI/node_modules   (npm install)
#   실행    : npm run dev  (Vite dev server)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
echo -e "${BOLD}[frontend]${RESET} node_modules → ${GREEN}$UI/node_modules${RESET}"

if [ ! -d "$UI/node_modules" ]; then
  log "프론트엔드 의존성 설치 중…"
  (cd "$UI" && npm install --silent)
  ok "프론트엔드 deps 준비"
fi

# ─── 포트 충돌 확인 ───────────────────────────────────────────────────────────
check_port() {
  if lsof -i ":$1" -sTCP:LISTEN -t &>/dev/null; then
    err "포트 $1 이미 사용 중. 프로세스를 종료하거나 포트를 변경하세요."
    exit 1
  fi
}
check_port 8000
check_port 5173

# ─── 백엔드 실행 ──────────────────────────────────────────────────────────────
# venv: $BACKEND_VENV  /  실행파일: $BACKEND_UVICORN
log "백엔드 시작 → http://localhost:8000"
log "  venv    : $BACKEND_VENV"
log "  uvicorn : $BACKEND_UVICORN"
(cd "$BACKEND" && "$BACKEND_UVICORN" main:app --reload --port 8000 --log-level warning) \
  2>&1 | sed $'s/^/\033[0;36m[server]\033[0m /' &
BACKEND_PID=$!

# 백엔드 헬스체크 (최대 10초)
log "백엔드 준비 대기…"
for i in $(seq 1 20); do
  if curl -sf http://localhost:8000/api/nodes > /dev/null 2>&1; then
    ok "백엔드 준비 완료 (http://localhost:8000)"
    break
  fi
  sleep 0.5
  if [ $i -eq 20 ]; then
    warn "백엔드 헬스체크 타임아웃 — 프론트엔드 시작 진행."
  fi
done

# ─── 프론트엔드 실행 ──────────────────────────────────────────────────────────
# Node.js 시스템 런타임 / 패키지: $UI/node_modules
log "프론트엔드 시작 → http://localhost:5173"
log "  node_modules : $UI/node_modules"
(cd "$UI" && npm run dev -- --port 5173) \
  2>&1 | sed $'s/^/\033[0;32m[frontend]\033[0m /' &
UI_PID=$!

# ─── 실행 요약 ────────────────────────────────────────────────────────────────
echo ""
echo -e "${BOLD}  프로세스     가상환경 / 런타임${RESET}"
echo   "  ──────────  ──────────────────────────────────────────────────"
echo -e "  ${CYAN}server${RESET}      Python 3.12  $BACKEND_VENV"
echo -e "  ${GREEN}frontend${RESET}    Node.js      $UI/node_modules"
echo ""
ok "서버 실행 중. 브라우저: ${GREEN}http://localhost:5173${RESET}"
echo ""
echo "  Backend  → http://localhost:8000"
echo "  Frontend → http://localhost:5173"
echo ""
echo "  Ctrl+C 로 모두 종료."
echo ""

# 어느 한 쪽이 죽으면 cleanup
wait "$BACKEND_PID" "$UI_PID"
cleanup
