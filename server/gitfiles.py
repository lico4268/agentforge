"""Git plumbing for a run's files/ folder (agent nodes work there; every visit ends in a commit)."""

import subprocess
import threading
from pathlib import Path

# Fixed identity so commits work on machines without a git user configured.
_GIT = ["git", "-c", "user.name=agentforge", "-c", "user.email=agentforge@localhost"]
_GIT += ["-c", "commit.gpgsign=false"]

_EXCLUDE = "__pycache__/\n*.pyc\n.pytest_cache/\n.venv/\nnode_modules/\n"

# ponytail: one lock for every repo; parallel agent nodes commit one at a time
_lock = threading.Lock()


def git(path: Path, *args: str) -> str:
    out = subprocess.run(
        [*_GIT, "-C", str(path), *args], check=True, capture_output=True, text=True
    )
    return out.stdout.strip()


def ensure_repo(path: Path) -> None:
    """A fresh files/ folder becomes a repo with an empty root commit, so every agent visit
    has a parent commit to diff against and replay from."""
    if (path / ".git").exists():
        return
    path.mkdir(parents=True, exist_ok=True)
    git(path, "init", "-q")
    # Build litter stays out of the per-visit commits (info/exclude is not itself committed).
    (path / ".git" / "info").mkdir(exist_ok=True)
    (path / ".git" / "info" / "exclude").write_text(_EXCLUDE)
    git(path, "commit", "-q", "--allow-empty", "-m", "agentforge: start")


def commit(path: Path, message: str) -> str:
    with _lock:
        git(path, "add", "-A")
        git(path, "commit", "-q", "--allow-empty", "-m", message)
        return git(path, "rev-parse", "HEAD")


def head(path: Path) -> str:
    return git(path, "rev-parse", "HEAD")


def changed(path: Path, before: str, after: str) -> list[str]:
    return git(path, "diff", "--name-only", before, after).splitlines()
