"""arch.yaml → Architecture dict.

flow: 블록은 mermaid flowchart 문법 그대로다 — 자체 문법을 만들지 않는다.
그래서 같은 문자열을 브라우저 mermaid에 그대로 넘겨 그림을 그릴 수 있고,
파서는 정규식 하나로 끝난다 (설계 §3.2).
"""

import re
from typing import TypedDict

import yaml


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


# "a -->|label| b --> c" 를 훑는다. 라벨은 대부분 임의 문자열이다 — 예외는 사용자가
# 만들 수 없는 loop.guard(loopBack/exit)와 human.checkpoint(approve/revise/reject)
# 뿐이다(설계 §3.1-3).
_HOP = re.compile(r"\s*-->\s*(?:\|(.*?)\|\s*)?")
_NAME = re.compile(r"[^\s|>-](?:(?!-->)[^\s|])*")

# mermaid 문서의 첫 줄에 오는 `flowchart LR`/`graph TD` 같은 지시문. `flow:` 블록을
# GitHub/Obsidian 등에 그대로 붙여넣어 mermaid로 렌더하려면 이 헤더가 필요한데,
# 우리 파서에는 화살표가 없는 줄이라 예전에는 "expected '-->'"로 거부됐다 — 첫
# 줄에 한해 건너뛴다(설계 §3.2).
_DIRECTIVE = re.compile(r"^(flowchart|graph)\b")


def parse_flow(text: str, line_offset: int = 0) -> list[FlowEdge]:
    """text(YAML 블록 스칼라로 추출된 flow: 내용)를 훑어 엣지를 만든다.

    line_offset은 text의 1번째 줄이 원본 문서에서 실제로 몇 번째 줄인지를 알려준다
    (기본 0 — text 자체가 이미 파일 전체라고 가정하는 parse_flow 직접 호출/테스트용).
    parse_arch는 이 값을 _flow_line_offset으로 미리 계산해 넘긴다 — 그래야 안에서
    던져지는 ArchError도 성공 경로의 엣지들과 똑같이 파일 기준 줄 번호를 갖는다
    (BLOCKING 2: 예전에는 성공한 엣지에만 사후 보정을 더해서, 실패 경로는 블록
    상대 줄 번호가 그대로 새 나갔다)."""
    edges: list[FlowEdge] = []
    seen_content = False
    for lineno, raw in enumerate(text.splitlines(), start=1):
        line = raw.strip()
        if not line or line.startswith("%%"):
            continue
        if not seen_content:
            seen_content = True
            if _DIRECTIVE.match(line):
                continue
        edges.extend(_parse_flow_line(line, lineno + line_offset))
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
        if pos >= len(line):
            raise ArchError(f"trailing arrow with no target in {line!r}", lineno)
    if len(names) < 2:
        raise ArchError(f"not an edge: {line!r}", lineno)
    return [
        FlowEdge(source=names[i], target=names[i + 1], label=labels[i], line=lineno)
        for i in range(len(names) - 1)
    ]


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

# compile.py `_branch_labels`(설계 §5)가 분기로 인정하는 타입 — 라벨을 스스로 고를
# 수단(LLM 구조화 출력 또는 런타임 고유 로직)이 있는 타입만 분기 노드가 될 수 있다.
# io.input/io.output은 여기 없다 — 라벨을 낼 방법이 없으므로 라벨 2개 이상을 달면
# 사용자 의도가 조용히 버려진다(Task 3 다이아몬드 버그와 같은 부류).
_BRANCH_CAPABLE_TYPES = {USER_NODE_TYPE, "human.checkpoint", "loop.guard"}


def _split_model(spec: str) -> tuple[str, str]:
    """'google/gemini-3.1-flash-lite' → ('google', 'gemini-3.1-flash-lite')."""
    provider, _, model = spec.partition("/")
    if not model:
        raise ArchError(f"model must be 'provider/model', got {spec!r}")
    return provider, model


def _ports(names: list[str]) -> list[dict]:
    return [{"id": n, "label": n} for n in names]


_FLOW_KEY = re.compile(r"^flow\s*:\s*(.*)$")


