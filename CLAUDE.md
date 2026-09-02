# Agentforge

텍스트(`arch.yaml`)로 LLM 에이전트 파이프라인을 짓고, 그 자리에서 실행·테스트하는
도구. 저작은 YAML 파일이고, 그림(mermaid)은 그 텍스트에서 자동 생성되는 읽기 전용
산출물이다 — 노드 캔버스로 그려서 짓던 방식(ComfyUI 스타일)은 2026-09-02 텍스트
우선 전환으로 폐기됐다.

> **설계 방향은 [DIRECTION.md](./DIRECTION.md)가 최우선이다** — 다른 문서와 충돌하면 그쪽이 낡은 것이다.
> `docs/superpowers/**`, `work/**`, `POLICY_*.md`는 과거 기록이며 현재 설계가 아니다.
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
│   ├── archfile.py           # parse_arch — arch.yaml(mermaid flow + node defs) → Architecture dict
│   ├── arch_files.py         # server/arch/*.yaml 목록/조회 (파일 기반, GET /api/arch[/​{name}])
│   ├── arch/                 # 사람이 저작하는 arch.yaml 파일들 (예: gsm8k.yaml)
│   ├── nodes/               # 그래프가 호출하는 노드 헬퍼 (NodeRegistry 아님 — __init__.py는 빈 패키지 마커)
│   │   ├── llm_step.py      # run_llm_step — 구조화 출력 LLM 호출 헬퍼
│   │   ├── checkpoint.py    # make_human_checkpoint — interrupt 기반 인간 검토
│   │   ├── review.py        # make_review — intent×criteria 대조 리뷰 (ReviewDelta 산출, treatment.py 전용)
│   │   └── policy.py        # compute_review_branch / make_route_review — 순수 라우팅 함수
│   └── graphs/              # LangGraph StateGraph 정의 (실제 실행 엔진)
│       ├── baseline.py      # build_baseline — Reasoning만 하는 단발 베이스라인
│       ├── treatment.py     # build_treatment — Planning→Reasoning→Policy 3분기 구조
│       └── compile.py       # compile_graph — arch.yaml에서 parse_arch가 만든 Architecture dict를 동적 컴파일
│
├── ui/                      # React + TypeScript 프론트엔드 (Vite)
│   └── src/
│       ├── App.tsx           # 루트 컴포넌트 — <Dashboard /> 렌더
│       ├── app/
│       │   ├── Dashboard.tsx            # 읽기 전용 대시보드 — arch.yaml 선택·Run·체크포인트 승인/반려
│       │   ├── FlowDiagram.tsx          # architecture.flow(mermaid 문자열)를 그대로 렌더 + 실행 중 노드 색칠
│       │   └── NodeProgress.tsx         # 실행 이벤트를 노드별 방문 목록으로 나열
│       ├── panels/
│       │   └── Markdown.tsx  # react-markdown + remark-gfm 렌더러 (LogPanel output 표시)
│       ├── transport/        # WebSocket / MockTransport 추상 레이어
│       │   └── TransportContext.tsx  # MockTransport ↔ WebSocketTransport 전환 지점
│       ├── types/            # Zod 스키마 (백엔드 Pydantic과 1:1 대응)
│       │   ├── arch.ts       # ArchGraphSchema 등 — archfile.py의 Architecture dict 대응
│       │   └── workspace.ts  # run 파일 목록/내용 Zod 스키마 (workspace.py REST 대응)
│       ├── registry/         # 백엔드 REST fetch 헬퍼
│       │   ├── loadArchFiles.ts  # GET /api/arch[/​{name}] fetch + 파싱
│       │   └── loadRunFiles.ts   # GET /api/runs/{id}/files fetch + 파싱
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
사람이 server/arch/*.yaml 작성
    │
프론트 Dashboard (arch.yaml 목록에서 선택 + task 입력 + Run)
    │ WebSocket ws://localhost:8000/ws/run
    ▼
백엔드 WS 핸들러 (main.py: ws_run)
    │ { kind: "run", archFile: "<name>.yaml", input, model }
    ▼
archfile.parse_arch(yaml_text) → Architecture dict (nodes/edges/flow)
    │
dispatch_graph(architecture) → graphs/*.py의 LangGraph StateGraph 빌더
    │ graph.ainvoke(state0)
    ▼
각 노드 함수 → emit(make_event(...)) → WSEventEmitter → WS 스트림
    │
    ▼
프론트 FlowDiagram(architecture.flow를 mermaid에 그대로 전달) 색칠 +
NodeProgress 목록 업데이트 (running / done / failed / paused / skipped)
```

> `dispatch_graph`는 고정 arch 이름(`gsm8k-baseline`/`gsm8k-treatment`)이면 고정 그래프 빌더에 디스패치하고,
> 그 외에는 `compile_graph(architecture)`(`graphs/compile.py`)로 폴백해 파싱된 그래프를 직접 `StateGraph`로
> 컴파일·실행한다 (v0.3, 커밋 `faa736e`). `architecture`를 캔버스가 아니라 `archfile.parse_arch`가 만든다는
> 점만 2026-09-02 텍스트 우선 전환으로 바뀌었다 — `compile_graph` 자체는 무변경. 한계·남은 검증은 ROADMAP 참고.

**MockTransport → WebSocketTransport 전환**: `ui/src/transport/TransportContext.tsx`에서 한 줄 변경.

---

## refer_data 사용 지침

- `refer_data/docs/` — 초기 기획서. 참고하되 `DIRECTION.md`와 충돌하는 부분(노드 역할 고정, 분기 이름 `accept`/`refine`/`clarify` 고정)은 **무효**다.
- `refer_data/papers/` — 알고리즘/아키텍처 설계 결정 시 참고 논문 확인.
- 이 폴더는 **읽기 전용**이며 코드 생성의 근거 자료다. 수정하지 않는다.

---

## 개발 규칙

- 타입 계약: 백엔드 Pydantic 필드명은 프론트 Zod 스키마와 **camelCase로 통일** (snake_case 변환 없음).
- 노드 추가: 사용자가 arch.yaml에 새 노드를 쓰면 `archfile.py`가 전부 `custom.node`(runtime `llm_step`)로 발행하므로, 대부분은 매니페스트를 건드릴 필요가 없다. 진짜 새 **런타임**(입출력 계약이 다른 실행 로직)이 필요할 때만 `server/nodes/`에 헬퍼 함수(예: `run_llm_step` 패턴)를 만들고 `server/manifests.py`의 `BUILTIN_MANIFESTS`에 manifest(dict)를 추가한 뒤 `graphs/compile.py`에서 그 `runtime` 키로 분기한다. (구 `NodeBase`/`NodeRegistry` 방식 아님 — 그 규칙은 폐기됨. 프론트 노드 팔레트도 없다 — 그림은 mermaid 자동 생성이라 프론트에 매니페스트를 등록할 대상 자체가 없다.)
- 이벤트 `output` 필드: 프론트 `NodeProgress`/`LogPanel`에 JSON/Markdown으로 그대로 표시되고, `node_end`의 output은 `WSEventEmitter`가 `server/workspace/<run_id>/`에 `.md` 파일로 자동 영속화하므로 직렬화 가능한 형태(`str`, `dict`, `list`)만 넣는다.
- 실행 엔진은 v0.1부터 LangGraph `StateGraph`다. v0.3의 동적 컴파일(`compile_graph(architecture)`)은 구현 완료 — `architecture`의 출처만 2026-09-02에 캔버스에서 `archfile.parse_arch(arch.yaml)`로 바뀌었다. 남은 것은 ROADMAP 참고.
