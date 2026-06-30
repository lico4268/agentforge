# Agentforge — 백엔드 설계 & 프론트엔드 연동 문서

> 상태: Living doc (실제 구현 반영)
> 최초 작성: 2026-06-26 · 전면 개정: 2026-06-30
> 관련 문서: [CLAUDE.md](./CLAUDE.md) · [AGENTS.md](./AGENTS.md) · [ROADMAP.md](./ROADMAP.md) · [ui-architecture.md](./refer_data/docs/ui-architecture.md)

이 문서는 FastAPI 백엔드가 **무엇을 어떻게 구현해 프론트엔드와 연동되는지**를 기술한다.
프론트 코드(`ui/src/transport/`, `ui/src/types/`)가 계약을 정의해두었고, 백엔드는 그 계약을 이행한다.

> 📌 **개정 이력 메모**: 이 문서의 2026-06-26 초안은 `NodeBase` 추상 클래스 + `NodeRegistry` +
> 위상 정렬 `ExecutionEngine`를 전제했고 LangGraph를 "나중에 업그레이드"로 미뤘다. **실제 구현은
> 그 단계를 건너뛰고 v0.1부터 LangGraph `StateGraph`를 채택**했다. 이 개정판은 실제 코드(`server/`)를
> 기준으로 다시 쓴 것이다. 옛 초안 내용이 필요하면 git 히스토리를 참고하라.

---

## 0. 연동의 핵심 원칙

백엔드는 두 계약만 이행하면 프론트와 붙는다.

1. **REST `GET /api/nodes`** — 노드 manifest 목록 반환 (노드 팔레트 채우기)
2. **WebSocket `ws://…/ws/run`** — 실행 이벤트 스트리밍 + 제어 메시지(run / resume / reconnect) 수신

부가 계약: `GET /api/models`(모델 드롭다운), `GET|POST /api/architectures`(저장/불러오기).

핵심 규칙: **타입은 camelCase로 통일**한다. 백엔드가 WS/REST로 내보내는 페이로드는
`ExecutionEvent.to_frontend()`처럼 camelCase로 직렬화하고, 프론트 Zod 스키마(`ui/src/types/`)와 1:1 대응시킨다.
snake_case ↔ camelCase 변환 레이어를 두지 않는다 (AGENTS.md §4).

---

## 1. 기술 스택

| 영역 | 사용 |
|------|------|
| 웹 프레임워크 | FastAPI + uvicorn |
| 실행 엔진 | **LangGraph** (`StateGraph`, `MemorySaver`, `interrupt`/`Command`) |
| LLM 어댑터 | LangChain (`langchain-core`, `langchain-anthropic`, `langchain-openai`, `langchain-google-genai`) |
| 타입/검증 | Pydantic v2 (LLM 구조화 출력 스키마) |
| 설정 | PyYAML(`config.yaml`) + python-dotenv(`.env` API 키) |
| 패키지 | `uv` (Python 3.12, `server/.venv`) |

---

## 2. 프로젝트 구조 (실제)

```
agentforge/
├── config.yaml              # 중앙 설정: 서버·모델 목록·실행 파라미터·UI
├── server/
│   ├── main.py              # FastAPI 앱, REST, WebSocket(ws_run), dispatch_graph
│   ├── manifests.py         # BUILTIN_MANIFESTS (노드 manifest dict 목록)
│   ├── models.py            # LLM 출력 스키마(PlanOut/ReasonOut/VerdictOut) + build_model 팩토리
│   ├── state.py             # AgentState(TypedDict) + initial_state
│   ├── events.py            # ExecutionEvent + make_event/make_error_event + WS/List emitter
│   ├── logging_config.py    # setup_logging() / logger
│   ├── harness.py           # 벤치마크 하니스 (run_dataset + gsm8k_grader + Report)
│   ├── config.py            # config.yaml + .env 로드
│   ├── nodes/               # 그래프가 호출하는 노드 헬퍼 (NodeRegistry 아님)
│   │   ├── __init__.py      # 빈 패키지 마커
│   │   ├── llm_step.py      # run_llm_step (구조화 출력 LLM 호출)
│   │   ├── checkpoint.py    # make_human_checkpoint (interrupt 기반)
│   │   └── policy.py        # compute_branch / route_review / route_verify
│   ├── graphs/              # LangGraph StateGraph 정의 (= 실제 실행 엔진)
│   │   ├── baseline.py      # build_baseline
│   │   └── treatment.py     # build_treatment
│   ├── architectures/       # POST /api/architectures 저장 위치 (JSON 파일)
│   └── tests/               # pytest
└── ui/                      # 프론트 (별도 문서)
```

