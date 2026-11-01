import json
import shutil
import subprocess

import pytest
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, ChatResult

import config
import workspace
from archfile import ArchError, parse_arch
from cli import main

needs_bwrap = pytest.mark.skipif(shutil.which("bwrap") is None, reason="bwrap not installed")

SUBMIT = "printf 'COMPLETE_TASK_AND_SUBMIT_FINAL_OUTPUT\\n%s\\n' "

AGENT_YAML = """\
model: anthropic/claude-haiku-4-5-20251001
flow: |
  input --> coder --> output
nodes:
  coder:
    run: agent
    in: [task]
    out: [answer]
    prompt: Do the task.
"""


class ScriptedChat(BaseChatModel):
    """Answers each call with the next bash command from `script`."""

    script: list[str]
    calls: int = 0

    @property
    def _llm_type(self) -> str:
        return "scripted"

    def bind_tools(self, tools, **kwargs):
        return self

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        cmd = self.script[self.calls]
        self.calls += 1
        msg = AIMessage(
            content="ok",
            tool_calls=[{"name": "bash", "args": {"command": cmd}, "id": f"c{self.calls}"}],
            usage_metadata={"input_tokens": 100, "output_tokens": 10, "total_tokens": 110},
            response_metadata={"model_name": "fake-model"},
        )
        return ChatResult(generations=[ChatGeneration(message=msg)])


@pytest.fixture
def agent_run(tmp_workspace, tmp_path, monkeypatch, capsys):
    import graphs.compile as gc

    monkeypatch.setattr(config, "PRICING", {"fake-model": {"input": 1, "output": 5}})

    def run(script, yaml=AGENT_YAML, extra=""):
        chat = ScriptedChat(script=script)
        monkeypatch.setattr(gc, "build_model", lambda s: chat)
        p = tmp_path / "a.yaml"
        p.write_text(yaml + extra)
        code = main(["run", str(p), "--task", "t", "--json"])
        out = json.loads(capsys.readouterr().out)
        files = workspace.files_dir(out["runId"])
        return code, out, files

    return run


def _events(run_id, kind):
    return [e for e in workspace.read_events(run_id) if e["eventType"] == kind]


@needs_bwrap
def test_agent_writes_files_commits_and_answers(agent_run):
    code, out, files = agent_run(
        ["echo hello > a.txt; mkdir __pycache__; touch __pycache__/x.pyc", SUBMIT + "'wrote a.txt'"]
    )
    assert code == 0
    assert (files / "a.txt").read_text() == "hello\n"
    log = subprocess.run(
        ["git", "-C", str(files), "log", "--format=%s"], capture_output=True, text=True
    ).stdout.split("\n")
    assert log[:2] == ["agentforge: coder visit 1", "agentforge: start"]
    end = _events(out["runId"], "node_end")
    agent_end = next(e for e in end if e["nodeId"] == "coder")["output"]
    assert agent_end["answer"] == "wrote a.txt"
    assert agent_end["changedFiles"] == ["a.txt"]
    assert agent_end["steps"] == 2
    usage = [e for e in _events(out["runId"], "log") if e.get("tokenUsage")]
    assert usage[0]["tokenUsage"]["total_tokens"] == 220
    assert usage[0]["tokenUsage"]["cost"] == pytest.approx(2 * (100e-6 + 50e-6))


@needs_bwrap
def test_agent_step_limit_errors_but_keeps_work(agent_run):
    code, out, files = agent_run(
        ["echo 1 > a.txt", "echo 2 > b.txt", "echo 3"], extra="    limits: {steps: 2}\n"
    )
    assert code == 1
    assert "LimitsExceeded" in workspace.read_run_record(out["runId"])["error"]
    assert (files / "b.txt").exists()  # committed even though the node failed


