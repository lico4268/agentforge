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