> 초안의 `backend/`, `nodes/base.py`, `execution/engine.py`는 실제로 존재하지 않는다. 실행 로직은
> `graphs/`의 `StateGraph` 빌더에 있다.

---

## 3. 타입 계약 — 프론트 Zod ↔ 백엔드 Pydantic/dict

### 3.1 NodeManifest

노드 *타입*의 정의다. 백엔드는 Pydantic 모델이 아니라 **dict 리스트**(`manifests.py`의 `BUILTIN_MANIFESTS`)로 들고 있고,
`GET /api/nodes`가 그대로 반환한다. 프론트는 `ui/src/types/manifest.ts`의 `NodeManifestSchema`(Zod)로 파싱한다.

manifest 한 건의 형태:

```python
{
    "type": "reasoning.cot",          # 고유 타입 id
    "runtime": "llm_step",            # 실행 매핑 힌트 (llm_step/policy/checkpoint/io/model)
    "category": "cognitive",          # 팔레트 분류 (cognitive/memory/model/tool/policy/human/io)
    "label": "Reasoning",
    "description": "Chain-of-thought 추론.",
    "maxModelSlots": 2,               # 설정 시 model 입력 포트 대신 인라인 모델 슬롯 UI
    "inputs":  [{"id": "task", "label": "Task", "dataType": "text", "required": True}, ...],
    "outputs": [{"id": "answer", "label": "Answer", "dataType": "text"}, ...],
    "config":  [{"key": "style", "label": "Style", "type": "select", "options": [...]}],
    "defaults": {"systemPrompt": "...", "outputSchema": {"answer": "string", "confidence": "number"}},
}
```

> ⚠️ 계약 변경 주의: manifest 필드를 추가하면 프론트 `manifest.ts`의 Zod 스키마를 **동시에** 갱신한다.
> 최근 변경: 외부 `model` 입력 포트 → `maxModelSlots` 인라인 슬롯으로 전환됨 (`ModelSlotSchema`).

### 3.2 Architecture (프론트가 `run` 메시지에 담아 보내는 그래프)

캔버스의 노드/엣지를 직렬화한 것. 프론트 `useGraphStore.toArchitecture(name)`가 만든다.

```jsonc
{
  "version": "0.1",
  "metadata": { "name": "gsm8k-treatment", "createdAt": "..." },
  "nodes": [
    { "id": "reasoning", "type": "reasoning.cot", "position": {"x":300,"y":360}, "config": {} }
  ],
  "edges": [
    { "id": "e4", "source": "reasoning", "sourceHandle": "answer",
      "target": "review_policy", "targetHandle": "answer" }
  ]
}
```

> v0.1 현재 백엔드는 `architecture.metadata.name`만 보고 고정 그래프에 디스패치한다 (§7).
> v0.3에서 `nodes`/`edges`를 직접 `StateGraph`로 컴파일한다 (§12).

### 3.3 ExecutionEvent (백엔드 → 프론트, WS 스트리밍)

`events.py`의 `ExecutionEvent`. `to_frontend()`가 camelCase dict를 만들어 WS로 나간다.
프론트 `ui/src/types/events.ts`의 `ExecutionEventSchema`와 1:1.

| 필드 (camelCase) | 의미 |
|------------------|------|
| `eventType` | `node_start` / `node_end` / `error` / `interrupt` / `decision_record` 등 |
| `runId`, `nodeId`, `timestamp` | 항상 포함 |
| `durationMs` | 노드 실행 시간 (선택) |
| `output` | 노드 산출물 — Inspector에 JSON 표시 (직렬화 가능 형태만) |
| `tokenUsage` | `{total_tokens, ...}` (선택) |
| `policyDecision` | `{activated: bool, reason: str}` — Policy 노드 |
| `error` | `{type, detail}` — 실패 시 (§ 노드 에러 표준) |
| `message` | 자유 텍스트 |

