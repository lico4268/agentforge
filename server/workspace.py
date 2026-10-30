"""
Filesystem workspace — persist each run's node output as .md files.

Directory layout:
    server/workspace/<run_id>/<seq>-<node_id>.md

When WSEventEmitter emits a node_end event it calls write_node_output(), which saves
that node's output as a markdown file.
The frontend lists files via GET /api/runs/{run_id}/files,
and reads content via GET /api/runs/{run_id}/files/{name} to render Markdown.
"""

import json
import re
from pathlib import Path
from typing import TYPE_CHECKING, Any

from logging_config import logger

if TYPE_CHECKING:
    from events import ExecutionEvent

WORKSPACE_DIR = Path(__file__).parent / "workspace"

# String fields of the output dict used as the body (in priority order)
_BODY_KEYS = ("answer", "plan", "reasoning", "summary", "result")


_RUN_ID_RE = re.compile(r"^[\w-]+$")


def _valid_run_id(run_id: Any) -> bool:
    return isinstance(run_id, str) and _RUN_ID_RE.fullmatch(run_id) is not None


def _check_run_id(run_id: Any) -> None:
    """Run ids become directory names; reject anything that could escape WORKSPACE_DIR."""
    if not _valid_run_id(run_id):
        raise ValueError(f"invalid run id: {run_id!r}")


def _run_dir(run_id: str) -> Path:
    _check_run_id(run_id)
    d = WORKSPACE_DIR / run_id
    d.mkdir(parents=True, exist_ok=True)
    return d


def _extract_body(output: Any) -> str | None:
    """Extract the representative string field from output. None if absent."""
    if isinstance(output, str):
        return output
    if isinstance(output, dict):
        for key in _BODY_KEYS:
            v = output.get(key)
            if isinstance(v, str) and v.strip():
                return v
    return None


def _seq_prefix(run_dir: Path, node_id: str) -> str:
    """Build a filename prefix with a sequence number, accounting for re-runs of the same node."""
    existing = sorted(run_dir.glob("*-*.md"))
    # If node_id already exists, compute the next sequence number
    max_seq = -1
    for f in existing:
        stem = f.stem  # e.g. "0-planning"
        parts = stem.split("-", 1)
        if len(parts) == 2:
            try:
                seq = int(parts[0])
                if seq > max_seq:
                    max_seq = seq
            except ValueError:
                pass
    return f"{max_seq + 1:03d}-{node_id}"


def write_node_output(run_id: str, node_id: str, output: Any) -> Path | None:
    """Save node output as a markdown file. Returns the file path on success, None on failure."""
    _check_run_id(run_id)
    if output is None:
        return None

    try:
        run_dir = _run_dir(run_id)
        prefix = _seq_prefix(run_dir, node_id)
        filename = f"{prefix}.md"
        path = run_dir / filename

        body = _extract_body(output)
        lines: list[str] = [f"# {node_id}", ""]

        if body:
            lines.append(body)
            lines.append("")

        # Append metadata beyond the body as a code block
        if isinstance(output, dict):
            meta = {k: v for k, v in output.items() if k not in _BODY_KEYS or v != body}
            if meta:
                lines.append("```json")
                lines.append(json.dumps(meta, ensure_ascii=False, indent=2))
                lines.append("```")
        elif not body:
            # output is neither a dict nor a string
            lines.append("```json")
            lines.append(json.dumps(output, ensure_ascii=False, indent=2, default=str))
            lines.append("```")

        path.write_text("\n".join(lines), encoding="utf-8")
        logger.info("workspace: wrote %s", path)
        return path
    except Exception:
        logger.exception("workspace: failed to write output for run=%s node=%s", run_id, node_id)
        return None


def list_run_files(run_id: str) -> list[dict]:
    """Return the file list for the run_id directory. Uses camelCase keys (type contract)."""
    if not _valid_run_id(run_id):
        return []
    run_dir = WORKSPACE_DIR / run_id
    if not run_dir.exists():
        return []

    files: list[dict] = []
    for f in sorted(run_dir.glob("*.md")):
        # Extract nodeId from the filename: "001-planning.md" → "planning"
        stem = f.stem
        parts = stem.split("-", 1)
        node_id = parts[1] if len(parts) == 2 else stem
        files.append(
            {
                "name": f.name,
                "nodeId": node_id,
                "sizeBytes": f.stat().st_size,
            }
        )
    return files


def read_run_file(run_id: str, name: str) -> dict | None:
    """Return a single file's content. None if missing."""
    if not _valid_run_id(run_id):
        return None
    run_dir = WORKSPACE_DIR / run_id
    path = run_dir / name

    # Path traversal guard
    try:
        path.resolve().relative_to(run_dir.resolve())
    except ValueError:
        return None

    if not path.exists() or not path.is_file():
        return None

    return {
        "name": path.name,
        "content": path.read_text(encoding="utf-8"),
    }


def persist_event(run_id: str, event: "ExecutionEvent") -> None:
    """Append the event to events.jsonl; also write the node .md file for node_end with output."""
    with (_run_dir(run_id) / "events.jsonl").open("a", encoding="utf-8") as f:
        f.write(json.dumps(event.to_frontend(), ensure_ascii=False) + "\n")
    if event.event_type == "node_end" and event.output is not None:
        write_node_output(run_id, event.node_id, event.output)


def read_events(run_id: str) -> list[dict]:
    """Return all events recorded for the run. [] if none."""
    if not _valid_run_id(run_id):
        return []
    path = WORKSPACE_DIR / run_id / "events.jsonl"
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def write_run_record(run_id: str, record: dict) -> None:
    (_run_dir(run_id) / "run.json").write_text(
        json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def read_run_record(run_id: str) -> dict | None:
    if not _valid_run_id(run_id):
        return None
    path = WORKSPACE_DIR / run_id / "run.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def update_run_record(run_id: str, **fields: Any) -> None:
    """Merge fields into the existing run.json (KeyError-free: starts from {} if missing)."""
    write_run_record(run_id, {**(read_run_record(run_id) or {}), **fields})
