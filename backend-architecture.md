# Agentforge — 백엔드 설계 & 프론트엔드 연동 문서

> 상태: Draft  
> 작성일: 2026-06-26  
> 관련 문서: [ui-architecture.md](./ui-architecture.md)

이 문서는 FastAPI 백엔드를 만들 때 **정확히 무엇을 어떻게 구현해야 프론트엔드와 연동되는지**를 기술한다.  
프론트 코드(`ui/src/transport/`, `ui/src/types/`)가 이미 계약을 정의해두었으므로, 백엔드는 그 계약을 이행하는 역할이다.

---

## 0. 연동의 핵심 원칙

백엔드는 두 가지만 구현하면 프론트와 붙는다.

1. **REST `GET /api/nodes`** — 노드 manifest 목록 반환 (노드 팔레트 채우기)
2. **WebSocket `ws://…/ws/run`** — 실행 이벤트 스트리밍 + 제어 메시지 수신

나머지(아키텍처 저장, 멀티런, 디버깅 등)는 v0.3+ 단계에서 추가한다.

---

## 1. 기술 스택

| 영역 | 선택 | 이유 |
|------|------|------|
| 웹 프레임워크 | **FastAPI** | 비동기 WebSocket 네이티브 지원, Pydantic 계약, 자동 OpenAPI |
| 데이터 검증 | **Pydantic v2** | 프론트 Zod 스키마와 1:1 대응. `model_json_schema()`로 configSchema 자동 생성 |
| AI 실행 | **LangChain / LangGraph** | 프론트 agentforge.md 기반 설계가 LangGraph 그래프와 1:1 대응 |
| 비동기 큐 | **asyncio.Queue** | 노드 실행 이벤트 → WS 스트림 브리지 |
| 저장소 | **SQLite (v0.1~0.3)** | 아키텍처 저장/불러오기. 나중에 PostgreSQL로 교체 가능 |
| 패키지 관리 | **uv** | 빠른 의존성 해결 |

---

## 2. 프로젝트 구조

```
agentforge/
  backend/
    main.py                  # FastAPI 앱 진입점
    api/
      nodes.py               # GET /api/nodes
      architectures.py       # CRUD /api/architectures  (v0.3)
      runs.py                # GET /api/runs/{runId}    (v0.3)
    ws/
      run_handler.py         # ws://.../ws/run  ← 핵심
      protocol.py            # ClientMessage / ServerMessage Pydantic 모델
    nodes/                   # ★ 노드 플러그인 디렉토리
      __init__.py            # 레지스트리
      base.py                # NodeBase 추상 클래스
      manifest.py            # NodeManifest Pydantic 모델
      builtin/
        io_input.py
        io_output.py
        planning.py               # planning.task_decomposition
        verification_critique.py  # verification.critique  (pass / retry 출력)
        cognitive_reflection.py   # cognitive.reflection
        memory_buffer.py          # memory.buffer
        memory_retrieval.py       # memory.retrieval
        model_inference.py        # model.inference  (systemPrompt, maxTokens)
        tool_web_search.py        # tool.web_search
        tool_code_exec.py         # tool.code_exec
        policy_verification.py    # policy.verification  (mode + threshold)
    execution/
      engine.py              # Architecture → LangGraph 실행
      event_emitter.py       # 이벤트 → asyncio.Queue 브리지
      graph_builder.py       # GraphNode/GraphEdge → LangGraph StateGraph
    types/
      graph.py               # GraphNode, GraphEdge, Architecture Pydantic 모델
      events.py              # ExecutionEvent Pydantic 모델
    db/
      models.py              # SQLAlchemy 모델 (v0.3)
      session.py
```

---

## 3. 타입 계약 — 프론트 Zod ↔ 백엔드 Pydantic

프론트 `ui/src/types/`의 Zod 스키마와 **필드명/타입을 1:1로 맞춰야 한다**.  
직렬화는 snake_case → camelCase 변환 없이 **camelCase 통일** (FastAPI에서 `model_config = ConfigDict(populate_by_name=True)` + alias 사용).

### 3.1 NodeManifest