@needs_bwrap
def test_sandbox_hides_env_and_network(agent_run, monkeypatch):
    monkeypatch.setenv("FAKE_SECRET", "s3cret")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-should-not-leak")
    probe = (
        'echo "secret=$FAKE_SECRET key=$ANTHROPIC_API_KEY home=$HOME" > env.txt; '
        "python3 -c \"import socket; socket.create_connection(('1.1.1.1', 53), 2)\" "
        "&& echo net=on >> env.txt || echo net=off >> env.txt; "
        "touch /usr/x 2>/dev/null && echo usr=rw >> env.txt || echo usr=ro >> env.txt; "
        "command -v search >> env.txt"
    )
    _, _, files = agent_run([probe, SUBMIT + "done"])
    text = (files / "env.txt").read_text()
    assert "secret= key= home=/tmp" in text
    assert "net=off" in text and "usr=ro" in text
    assert "/opt/agentforge/bin/search" in text


@needs_bwrap
def test_listed_secret_reaches_the_sandbox(agent_run, monkeypatch):
    monkeypatch.setenv("FAKE_SECRET", "s3cret")
    _, _, files = agent_run(
        ['echo "$FAKE_SECRET" > s.txt', SUBMIT + "done"], extra="    secrets: [FAKE_SECRET]\n"
    )
    assert (files / "s.txt").read_text() == "s3cret\n"


def test_missing_secret_fails_at_compile(agent_run, monkeypatch):
    monkeypatch.delenv("NOPE_KEY", raising=False)
    code, out, _ = agent_run([], extra="    secrets: [NOPE_KEY]\n")
    assert code == 1
    assert "NOPE_KEY" in workspace.read_run_record(out["runId"])["error"]


@pytest.mark.parametrize(
    "extra, msg",
    [
        ("    limits: {turns: 3}\n", "limits takes only"),
        ("    limits: {steps: 0}\n", "limits.steps must be a positive number"),
        ("    limits: {memory_mb: 1.5}\n", "limits.memory_mb must be a positive integer"),
        ("    limits: {cpu_seconds: 0}\n", "limits.cpu_seconds must be a positive integer"),
        ("    network: yes please\n", "network must be true or false"),
        ("    secrets: KEY\n", "secrets must be a list"),
        ("    tools: git\n", "tools must be a list of command names"),
        ("    tools: [bin/git]\n", "tools must be a list of command names"),
        ("    files: notes\n", "files must be a mapping"),
        ("    files: {exec: [a]}\n", r"files takes only \['read', 'write'\]"),
        ("    files: {read: notes}\n", "files.read must be a list"),
        ("    files: {read: [/etc]}\n", "must be a relative folder inside files/"),
        ("    files: {read: [../x]}\n", "must be a relative folder inside files/"),
        ("    files: {write: [a/.git]}\n", "must be a relative folder inside files/"),
        ("    files: {read: [a], write: [./a/]}\n", "'a' is in both files.read and files.write"),
    ],
)
def test_agent_spec_validation(extra, msg):
    with pytest.raises(ArchError, match=msg):
        parse_arch(AGENT_YAML + extra)


def test_agent_needs_exactly_one_out():
    with pytest.raises(ArchError, match="exactly one out"):
        parse_arch(AGENT_YAML.replace("out: [answer]", "out: [answer, notes]"))


def test_agent_node_parses_to_agent_type():
    arch, _ = parse_arch(AGENT_YAML + "    network: true\n    limits: {steps: 5}\n")
    coder = next(n for n in arch["nodes"] if n["id"] == "coder")
    assert coder["type"] == "agent.node"
    assert coder["config"]["network"] is True
    assert coder["config"]["limits"] == {"steps": 5}
    assert coder["config"]["modelSlots"][0]["model"] == "claude-haiku-4-5-20251001"


# ── --repo ─────────────────────────────────────────────────────────────────────


def _git(path, *args):
    return subprocess.run(
        ["git", "-C", str(path), *args], capture_output=True, text=True, check=True
    ).stdout.strip()