생성 헬퍼:
- `make_event(run_id, node_id, event_type, **kwargs)` — 일반 이벤트
- `make_error_event(run_id, node_id, exc)` — `eventType="error"` + 구조화 `error={type, detail}`

### 3.4 WebSocket 프로토콜

**프론트 → 백엔드** (`kind`):

```jsonc
// 실행 시작
{ "kind": "run", "architecture": {...}, "input": { "task": "...", "task_tags": [] },
  "model": { "provider": "anthropic", "model": "claude-haiku-4-5-20251001", "temperature": 0 } }

// Human Checkpoint 재개
{ "kind": "resume", "runId": "...", "decision": { "action": "approve|revise|reject", "edits": {}, "reason": "" } }

// 재접속 (누적 이벤트 스냅샷 요청)
{ "kind": "reconnect", "runId": "..." }
```

**백엔드 → 프론트** (`kind`):

```jsonc
{ "kind": "run_started", "runId": "..." }
{ "kind": "event", "event": { /* ExecutionEvent.to_frontend() */ } }
{ "kind": "run_complete", "runId": "...", "result": { "answer": "...", "verdict": {...}, "confidence": 0.9 } }
{ "kind": "error", "runId": "...", "message": "..." }
{ "kind": "state", "runId": "...", "snapshot": [ /* 누적 이벤트 배열 */ ] }   // reconnect 응답
```

프론트 `TransportContext.tsx`가 이 메시지들을 받아 `useExecutionStore`에 반영한다.

---

## 4. REST API (`server/main.py`)

| 엔드포인트 | 설명 |
|-----------|------|
| `GET /api/nodes` | `BUILTIN_MANIFESTS` 반환 (노드 팔레트) |
| `GET /api/models` | `config.yaml`의 `models.list` 중 `enabled` 모델. provider별 API 키 유무를 `available` 필드로 표시 |
| `GET /api/architectures` | `server/architectures/*.json` 전체 |
| `POST /api/architectures` | 아키텍처 JSON 저장 (`id` 없으면 uuid 생성) |
| `GET /api/architectures/{id}` | 단건 조회 (없으면 404) |

`GET /api/models` 응답 한 건:

```jsonc
{ "id": "claude-haiku-4-5-20251001", "provider": "anthropic", "label": "Claude Haiku 4.5",
  "description": "...", "available": true, "temperature": 0.0, "maxTokens": 4096 }
```

---

## 5. WebSocket 엔드포인트 — 연동의 핵심 (`main.py: ws_run`)

### 5.1 흐름

```
accept
  └─ while True: receive_text → json
       ├─ kind="run":       run_id 생성 → run_started → dispatch_graph → graph.ainvoke → run_complete
       ├─ kind="resume":    active_runs[run_id] 조회 → graph.ainvoke(Command(resume=decision))
       └─ kind="reconnect": run_history[run_id] 스냅샷 → state
  (WebSocketDisconnect 시 종료)
```

상태 보관(프로세스 메모리):
- `run_history: dict[run_id, list[ExecutionEvent]]` — 재접속 시 재전송용
- `active_runs: dict[run_id, CompiledGraph]` — resume(인간 검토 재개)용

### 5.2 run 처리 핵심

```python
emitter = WSEventEmitter(ws, run_id, history)          # 이벤트 → WS 스트림
await ws.send_json({"kind": "run_started", "runId": run_id})

graph = dispatch_graph(arch_name, model_cfg, emitter, run_id)
active_runs[run_id] = graph

state0 = initial_state(task=..., task_tags=..., batch_mode=False)
config = {"configurable": {"thread_id": run_id}}        # MemorySaver 스레드 키
final = await graph.ainvoke(state0, config=config)

await ws.send_json({"kind": "run_complete", "runId": run_id,
                    "result": {"answer": final.get("answer"), ...}})
```

