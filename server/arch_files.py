"""arch.yaml file store — reads the .yaml files under server/arch/.

These are edited by hand (or by Claude Code), so there is no write API — authoring happens outside
the browser.
"""

from pathlib import Path

from archfile import parse_arch

ARCH_DIR = Path(__file__).parent / "arch"


def _resolve(name: str) -> Path:
    """Resolve a name to an actual path inside ARCH_DIR.

    Pattern matching alone (e.g. checking for "/") cannot catch URL-encoded separators or
    symlinks — so finally we confirm by containment that the resolve()d absolute path really lies
    under ARCH_DIR. That is the real line of defence; the earlier character checks only
    filter ambiguous names early so the error message is clearer.
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
    result = []
    for p in sorted(ARCH_DIR.glob("*.yaml")):
        try:
            size = p.stat().st_size
        except OSError:
            # A single entry on which stat() fails, such as a broken symlink, must not kill the
            # whole
            # list — skip only that entry.
            continue
        result.append({"name": p.name, "size": size})
    return result


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