@pytest.fixture
def repo(tmp_path):
    r = tmp_path / "repo"
    r.mkdir()
    _git(r, "init", "-q", "-b", "main")
    (r / "README").write_text("hi\n")
    _git(r, "add", "-A")
    _git(r, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-m", "init")
    return r


@pytest.fixture
def repo_run(tmp_workspace, tmp_path, monkeypatch, capsys):
    import graphs.compile as gc

    monkeypatch.setattr(config, "PRICING", {"fake-model": {"input": 1, "output": 5}})

    def run(script, repo, yaml=AGENT_YAML, json_out=False):
        monkeypatch.setattr(gc, "build_model", lambda s: ScriptedChat(script=script))
        p = tmp_path / "a.yaml"
        p.write_text(yaml)
        args = ["run", str(p), "--task", "t", "--repo", str(repo)]
        code = main(args + (["--json"] if json_out else []))
        return code, capsys.readouterr()

    return run


@needs_bwrap
def test_repo_run_leaves_a_branch_and_the_checkout_alone(repo_run, repo):
    script = ["echo more >> README && git log --oneline | wc -l > count.txt", SUBMIT + "done"]
    code, cap = repo_run(script, repo)
    assert code == 0
    assert "review and merge it yourself" in cap.out
    run_id = cap.out.split()[1]
    assert _git(repo, "log", "-1", "--format=%s", f"agentforge/{run_id}") == (
        "agentforge: coder visit 1"
    )
    assert _git(repo, "show", f"agentforge/{run_id}:count.txt") == "1"  # git worked inside
    assert (repo / "README").read_text() == "hi\n"  # user's checkout untouched
    assert not workspace.files_dir(run_id).exists()  # worktree folder removed
    assert "2 files changed" in workspace.read_run_record(run_id)["repo"]["diffstat"]


def test_repo_needs_an_agent_node(repo_run, repo, capsys):
    from tests.arch_samples import LINEAR_YAML

    code, cap = repo_run([], repo, yaml=LINEAR_YAML)
    assert code == 1
    assert "--repo needs a run: agent node" in cap.err


def test_repo_must_be_a_git_repo(repo_run, tmp_path):
    code, cap = repo_run([], tmp_path)
    assert code == 1
    assert "git rev-parse" in cap.err


@needs_bwrap
def test_dirty_repo_warns(repo_run, repo):
    (repo / "README").write_text("edited\n")
    _, cap = repo_run([SUBMIT + "done"], repo)
    assert "uncommitted changes" in cap.err


# ── replay ─────────────────────────────────────────────────────────────────────

TWO_AGENTS = """\
model: anthropic/claude-haiku-4-5-20251001
flow: |
  input --> coder --> fixer --> output
nodes:
  coder: {run: agent, in: [task], out: [code], prompt: write}
  fixer: {run: agent, in: [code], out: [answer], prompt: %s}
"""


def _replay(tmp_path, monkeypatch, capsys, run_id, yaml, script, *extra):
    import graphs.compile as gc

    monkeypatch.setattr(gc, "build_model", lambda s: ScriptedChat(script=script))
    p = tmp_path / "b.yaml"
    p.write_text(yaml)
    code = main(["replay", run_id, "--arch", str(p), "--json", *extra])
    return code, json.loads(capsys.readouterr().out)


@needs_bwrap
def test_replay_rewinds_files_to_before_the_start_node(agent_run, tmp_path, monkeypatch, capsys):
    code, out, files = agent_run(
        ["echo a > a.txt", SUBMIT + "a", "echo b > b.txt", SUBMIT + "b"],
        yaml=TWO_AGENTS % "fix",
    )
    assert code == 0 and {p.name for p in files.iterdir()} == {".git", "a.txt", "b.txt"}
    code, out2 = _replay(
        tmp_path,
        monkeypatch,
        capsys,
        out["runId"],
        TWO_AGENTS % "fix better",
        ["ls > seen.txt", SUBMIT + "c"],
    )
    assert code == 0
    assert out2["reused"] == ["coder"]
    files2 = workspace.files_dir(out2["runId"])
    assert (files2 / "seen.txt").read_text().split() == ["a.txt", "seen.txt"]  # no b.txt
    assert (files / "b.txt").exists()  # parent's files untouched
    rec = workspace.read_run_record(out2["runId"])
    coder_commit = next(
        e["output"]["commit"]
        for e in workspace.read_events(out["runId"])
        if e["eventType"] == "node_end" and e["nodeId"] == "coder"
    )
    assert rec["filesStart"] == coder_commit


@needs_bwrap
def test_replay_of_a_repo_run_branches_from_the_fork_commit(
    repo_run, repo, tmp_path, monkeypatch, capsys
):
    code, cap = repo_run(
        ["echo a > a.txt", SUBMIT + "a", "echo b > b.txt", SUBMIT + "b"],
        repo,
        yaml=TWO_AGENTS % "fix",
    )
    run_id = cap.out.split()[1]
    code, out2 = _replay(
        tmp_path,
        monkeypatch,
        capsys,
        run_id,
        TWO_AGENTS % "fix better",
        ["echo c > c.txt", SUBMIT + "c"],
    )
    assert code == 0
    branch = f"agentforge/{out2['runId']}"
    assert _git(repo, "ls-tree", "--name-only", branch).split() == ["README", "a.txt", "c.txt"]
    rec = workspace.read_run_record(out2["runId"])
    assert rec["repo"]["base"] == workspace.read_run_record(run_id)["repo"]["base"]
    assert "2 files changed" in rec["repo"]["diffstat"]  # a.txt + c.txt vs the user's HEAD


def test_bwrap_args_network_switch():
    from nodes.agent_step import bwrap_args

    assert "--share-net" not in bwrap_args(False, {})
    on = bwrap_args(True, {})
    assert "--share-net" in on and "--clearenv" in on


def test_files_scope_is_normalized():
    arch, _ = parse_arch(AGENT_YAML + "    files: {read: [./notes/, .], write: [src]}\n")
    node = next(n for n in arch["nodes"] if n["id"] == "coder")
    assert node["config"]["files"] == {"read": ["notes", "."], "write": ["src"]}


def test_no_files_key_means_no_scope():
    arch, _ = parse_arch(AGENT_YAML)
    node = next(n for n in arch["nodes"] if n["id"] == "coder")
    assert "files" not in node["config"]


def test_files_mounts(tmp_path):
    from nodes.agent_step import files_mounts

    f = str(tmp_path)
    git = ["--ro-bind-try", f"{f}/.git", f"{f}/.git"]
    assert files_mounts(tmp_path, None) == ["--bind", f, f, *git]
    assert files_mounts(tmp_path, {"read": ["a"], "write": []}) == [
        "--tmpfs", f, "--ro-bind-try", f"{f}/a", f"{f}/a"
    ]
    assert files_mounts(tmp_path, {"read": ["src/secret", "."], "write": ["src"]}) == [
        "--tmpfs", f,
        "--ro-bind-try", f, f,
        "--bind", f"{f}/src", f"{f}/src",
        "--ro-bind-try", f"{f}/src/secret", f"{f}/src/secret",
        *git,
    ]


SCOPED_YAML = """\
model: anthropic/claude-haiku-4-5-20251001
flow: |
  input --> prep --> coder --> output
nodes:
  prep:
    run: agent
    in: [task]
    out: [notes]
    prompt: Prepare.
  coder:
    run: agent
    in: [notes]
    out: [answer]
    prompt: Code.
    files: {read: [notes], write: [src]}
"""


@needs_bwrap
def test_scoped_node_sees_only_its_folders(agent_run):
    code, out, files = agent_run(
        [
            "mkdir notes && echo n > notes/n.txt && echo s > secret.txt",
            SUBMIT + "'prep done'",
            "cat notes/n.txt > src/copy.txt; ls -A > src/ls.txt; "
            "(echo x > notes/n.txt) 2>/dev/null || echo ro > src/notes.txt; echo junk > junk.txt",
            SUBMIT + "done",
        ],
        yaml=SCOPED_YAML,
    )
    assert code == 0
    assert (files / "src" / "copy.txt").read_text() == "n\n"
    assert (files / "src" / "notes.txt").read_text() == "ro\n"
    ls = set((files / "src" / "ls.txt").read_text().split())
    assert ls == {"notes", "src"}  # no .git, no secret.txt
    assert (files / "notes" / "n.txt").read_text() == "n\n"
    assert not (files / "junk.txt").exists()
    end = next(e for e in _events(out["runId"], "node_end") if e["nodeId"] == "coder")
    assert end["output"]["changedFiles"] == ["src/copy.txt", "src/ls.txt", "src/notes.txt"]


@needs_bwrap
def test_scope_through_preplanted_symlink_fails(agent_run):
    code, out, files = agent_run(
        [
            "mkdir -p ../outside && echo SECRET > ../outside/s.txt && ln -s ../outside notes",
            SUBMIT + "'prep done'",
            "cp notes/s.txt src/leak.txt",
            SUBMIT + "done",
        ],
        yaml=SCOPED_YAML,
    )
    assert code == 1
    assert "symlink" in workspace.read_run_record(out["runId"])["error"]
    assert not (files / "src" / "leak.txt").exists()


SELF_PLANT_YAML = SCOPED_YAML.replace(
    "files: {read: [notes], write: [src]}", "files: {read: [src/secret], write: [src]}"
)


@needs_bwrap
def test_scoped_node_cannot_plant_symlink_to_escape(agent_run):
    code, out, files = agent_run(
        [
            SUBMIT + "'prep done'",
            "ln -s ../.. src/secret",
            "cp src/secret/server/.env src/leak.txt 2>/dev/null; ls src/secret > src/leak2.txt",
            SUBMIT + "done",
        ],
        yaml=SELF_PLANT_YAML,
    )
    assert code == 1
    assert "symlink" in workspace.read_run_record(out["runId"])["error"]
    assert not (files / "src" / "leak2.txt").exists()


@needs_bwrap
def test_git_dir_is_read_only_in_sandbox(agent_run):
    code, out, files = agent_run(
        ["echo x > .git/hooks/pre-commit 2>/dev/null || echo ro > r.txt", SUBMIT + "done"]
    )
    assert code == 0
    assert (files / "r.txt").read_text() == "ro\n"
    assert not (files / ".git" / "hooks" / "pre-commit").exists()


def test_pick_tools():
    from nodes.agent_step import TOOLS_DIR, pick_tools, sandbox_tools

    assert pick_tools("n", None) == sandbox_tools()
    assert pick_tools("n", ["search", "git"]) == {"search": str(TOOLS_DIR / "search"), "git": None}
    with pytest.raises(ValueError, match="node 'n': tool 'no-such-tool-xyz' not found"):
        pick_tools("n", ["no-such-tool-xyz"])


@needs_bwrap
def test_tools_list_limits_the_sandbox_path(agent_run):
    _, _, files = agent_run(
        ["(command -v search || echo none) > t.txt; command -v git >> t.txt", SUBMIT + "done"],
        extra="    tools: [git]\n",
    )
    lines = (files / "t.txt").read_text().split()
    assert lines[0] == "none" and lines[1].endswith("/git")


def test_ulimit_prefix():
    from nodes.agent_step import ulimit_prefix

    assert ulimit_prefix(None, None) == ""
    assert ulimit_prefix(256, 5) == "ulimit -v 262144; ulimit -t 5\n"
    assert ulimit_prefix(None, 5) == "ulimit -t 5\n"


@needs_bwrap
def test_memory_and_cpu_limits_apply_to_commands(agent_run):
    _, _, files = agent_run(
        [
            "python3 -c 'b = bytearray(512 * 1024 * 1024)' 2>/dev/null && echo big > m.txt "
            "|| echo capped > m.txt; "
            "python3 -c 'while True: pass' 2>/dev/null; echo $? > c.txt",
            SUBMIT + "done",
        ],
        extra="    limits: {memory_mb: 128, cpu_seconds: 1}\n",
    )
    assert (files / "m.txt").read_text() == "capped\n"
    assert (files / "c.txt").read_text().strip() != "0"