```python
# backend/nodes/manifest.py

from typing import Literal
from pydantic import BaseModel

class Port(BaseModel):
    id: str
    label: str
    dataType: str                    # "text" | "messages" | "plan" | "any" ...
    required: bool = False

class ConfigField(BaseModel):
    key: str
    label: str
    type: Literal["string", "text", "number", "boolean", "select"]
    default: object = None
    options: list[dict] | None = None    # [{ "label": str, "value": str }]
    placeholder: str | None = None
    description: str | None = None

class NodeManifest(BaseModel):
    type: str                            # "planning.task_decomposition"
    category: Literal["cognitive", "memory", "model", "tool", "policy", "io"]
    label: str
    description: str = ""
    inputs: list[Port] = []
    outputs: list[Port] = []
    config: list[ConfigField] = []
    ui: dict | None = None               # { "component": str } — 커스텀 UI 키
```

### 3.2 Architecture (프론트가 `run` 메시지에 담아 보내는 그래프)

```python
# backend/types/graph.py

class GraphNode(BaseModel):
    id: str
    type: str                           # manifest.type 참조
    position: dict                      # { "x": float, "y": float }
    config: dict = {}                   # configSchema에 맞는 값

class GraphEdge(BaseModel):
    id: str
    source: str
    sourceHandle: str
    target: str
    targetHandle: str

class Architecture(BaseModel):
    version: str
    metadata: dict
    nodes: list[GraphNode]
    edges: list[GraphEdge]
```

### 3.3 ExecutionEvent (백엔드 → 프론트, WS로 스트리밍)

```python
# backend/types/events.py

from datetime import datetime, timezone
from typing import Literal

class TokenUsage(BaseModel):
    prompt: int
    completion: int

class PolicyDecision(BaseModel):
    activated: bool
    reason: str

class ExecutionEvent(BaseModel):
    eventType: Literal[
        "node_start", "node_end", "tool_call",
        "agent_action", "log", "error"
    ]
    runId: str
    nodeId: str
    agentId: str | None = None
    parentAgent: str | None = None
    callIndex: int | None = None
    durationMs: float | None = None
    input: object = None
    output: object = None
    tokenUsage: TokenUsage | None = None
    policyDecision: PolicyDecision | None = None
    message: str | None = None
    timestamp: str = ""

    def stamp(self) -> "ExecutionEvent":
        return self.model_copy(
            update={"timestamp": datetime.now(timezone.utc).isoformat()}
        )
```

### 3.4 WebSocket 프로토콜 (protocol.py)

```python
# backend/ws/protocol.py

from typing import Annotated, Literal
from pydantic import BaseModel, Field

# 프론트 → 백엔드
class RunMessage(BaseModel):
    kind: Literal["run"]
    architecture: Architecture
    input: object = None

class StopMessage(BaseModel):
    kind: Literal["stop"]
    runId: str

class RerunFromMessage(BaseModel):     # v0.3
    kind: Literal["rerun_from"]
    runId: str
    nodeId: str

class UpdateNodeMessage(BaseModel):    # v0.3
    kind: Literal["update_node"]
    nodeId: str
    config: dict

ClientMessage = Annotated[
    RunMessage | StopMessage | RerunFromMessage | UpdateNodeMessage,
    Field(discriminator="kind"),
]

# 백엔드 → 프론트
class EventMessage(BaseModel):
    kind: Literal["event"]
    event: ExecutionEvent

class StateMessage(BaseModel):         # 재접속 시 현재 상태 일괄
    kind: Literal["state"]
    snapshot: object

class ErrorMessage(BaseModel):
    kind: Literal["error"]
    message: str

ServerMessage = EventMessage | StateMessage | ErrorMessage
```

---

## 4. REST API

### `GET /api/nodes`

프론트 앱이 시작할 때 `loadManifests()`가 호출하는 엔드포인트.  
이게 없으면 프론트는 번들된 builtin manifest로 fallback한다.

```python
# backend/api/nodes.py

from fastapi import APIRouter
from ..nodes import registry            # 모든 등록된 노드

router = APIRouter()

@router.get("/api/nodes")
async def list_nodes() -> list[NodeManifest]:
    return registry.all_manifests()
```