에러는 `ValueError`(잘못된 arch 이름 등)와 일반 `Exception`을 구분해 `{"kind": "error"}`로 보낸다.
노드 내부 실패는 `make_error_event`로 `event` 스트림에 흘려보낸다 (AGENTS.md §7).

---

## 6. 노드 = 그래프가 호출하는 헬퍼 (NodeBase 아님)

실행 엔진이 LangGraph이므로 노드는 추상 클래스가 아니라 **`StateGraph`에 등록되는 async 함수**다.
공통 로직은 `server/nodes/`의 헬퍼로 뽑혀 있다.

### 6.1 `run_llm_step` (`nodes/llm_step.py`)

구조화 출력 LLM 호출의 공통 헬퍼. `AgentState`에서 입력 키를 모아 프롬프트를 구성하고,
`model.with_structured_output(output_model)`로 호출한다. 1회 복구 재시도 후 실패하면 `make_error_event` 방출.

```python
result = await run_llm_step(
    state, node_id="reasoning",
    system_prompt=REASONING_SYSTEM_PROMPT,
    input_keys=[("task", "Task"), ("plan", "Plan"), ("feedback", "Previous Feedback")],
    output_model=ReasonOut,           # Pydantic: {answer: str, confidence: float}
    model=model, emit=emit, run_id=run_id,
)
```

### 6.2 `make_human_checkpoint` (`nodes/checkpoint.py`)

LangGraph `interrupt()` 기반. `interrupt` 이벤트를 emit하고 그래프를 정지시킨다.
프론트가 `resume`로 보낸 `decision`이 `interrupt()`의 반환값이 되고, `action`에 따라
`Command(goto=..., update=...)`로 분기한다 (`revise`→`reasoning` 재진입, `approve`/`reject`→`output`).

### 6.3 `policy.py` — 순수 라우팅 함수

`compute_branch(state)`가 confidence·태그로 `pass`/`auto`/`human`을 결정한다(`escalate_tags`는 무조건 human,
`batch_mode`면 human→auto 강등). `make_route_review()`/`make_route_verify()`가 LangGraph
`add_conditional_edges`용 sync 라우터를 만든다. emit은 그래프 노드 쪽에서 한다.

> **새 노드 추가 절차**: ① `nodes/`에 헬퍼 함수 작성 → ② `graphs/`의 빌더에서 `add_node`/엣지 연결 →
> ③ `manifests.py`의 `BUILTIN_MANIFESTS`에 manifest dict 추가 → ④ 프론트 Zod 스키마 영향 확인.

---

## 7. 실행 엔진 = LangGraph StateGraph (`server/graphs/`)

`ExecutionEngine`/위상 정렬은 없다. 각 아키텍처가 하나의 `StateGraph` 빌더 함수다.
공유 상태는 `state.py`의 `AgentState`(TypedDict), 체크포인터는 `MemorySaver`.

### 7.1 디스패치 (`main.py: dispatch_graph`)

```python
def dispatch_graph(arch_name, model_cfg, emit, run_id):
    model = build_model(provider, model_id, temperature)   # LangChain BaseChatModel
    if arch_name == "gsm8k-baseline":  return build_baseline(model, emit, run_id)
    if arch_name == "gsm8k-treatment": return build_treatment(model, emit, run_id)
    raise ValueError(f"Unknown architecture name: {arch_name!r}")
```

### 7.2 baseline (`graphs/baseline.py`)

```
reasoning → output → END
```
검증 없는 단발 추론. v0.1 검증 전략(`v0.1-validation.md`)의 Baseline 측.

### 7.3 treatment (`graphs/treatment.py`)

```
planning → reasoning → review_policy
                          ├─(pass)  → output
                          ├─(auto)  → auto_verify ─(retry)→ reasoning
                          │                        └(output)→ output
                          └─(human) → human_checkpoint ─(approve/reject)→ output
                                                        └(revise)─────────→ reasoning
output → END
```

