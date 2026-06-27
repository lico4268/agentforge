# Agentforge

ComfyUI 스타일의 에이전트 아키텍처 빌더. 노드 캔버스에서 LLM 에이전트 파이프라인을 시각적으로 설계하고 실행한다.

---

## 디렉토리 구조

```
agentforge/
├── server/                  # FastAPI 백엔드 (Python 3.12)
│   ├── main.py              # FastAPI 앱 진입점, CORS, WebSocket 라우팅
│   ├── manifests.py         # GET /api/nodes — 노드 manifest 목록 반환
│   ├── models.py            # Pydantic 타입 (NodeManifest, GraphNode, ExecutionEvent 등)
│   ├── models_config.json   # 사용 가능한 LLM 모델 목록
│   ├── state.py             # 실행 상태 관리
│   ├── events.py            # ExecutionEvent 정의 및 asyncio.Queue 브리지
│   ├── harness.py           # 실행 엔진 (위상 정렬 → 노드 순차 실행)
│   ├── config.py            # 환경 변수 로드 (.env)
│   ├── nodes/               # 노드 플러그인 디렉토리
│   │   ├── __init__.py      # NodeRegistry (노드 타입 등록/조회)
│   │   ├── llm_step.py      # LLM 호출 노드
│   │   ├── checkpoint.py    # 체크포인트 노드
│   │   └── policy.py        # 정책 검증 노드
│   └── graphs/              # LangGraph 그래프 정의
│       ├── baseline.py      # 기본 실행 그래프
│       └── treatment.py     # 실험/처리 그래프
│
├── ui/                      # React + TypeScript 프론트엔드 (Vite)
│   └── src/
│       ├── App.tsx           # 루트 컴포넌트
│       ├── canvas/           # React Flow 기반 노드 캔버스
│       ├── panels/           # Inspector, LogPanel 등 사이드 패널
│       ├── stores/           # Zustand 상태 스토어
│       ├── transport/        # WebSocket / MockTransport 추상 레이어
│       │   └── TransportContext.tsx  # MockTransport ↔ WebSocketTransport 전환 지점
│       ├── types/            # Zod 스키마 (백엔드 Pydantic과 1:1 대응)
│       ├── registry/         # 프론트 노드 타입 레지스트리
│       └── execution/        # 실행 흐름 훅/컨텍스트
│
├── refer_data/              # 기획 문서 및 참고 자료 (읽기 전용)
│   ├── docs/                # 프로젝트 기획서 및 설계 스펙
│   │   ├── agentforge.md    # 프로젝트 전체 기획서
│   │   ├── backend-spec.md  # 백엔드 상세 스펙
│   │   ├── node-spec.md     # 노드 타입 상세 스펙
│   │   ├── ui-architecture.md  # UI 아키텍처 설계
│   │   └── v0.1-validation.md  # v0.1 검증 기준
│   └── papers/              # 참고 논문
│       ├── AgentFlow (Stanford, 2025).pdf
│       ├── Agentic Auto-Scheduling.pdf
│       ├── CCA (Cognitive Control Architecture) 2025.pdf
│       └── CoALA (Cognitive Architectures for Language Agents) 2023.pdf
│
├── backend-architecture.md  # 백엔드 설계 & 프론트 연동 상세 문서
├── start.sh                 # 개발 서버 통합 실행 스크립트
└── CLAUDE.md                # 이 파일
```

---

## 로컬 개발 환경 시작

### 사전 요건

- Python 3.12
- Node.js (시스템 설치)
- `uv` 패키지 매니저: `curl -LsSf https://astral.sh/uv/install.sh | sh`

### 환경 변수 설정

`server/.env` 파일에 API 키를 설정한다 (없으면 start.sh가 `.env.example`에서 자동 복사):

```
ANTHROPIC_API_KEY=sk-ant-...
OPENAI_API_KEY=sk-...        # 선택
DATABASE_URL=sqlite:///./agentforge.db
```

### 실행

```bash
./start.sh
```

백엔드(FastAPI)와 프론트엔드(Vite)를 동시에 시작한다. `Ctrl+C`로 모두 종료.

| 프로세스 | URL | 가상환경 |
|---------|-----|---------|
| Backend (FastAPI/uvicorn) | http://localhost:8000 | `server/.venv` (Python 3.12) |
| Frontend (Vite) | http://localhost:5173 | `ui/node_modules` (Node.js) |

### 개별 실행

```bash
# 백엔드만
cd server && ../.venv/bin/uvicorn main:app --reload --port 8000

# 프론트엔드만
cd ui && npm run dev -- --port 5173
```

### 의존성 추가

```bash
# Python (백엔드)
cd server && ../server/.venv/bin/pip install <패키지>
# 또는 pyproject.toml 편집 후: uv pip install -e ".[dev]"

# Node (프론트엔드)
cd ui && npm install <패키지>
```

---

## 핵심 연동 구조

```
프론트 캔버스 (React Flow)
    │ WebSocket ws://localhost:8000/ws/run
    ▼
백엔드 WS 핸들러
    │ { kind: "run", architecture, input }
    ▼
ExecutionEngine (harness.py)
    │ 위상 정렬 → 노드 순차 실행
    ▼
각 Node.run() → emit(ExecutionEvent) → asyncio.Queue → WS 스트림
    │
    ▼
프론트 노드 상태 업데이트 (running / done / failed / skipped)
```

**MockTransport → WebSocketTransport 전환**: `ui/src/transport/TransportContext.tsx`에서 한 줄 변경.

---

## refer_data 사용 지침

- `refer_data/docs/` — 기능 구현 전 관련 스펙 문서를 먼저 참고한다.
- `refer_data/papers/` — 알고리즘/아키텍처 설계 결정 시 참고 논문 확인.
- 이 폴더는 **읽기 전용**이며 코드 생성의 근거 자료다. 수정하지 않는다.

---

## 개발 규칙

- 타입 계약: 백엔드 Pydantic 필드명은 프론트 Zod 스키마와 **camelCase로 통일** (snake_case 변환 없음).
- 노드 추가: `server/nodes/`에 `NodeBase` 구현 → `nodes/__init__.py` 레지스트리에 등록.
- 이벤트 `output` 필드: Inspector에 JSON으로 그대로 표시되므로 직렬화 가능한 형태(`str`, `dict`, `list`)만 넣는다.
- v0.1~v0.2는 위상 정렬 순차 실행. v0.3+에서 LangGraph `StateGraph`로 `ExecutionEngine` 교체 예정.