**응답 예시:**
```json
[
  {
    "type": "planning.task_decomposition",
    "category": "cognitive",
    "label": "Planning",
    "description": "Decomposes the task into ordered sub-steps.",
    "inputs": [{ "id": "in", "label": "task", "dataType": "text", "required": true }],
    "outputs": [{ "id": "plan", "label": "plan", "dataType": "plan", "required": false }],
    "config": [
      {
        "key": "strategy",
        "label": "Strategy",
        "type": "select",
        "default": "decompose",
        "options": [
          { "label": "Decompose", "value": "decompose" },
          { "label": "Goal-first", "value": "goal" }
        ]
      }
    ]
  },
  ...
]
```

### `GET /api/architectures` / `POST` / `GET /{id}` / `DELETE /{id}` — v0.3

```
GET  /api/architectures         → 저장된 아키텍처 목록
POST /api/architectures         → 현재 Architecture JSON 저장
GET  /api/architectures/{id}    → 불러오기
DEL  /api/architectures/{id}    → 삭제
```

프론트 `restClient.ts`(현재 stub)가 이걸 호출한다.

---

## 5. WebSocket 엔드포인트 — 연동의 핵심

```
ws://localhost:8000/ws/run
```

### 5.1 연결 흐름

```
프론트                                백엔드
  │                                     │
  │── WebSocket connect ────────────────▶│
  │                                     │  accept()
  │── { kind: "run", architecture, input } ─▶│
  │                                     │  runId = uuid4()
  │                                     │  engine.run(arch, input, runId, queue)
  │◀── { kind: "event", event: node_start(node_1) } ──│
  │◀── { kind: "event", event: node_end(node_1) } ────│
  │◀── { kind: "event", event: node_start(node_2) } ──│
  │      ...                            │
  │◀── { kind: "event", event: node_end(last_node) } ─│
  │                                     │  (연결 유지 — 다음 run 대기)
  │── { kind: "stop", runId } ──────────▶│
  │                                     │  cancel()
```

### 5.2 구현

```python
# backend/ws/run_handler.py

import asyncio, json, uuid
from fastapi import WebSocket, WebSocketDisconnect
from ..execution.engine import ExecutionEngine
from ..ws.protocol import ClientMessage, EventMessage, ErrorMessage
from pydantic import TypeAdapter

_client_msg = TypeAdapter(ClientMessage)

async def run_ws(websocket: WebSocket):
    await websocket.accept()
    engine = ExecutionEngine()
    current_task: asyncio.Task | None = None

    try:
        while True:
            raw = await websocket.receive_text()
            msg = _client_msg.validate_json(raw)

            if msg.kind == "run":
                # 이전 실행 취소
                if current_task and not current_task.done():
                    current_task.cancel()

                queue: asyncio.Queue = asyncio.Queue()
                run_id = str(uuid.uuid4())

                # 실행은 별도 태스크 — 이벤트는 queue로 수신
                current_task = asyncio.create_task(
                    engine.run(msg.architecture, msg.input, run_id, queue)
                )

                # queue → WS 포워드 (실행 태스크와 병렬)
                asyncio.create_task(
                    _forward_events(websocket, queue, current_task)
                )

            elif msg.kind == "stop":
                if current_task and not current_task.done():
                    current_task.cancel()

    except WebSocketDisconnect:
        if current_task:
            current_task.cancel()


async def _forward_events(ws: WebSocket, queue: asyncio.Queue, task: asyncio.Task):
    while not task.done() or not queue.empty():
        try:
            event = await asyncio.wait_for(queue.get(), timeout=0.1)
            msg = EventMessage(kind="event", event=event)
            await ws.send_text(msg.model_dump_json())
        except asyncio.TimeoutError:
            continue
        except Exception:
            break
```

```python
# backend/main.py

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from .api.nodes import router as nodes_router
from .ws.run_handler import run_ws

app = FastAPI(title="Agentforge")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],   # Vite dev server
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(nodes_router)

@app.websocket("/ws/run")
async def websocket_run(ws):
    await run_ws(ws)
```

---

## 6. 노드 플러그인 시스템

