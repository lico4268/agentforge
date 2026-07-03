"""
파일시스템 워크스페이스 — 실행마다 노드 output을 .md 파일로 영속화.

디렉토리 구조:
    server/workspace/<run_id>/<seq>-<node_id>.md

WSEventEmitter가 node_end 이벤트를 발생시킬 때 write_node_output()을 호출하면
해당 노드의 output이 markdown 파일로 저장된다.
프론트는 GET /api/runs/{run_id}/files 로 파일 목록을 조회하고,
GET /api/runs/{run_id}/files/{name} 으로 내용을 읽어 Markdown 렌더링한다.
"""

import json
from pathlib import Path
from typing import Any

from logging_config import logger

WORKSPACE_DIR = Path(__file__).parent / "workspace"

# output dict에서 본문으로 사용할 문자열 필드 (우선순위 순)
_BODY_KEYS = ("answer", "plan", "reasoning", "summary", "result")


def _run_dir(run_id: str) -> Path:
    d = WORKSPACE_DIR / run_id
    d.mkdir(parents=True, exist_ok=True)
    return d


def _extract_body(output: Any) -> str | None:
    """output에서 대표 문자열 필드를 추출. 없으면 None."""
    if isinstance(output, str):
        return output
    if isinstance(output, dict):
        for key in _BODY_KEYS:
            v = output.get(key)
            if isinstance(v, str) and v.strip():
                return v
    return None


def _seq_prefix(run_dir: Path, node_id: str) -> str:
    """동일 노드 재실행을 고려해 시퀀스 번호를 붙인 파일명 접두부 생성."""
    existing = sorted(run_dir.glob("*-*.md"))
    # node_id가 이미 존재하는 경우 다음 시퀀스 계산
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
    """노드 output을 markdown 파일로 저장. 성공 시 파일 경로, 실패 시 None."""
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

        # 본문 외 메타데이터를 코드블록으로 append
        if isinstance(output, dict):
            meta = {k: v for k, v in output.items() if k not in _BODY_KEYS or v != body}
            if meta:
                lines.append("```json")
                lines.append(json.dumps(meta, ensure_ascii=False, indent=2))
                lines.append("```")
        elif not body:
            # output이 dict도 string도 아닌 경우
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
    """run_id 디렉토리의 파일 목록을 반환. camelCase 키 사용 (타입 계약)."""
    run_dir = WORKSPACE_DIR / run_id
    if not run_dir.exists():
        return []

    files: list[dict] = []
    for f in sorted(run_dir.glob("*.md")):
        # 파일명에서 nodeId 추출: "001-planning.md" → "planning"
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
    """단일 파일 내용 반환. 없으면 None."""
    run_dir = WORKSPACE_DIR / run_id
    path = run_dir / name

    # 경로 탈방지 (path traversal)
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
