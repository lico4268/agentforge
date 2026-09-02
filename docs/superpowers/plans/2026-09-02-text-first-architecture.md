# 텍스트 우선 아키텍처 저작 구현 계획

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 노드 캔버스를 아키텍처 저작 수단에서 내리고, `arch.yaml`(mermaid `flow:` + 사용자 정의 `nodes:`)로 에이전트 그래프를 짓게 한다.

**Architecture:** 새 모듈 `server/archfile.py`가 YAML을 읽어 기존 `compile_graph`가 먹는 `Architecture` dict로 변환한다. 사용자 정의 노드는 전부 `custom.node` 타입으로 나가므로 컴파일러는 대부분 무변경이다. 런타임 변경은 분기 일반화 하나뿐 — 라벨 달린 나가는 엣지가 둘 이상인 노드가 분기 노드가 된다. 프론트는 캔버스를 지우고 mermaid 그림 + 노드 진행 리스트만 남긴 읽기 전용 대시보드로 교체한다.

**Tech Stack:** Python 3.12 / FastAPI / LangGraph / PyYAML · React + TypeScript / Vite / Zustand / mermaid

**Spec:** `docs/superpowers/specs/2026-09-02-text-first-architecture-design.md`

## Global Constraints

- 백엔드 테스트는 `cd server && ../.venv/bin/python -m pytest`, 린트는 `cd server && ruff check .`
- 프론트 테스트는 `cd ui && npm run test`, **최종 확인은 반드시 `npm run build`** (`tsc -b`가 `tsc --noEmit`이 놓치는 오류를 잡은 전례가 있다)
- 착수 시점 기준선: 백엔드 pytest 209/209, 프론트 117/117(19 files), ruff clean. 각 태스크 종료 시 이 숫자가 줄지 않아야 한다 (삭제 태스크에서 줄어드는 건 정상 — 무엇이 왜 줄었는지 커밋 메시지에 적는다)
- 백엔드 Pydantic 필드명과 프론트 Zod 스키마는 **camelCase로 통일** (snake_case 변환 없음)
- `server/graphs/treatment.py`, `server/graphs/baseline.py`, `server/harness.py`는 **건드리지 않는다** — GSM8K 벤치마크 기준선 보존
- 브랜치: `text-first-arch` (이미 생성됨, `main` 기준)
- 커밋 메시지 말미에:
  ```
  Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
  Claude-Session: https://claude.ai/code/session_01TjeHp2KEmXXbbgS3wXgY3q
  ```

## 파일 구조

| 파일 | 책임 |
|---|---|
| `server/archfile.py` (신규) | `arch.yaml` 텍스트 → `Architecture` dict. 순수 함수, I/O 없음. mermaid 파싱 / 노드 변환 / 검증 / 가드 자동 삽입 |
| `server/tests/test_archfile.py` (신규) | 위 모듈 단위 테스트 |
| `server/graphs/compile.py` (수정) | 분기 판정을 타입 멤버십 → 그래프 구조 기준으로 일반화 |
| `server/main.py` (수정) | `GET /api/arch`, `GET /api/arch/{name}` 추가. WS `run`이 `archFile`을 받게 확장 |
| `ui/src/app/Dashboard.tsx` (신규) | 읽기 전용 대시보드 루트 |
| `ui/src/app/FlowDiagram.tsx` (신규) | mermaid 렌더 + 실행 상태 색칠 |
| `ui/src/app/NodeProgress.tsx` (신규) | 노드별 진행 리스트 + 출력 펼침 + 체크포인트 버튼 |
| `ui/src/canvas/**`, `ui/src/panels/Inspector.tsx` 등 (삭제) | Task 7 |

---

### Task 1: `flow:` 블록 파서 (mermaid → 엣지 리스트)

`flow:` 문자열을 엣지 리스트로 바꾸는 순수 함수. 이 태스크는 다른 어떤 것에도 의존하지 않는다.

**Files:**
- Create: `server/archfile.py`
- Test: `server/tests/test_archfile.py`

**Interfaces:**
- Consumes: 없음
- Produces:
  - `class ArchError(ValueError)` — 속성 `line: int | None`
  - `FlowEdge = TypedDict("FlowEdge", {"source": str, "target": str, "label": str, "line": int})`
  - `def parse_flow(text: str) -> list[FlowEdge]`

- [ ] **Step 1: 실패하는 테스트를 쓴다**

`server/tests/test_archfile.py`:

```python
import pytest

from archfile import ArchError, parse_flow


def test_simple_chain_splits_into_edges():
    edges = parse_flow("a --> b --> c")
    assert [(e["source"], e["target"], e["label"]) for e in edges] == [
        ("a", "b", ""),
        ("b", "c", ""),
    ]


def test_labelled_edge_keeps_label_verbatim():
    edges = parse_flow("review -->|재시도| reasoning")
    assert edges[0] == {
        "source": "review",
        "target": "reasoning",
        "label": "재시도",
        "line": 1,
    }


def test_blank_lines_and_comments_ignored():
    edges = parse_flow("a --> b\n\n%% 주석\n  \nb --> c")
    assert len(edges) == 2
    assert edges[1]["line"] == 5


def test_unicode_node_names_allowed():
    edges = parse_flow("입력 --> 초안 --> 출력")
    assert [e["source"] for e in edges] == ["입력", "초안"]


def test_malformed_line_raises_with_line_number():
    with pytest.raises(ArchError) as exc:
        parse_flow("a --> b\nthis is not an edge")
    assert exc.value.line == 2
    assert "this is not an edge" in str(exc.value)


def test_label_only_on_first_hop_of_chain():
    edges = parse_flow("a -->|go| b --> c")
    assert edges[0]["label"] == "go"
    assert edges[1]["label"] == ""
```

- [ ] **Step 2: 실패를 확인한다**

Run: `cd server && ../.venv/bin/python -m pytest tests/test_archfile.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'archfile'`

- [ ] **Step 3: 최소 구현**

`server/archfile.py`:

```python
"""arch.yaml → Architecture dict.

flow: 블록은 mermaid flowchart 문법 그대로다 — 자체 문법을 만들지 않는다.
그래서 같은 문자열을 브라우저 mermaid에 그대로 넘겨 그림을 그릴 수 있고,
파서는 정규식 하나로 끝난다 (설계 §3.2).
"""

import re
from typing import TypedDict


class ArchError(ValueError):
    """arch.yaml 거부 사유. line이 있으면 사용자에게 줄 번호를 보여준다."""

    def __init__(self, message: str, line: int | None = None):
        super().__init__(f"line {line}: {message}" if line else message)
        self.line = line


class FlowEdge(TypedDict):
    source: str
    target: str
    label: str
    line: int


# "a -->|label| b --> c" 를 훑는다. 라벨은 임의 문자열(어휘 아님, 설계 §3.1-3).
_HOP = re.compile(r"\s*-->\s*(?:\|(.*?)\|\s*)?")
_NAME = re.compile(r"[^\s|>-][^\s|]*")


def parse_flow(text: str) -> list[FlowEdge]:
    edges: list[FlowEdge] = []
    for lineno, raw in enumerate(text.splitlines(), start=1):
        line = raw.strip()
        if not line or line.startswith("%%"):
            continue
        edges.extend(_parse_flow_line(line, lineno))
    return edges


def _parse_flow_line(line: str, lineno: int) -> list[FlowEdge]:
    names: list[str] = []
    labels: list[str] = []
    pos = 0
    while pos < len(line):
        name = _NAME.match(line, pos)
        if not name:
            raise ArchError(f"cannot read node name in {line!r}", lineno)
        names.append(name.group(0))
        pos = name.end()
        if pos >= len(line):
            break
        hop = _HOP.match(line, pos)
        if not hop:
            raise ArchError(f"expected '-->' in {line!r}", lineno)
        labels.append(hop.group(1) or "")
        pos = hop.end()
    if len(names) < 2:
        raise ArchError(f"not an edge: {line!r}", lineno)
    return [
        FlowEdge(source=names[i], target=names[i + 1], label=labels[i], line=lineno)
        for i in range(len(names) - 1)
    ]
```

- [ ] **Step 4: 통과를 확인한다**