### 6.1 NodeBase 추상 클래스

```python
# backend/nodes/base.py

from abc import ABC, abstractmethod
from .manifest import NodeManifest
from ..types.events import ExecutionEvent
import asyncio

class NodeBase(ABC):
    @classmethod
    @abstractmethod
    def manifest(cls) -> NodeManifest:
        """이 노드의 타입 정의. 프론트 팔레트에 표시된다."""
        ...

    @abstractmethod
    async def run(
        self,
        inputs: dict,           # 연결된 상류 노드들의 출력 { portId: value }
        config: dict,           # 사용자가 Inspector에서 설정한 값
        emit: callable,         # emit(ExecutionEvent) — 이벤트 발행
    ) -> dict:
        """실행 후 outputs dict 반환. { portId: value }"""
        ...
```

### 6.2 노드 구현 예시

```python
# backend/nodes/builtin/planning.py

import time
from ..base import NodeBase
from ..manifest import NodeManifest, Port, ConfigField
from ...types.events import ExecutionEvent, TokenUsage

class TaskDecompositionNode(NodeBase):
    @classmethod
    def manifest(cls) -> NodeManifest:
        return NodeManifest(
            type="planning.task_decomposition",
            category="cognitive",
            label="Planning",
            description="Decomposes the task into ordered sub-steps.",
            inputs=[Port(id="in", label="task", dataType="text", required=True)],
            outputs=[Port(id="plan", label="plan", dataType="plan")],
            config=[
                ConfigField(
                    key="strategy",
                    label="Strategy",
                    type="select",
                    default="decompose",
                    options=[
                        {"label": "Decompose", "value": "decompose"},
                        {"label": "Goal-first", "value": "goal"},
                    ],
                )
            ],
        )

    async def run(self, inputs: dict, config: dict, emit: callable) -> dict:
        task_text = inputs.get("in", "")
        strategy = config.get("strategy", "decompose")

        # 실제로는 LLM 호출
        result = {"steps": [f"[{strategy}] step 1", "step 2", "step 3"]}

        return {"plan": result}
```

### 6.3 레지스트리

```python
# backend/nodes/__init__.py

from .base import NodeBase
from .manifest import NodeManifest
from .builtin.io_input import InputNode
from .builtin.planning import TaskDecompositionNode
from .builtin.model_inference import ModelInferenceNode
from .builtin.policy_verification import PolicyVerificationNode
from .builtin.verification_critique import VerificationCritiqueNode
from .builtin.io_output import OutputNode

class NodeRegistry:
    def __init__(self):
        self._nodes: dict[str, type[NodeBase]] = {}

    def register(self, node_cls: type[NodeBase]):
        manifest = node_cls.manifest()
        self._nodes[manifest.type] = node_cls
        return node_cls          # 데코레이터로도 사용 가능

    def get(self, node_type: str) -> type[NodeBase] | None:
        return self._nodes.get(node_type)

    def all_manifests(self) -> list[NodeManifest]:
        return [cls.manifest() for cls in self._nodes.values()]

registry = NodeRegistry()
for cls in [
    InputNode,
    TaskDecompositionNode,
    ModelInferenceNode,
    PolicyVerificationNode,
    VerificationCritiqueNode,
    OutputNode,
]:
    registry.register(cls)
```

---

## 7. 실행 엔진