조건 분기는 `add_conditional_edges(review_policy, route_review, {...})`,
재시도 한계는 `route_verify` + `recursion_limit`로 통제한다. Treatment 측 = "구조가 같은 모델의 pass@1을 올린다"를 증명.

---

## 8. 프론트엔드 연결 — 딱 한 줄 (`ui/src/transport/TransportContext.tsx`)

```ts
function createTransport(): Transport {
  const wsUrl = import.meta.env.VITE_WS_URL   // 있으면 실서버, 없으면 Mock
  return wsUrl ? new WebSocketTransport(wsUrl) : new MockTransport()
}
```

백엔드에 붙이려면 `ui/.env`에 `VITE_WS_URL=ws://localhost:8000/ws/run`. 코드 변경 없음.

### CORS

`config.yaml`의 `server.cors_origins`(기본 `http://localhost:5173`)가 `main.py`의 `CORSMiddleware`에 들어간다.

---

## 9. 단계별 구현 상태 (ROADMAP과 동기화)

| Phase | 내용 | 상태 |
|-------|------|------|
| v0.1 | `/api/nodes`, `ws/run`(run), LangGraph baseline/treatment, 노드 하이라이트 | ✅ (E2E 수동 검증만 남음) |
| v0.2 | 거버넌스/ruff/테스트, 에러·로깅 표준화, 문서 정합성 | ✅ |
| v0.3 | **캔버스 그래프 동적 컴파일** (`dispatch_graph` → `compile(architecture)`) | ⬜ 다음 목표 |
| v0.4+ | GSM8K 배치 실행(Baseline vs Treatment pass@1), Human Checkpoint 프론트 UI, 아키텍처 저장 UI | ⬜ |

---

## 10. 이벤트 타입별 프론트 처리

| eventType | 프론트 처리 (`eventReducer`/`TransportContext`) |
|-----------|----------------------------------------------|
| `node_start` | 해당 노드 status → `running`, `activeNodeId` 갱신 |
| `node_end` | status → `success`, output/메트릭 누적 |
| `error` | status → `failed`, `error.detail`을 LogPanel/Inspector 표시 |
| `interrupt` | (v0.4 예정) Human Checkpoint UI 표시 → 사용자 decision → `resume` 전송 |
| `decision_record` | 인간 결정 로그 기록 |
| `run_complete` / `run_started` / `error`(kind) | `setRunState`로 실행 상태 배너 갱신 |

---

## 11. 개발 환경

```bash
# 통합 실행 (백엔드 + 프론트)
./start.sh

# 개별
cd server && ../.venv/bin/uvicorn main:app --reload --port 8000
cd ui && npm run dev -- --port 5173
```

API 키는 `server/.env` (`ANTHROPIC_API_KEY` 등). 나머지 설정은 `config.yaml`.

---

## 12. v0.3 — 캔버스 그래프 동적 컴파일 (다음 큰 과제)

현재 `dispatch_graph`는 arch 이름으로 고정 그래프에 보낸다. 프론트 Toolbar의 `current canvas` 옵션은
캔버스를 직렬화해 보내지만, 백엔드가 그 이름을 모르므로 `ValueError`가 난다. v0.3 목표는 이 seam을
**`compile_graph(architecture: dict) -> CompiledGraph`** 로 교체하는 것이다.

```
Architecture.nodes / edges
        ↓
compile_graph: manifest type → 노드 함수 매핑, edges → StateGraph 엣지
        ↓
policy.review → add_conditional_edges,  human.checkpoint → interrupt
        ↓
StateGraph.compile(checkpointer=MemorySaver()).ainvoke(state0)
        ↓
ExecutionEvent → WSEventEmitter → WS  (위층 ws_run 핸들러는 무변경)
```

`dispatch_graph`의 시그니처(`(arch_name, model_cfg, emit, run_id) -> CompiledGraph`)를 유지하면서
미지의 arch 이름일 때 `compile_graph`로 폴백하면, WS 핸들러는 그대로 두고 엔진만 확장된다.
`starterArchitecture.ts`의 노드 id가 이미 treatment 그래프 노드명과 일치하도록 정렬돼 있어 매핑이 단순하다.
