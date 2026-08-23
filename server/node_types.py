"""사용자 정의 노드 타입(커스텀 매니페스트) 파일 저장소 — Phase B③.

server/node_types/<type>.json 하나당 매니페스트 하나. BUILTIN_MANIFESTS(파이썬
하드코딩, 7개 런타임의 실제 실행 로직과 묶임)는 건드리지 않는다 — 여기 저장되는
매니페스트는 그 7개 런타임 중 하나를 골라 쓰는 "설정"일 뿐, 새 런타임을 만들지
않는다(Phase A2 디스패치 정규화 + Phase B①/② 덕분에 7개 런타임 전부 이미 매니페스트
만으로 새 타입을 만들 수 있는 상태 — server/graphs/compile.py는 이 파일이 존재하는지도
모른다, main.py가 GET /api/nodes에서 BUILTIN_MANIFESTS와 합쳐 내보낼 뿐).

/api/architectures(server/main.py)의 파일 기반 저장 패턴을 그대로 따른다.
"""

import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel, field_validator

from manifests import BUILTIN_MANIFESTS

NODE_TYPES_DIR = Path(__file__).parent / "node_types"
NODE_TYPES_DIR.mkdir(exist_ok=True)

_BUILTIN_TYPES = {m["type"] for m in BUILTIN_MANIFESTS}
_KNOWN_RUNTIMES = {"llm_step", "review", "checkpoint", "loop_guard", "model", "io", "passthrough"}
_KNOWN_CATEGORIES = {"cognitive", "memory", "model", "tool", "policy", "human", "io"}


class PortSpec(BaseModel):
    id: str
    label: str
    dataType: str
    required: bool = False


class ConfigFieldSpec(BaseModel):
    key: str
    label: str
    type: str
    default: Any | None = None
    options: list[Any] | None = None
    placeholder: str | None = None
    description: str | None = None


class NodeTypeManifest(BaseModel):
    """사용자가 POST하는 커스텀 노드 타입 매니페스트 — 신뢰 경계라 Pydantic으로 검증한다
    (BUILTIN_MANIFESTS는 코드로만 바뀌는 신뢰된 데이터라 이 검증을 거치지 않는다)."""

    type: str
    runtime: str
    category: str
    label: str
    description: str = ""
    inputs: list[PortSpec] = []
    outputs: list[PortSpec] = []
    config: list[ConfigFieldSpec] = []
    maxModelSlots: int | None = None
    defaults: dict[str, Any] | None = None

    @field_validator("runtime")
    @classmethod
    def _runtime_is_known(cls, v: str) -> str:
        if v not in _KNOWN_RUNTIMES:
            raise ValueError(f"unknown runtime {v!r}; must be one of {sorted(_KNOWN_RUNTIMES)}")
        return v

    @field_validator("category")
    @classmethod
    def _category_is_known(cls, v: str) -> str:
        if v not in _KNOWN_CATEGORIES:
            raise ValueError(f"unknown category {v!r}; must be one of {sorted(_KNOWN_CATEGORIES)}")
        return v

    @field_validator("type")
    @classmethod
    def _type_does_not_shadow_builtin(cls, v: str) -> str:
        if v in _BUILTIN_TYPES:
            raise ValueError(f"{v!r} is a built-in node type and cannot be overridden")
        return v


def list_custom_manifests() -> list[dict]:
    result = []
    for f in NODE_TYPES_DIR.glob("*.json"):
        try:
            result.append(json.loads(f.read_text()))
        except Exception:
            pass
    return result


def save_custom_manifest(manifest: NodeTypeManifest) -> dict:
    """생성/수정(upsert) — 같은 type으로 다시 저장하면 덮어쓴다."""
    path = NODE_TYPES_DIR / f"{manifest.type}.json"
    body = manifest.model_dump(exclude_none=True)
    path.write_text(json.dumps(body, ensure_ascii=False, indent=2))
    return body


def delete_custom_manifest(type_: str) -> bool:
    path = NODE_TYPES_DIR / f"{type_}.json"
    if not path.exists():
        return False
    path.unlink()
    return True