Run: `cd server && ../.venv/bin/python -m pytest tests/test_archfile.py -v`
Expected: 6 passed

- [ ] **Step 5: 린트 후 커밋**

```bash
cd server && ruff check . && cd ..
git add server/archfile.py server/tests/test_archfile.py
git commit -m "feat(arch): mermaid flow 블록 파서

flow: 를 자체 문법 대신 mermaid flowchart 문법으로 읽는다 — 같은 문자열을
브라우저 렌더러에 그대로 넘길 수 있고 파서는 정규식 하나로 끝난다.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01TjeHp2KEmXXbbgS3wXgY3q"
```

---

### Task 2: `arch.yaml` → Architecture dict

`flow:` 엣지와 `nodes:` 정의를 합쳐 `compile_graph`가 먹는 dict를 만든다. 사용자 정의 노드는 전부 `custom.node` 타입으로 나가므로 컴파일러 변경이 필요 없다.

**Files:**
- Modify: `server/archfile.py`
- Test: `server/tests/test_archfile.py`

**Interfaces:**
- Consumes: Task 1의 `parse_flow`, `ArchError`
- Produces:
  - `def parse_arch(text: str) -> tuple[dict, list[str]]` — `(architecture, warnings)`
  - 상수 `PREDEFINED = {"input": "io.input", "output": "io.output", "human.checkpoint": "human.checkpoint", "loop.guard": "loop.guard"}`

- [ ] **Step 1: 실패하는 테스트를 쓴다**

`server/tests/test_archfile.py`에 추가:

```python
from archfile import parse_arch

STARTER = """
name: 테스트 그래프
model: google/gemini-3.1-flash-lite

flow: |
  input --> 초안 --> 검토 --> output

nodes:
  초안:
    in:  [task]
    out: [draft]
    prompt: 빠르게 답을 내라.
  검토:
    in:  [task, draft]
    out: [answer]
    model: anthropic/claude-opus-5
    prompt: 허점을 짚어 고쳐라.
"""


def test_user_nodes_become_custom_node_type():
    arch, _ = parse_arch(STARTER)
    by_id = {n["id"]: n for n in arch["nodes"]}
    assert by_id["초안"]["type"] == "custom.node"
    assert by_id["초안"]["config"]["systemPrompt"] == "빠르게 답을 내라."
    assert by_id["초안"]["config"]["outputs"] == [{"id": "draft", "label": "draft"}]
    assert by_id["초안"]["config"]["inputs"] == [{"id": "task", "label": "task"}]


def test_boundary_nodes_get_predefined_types():
    arch, _ = parse_arch(STARTER)
    by_id = {n["id"]: n for n in arch["nodes"]}
    assert by_id["input"]["type"] == "io.input"
    assert by_id["output"]["type"] == "io.output"


def test_node_model_overrides_default():
    arch, _ = parse_arch(STARTER)
    by_id = {n["id"]: n for n in arch["nodes"]}
    assert by_id["초안"]["config"]["modelSlots"][0]["model"] == "gemini-3.1-flash-lite"
    assert by_id["초안"]["config"]["modelSlots"][0]["provider"] == "google"
    assert by_id["검토"]["config"]["modelSlots"][0]["model"] == "claude-opus-5"
    assert by_id["검토"]["config"]["modelSlots"][0]["provider"] == "anthropic"


def test_edges_carry_label_as_source_role():
    arch, _ = parse_arch("""
flow: |
  a -->|ok| b
nodes:
  a: { out: [x], prompt: p }
  b: { in: [x], out: [y], prompt: q }
""")
    e = arch["edges"][0]
    assert e["source"] == "a"
    assert e["target"] == "b"
    assert e["sourceRole"] == "ok"
    assert e["sourceHandle"] == "ok"


def test_flow_node_missing_from_nodes_raises():
    with pytest.raises(ArchError) as exc:
        parse_arch("""
flow: |
  a --> ghost
nodes:
  a: { out: [x], prompt: p }
""")
    assert "ghost" in str(exc.value)
    assert exc.value.line == 3


def test_input_name_with_no_producer_raises():
    with pytest.raises(ArchError) as exc:
        parse_arch("""
flow: |
  a --> b
nodes:
  a: { out: [x], prompt: p }
  b: { in: [나없음], out: [y], prompt: q }
""")
    assert "나없음" in str(exc.value)


def test_optional_input_marker_skips_producer_check():
    arch, _ = parse_arch("""
flow: |
  a --> b
nodes:
  a: { out: [x], prompt: p }
  b: { in: [x, feedback?], out: [y], prompt: q }
""")
    by_id = {n["id"]: n for n in arch["nodes"]}
    assert by_id["b"]["config"]["inputs"] == [
        {"id": "x", "label": "x"},
        {"id": "feedback", "label": "feedback"},
    ]


def test_duplicate_output_name_warns_but_parses():
    arch, warnings = parse_arch("""
flow: |
  a --> b --> output
nodes:
  a: { out: [answer], prompt: p }
  b: { in: [answer], out: [answer], prompt: q }
""")
    assert arch is not None
    assert any("answer" in w for w in warnings)


def test_predefined_run_node():
    arch, _ = parse_arch("""
flow: |
  a --> 승인 --> output
nodes:
  a: { out: [x], prompt: p }
  승인: { run: human.checkpoint }
""")
    by_id = {n["id"]: n for n in arch["nodes"]}
    assert by_id["승인"]["type"] == "human.checkpoint"


def test_unknown_run_value_raises():
    with pytest.raises(ArchError) as exc:
        parse_arch("""
flow: |
  a --> b
nodes:
  a: { out: [x], prompt: p }
  b: { run: no.such.thing }
""")
    assert "no.such.thing" in str(exc.value)
```

- [ ] **Step 2: 실패를 확인한다**

Run: `cd server && ../.venv/bin/python -m pytest tests/test_archfile.py -v`
Expected: FAIL — `ImportError: cannot import name 'parse_arch'`

- [ ] **Step 3: 최소 구현**

`server/archfile.py`에 추가 (파일 상단 import에 `yaml` 추가):