```python
# backend/execution/engine.py

import asyncio, time, uuid
from ..nodes import registry
from ..types.graph import Architecture
from ..types.events import ExecutionEvent, TokenUsage

class ExecutionEngine:
    async def run(
        self,
        arch: Architecture,
        input_data: object,
        run_id: str,
        queue: asyncio.Queue,
    ):
        """
        Architecture를 위상 정렬해서 노드를 순서대로 실행한다.
        각 노드 실행 전후에 node_start / node_end 이벤트를 emit한다.
        """
        async def emit(event: ExecutionEvent):
            await queue.put(event.stamp())

        order = self._topo_sort(arch)
        node_outputs: dict[str, dict] = {}   # nodeId → { portId: value }

        # 첫 노드에 input_data 주입
        if order:
            node_outputs["__input__"] = {"value": input_data}

        for node_id in order:
            node_cfg = next((n for n in arch.nodes if n.id == node_id), None)
            if not node_cfg:
                continue

            node_cls = registry.get(node_cfg.type)
            if not node_cls:
                await emit(ExecutionEvent(
                    eventType="error",
                    runId=run_id,
                    nodeId=node_id,
                    message=f"Unknown node type: {node_cfg.type}",
                ))
                continue

            # 상류 노드 출력을 portId로 묶어서 inputs 구성
            inputs = self._resolve_inputs(node_id, arch, node_outputs)

            await emit(ExecutionEvent(
                eventType="node_start",
                runId=run_id,
                nodeId=node_id,
                input=inputs,
            ))

            start = time.monotonic()
            try:
                node = node_cls()
                outputs = await node.run(inputs, node_cfg.config, emit)
                duration_ms = (time.monotonic() - start) * 1000
                node_outputs[node_id] = outputs

                await emit(ExecutionEvent(
                    eventType="node_end",
                    runId=run_id,
                    nodeId=node_id,
                    output=outputs,
                    durationMs=duration_ms,
                ))
            except asyncio.CancelledError:
                raise
            except Exception as e:
                await emit(ExecutionEvent(
                    eventType="error",
                    runId=run_id,
                    nodeId=node_id,
                    message=str(e),
                    durationMs=(time.monotonic() - start) * 1000,
                ))

    def _resolve_inputs(
        self,
        node_id: str,
        arch: Architecture,
        node_outputs: dict[str, dict],
    ) -> dict:
        """엣지를 따라 상류 노드의 출력 포트를 이 노드의 입력 포트로 연결."""
        inputs = {}
        for edge in arch.edges:
            if edge.target == node_id:
                source_out = node_outputs.get(edge.source, {})
                inputs[edge.targetHandle] = source_out.get(edge.sourceHandle)
        return inputs

    def _topo_sort(self, arch: Architecture) -> list[str]:
        """Kahn 알고리즘 위상 정렬."""
        from collections import deque
        indeg: dict[str, int] = {n.id: 0 for n in arch.nodes}
        adj: dict[str, list[str]] = {n.id: [] for n in arch.nodes}
        for e in arch.edges:
            if e.source in adj and e.target in indeg:
                adj[e.source].append(e.target)
                indeg[e.target] += 1
        queue = deque(nid for nid, d in indeg.items() if d == 0)
        order = []
        while queue:
            nid = queue.popleft()
            order.append(nid)
            for nxt in adj.get(nid, []):
                indeg[nxt] -= 1
                if indeg[nxt] == 0:
                    queue.append(nxt)
        return order if len(order) == len(arch.nodes) else [n.id for n in arch.nodes]
```

---

## 8. 프론트엔드 연결 — 딱 한 줄 변경

현재 프론트 `ui/src/transport/TransportContext.tsx`는 `MockTransport`를 쓰고 있다.  
백엔드가 올라오면 이 한 줄만 바꾸면 된다.

```tsx
// Before
const transport = new MockTransport()

// After
const transport = new WebSocketTransport('ws://localhost:8000/ws/run')
```

`WebSocketTransport`는 이미 `ui/src/transport/WebSocketTransport.ts`에 구현 준비가 되어 있다.  
(`Transport` 인터페이스를 동일하게 구현하므로 위층 코드는 아무것도 안 바뀐다.)

### CORS 설정 확인

백엔드 `main.py`에서 Vite dev 서버 오리진을 허용해야 한다.

```python
allow_origins=["http://localhost:5173"]
```

프로덕션에서는 실제 도메인으로 교체.

---

## 9. 단계별 구현 순서

### Phase 1 — 뼈대 연동 (v0.1)

목표: 프론트 Run 버튼 → 백엔드 실행 → 노드 하이라이트 동작

