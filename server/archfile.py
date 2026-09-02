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


# "a -->|label| b --> c" 를 훑는다. 라벨은 임의 문자열(어휘 아님, 설계 §3.1-3).
_HOP = re.compile(r"\s*-->\s*(?:\|(.*?)\|\s*)?")
_NAME = re.compile(r"[^\s|>-](?:(?!-->)[^\s|])*")


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


def _split_model(spec: str) -> tuple[str, str]:
    """'google/gemini-3.1-flash-lite' → ('google', 'gemini-3.1-flash-lite')."""
    provider, _, model = spec.partition("/")
    if not model:
        raise ArchError(f"model must be 'provider/model', got {spec!r}")
    return provider, model


def _ports(names: list[str]) -> list[dict]:
    return [{"id": n.rstrip("?"), "label": n.rstrip("?")} for n in names]


# PyYAML은 flow 시퀀스([a, b]) 안의 평범한 스칼라에 '?'를 허용하지 않는다(YAML 자체
# 스펙 위반은 아니지만 PyYAML 파서가 이렇게 구현돼 있다) — 'feedback?' 같은 선택
# 입력 마커를 파싱 전에 따옴표로 감싸 우회한다.
_OPTIONAL_MARKER = re.compile(r'([^\s,\[\]{}"\']+\?)(?=[\s,\]}])')

_FLOW_KEY = re.compile(r"^flow\s*:")


def _flow_line_offset(text: str) -> int:
    """`flow:` 키가 원본 문서의 몇 번째 줄에 있는지. parse_flow는 블록 스칼라로
    추출된 문자열만 보고 1번 줄부터 세므로, ArchError.line을 사용자가 보는 실제
    파일 줄 번호로 되돌리려면 이 오프셋을 더해야 한다."""
    for i, line in enumerate(text.splitlines(), start=1):
        if _FLOW_KEY.match(line):
            return i
    return 0


def parse_arch(text: str) -> tuple[dict, list[str]]:
    """arch.yaml 텍스트 → (Architecture dict, 경고 목록)."""
    doc = yaml.safe_load(_OPTIONAL_MARKER.sub(r'"\1"', text)) or {}
    flow_text = doc.get("flow") or ""
    raw_nodes = doc.get("nodes") or {}
    default_model = doc.get("model")

    flow_edges = parse_flow(flow_text)
    offset = _flow_line_offset(text)
    for e in flow_edges:
        e["line"] += offset
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