```python
import yaml

# 사용자가 프롬프트로 만들 수 없는 노드 — 경계와 런타임 장치뿐이다 (설계 §2).
PREDEFINED = {
    "input": "io.input",
    "output": "io.output",
    "human.checkpoint": "human.checkpoint",
    "loop.guard": "loop.guard",
}

# 사용자 정의 노드가 나가는 타입. 매니페스트가 빈 llm_step 노드라 compile_graph가
# config.inputs/outputs/systemPrompt를 그대로 읽는다 (설계 §4).
USER_NODE_TYPE = "custom.node"


def _split_model(spec: str) -> tuple[str, str]:
    """'google/gemini-3.1-flash-lite' → ('google', 'gemini-3.1-flash-lite')."""
    provider, _, model = spec.partition("/")
    if not model:
        raise ArchError(f"model must be 'provider/model', got {spec!r}")
    return provider, model


def _ports(names: list[str]) -> list[dict]:
    return [{"id": n.rstrip("?"), "label": n.rstrip("?")} for n in names]


def parse_arch(text: str) -> tuple[dict, list[str]]:
    """arch.yaml 텍스트 → (Architecture dict, 경고 목록)."""
    doc = yaml.safe_load(text) or {}
    flow_text = doc.get("flow") or ""
    raw_nodes = doc.get("nodes") or {}
    default_model = doc.get("model")

    flow_edges = parse_flow(flow_text)
    referenced = {n for e in flow_edges for n in (e["source"], e["target"])}

    nodes: list[dict] = []
    produced: dict[str, str] = {}  # out 이름 → 그걸 만든 노드 id
    warnings: list[str] = []

    for name in referenced:
        spec = raw_nodes.get(name)
        if spec is None and name not in PREDEFINED:
            line = next(
                e["line"] for e in flow_edges if name in (e["source"], e["target"])
            )
            raise ArchError(f"node {name!r} is used in flow but not defined in nodes:", line)
        nodes.append(_build_node(name, spec or {}, default_model, produced, warnings))

    for name, spec in raw_nodes.items():
        if name not in referenced:
            warnings.append(f"node {name!r} is defined but never used in flow:")

    _validate_inputs(raw_nodes, produced)

    edges = [
        {
            "id": f"e{i}",
            "source": e["source"],
            "target": e["target"],
            "sourceHandle": e["label"] or "out",
            "sourceRole": e["label"],
            "targetHandle": "in",
        }
        for i, e in enumerate(flow_edges)
    ]
    return {
        "version": "0.1",
        "metadata": {"name": doc.get("name") or "untitled"},
        "nodes": nodes,
        "edges": edges,
        "flow": flow_text,  # 프론트 mermaid 렌더용 원본 문자열
    }, warnings


def _build_node(
    name: str, spec: dict, default_model: str | None, produced: dict, warnings: list
) -> dict:
    run = spec.get("run")
    if run is not None or name in PREDEFINED:
        type_ = PREDEFINED.get(run or name)
        if type_ is None:
            raise ArchError(f"unknown run: {run!r} — expected one of {sorted(PREDEFINED)}")
        config = {k: v for k, v in spec.items() if k != "run"}
        if "max" in config:
            config["maxIterations"] = config.pop("max")
        return {"id": name, "type": type_, "position": {"x": 0, "y": 0}, "config": config}

    outs = spec.get("out") or []
    for out in outs:
        if out in produced:
            warnings.append(
                f"nodes {produced[out]!r} and {name!r} both write {out!r} — "
                "the later one wins; rename if that is not intended"
            )
        produced[out] = name

    model_spec = spec.get("model") or default_model
    slots = []
    if model_spec:
        provider, model = _split_model(model_spec)
        slots = [
            {
                "id": f"slot-{name}",
                "provider": provider,
                "model": model,
                "temperature": 0,
                "role": "",
            }
        ]
    return {
        "id": name,
        "type": USER_NODE_TYPE,
        "position": {"x": 0, "y": 0},
        "config": {
            "label": name,
            "systemPrompt": spec.get("prompt") or "",
            "inputs": _ports(spec.get("in") or []),
            "outputs": _ports(outs),
            "modelSlots": slots,
        },
    }


# compile.py의 _PRESEEDED_STATE_KEYS와 같은 뜻 — 실행 시작 시 이미 상태에 있는 값들.
_PRESEEDED = {"task", "task_tags", "intent", "criteria", "batch_mode"}


def _validate_inputs(raw_nodes: dict, produced: dict) -> None:
    for name, spec in raw_nodes.items():
        if not isinstance(spec, dict):
            continue
        for want in spec.get("in") or []:
            if want.endswith("?"):
                continue  # 선택 입력 — 만드는 노드가 없어도 된다 (설계 §5.1)
            if want not in produced and want not in _PRESEEDED:
                raise ArchError(
                    f"node {name!r} reads {want!r} but no node writes it — "
                    f"add it to some node's out:, or mark it optional as {want}?"
                )
```

- [ ] **Step 4: 통과를 확인한다**

Run: `cd server && ../.venv/bin/python -m pytest tests/test_archfile.py -v`
Expected: 16 passed

- [ ] **Step 5: 실제로 컴파일되는지 확인하는 통합 테스트를 추가한다**

`server/tests/test_archfile.py`에 추가:

```python
from graphs.compile import compile_graph


async def _noop_emit(_event):
    return None


def test_parsed_arch_compiles_with_compile_graph():
    arch, _ = parse_arch(STARTER)
    graph = compile_graph(
        arch,
        {"provider": "google", "model": "gemini-3.1-flash-lite", "temperature": 0},
        _noop_emit,
        "test-run",
    )
    assert graph is not None
```

- [ ] **Step 6: 통합 테스트 통과를 확인한다**

Run: `cd server && ../.venv/bin/python -m pytest tests/test_archfile.py -v`
Expected: 17 passed. 실패하면 `compile_graph`가 요구하는 필드가 무엇인지 에러 메시지를 읽고 `_build_node`를 맞춘다 — **컴파일러를 고치지 말 것.** 이 태스크의 요점은 컴파일러 무변경이다.

- [ ] **Step 7: 린트 후 커밋**

```bash
cd server && ruff check . && ../.venv/bin/python -m pytest && cd ..
git add server/archfile.py server/tests/test_archfile.py
git commit -m "feat(arch): arch.yaml → Architecture dict 변환

사용자 정의 노드를 custom.node 타입으로 내보내 compile_graph를 무변경으로
재사용한다. in/out 이름으로 데이터가 맞물리므로 포트 핸들 수동 매칭이 없다.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01TjeHp2KEmXXbbgS3wXgY3q"
```

---

### Task 3: 루프 가드 자동 삽입

뒤로 가는 화살표를 발견하면 기본 가드 노드를 끼워 넣는다. 사용자가 가드를 명시하면 건드리지 않는다.

**Files:**
- Modify: `server/archfile.py`
- Test: `server/tests/test_archfile.py`

**Interfaces:**
- Consumes: Task 2의 `parse_arch`, `PREDEFINED`
- Produces: `parse_arch`의 동작 확장 (시그니처 불변). 삽입되는 노드 id는 `__guard_1`, `__guard_2`, … 이며 `type: "loop.guard"`

- [ ] **Step 1: 실패하는 테스트를 쓴다**

`server/tests/test_archfile.py`에 추가:

```python
LOOPED = """
flow: |
  input --> 풀이 --> 검토
  검토 -->|ok|    output
  검토 -->|retry| 풀이

nodes:
  풀이:  { in: [task, feedback?], out: [answer], prompt: 풀어라 }
  검토:  { in: [task, answer],    out: [verdict, feedback], prompt: 검토하라 }
"""


def test_back_edge_gets_default_guard_inserted():
    arch, _ = parse_arch(LOOPED)
    guards = [n for n in arch["nodes"] if n["type"] == "loop.guard"]
    assert len(guards) == 1
    assert guards[0]["id"] == "__guard_1"
    assert guards[0]["config"]["maxIterations"] == 3


def test_inserted_guard_is_wired_between_and_to_terminal():
    arch, _ = parse_arch(LOOPED)
    by_src = {}
    for e in arch["edges"]:
        by_src.setdefault(e["source"], []).append(e)
    # 검토 --retry--> __guard_1 로 바뀌었고 풀이로 직접 가지 않는다
    retry = [e for e in by_src["검토"] if e["sourceRole"] == "retry"][0]
    assert retry["target"] == "__guard_1"
    guard_targets = {e["sourceRole"]: e["target"] for e in by_src["__guard_1"]}
    assert guard_targets == {"loopBack": "풀이", "exit": "output"}


def test_explicit_guard_is_left_alone():
    arch, _ = parse_arch("""
flow: |
  input --> 풀이 --> 검토
  검토 -->|ok|    output
  검토 -->|retry| retry5
  retry5 -->|loopBack| 풀이
  retry5 -->|exit|     output
nodes:
  풀이:   { in: [task], out: [answer], prompt: p }
  검토:   { in: [answer], out: [verdict], prompt: q }
  retry5: { run: loop.guard, max: 5 }
""")
    guards = [n for n in arch["nodes"] if n["type"] == "loop.guard"]
    assert [g["id"] for g in guards] == ["retry5"]
    assert guards[0]["config"]["maxIterations"] == 5


def test_ambiguous_exit_raises():
    with pytest.raises(ArchError) as exc:
        parse_arch("""
flow: |
  input --> 풀이 --> 검토
  검토 -->|a| out1
  검토 -->|b| out2
  검토 -->|retry| 풀이
nodes:
  풀이: { in: [task], out: [answer], prompt: p }
  검토: { in: [answer], out: [v], prompt: q }
  out1: { run: output }
  out2: { run: output }
""")
    assert "exit" in str(exc.value).lower()
```

- [ ] **Step 2: 실패를 확인한다**

Run: `cd server && ../.venv/bin/python -m pytest tests/test_archfile.py -k guard -v`
Expected: FAIL — 가드 노드가 삽입되지 않아 `len(guards) == 0`

- [ ] **Step 3: 최소 구현**

`server/archfile.py`에 추가하고, `parse_arch`의 `return` 직전에 `nodes, edges = _insert_guards(nodes, edges)`를 호출한다:

```python
DEFAULT_MAX_ITERATIONS = 3


def _back_edges(nodes: list[dict], edges: list[dict]) -> list[dict]:
    """flow의 등장 순서를 위상 근사로 삼아, 뒤로 가는 엣지를 고른다.
    노드 순서는 첫 등장 순이므로 target이 source보다 앞서면 뒤로 가는 엣지다.
    """
    order = {n["id"]: i for i, n in enumerate(nodes)}
    return [e for e in edges if order.get(e["target"], 0) <= order.get(e["source"], 0)]


def _terminal_node_id(nodes: list[dict], edges: list[dict]) -> str:
    """나가는 엣지가 없는 노드. 정확히 하나여야 한다."""
    sources = {e["source"] for e in edges}
    terminals = [n["id"] for n in nodes if n["id"] not in sources]
    if len(terminals) != 1:
        raise ArchError(
            f"cannot pick a loop exit target — found {len(terminals)} terminal nodes "
            f"{sorted(terminals)}; declare the guard explicitly with "
            "{ run: loop.guard, max: N } and wire its exit edge"
        )
    return terminals[0]


def _insert_guards(nodes: list[dict], edges: list[dict]) -> tuple[list[dict], list[dict]]:
    """가드 없는 뒤로 가는 엣지마다 기본 가드를 끼운다 (설계 §5.1).

    a -->|retry| b  ⇒  a -->|retry| __guard_N,
                        __guard_N -->|loopBack| b, __guard_N -->|exit| <terminal>
    """
    guard_ids = {n["id"] for n in nodes if n["type"] == "loop.guard"}
    pending = [e for e in _back_edges(nodes, edges) if e["source"] not in guard_ids]
    if not pending:
        return nodes, edges

    terminal = _terminal_node_id(nodes, edges)
    for i, edge in enumerate(pending, start=1):
        gid = f"__guard_{i}"
        nodes.append(
            {
                "id": gid,
                "type": "loop.guard",
                "position": {"x": 0, "y": 0},
                "config": {
                    "kind": "critiqueRevise",
                    "maxIterations": DEFAULT_MAX_ITERATIONS,
                    "onExhaustion": "exit",
                    "synthetic": True,  # 대시보드가 "기본값"으로 표시하는 근거
                },
            }
        )
        loop_target = edge["target"]
        edge["target"] = gid
        edges.append(
            {
                "id": f"{gid}-back",
                "source": gid,
                "target": loop_target,
                "sourceHandle": "loopBack",
                "sourceRole": "loopBack",
                "targetHandle": "in",
            }
        )
        edges.append(
            {
                "id": f"{gid}-exit",
                "source": gid,
                "target": terminal,
                "sourceHandle": "exit",
                "sourceRole": "exit",
                "targetHandle": "in",
            }
        )
    return nodes, edges
```

- [ ] **Step 4: 통과를 확인한다**

Run: `cd server && ../.venv/bin/python -m pytest tests/test_archfile.py -v`
Expected: 21 passed

- [ ] **Step 5: 루프 그래프가 실제로 컴파일되는지 확인한다**

`server/tests/test_archfile.py`에 추가:

```python
def test_looped_arch_compiles():
    arch, _ = parse_arch(LOOPED)
    graph = compile_graph(
        arch,
        {"provider": "google", "model": "gemini-3.1-flash-lite", "temperature": 0},
        _noop_emit,
        "test-run",
    )
    assert graph is not None
```

Run: `cd server && ../.venv/bin/python -m pytest tests/test_archfile.py -v`
Expected: 22 passed. `_validate_gated_cycles`가 통과해야 한다 — 실패하면 삽입된 가드가 사이클 안에 들어가 있지 않다는 뜻이므로 `_insert_guards`의 배선을 고친다.

- [ ] **Step 6: 린트 후 커밋**

```bash
cd server && ruff check . && ../.venv/bin/python -m pytest && cd ..
git add server/archfile.py server/tests/test_archfile.py
git commit -m "feat(arch): 뒤로 가는 화살표에 기본 가드 자동 삽입

루프를 그리는 데 필요한 최소 표기를 화살표 하나로 줄인다. 예산을 정하고 싶으면
가드를 이름 있는 노드로 꺼내면 되고, 탈출 지점이 애매하면 추측 대신 에러를 낸다.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01TjeHp2KEmXXbbgS3wXgY3q"
```

---

### Task 4: 분기 일반화

지금은 `review.intent`/`human.checkpoint`/`loop.guard` 세 타입만 분기할 수 있다. 이를 그래프 구조 기준으로 바꾼다 — **라벨 달린 나가는 엣지가 둘 이상인 노드는 분기 노드다.**

**Files:**
- Modify: `server/graphs/compile.py:32-92` (`_OUTPUT_SCHEMA_TYPES`, `_build_output_model`, `_effective_output_schema`, `_llm_step_spec`), `:214-268` (`_make_llm_step_node`), `:596` (`_CONDITIONAL_ROUTING_TYPES` 주변), `:652` (`compile_graph`)
- Test: `server/tests/test_compile.py`

**Interfaces:**
- Consumes: Task 2/3이 만드는 Architecture dict (엣지에 `sourceRole`이 라벨로 들어있음)
- Produces:
  - `def _branch_labels(node_id: str, edges: list[dict]) -> list[str]` — 라벨 달린 나가는 엣지가 2개 이상이면 라벨 목록, 아니면 `[]`
  - 분기 노드의 상태 기록 키: `__route__<node_id>` (노드마다 달라 충돌하지 않음)

- [ ] **Step 1: 실패하는 테스트를 쓴다**

`server/tests/test_compile.py`에 추가 (파일 상단 import에 `from graphs.compile import _branch_labels` 추가):

```python
def test_branch_labels_needs_two_labelled_edges():
    edges = [
        {"source": "a", "target": "b", "sourceRole": "ok"},
        {"source": "a", "target": "c", "sourceRole": "no"},
        {"source": "b", "target": "c", "sourceRole": ""},
    ]
    assert _branch_labels("a", edges) == ["ok", "no"]
    assert _branch_labels("b", edges) == []


def test_branch_labels_ignores_unlabelled_fanout():
    edges = [
        {"source": "a", "target": "b", "sourceRole": ""},
        {"source": "a", "target": "c", "sourceRole": ""},
    ]
    assert _branch_labels("a", edges) == []


def test_user_node_with_labels_gets_route_field_in_output_model():
    from archfile import parse_arch
    from graphs.compile import _effective_output_schema, MANIFESTS_BY_TYPE

    arch, _ = parse_arch("""
flow: |
  input --> 판단
  판단 -->|좋음| output
  판단 -->|나쁨| output2
nodes:
  판단:   { in: [task], out: [verdict], prompt: p }
  output2: { run: output }
""")
    node = next(n for n in arch["nodes"] if n["id"] == "판단")
    schema = _effective_output_schema(
        node, MANIFESTS_BY_TYPE[node["type"]], branch_labels=["좋음", "나쁨"]
    )
    assert schema["verdict"] == "string"
    assert schema["route"] == ["좋음", "나쁨"]


def test_branching_user_node_compiles():
    from archfile import parse_arch

    async def _emit(_e):
        return None

    arch, _ = parse_arch("""
flow: |
  input --> 판단
  판단 -->|좋음| output
  판단 -->|나쁨| 재작업
  재작업 --> output
nodes:
  판단:   { in: [task], out: [verdict], prompt: p }
  재작업: { in: [task], out: [answer], prompt: q }
""")
    graph = compile_graph(
        arch,
        {"provider": "google", "model": "gemini-3.1-flash-lite", "temperature": 0},
        _emit,
        "r1",
    )
    assert graph is not None
```

- [ ] **Step 2: 실패를 확인한다**

Run: `cd server && ../.venv/bin/python -m pytest tests/test_compile.py -k branch -v`
Expected: FAIL — `ImportError: cannot import name '_branch_labels'`

- [ ] **Step 3: `_branch_labels`와 `route` 스키마를 구현한다**

`server/graphs/compile.py`:

```python
def _branch_labels(node_id: str, edges: list[dict]) -> list[str]:
    """이 노드가 분기 노드인지를 타입이 아니라 그래프 구조로 판정한다 (설계 §5).

    라벨(sourceRole) 달린 나가는 엣지가 둘 이상이면 분기 노드이고, 그 라벨들이
    곧 LLM이 고를 선택지다. 라벨 없는 fan-out은 분기가 아니라 병렬 실행이다.
    """
    labels = [
        e.get("sourceRole") or "" for e in edges if e["source"] == node_id
    ]
    labelled = [label for label in labels if label]
    return labelled if len(labelled) >= 2 else []
```

`_effective_output_schema`에 `branch_labels` 인자를 추가한다 (기본값 `None` — 기존 호출부 무변화):

```python
def _effective_output_schema(
    node: dict, manifest: dict, branch_labels: list[str] | None = None
) -> dict[str, Any]:
    defaults = manifest.get("defaults") or {}
    output_schema = dict(defaults.get("outputSchema") or {})
    if not output_schema:
        config = node.get("config") or {}
        output_ports = config.get("outputs") or manifest.get("outputs") or []
        output_schema = {p["id"]: "string" for p in output_ports}
    if branch_labels:
        # 분기 노드는 어디로 갈지 스스로 고른다 — 라벨 목록이 곧 Literal 선택지.
        output_schema["route"] = branch_labels
    return output_schema
```

`_build_output_model`이 리스트 값을 `Literal`로 다루게 한다 (파일 상단에 `from typing import Literal` 추가):

```python
def _build_output_model(node_type: str, output_schema: dict[str, Any]) -> type[BaseModel]:
    fields: dict[str, Any] = {}
    for key, spec in output_schema.items():
        if isinstance(spec, list):
            # 분기 라벨 목록 → Literal["a", "b"] — LLM이 이 중 하나만 낼 수 있다.
            fields[key] = (Literal[tuple(spec)], ...)
        else:
            fields[key] = (_OUTPUT_SCHEMA_TYPES[spec], ...)
    return create_model(f"{node_type}_Out", **fields)
```

- [ ] **Step 4: `_branch_labels` 단위 테스트 통과를 확인한다**

Run: `cd server && ../.venv/bin/python -m pytest tests/test_compile.py -k "branch_labels or route_field" -v`
Expected: 3 passed

- [ ] **Step 5: 라우팅 배선을 구현한다**

`_llm_step_spec`이 `branch_labels`를 받아 `route`를 노드별 상태 키에 쓰게 한다. `compile.py:76-92`의 함수 전체를 다음으로 교체한다:

```python
def _llm_step_spec(
    node: dict, manifest: dict, branch_labels: list[str] | None = None
) -> dict[str, Any]:
    """매니페스트 defaults(+ Phase B④: 인스턴스 config)에서 llm_step 노드 실행에
    필요한 모든 것을 유도한다 — output_model(동적 Pydantic 모델), extra_inputs(포트에
    없는, state에서 직접 읽는 입력), writes, key_map(LLM 출력 필드명 → AgentState 키,
    다르면 outputKeyMap로 선언).

    branch_labels가 있으면 이 노드는 분기 노드다 — route 필드를 스키마에 더하고,
    노드마다 다른 상태 키(__route__<id>)에 쓰도록 key_map을 확장한다. 그래야 분기
    노드가 여럿이어도 서로의 route 값을 덮어쓰지 않는다.
    """
    defaults = manifest.get("defaults") or {}
    output_schema = _effective_output_schema(node, manifest, branch_labels)
    key_map = defaults.get("outputKeyMap") or {}
    if branch_labels:
        key_map = {**key_map, "route": f"__route__{node['id']}"}
    extra_inputs = [(f["id"], f["label"]) for f in defaults.get("extraInputs") or []]
    return {
        "output_model": _build_output_model(node["type"], output_schema),
        "extra_inputs": extra_inputs,
        "writes": [key_map.get(k, k) for k in output_schema],
        "key_map": key_map,
    }
```

`_make_llm_step_node`(`:214`)는 시그니처 끝에 `branch_labels: list[str] | None = None`을 추가하고, 본문 첫 줄의 `spec = _llm_step_spec(node, manifest)`를 `spec = _llm_step_spec(node, manifest, branch_labels)`로 바꾼다. 그 외 본문은 손대지 않는다 — `write_state_value`가 `__route__<id>`를 `vars`에 넣어주고, `_output_write_keys`도 `_llm_step_spec`을 거치므로 자동으로 맞는다.

`compile_graph`가 `_make_llm_step_node`를 호출하는 자리에 `branch_labels=_branch_labels(node_id, edges)`를 넘긴다.

`compile_graph`에서, 각 노드를 등록한 뒤 분기 배선을 건다:

```python
    for node in nodes:
        node_id = node["id"]
        node_type = node["type"]
        if node_type in _CONDITIONAL_ROUTING_TYPES:
            continue  # 특수 노드는 기존 경로 유지 (런타임이 라벨을 정한다)
        labels = _branch_labels(node_id, edges)
        if not labels:
            continue
        targets = {
            (e.get("sourceRole") or ""): e["target"]
            for e in edges
            if e["source"] == node_id and e.get("sourceRole")
        }
        graph.add_conditional_edges(
            node_id,
            _make_router(node_id, labels),
            targets,
        )
```

라우터는 순수 함수로 뺀다:

```python
def _make_router(node_id: str, labels: list[str]):
    """분기 노드가 상태에 쓴 __route__<id> 값을 읽어 라벨을 돌려준다.
    값이 없거나 모르는 라벨이면 첫 번째 라벨로 떨어뜨린다 — 구조화 출력이
    Literal을 강제하므로 정상 경로에서는 도달하지 않는다."""

    def route(state: AgentState) -> str:
        value = read_state_value(state, f"__route__{node_id}")
        return value if value in labels else labels[0]

    return route
```

분기 노드가 `_build_plain_edge_plan`에서도 제외되어야 이중 배선이 되지 않는다. `_build_plain_edge_plan`에 `branch_node_ids: set[str]` 인자를 추가하고, `source_type in _CONDITIONAL_ROUTING_TYPES` 검사 옆에 `or e["source"] in branch_node_ids`를 더한다. `compile_graph`는 호출 전에 다음을 만든다:

```python
    branch_node_ids = {
        n["id"]
        for n in nodes
        if n["type"] not in _CONDITIONAL_ROUTING_TYPES and _branch_labels(n["id"], edges)
    }
```

- [ ] **Step 6: 전체 테스트 통과를 확인한다**

Run: `cd server && ../.venv/bin/python -m pytest -v`
Expected: 기존 209 + 신규 전부 통과. **기존 테스트가 하나라도 깨지면 `_branch_labels`가 기존 아키텍처의 엣지를 분기로 오인한 것이다** — 기존 저장 아키텍처는 `sourceRole`이 없고 `sourceHandle`만 있으므로 `_branch_labels`가 `sourceRole`만 본다는 점을 재확인한다.

- [ ] **Step 7: 린트 후 커밋**

```bash
cd server && ruff check . && ../.venv/bin/python -m pytest && cd ..
git add server/graphs/compile.py server/tests/test_compile.py
git commit -m "feat(compile): 분기 판정을 타입 멤버십에서 그래프 구조로 일반화

라벨 달린 나가는 엣지가 둘 이상인 노드는 분기 노드가 되고, 라벨 목록이 출력
스키마의 Literal 선택지가 된다. 사용자 정의 노드가 자유로워진 이상 분기만 고정
3종 타입에 묶어둘 수 없다.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01TjeHp2KEmXXbbgS3wXgY3q"
```

---

### Task 5: REST + WS 연동

브라우저가 `arch.yaml` 목록을 읽고, 파일 이름으로 실행을 요청할 수 있게 한다.

**Files:**
- Create: `server/arch_files.py`
- Modify: `server/main.py:92-117` (라우트 추가), `:210-232` (`dispatch_graph`), `:287+` (`ws_run`)
- Test: `server/tests/test_arch_files.py`

**Interfaces:**
- Consumes: Task 2/3의 `parse_arch`, `ArchError`
- Produces:
  - `def list_arch_files() -> list[dict]` — `[{"name": "gsm8k.yaml", "size": 412}]`
  - `def read_arch_file(name: str) -> dict` — `{"name", "text", "architecture", "warnings"}`
  - `GET /api/arch`, `GET /api/arch/{name}`
  - WS `run` 메시지가 `architecture` 대신 `archFile: "<name>"`도 받는다

