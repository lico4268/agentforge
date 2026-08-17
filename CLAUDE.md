# Agentforge

ComfyUI 스타일의 에이전트 아키텍처 빌더. 노드 캔버스에서 LLM 에이전트 파이프라인을 시각적으로 설계하고 실행한다.

> 코딩·린트·import·타입 계약 규칙은 [AGENTS.md](./AGENTS.md)를 따른다. 진행 상태는 [ROADMAP.md](./ROADMAP.md) 참고.

---

## 디렉토리 구조

```
agentforge/
├── config.yaml              # 중앙 설정 (서버·모델 목록·실행 파라미터·UI). config.py가 로드
├── server/                  # FastAPI 백엔드 (Python 3.12)
│   ├── main.py              # FastAPI 앱 진입점, CORS, REST, WebSocket, dispatch_graph
│   ├── manifests.py         # GET /api/nodes — 빌트인 노드 manifest(dict) 목록
│   ├── models.py            # LLM 출력 스키마(PlanOut/ReasonOut/Criterion/ReviewDelta) + build_model 팩토리
│   ├── state.py             # AgentState(TypedDict) 정의 및 initial_state
│   ├── events.py            # ExecutionEvent + make_event/make_error_event + WS/List emitter
│   ├── logging_config.py    # setup_logging() / logger (config.LOG_LEVEL 기준)
│   ├── harness.py           # 벤치마크 하니스 (run_dataset + gsm8k_grader + Report) — pass@1 측정
│   ├── workspace.py         # run 아티팩트 — node_end output을 workspace/<run_id>/*.md로 저장/조회
│   ├── config.py            # config.yaml + .env(API 키) 로드
│   ├── nodes/               # 그래프가 호출하는 노드 헬퍼 (NodeRegistry 아님 — __init__.py는 빈 패키지 마커)
│   │   ├── llm_step.py      # run_llm_step — 구조화 출력 LLM 호출 헬퍼
│   │   ├── checkpoint.py    # make_human_checkpoint — interrupt 기반 인간 검토
│   │   ├── review.py        # make_review — intent×criteria 대조 리뷰 (ReviewDelta 산출)
│   │   └── policy.py        # compute_review_branch / make_route_review — 순수 라우팅 함수
│   └── graphs/              # LangGraph StateGraph 정의 (실제 실행 엔진)
│       ├── baseline.py      # build_baseline — Reasoning만 하는 단발 베이스라인
│       ├── treatment.py     # build_treatment — Planning→Reasoning→Policy 3분기 구조
│       └── compile.py       # compile_graph — 캔버스 그래프(Architecture dict) 동적 컴파일 (v0.3)
│
├── ui/                      # React + TypeScript 프론트엔드 (Vite)
│   └── src/
│       ├── App.tsx           # 루트 컴포넌트
│       ├── canvas/           # React Flow 기반 노드 캔버스
│       ├── panels/           # Inspector, LogPanel 등 사이드 패널
│       │   └── Markdown.tsx  # react-markdown + remark-gfm 렌더러 (Inspector/LogPanel output 표시)
│       ├── stores/           # Zustand 상태 스토어
│       ├── transport/        # WebSocket / MockTransport 추상 레이어
│       │   └── TransportContext.tsx  # MockTransport ↔ WebSocketTransport 전환 지점
│       ├── types/            # Zod 스키마 (백엔드 Pydantic과 1:1 대응)
│       │   └── workspace.ts  # run 파일 목록/내용 Zod 스키마 (workspace.py REST 대응)
│       ├── registry/         # 프론트 노드 타입 레지스트리
│       │   └── loadRunFiles.ts  # GET /api/runs/{id}/files fetch + 파싱
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
| Frontend (Vite) | http://localhost:5137 | `ui/node_modules` (Node.js) |

### 개별 실행

```bash
# 백엔드만
cd server && ../.venv/bin/uvicorn main:app --reload --port 8000

# 프론트엔드만
cd ui && npm run dev -- --port 5137
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
백엔드 WS 핸들러 (main.py: ws_run)
    │ { kind: "run", architecture, input, model }
    ▼
dispatch_graph(architecture) → graphs/*.py의 LangGraph StateGraph 빌더
    │ graph.ainvoke(state0)
    ▼
각 노드 함수 → emit(make_event(...)) → WSEventEmitter → WS 스트림
    │
    ▼
프론트 노드 상태 업데이트 (running / done / failed / skipped)
```

> `dispatch_graph`는 고정 arch 이름(`gsm8k-baseline`/`gsm8k-treatment`)이면 고정 그래프 빌더에 디스패치하고,
> 그 외에는 `compile_graph(architecture)`(`graphs/compile.py`)로 폴백해 캔버스 그래프를 직접 `StateGraph`로
> 컴파일·실행한다 (v0.3, 커밋 `faa736e`). 한계·남은 검증은 ROADMAP v0.3 참고.

**MockTransport → WebSocketTransport 전환**: `ui/src/transport/TransportContext.tsx`에서 한 줄 변경.

---

## refer_data 사용 지침

- `refer_data/docs/` — 기능 구현 전 관련 스펙 문서를 먼저 참고한다.
- `refer_data/papers/` — 알고리즘/아키텍처 설계 결정 시 참고 논문 확인.
- 이 폴더는 **읽기 전용**이며 코드 생성의 근거 자료다. 수정하지 않는다.

---

## 개발 규칙

- 타입 계약: 백엔드 Pydantic 필드명은 프론트 Zod 스키마와 **camelCase로 통일** (snake_case 변환 없음).
- 노드 추가: `server/nodes/`에 헬퍼 함수(예: `run_llm_step` 패턴)를 만들고, `server/graphs/`의 `StateGraph` 빌더에서 `add_node`로 연결한다. 프론트에는 `server/manifests.py`의 `BUILTIN_MANIFESTS`에 manifest(dict)를 추가한다. (구 `NodeBase`/`NodeRegistry` 방식 아님 — 그 규칙은 폐기됨)
- 이벤트 `output` 필드: Inspector에 JSON/Markdown으로 그대로 표시되고, `node_end`의 output은 `WSEventEmitter`가 `server/workspace/<run_id>/`에 `.md` 파일로 자동 영속화하므로 직렬화 가능한 형태(`str`, `dict`, `list`)만 넣는다.
- 실행 엔진은 v0.1부터 LangGraph `StateGraph`다. v0.3의 캔버스 그래프 동적 컴파일(`compile_graph(architecture)`)은 구현 완료 — 남은 것은 E2E 검증과 `compile.py` 단위 테스트 (ROADMAP 참고).
