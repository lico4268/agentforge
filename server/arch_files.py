"""arch.yaml 파일 저장소 — server/arch/ 아래의 .yaml 파일을 읽는다.

/api/architectures(JSON 저장소)와 같은 파일 기반 패턴이되, 이쪽은 사람이 에디터로
편집하는 원본이라 쓰기 API가 없다 (설계 §7 — 저작은 브라우저 밖에서 한다).
"""

from pathlib import Path

from archfile import parse_arch

ARCH_DIR = Path(__file__).parent / "arch"


def _resolve(name: str) -> Path:
    """이름 하나를 ARCH_DIR 안의 실제 경로로 해석한다.

    패턴 매칭("/" 포함 여부 등)만으로는 URL 인코딩된 구분자나 심볼릭 링크를 못
    잡는다 — 그래서 최종적으로 resolve()한 절대경로가 ARCH_DIR 밑에 실제로 있는지
    포함 관계로 확인한다. 이게 진짜 방어선이고, 앞의 문자 검사는 애매한 이름을
    조기에 걸러 에러 메시지를 명확하게 하기 위한 것일 뿐이다.
    """
    if "\x00" in name:
        raise ValueError(f"invalid arch file name: {name!r}")
    if "/" in name or "\\" in name or name.startswith(".") or not name:
        raise ValueError(f"invalid arch file name: {name!r}")

    base = ARCH_DIR.resolve()
    candidate = (ARCH_DIR / name).resolve()
    if candidate != base and base not in candidate.parents:
        raise ValueError(f"invalid arch file name: {name!r}")
    return candidate


def list_arch_files() -> list[dict]:
    if not ARCH_DIR.exists():
        return []
    return [
        {"name": p.name, "size": p.stat().st_size}
        for p in sorted(ARCH_DIR.glob("*.yaml"))
    ]


def read_arch_file(name: str) -> dict:
    path = _resolve(name)
    if not path.is_file():
        raise FileNotFoundError(name)
    text = path.read_text(encoding="utf-8")
    architecture, warnings = parse_arch(text)
    return {
        "name": name,
        "text": text,
        "architecture": architecture,
        "warnings": warnings,
    }