- [ ] **Step 1: 실패하는 테스트를 쓴다**

`server/tests/test_arch_files.py`:

```python
import pytest
from fastapi.testclient import TestClient

import arch_files
from main import app

SAMPLE = """
name: 샘플
flow: |
  input --> 풀이 --> output
nodes:
  풀이: { in: [task], out: [answer], prompt: 풀어라 }
"""


@pytest.fixture
def arch_dir(tmp_path, monkeypatch):
    (tmp_path / "sample.yaml").write_text(SAMPLE, encoding="utf-8")
    monkeypatch.setattr(arch_files, "ARCH_DIR", tmp_path)
    return tmp_path


def test_list_arch_files(arch_dir):
    names = [f["name"] for f in arch_files.list_arch_files()]
    assert names == ["sample.yaml"]


def test_read_arch_file_returns_text_and_architecture(arch_dir):
    result = arch_files.read_arch_file("sample.yaml")
    assert result["name"] == "sample.yaml"
    assert "flow:" in result["text"]
    assert {n["id"] for n in result["architecture"]["nodes"]} == {"input", "풀이", "output"}
    assert result["warnings"] == []


def test_read_rejects_path_traversal(arch_dir):
    with pytest.raises(ValueError):
        arch_files.read_arch_file("../../etc/passwd")


def test_rest_list_and_read(arch_dir):
    client = TestClient(app)
    assert client.get("/api/arch").json() == [
        {"name": "sample.yaml", "size": len(SAMPLE.encode("utf-8"))}
    ]
    body = client.get("/api/arch/sample.yaml").json()
    assert body["architecture"]["metadata"]["name"] == "샘플"


def test_rest_read_missing_file_404(arch_dir):
    client = TestClient(app)
    assert client.get("/api/arch/nope.yaml").status_code == 404


def test_rest_read_broken_yaml_400_with_line(arch_dir):
    (arch_dir / "broken.yaml").write_text(
        "flow: |\n  a --> ghost\nnodes:\n  a: { out: [x], prompt: p }\n", encoding="utf-8"
    )
    client = TestClient(app)
    resp = client.get("/api/arch/broken.yaml")
    assert resp.status_code == 400
    assert "ghost" in resp.json()["detail"]
```

- [ ] **Step 2: 실패를 확인한다**

Run: `cd server && ../.venv/bin/python -m pytest tests/test_arch_files.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'arch_files'`

- [ ] **Step 3: 최소 구현**

`server/arch_files.py`:

```python
"""arch.yaml 파일 저장소 — server/arch/ 아래의 .yaml 파일을 읽는다.

/api/architectures(JSON 저장소)와 같은 파일 기반 패턴이되, 이쪽은 사람이 에디터로
편집하는 원본이라 쓰기 API가 없다 (설계 §7 — 저작은 브라우저 밖에서 한다).
"""

from pathlib import Path

from archfile import parse_arch

ARCH_DIR = Path(__file__).parent / "arch"


def _resolve(name: str) -> Path:
    if "/" in name or "\\" in name or name.startswith("."):
        raise ValueError(f"invalid arch file name: {name!r}")
    return ARCH_DIR / name


def list_arch_files() -> list[dict]:
    if not ARCH_DIR.exists():
        return []
    return [
        {"name": p.name, "size": p.stat().st_size}
        for p in sorted(ARCH_DIR.glob("*.yaml"))
    ]


def read_arch_file(name: str) -> dict:
    path = _resolve(name)
    text = path.read_text(encoding="utf-8")
    architecture, warnings = parse_arch(text)
    return {
        "name": name,
        "text": text,
        "architecture": architecture,
        "warnings": warnings,
    }
```

`server/main.py`에 라우트 추가 (`/api/nodes` 아래):

```python
import arch_files
from archfile import ArchError


@app.get("/api/arch")
async def list_arch() -> list[dict]:
    return arch_files.list_arch_files()


@app.get("/api/arch/{name}")
async def get_arch(name: str) -> dict:
    try:
        return arch_files.read_arch_file(name)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"arch file not found: {name}") from None
    except (ArchError, ValueError) as err:
        raise HTTPException(status_code=400, detail=str(err)) from None
```

`ws_run`의 `run` 분기에서, `architecture`가 없고 `archFile`이 있으면 파일에서 읽는다:

```python
        arch = msg.get("architecture")
        if arch is None and msg.get("archFile"):
            arch = arch_files.read_arch_file(msg["archFile"])["architecture"]
```

`server/arch/` 디렉터리를 만들고 스타터 파일을 하나 넣는다:

`server/arch/gsm8k.yaml`:

```yaml
name: GSM8K Treatment
model: google/gemini-3.1-flash-lite

flow: |
  input --> planning --> reasoning --> review
  review -->|ok|    output
  review -->|retry| reasoning

nodes:
  planning:
    in:  [task]
    out: [plan]
    prompt: |
      문제를 풀 단계로 쪼개라. 각 단계 한 줄씩.

  reasoning:
    in:  [task, plan, feedback?]
    out: [answer]
    prompt: |
      계획을 따라 풀어라. 마지막 줄에 답만 숫자로 써라.

  review:
    in:  [task, answer]
    out: [feedback]
    prompt: |
      답이 문제에 맞는지 확인해라. 맞으면 ok, 틀리면 retry로 보내고
      feedback에 무엇이 틀렸는지 써라.
```

- [ ] **Step 4: 통과를 확인한다**

Run: `cd server && ../.venv/bin/python -m pytest tests/test_arch_files.py -v`
Expected: 6 passed

- [ ] **Step 5: 스타터 파일이 실제로 컴파일되는지 확인한다**

`server/tests/test_arch_files.py`에 추가:

```python
def test_shipped_gsm8k_yaml_parses_and_compiles():
    """레포에 커밋된 실물 파일 — 문서와 코드가 어긋나면 여기서 잡힌다."""
    from pathlib import Path

    from archfile import parse_arch
    from graphs.compile import compile_graph

    async def _emit(_e):
        return None

    text = (Path(__file__).parent.parent / "arch" / "gsm8k.yaml").read_text(encoding="utf-8")
    arch, warnings = parse_arch(text)
    assert warnings == []
    assert compile_graph(
        arch,
        {"provider": "google", "model": "gemini-3.1-flash-lite", "temperature": 0},
        _emit,
        "r1",
    ) is not None
```

Run: `cd server && ../.venv/bin/python -m pytest tests/test_arch_files.py -v`
Expected: 7 passed

- [ ] **Step 6: 린트 후 커밋**

```bash
cd server && ruff check . && ../.venv/bin/python -m pytest && cd ..
git add server/arch_files.py server/arch/gsm8k.yaml server/main.py server/tests/test_arch_files.py
git commit -m "feat(api): arch.yaml 파일 목록/조회 REST + WS archFile 실행

저작은 브라우저 밖 에디터에서 하므로 쓰기 API는 없다. 레포에 커밋된
arch/gsm8k.yaml이 실제로 컴파일되는지 테스트가 지킨다.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01TjeHp2KEmXXbbgS3wXgY3q"
```

---

### Task 6: 읽기 전용 대시보드

캔버스를 아직 지우지 않은 채로 새 대시보드를 붙인다 — 새것이 돌아가는 걸 확인한 뒤에 Task 7에서 옛것을 지운다.

**Files:**
- Create: `ui/src/app/Dashboard.tsx`, `ui/src/app/FlowDiagram.tsx`, `ui/src/app/NodeProgress.tsx`, `ui/src/registry/loadArchFiles.ts`, `ui/src/types/arch.ts`
- Modify: `ui/src/App.tsx`, `ui/package.json` (mermaid 추가)
- Test: `ui/src/__tests__/archFiles.test.ts`, `ui/src/__tests__/nodeProgress.test.tsx`