| 순서 | 작업 | 확인 방법 |
|------|------|-----------|
| 1 | FastAPI 앱 + CORS 설정 | `uvicorn backend.main:app` 실행됨 |
| 2 | `GET /api/nodes` — builtin manifest 6개 반환 | 프론트 팔레트에 노드 표시됨 |
| 3 | `ws://…/ws/run` 엔드포인트 수신 | WebSocket 연결 성공 |
| 4 | `run` 메시지 수신 → 더미 이벤트(node_start/end) 방출 | 노드 하이라이트 동작 |
| 5 | 실제 NodeBase 구현 + ExecutionEngine | 실제 노드 로직 실행 |

### Phase 2 — 실제 LLM 연동 (v0.2)

| 순서 | 작업 |
|------|------|
| 1 | `ModelInferenceNode` 에 Anthropic/OpenAI API 연결 |
| 2 | `tokenUsage` 를 실제 API 응답에서 추출해서 이벤트에 포함 |
| 3 | `PlanningNode`에 LLM 기반 task decomposition 구현 |
| 4 | `PolicyVerificationNode`에 confidence 판단 로직 구현 |
| 5 | Inspector의 output JSON이 실제 결과를 보여주는지 확인 |

### Phase 3 — 아키텍처 저장/불러오기 (v0.3)

| 순서 | 작업 |
|------|------|
| 1 | SQLite + SQLAlchemy 설정 |
| 2 | `POST /api/architectures` — 현재 Architecture JSON 저장 |
| 3 | `GET /api/architectures` — 목록 반환 |
| 4 | 프론트 `restClient.ts` 연결 |
| 5 | `rerun_from` WS 메시지 처리 — 특정 노드부터 재실행 |

---

## 10. 이벤트 타입별 프론트 처리 방식

백엔드가 발행하는 이벤트가 프론트에서 어떻게 처리되는지 알아야 의미 있는 이벤트를 보낼 수 있다.

| eventType | 프론트 동작 |
|-----------|------------|
| `node_start` | 해당 노드 테두리 amber 색, "● running" 배지 표시 |
| `node_end` | 테두리 green, "✓ done" 배지, footer에 ms/토큰 표시 |
| `error` | 테두리 red, "✕ failed" 배지 |
| `node_end` + `policyDecision.activated=false` | 노드 skipped 처리 (회색, "⊘ skipped") |
| `log` | LogPanel에 메시지 출력 (노드 상태 변경 없음) |
| `tool_call` | LogPanel에 tool 호출 기록 (v0.3에서 엣지 두께 반영) |

**중요**: `node_end` 이벤트의 `output` 필드는 Inspector 우측 패널에 JSON으로 그대로 표시된다.  
직렬화 가능한 형태로만 보내야 한다 (`str`, `dict`, `list` — no Python objects).

---

## 11. 개발 환경 설정

```bash
# Python 가상환경 (이미 생성됨)
source /Users/lico/Documents/ideas/agentforge/.venv/bin/activate

# 의존성 설치
pip install fastapi uvicorn pydantic langchain langchain-anthropic

# 실행
uvicorn backend.main:app --reload --port 8000

# 프론트와 동시 실행
# 터미널 1: uvicorn backend.main:app --reload
# 터미널 2: cd ui && npm run dev
```

### 환경 변수 (`.env`)

```
ANTHROPIC_API_KEY=sk-ant-...
OPENAI_API_KEY=sk-...         # 선택
DATABASE_URL=sqlite:///./agentforge.db
```

---

## 12. 나중에 LangGraph로 업그레이드

Phase 1~2는 위상 정렬 + 순차 실행으로 충분하다.  
v0.3+에서 분기(Policy 노드의 조건 라우팅), 병렬 실행, 재진입이 필요해지면 `ExecutionEngine`을  
**LangGraph `StateGraph`로 교체**한다.

```
Architecture.nodes/edges
        ↓
graph_builder.py: GraphNode/GraphEdge → LangGraph StateGraph
        ↓
StateGraph.compile().astream(input)
        ↓
각 이벤트 → ExecutionEvent → queue → WS
```

`graph_builder.py`의 인터페이스(`run(arch, input, run_id, queue)`)는 그대로 유지되므로  
`ExecutionEngine`의 `run()` 내부만 교체하면 위층(WS 핸들러)은 변경 없다.

이게 `ExecutionEngine`을 클래스로 감싼 이유다.