def _flow_line_offset(text: str) -> int:
    """flow: 블록의 1번째 줄이 원본 문서에서 몇 번째 줄인지 (parse_flow의 line_offset
    인자로 그대로 넘긴다).

    블록 스칼라(`flow: |`)는 내용이 flow: 다음 줄부터 시작하므로 offset은 flow: 가
    있는 줄 번호 그대로(내용 1번째 줄 + offset = flow: 줄 + 1). 인라인 스칼라
    (`flow: "a --> b"`)는 내용이 flow: 와 같은 물리적 줄에 있으므로 offset은
    한 줄 적어야 한다(내용 1번째 줄 + offset = flow: 줄) — 이 구분이 없으면
    인라인 스칼라의 줄 번호가 하나씩 밀린다."""
    for i, line in enumerate(text.splitlines(), start=1):
        m = _FLOW_KEY.match(line)
        if not m:
            continue
        rest = m.group(1).strip()
        if rest and rest[0] not in "|>":
            return i - 1  # 인라인 스칼라 — 내용이 이 줄에 있다
        return i  # 블록 스칼라(| 또는 >) — 내용은 다음 줄부터
    return 0


def parse_arch(text: str) -> tuple[dict, list[str]]:
    """arch.yaml 텍스트 → (Architecture dict, 경고 목록)."""
    try:
        doc = yaml.safe_load(text) or {}
    except yaml.YAMLError as e:
        # problem_mark는 전체 문서 기준 0-based 줄 번호 — parse_flow의 결과와 달리
        # _flow_line_offset을 더하면 안 된다(이미 파일 전체 기준이라 이중 보정이 됨).
        mark = getattr(e, "problem_mark", None)
        line = mark.line + 1 if mark is not None else None
        raise ArchError(str(e), line) from e
    flow_text = doc.get("flow") or ""
    raw_nodes = doc.get("nodes") or {}
    default_model = doc.get("model")

    flow_edges = parse_flow(flow_text, _flow_line_offset(text))
    # 노드 리스트 순서 = flow에 처음 등장한 순서. dict.fromkeys는 삽입 순서를 보존하므로
    # set 컴프리헨션(해시 순서 — 프로세스마다 무작위)보다 이걸 쓴다. Task 3의 back-edge
    # (루프) 판별이 이 순서를 위상 근사로 쓰기 때문에 결정적이어야 한다.
    referenced = dict.fromkeys(
        n for e in flow_edges for n in (e["source"], e["target"])
    )

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

    for name in raw_nodes:
        if name not in referenced:
            warnings.append(f"node {name!r} is defined but never used in flow:")

    _validate_inputs(raw_nodes)
    _validate_branch_capable(nodes, flow_edges)

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
    nodes, edges = _insert_guards(nodes, edges)
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


def _validate_inputs(raw_nodes: dict) -> None:
    """in:이 요구하는 이름마다 nodes: 전체 어딘가에 그걸 만드는 out:이 있는지 확인한다.
    flow 순서가 아니라 그래프 전체를 보므로, 나중에 실행되는 노드가 루프를 통해
    피드백을 돌려주는 경우(설계 §5.1)도 정상으로 통과한다 — 진짜 오타만 걸러낸다."""
    produced_all = {
        out
        for spec in raw_nodes.values()
        if isinstance(spec, dict)
        for out in spec.get("out") or []
    }
    for name, spec in raw_nodes.items():
        if not isinstance(spec, dict):
            continue
        for want in spec.get("in") or []:
            if want not in produced_all and want not in _PRESEEDED:
                raise ArchError(
                    f"node {name!r} reads {want!r} but no node writes it — "
                    "add it to some node's out:"
                )