**Interfaces:**
- Consumes: Task 5의 `GET /api/arch`, `GET /api/arch/{name}`; 기존 `useExecutionStore`, `TransportContext`, `panels/Markdown.tsx`, `canvas/nodes/CheckpointActions.tsx`
- Produces:
  - `ArchFileSchema` (Zod) — `{ name: string; text: string; architecture: unknown; warnings: string[] }`
  - `loadArchFiles(): Promise<{name: string; size: number}[]>`, `loadArchFile(name: string): Promise<ArchFile>`
  - `<Dashboard />` — 앱 루트

- [ ] **Step 1: mermaid를 설치한다**

```bash
cd ui && npm install mermaid
```

- [ ] **Step 2: 실패하는 테스트를 쓴다**

`ui/src/__tests__/archFiles.test.ts`:

```typescript
import { describe, expect, it } from 'vitest'
import { ArchFileSchema } from '@/types/arch'

describe('ArchFileSchema', () => {
  it('parses a well-formed response', () => {
    const parsed = ArchFileSchema.parse({
      name: 'gsm8k.yaml',
      text: 'flow: |\n  a --> b',
      architecture: { nodes: [], edges: [], flow: 'a --> b' },
      warnings: [],
    })
    expect(parsed.name).toBe('gsm8k.yaml')
  })

  it('rejects a response missing warnings', () => {
    expect(() =>
      ArchFileSchema.parse({ name: 'x.yaml', text: '', architecture: {} }),
    ).toThrow()
  })
})
```

`ui/src/__tests__/nodeProgress.test.tsx`:

```typescript
import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { NodeProgress } from '@/app/NodeProgress'

describe('NodeProgress', () => {
  it('numbers repeat visits of the same node', () => {
    render(
      <NodeProgress
        entries={[
          { nodeId: 'reasoning', status: 'done', durationMs: 1200, output: null },
          { nodeId: 'review', status: 'done', durationMs: 800, output: null },
          { nodeId: 'reasoning', status: 'running', durationMs: null, output: null },
        ]}
        onResume={() => {}}
      />,
    )
    expect(screen.getByText('reasoning #1')).toBeInTheDocument()
    expect(screen.getByText('reasoning #2')).toBeInTheDocument()
    expect(screen.getByText('review')).toBeInTheDocument()
  })

  it('shows checkpoint buttons only for a paused checkpoint entry', () => {
    render(
      <NodeProgress
        entries={[
          { nodeId: '승인', status: 'paused', durationMs: null, output: null },
          { nodeId: 'reasoning', status: 'done', durationMs: 10, output: null },
        ]}
        onResume={() => {}}
      />,
    )
    expect(screen.getAllByRole('button', { name: /approve/i })).toHaveLength(1)
  })
})
```

- [ ] **Step 3: 실패를 확인한다**

Run: `cd ui && npm run test -- archFiles nodeProgress`
Expected: FAIL — `Cannot find module '@/types/arch'`

- [ ] **Step 4: 스키마와 로더를 구현한다**

`ui/src/types/arch.ts`:

```typescript
import { z } from 'zod'

export const ArchFileSchema = z.object({
  name: z.string(),
  text: z.string(),
  architecture: z.unknown(),
  warnings: z.array(z.string()),
})
export type ArchFile = z.infer<typeof ArchFileSchema>

export const ArchListItemSchema = z.object({ name: z.string(), size: z.number() })
export type ArchListItem = z.infer<typeof ArchListItemSchema>
```

`ui/src/registry/loadArchFiles.ts` (기존 `loadRunFiles.ts` 패턴을 그대로 따른다):

```typescript
import { ArchFileSchema, ArchListItemSchema, type ArchFile, type ArchListItem } from '@/types/arch'

const API = import.meta.env.VITE_API_URL ?? 'http://localhost:8000'

export async function loadArchFiles(): Promise<ArchListItem[]> {
  const res = await fetch(`${API}/api/arch`)
  if (!res.ok) throw new Error(`failed to list arch files: ${res.status}`)
  return ArchListItemSchema.array().parse(await res.json())
}

export async function loadArchFile(name: string): Promise<ArchFile> {
  const res = await fetch(`${API}/api/arch/${encodeURIComponent(name)}`)
  if (!res.ok) throw new Error((await res.json()).detail ?? `failed: ${res.status}`)
  return ArchFileSchema.parse(await res.json())
}
```

- [ ] **Step 5: `NodeProgress`를 구현한다**

`ui/src/app/NodeProgress.tsx`:

```typescript
import { useState } from 'react'
import { Markdown } from '@/panels/Markdown'

export type ProgressEntry = {
  nodeId: string
  status: 'running' | 'done' | 'failed' | 'paused' | 'skipped'
  durationMs: number | null
  output: unknown
}

const MARK = { running: '▸', done: '✓', failed: '✗', paused: '⏸', skipped: '·' } as const

/** 같은 노드가 여러 번 방문되면 #1, #2로 번호를 붙인다. 한 번뿐이면 번호 없음
 * — 루프가 없는 그래프에 잡음을 더하지 않는다 (설계 §5.1 회차 구분). */
function label(entries: ProgressEntry[], index: number): string {
  const { nodeId } = entries[index]
  const total = entries.filter((e) => e.nodeId === nodeId).length
  if (total < 2) return nodeId
  const nth = entries.slice(0, index + 1).filter((e) => e.nodeId === nodeId).length
  return `${nodeId} #${nth}`
}

export function NodeProgress({
  entries,
  onResume,
}: {
  entries: ProgressEntry[]
  onResume: (decision: string) => void
}) {
  const [open, setOpen] = useState<number | null>(null)
  return (
    <ul className="node-progress">
      {entries.map((entry, i) => (
        <li key={`${entry.nodeId}-${i}`}>
          <button type="button" onClick={() => setOpen(open === i ? null : i)}>
            <span>{MARK[entry.status]}</span>
            <span>{label(entries, i)}</span>
            {entry.durationMs !== null && <span>{(entry.durationMs / 1000).toFixed(1)}s</span>}
          </button>
          {entry.status === 'paused' && (
            <span className="checkpoint-actions">
              {['approve', 'revise', 'reject'].map((d) => (
                <button key={d} type="button" onClick={() => onResume(d)}>
                  {d}
                </button>
              ))}
            </span>
          )}
          {open === i && entry.output != null && (
            <Markdown source={typeof entry.output === 'string' ? entry.output : JSON.stringify(entry.output, null, 2)} />
          )}
        </li>
      ))}
    </ul>
  )
}
```

- [ ] **Step 6: 테스트 통과를 확인한다**

Run: `cd ui && npm run test -- archFiles nodeProgress`
Expected: 4 passed

- [ ] **Step 7: `FlowDiagram`과 `Dashboard`를 구현한다**

`ui/src/app/FlowDiagram.tsx`:

```typescript
import mermaid from 'mermaid'
import { useEffect, useRef } from 'react'

mermaid.initialize({ startOnLoad: false, theme: 'dark', securityLevel: 'strict' })

/** arch.yaml의 flow 문자열을 그대로 렌더한다 — 변환 코드 없음 (설계 §3.2).
 * 실행 상태는 classDef 한 줄을 덧붙여 색칠한다. */
