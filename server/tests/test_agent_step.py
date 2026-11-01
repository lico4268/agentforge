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
        ("    network: yes please\n", "network must be true or false"),
        ("    secrets: KEY\n", "secrets must be a list"),
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