def _validate_branch_capable(nodes: list[dict], flow_edges: list[FlowEdge]) -> None:
    """compile.py `_branch_labels`(설계 §5)와 같은 규칙 — 나가는 엣지에 라벨이 둘
    이상이면 분기 노드다 — 을 파서에서 먼저 적용해, 분기할 수 없는 타입(io.input/
    io.output)에 라벨이 둘 이상 달리면 줄 번호와 함께 거부한다. 같은 노드에서 라벨이
    중복되는 것도 여기서 함께 막는다 — 둘 다 "쓴 대로 실행되지 않는데 신호가 없는"
    같은 부류의 함정이기 때문이다.

    flow_edges(사용자가 실제로 mermaid에 쓴 엣지)만 본다 — _insert_guards가 나중에
    끼워 넣는 합성 loopBack/exit 엣지는 여기 없으므로 자동 삽입 가드는 애초에
    대상이 아니고, 사용자가 직접 `{ run: loop.guard }`로 꺼낸 가드는 loop.guard
    타입이라 애초에 분기 가능 목록에 있다.

    라벨 중복 검사는 compile.py의 branch-wiring 루프에도 똑같이 있다(중복이 아니다) —
    캔버스에서 저장된 architecture dict는 main.py의 dispatch_graph가 이 파서를 거치지
    않고 곧장 compile_graph로 넘기므로, 거기서도 반드시 막아야 조용한 엣지 소실을
    피할 수 있다. 여기(파서)는 arch.yaml 저자에게 줄 번호를 준다는 점만 다르다."""
    node_types = {n["id"]: n["type"] for n in nodes}
    labelled_by_source: dict[str, list[tuple[str, int]]] = {}
    unlabelled_by_source: dict[str, list[int]] = {}
    for e in flow_edges:
        if e["label"]:
            labelled_by_source.setdefault(e["source"], []).append((e["label"], e["line"]))
        else:
            unlabelled_by_source.setdefault(e["source"], []).append(e["line"])

    for node_id, labelled in labelled_by_source.items():
        if len(labelled) < 2:
            continue
        if node_types.get(node_id) not in _BRANCH_CAPABLE_TYPES:
            labels = [label for label, _ in labelled]
            raise ArchError(
                f"node {node_id!r} has {len(labels)} labelled outgoing edges {labels} "
                "but cannot branch — only user-defined nodes, human.checkpoint, and "
                "loop.guard can",
                labelled[0][1],
            )
        seen: dict[str, int] = {}
        for label, line in labelled:
            if label in seen:
                raise ArchError(
                    f"node {node_id!r} has the {label!r} label on two outgoing edges — "
                    "each label must have exactly one outgoing edge",
                    line,
                )
            seen[label] = line
        # 라벨 2개 이상(분기 확정)인데 라벨 없는 나가는 엣지가 하나라도 더 있으면
        # 그 엣지는 compile.py의 어디에도(plain edge 계획도, 분기 targets dict도)
        # 안 걸려 조용히 사라진다(BLOCKING 1) — 나가자마자 거부한다.
        if node_id in unlabelled_by_source:
            raise ArchError(
                f"node {node_id!r} branches ({len(labelled)} labelled outgoing edges) "
                "but also has an unlabelled outgoing edge — label it or it will "
                "silently never run",
                unlabelled_by_source[node_id][0],
            )


DEFAULT_MAX_ITERATIONS = 3


def _back_edges(nodes: list[dict], edges: list[dict]) -> list[dict]:
    """DFS로 진짜 사이클을 찾는다 — 방문 중(gray, 현재 재귀 스택 위)인 노드로 향하는
    엣지만 back edge다 (교과서 정의). 순수 도달가능성("v가 u에 닿는다")을 쓰면 안 된다:
    fan-out 후 fan-in(다이아몬드)만으로도 사이클이 아닌 정방향 엣지가 뒤로 가는 것처럼
    보이고(첫 등장 순서가 방문 경로에 좌우되므로), 반대로 사이클 하나에 엣지가 여러 개면
    (3-cycle이면 3개) 전부 back edge로 잡혀 가드가 중복 삽입된다 — gray-stack 판정이라야
    사이클 하나당 정확히 하나가 나온다.

    DFS root와 각 노드의 인접 엣지는 결정성을 위해 각각 nodes/edges 리스트 순서대로
    순회한다. 첫 root에서 닿지 않는 컴포넌트도 놓치지 않도록 방문 안 한 노드마다
    새로 DFS를 시작한다.
    """
    adjacency: dict[str, list[dict]] = {n["id"]: [] for n in nodes}
    for e in edges:
        adjacency.setdefault(e["source"], []).append(e)

    WHITE, GRAY, BLACK = 0, 1, 2
    color = dict.fromkeys((n["id"] for n in nodes), WHITE)
    back: list[dict] = []

    # 재귀 DFS를 명시적 스택으로 편다 — 긴 직선 체인(수백~수천 노드)에서 파이썬 기본
    # 재귀 한도(1000)를 넘겨 RecursionError로 파싱 전체가 죽는 걸 막는다. 프레임은
    # [node_id, 다음에 볼 인접 엣지 인덱스] — 재귀 버전과 동일한 순서로 색을 칠하고
    # 동일한 시점에 엣지를 훑으므로 back edge 판정 결과는 재귀 버전과 완전히 같다.
    for start in nodes:
        start_id = start["id"]
        if color[start_id] != WHITE:
            continue
        color[start_id] = GRAY
        stack: list[list] = [[start_id, 0]]
        while stack:
            frame = stack[-1]
            node_id, i = frame
            out_edges = adjacency[node_id]
            if i < len(out_edges):
                frame[1] += 1
                e = out_edges[i]
                target_color = color.get(e["target"], WHITE)
                if target_color == GRAY:
                    back.append(e)
                elif target_color == WHITE:
                    color[e["target"]] = GRAY
                    stack.append([e["target"], 0])
            else:
                color[node_id] = BLACK
                stack.pop()

    return back


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