export function FlowDiagram({
  flow,
  statuses,
}: {
  flow: string
  statuses: Record<string, 'running' | 'done' | 'failed'>
}) {
  const ref = useRef<HTMLDivElement>(null)
  useEffect(() => {
    if (!ref.current) return
    const classes = Object.entries(statuses)
      .map(([nodeId, status]) => `class ${nodeId} ${status}`)
      .join('\n')
    const source = [
      'flowchart LR',
      flow,
      'classDef running fill:#2563eb,color:#fff',
      'classDef done fill:#16a34a,color:#fff',
      'classDef failed fill:#dc2626,color:#fff',
      classes,
    ].join('\n')
    let cancelled = false
    mermaid
      .render(`flow-${Date.now()}`, source)
      .then(({ svg }) => {
        if (!cancelled && ref.current) ref.current.innerHTML = svg
      })
      .catch((err) => {
        if (!cancelled && ref.current) ref.current.textContent = String(err)
      })
    return () => {
      cancelled = true
    }
  }, [flow, statuses])
  return <div className="flow-diagram" ref={ref} />
}
```

`ui/src/app/Dashboard.tsx`: 파일 선택 `<select>` + 입력 `<input>` + Run 버튼, `FlowDiagram`, `NodeProgress`를 배치한다. 실행 이벤트는 기존 `useExecutionStore`에서 읽고, Run은 기존 transport의 `send({ kind: 'run', archFile, input, model })`을 호출한다. `warnings`가 비어있지 않으면 상단에 노란 줄로 표시한다.

`ui/src/App.tsx`가 `<Dashboard />`를 렌더하게 바꾼다.

- [ ] **Step 8: 빌드와 전체 테스트를 확인한다**

```bash
cd ui && npm run test && npm run build
```
Expected: 기존 117 + 신규 4 통과, 빌드 클린. **`npm run test` 통과가 `npm run build` 통과를 보장하지 않으므로 둘 다 반드시 돌린다.**

- [ ] **Step 9: 커밋**

```bash
git add ui/src/app/Dashboard.tsx ui/src/app/FlowDiagram.tsx ui/src/app/NodeProgress.tsx \
        ui/src/registry/loadArchFiles.ts ui/src/types/arch.ts ui/src/App.tsx \
        ui/src/__tests__/archFiles.test.ts ui/src/__tests__/nodeProgress.test.tsx \
        ui/package.json ui/package-lock.json
git commit -m "feat(ui): 읽기 전용 대시보드 — mermaid 그림 + 노드 진행

flow 문자열을 mermaid에 그대로 넘겨 그림을 얻는다 — 레이아웃 코드 0줄.
같은 노드 재방문은 #1/#2로 번호를 붙이고, 체크포인트에서만 버튼이 나온다.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01TjeHp2KEmXXbbgS3wXgY3q"
```

---

### Task 7: 캔버스 삭제

새 대시보드가 도는 것을 확인한 뒤에만 착수한다.

**Files:**
- Delete: `server/node_types.py`, `server/tests/test_node_types.py`
- Delete: `ui/src/canvas/**` (단 `canvas/nodes/CheckpointActions.tsx`는 Task 6이 흡수했으면 함께 삭제), `ui/src/panels/Inspector.tsx`, `ui/src/panels/NodeLibrary.tsx`, `ui/src/registry/builtinManifests.ts`, `ui/src/stores/useGraphStore.ts`, `ui/src/stores/useUiStore.ts`, `ui/src/app/starterArchitecture.ts`, `ui/src/app/OpenRouterFavoritesModal.tsx`, 그리고 이들만 대상으로 하는 `ui/src/__tests__/*` 파일들
- Delete: `work/radial-agent-canvas/`
- Modify: `ui/package.json` (`reactflow` 제거), `server/manifests.py` (노드 타입 정리)
- Test: 기존 스위트가 축소된 채로 전부 통과해야 한다

- [ ] **Step 1: 무엇이 남아있는지부터 확인한다**

```bash
cd ui && npx knip --include files 2>/dev/null || \
  grep -rl "useGraphStore\|builtinManifests\|reactflow\|Inspector" src --include=*.ts --include=*.tsx
```
Expected: 삭제 대상 목록. **여기에 Task 6이 만든 파일이 나오면 삭제하지 말고 의존을 먼저 끊는다.**

- [ ] **Step 2: 프론트 파일을 지운다**

```bash
cd /home/licodev/projects/agentforge
git rm -r ui/src/canvas ui/src/panels/Inspector.tsx ui/src/panels/NodeLibrary.tsx \
          ui/src/registry/builtinManifests.ts ui/src/stores/useGraphStore.ts \
          ui/src/stores/useUiStore.ts ui/src/app/starterArchitecture.ts \
          ui/src/app/OpenRouterFavoritesModal.tsx
git rm -r work/radial-agent-canvas
cd ui && npm uninstall reactflow
```

- [ ] **Step 3: 남은 참조를 끊고 빌드를 통과시킨다**

```bash
cd ui && npm run build
```
빌드가 가리키는 import를 하나씩 지운다. 삭제된 컴포넌트만 검증하던 테스트 파일도 함께 지운다 (`git rm`). **삭제된 기능이 아니라 살아있는 기능을 검증하던 테스트는 절대 지우지 않는다** — 그 경우 테스트를 새 구조에 맞게 고친다.

- [ ] **Step 4: 백엔드 노드 타입을 정리한다**

`server/manifests.py`에서 `planning.decompose`, `reasoning.cot`, `review.intent`, `model.binding`, `loop.reentry` manifest를 제거한다. **`custom.node`, `io.input`, `io.output`, `human.checkpoint`, `loop.guard`는 남긴다.**

`server/graphs/compile.py:94`의 `PASSTHROUGH_TYPES`에서 `loop.reentry`를 빼고, `:596`의 `_CONDITIONAL_ROUTING_TYPES`에서 `review.intent`를 뺀다. `:629`의 `if source_type == "loop.reentry":` 블록도 지운다.

`/api/node-types` CRUD도 함께 지운다 (스펙 §10). 노드 타입 카탈로그 자체가 사라지므로 재사용 가능한 타입을 저장할 대상이 없다 — Phase B③에서 만들었지만 프론트 어디서도 호출하지 않던 미배선 코드다.

```bash
git rm server/node_types.py server/tests/test_node_types.py
```

`server/main.py:97-117`의 세 라우트(`list_node_types`/`create_node_type`/`delete_node_type`)와 `import node_types as nt`를 지우고, `GET /api/nodes`가 빌트인 매니페스트만 반환하게 되돌린다.

```bash
cd server && ../.venv/bin/python -m pytest
```
삭제된 타입만 검증하던 테스트는 지우고, 그 외 실패는 **참조가 남았다는 신호이므로 고친다.** `treatment.py`/`baseline.py`/`harness.py`는 매니페스트를 안 쓰므로 영향이 없어야 한다 — 여기서 실패가 나면 그건 진짜 결함이니 삭제가 아니라 수정으로 대응한다.

- [ ] **Step 5: 전체 검증**

```bash
cd server && ruff check . && ../.venv/bin/python -m pytest && cd ../ui && npm run test && npm run build && npm run lint
```
Expected: 백엔드 전부 통과, 프론트 전부 통과, 빌드 클린, lint는 기존 경고 3건 외 신규 없음.

- [ ] **Step 6: 커밋**

```bash
git add -A
git commit -m "refactor(ui): 노드 캔버스 삭제 — 저작은 arch.yaml로

React Flow 캔버스, Inspector, 노드 매니페스트 카탈로그, 방사형/루프 view-layer를
제거한다. 좌표와 포트 핸들을 사람이 정하던 부기가 통째로 사라진다.
treatment.py/baseline.py와 GSM8K 벤치마크는 그대로다.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01TjeHp2KEmXXbbgS3wXgY3q"
```

- [ ] **Step 7: 문서를 갱신한다**

`CLAUDE.md`의 디렉토리 구조와 "핵심 연동 구조"에서 캔버스 서술을 `arch.yaml` 흐름으로 바꾸고, `DIRECTION.md`에 이 전환을 반영하고, `ROADMAP.md`에 완료 항목을 적는다. `docs/superpowers/specs/2026-08-16-freeform-connections-node-templates-design.md`와 `2026-08-22-loop-reentry-node-design.md` 상단에 "2026-09-02 텍스트 우선 전환으로 대체됨" 배너를 단다.

```bash
git add CLAUDE.md DIRECTION.md ROADMAP.md docs/superpowers/specs/
git commit -m "docs: 텍스트 우선 전환 반영

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01TjeHp2KEmXXbbgS3wXgY3q"
```

---

## 검증되지 않는 것

이 샌드박스에는 Chromium 구동용 공유 라이브러리가 없어 브라우저 육안 검증이 불가능하다. 다음은 사용자가 `./start.sh`로 직접 확인해야 한다:

- mermaid 그림이 실제로 그려지는지, 실행 중 노드 색칠이 보이는지
- 체크포인트 버튼이 뜨고 `resume`이 실제로 실행을 재개하는지
- `arch.yaml`을 고치고 새로고침했을 때 반영되는지

`ANTHROPIC_API_KEY` 401이 미해결이라 실제 LLM 호출을 타는 E2E도 보류 상태다 (`CLAUDE.local.md` 참고).
