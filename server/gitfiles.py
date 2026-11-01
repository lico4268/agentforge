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
    out = subprocess.run([*_GIT, "-C", str(path), *args], capture_output=True, text=True)
    if out.returncode:
        raise RuntimeError(f"git {args[0]} in {path}: {out.stderr.strip()}")
    return out.stdout.strip()


def ensure_repo(path: Path) -> None:
    """A fresh files/ folder becomes a repo with an empty root commit, so every agent visit
    has a parent commit to diff against and replay from."""
    if (path / ".git").exists():
        return
    path.mkdir(parents=True, exist_ok=True)
    git(path, "init", "-q")
    _exclude(path)
    git(path, "commit", "-q", "--allow-empty", "-m", "agentforge: start")


def _exclude(path: Path) -> None:
    """Build litter stays out of the per-visit commits (info/exclude is not itself committed)."""
    (path / ".git" / "info").mkdir(exist_ok=True)
    (path / ".git" / "info" / "exclude").write_text(_EXCLUDE)


def clone_at(src: Path, dst: Path, commit: str) -> None:
    """A replay's own files/ repo: a copy of the parent's, rewound to `commit`."""
    git(src.parent, "clone", "-q", str(src), str(dst))
    git(dst, "reset", "-q", "--hard", commit)
    _exclude(dst)


def root(path: Path) -> str:
    return git(path, "rev-list", "--max-parents=0", "HEAD").splitlines()[-1]


def commit(path: Path, message: str) -> str:
    with _lock:
        git(path, "add", "-A")
        git(path, "commit", "-q", "--allow-empty", "-m", message)
        return git(path, "rev-parse", "HEAD")


def head(path: Path) -> str:
    return git(path, "rev-parse", "HEAD")


def changed(path: Path, before: str, after: str) -> list[str]:
    return git(path, "diff", "--name-only", before, after).splitlines()


def toplevel(path: Path) -> Path:
    return Path(git(path, "rev-parse", "--show-toplevel"))


def dirty(repo: Path) -> bool:
    return bool(git(repo, "status", "--porcelain"))


def add_worktree(repo: Path, path: Path, branch: str, start: str = "HEAD") -> str:
    """New branch `branch` at `start`, checked out at `path`. Returns the start commit."""
    git(repo, "worktree", "add", "-q", "-b", branch, str(path), start)
    return head(path)


def remove_worktree(repo: Path, path: Path) -> None:
    git(repo, "worktree", "remove", "--force", str(path))


def common_dir(path: Path) -> Path | None:
    """The main repo's .git for a worktree (its `.git` is a file pointing there), else None."""
    if not (path / ".git").is_file():
        return None
    return Path(git(path, "rev-parse", "--path-format=absolute", "--git-common-dir"))


def shortstat(repo: Path, a: str, b: str) -> str:
    return git(repo, "diff", "--shortstat", a, b)
