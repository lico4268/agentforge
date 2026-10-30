import json

import graphs.compile as gc
from cli import main, summarize
from tests.arch_samples import CHECKPOINT_YAML, FAN_IN, LINEAR_YAML
from workspace import read_run_record


def _write(tmp_path, text, name="a.yaml"):
    p = tmp_path / name
    p.write_text(text)
    return p


def _run_json(*args):
    return main(["run", *args, "--json"])


def test_check_ok(tmp_path, capsys, monkeypatch):
    monkeypatch.setattr(gc, "build_model", lambda s: None)
    p = _write(tmp_path, LINEAR_YAML)
    assert main(["check", str(p)]) == 0
    assert "ok: " in capsys.readouterr().out


def test_check_reports_line_number_and_exits_1(tmp_path, capsys):
    p = _write(tmp_path, FAN_IN % "")
    assert main(["check", str(p)]) == 1
    assert "line 6" in capsys.readouterr().err


def test_run_linear_prints_summary_and_exits_0(tmp_workspace, fake_llm, tmp_path, capsys):
    p = _write(tmp_path, LINEAR_YAML)
    rc = main(["run", str(p), "--task", "t"])
    out = capsys.readouterr().out
    assert rc == 0 and "draft" in out and "15 tok" in out and "result: draft:answer" in out
    assert "input" not in out.split("\n", 1)[1]


def test_run_resolves_arch_path_absolute(tmp_workspace, fake_llm, tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "x.yaml").write_text(LINEAR_YAML)
    main(["run", "x.yaml", "--task", "t", "--json"])
    rec = read_run_record(json.loads(capsys.readouterr().out)["runId"])
    assert rec["archPath"] == str(tmp_path / "x.yaml")


def _paused(tmp_path, capsys):
    p = _write(tmp_path, CHECKPOINT_YAML)
    rc = main(["run", str(p), "--task", "t", "--json"])
    return rc, json.loads(capsys.readouterr().out)["runId"]


def test_run_checkpoint_exits_3_and_prints_next_command(tmp_workspace, fake_llm, tmp_path, capsys):
    p = _write(tmp_path, CHECKPOINT_YAML)
    rc = main(["run", str(p), "--task", "t"])
    out = capsys.readouterr().out
    assert rc == 3
    assert "paused at gate" in out
    assert "choices: approve | revise | reject" in out
    assert "agentforge resume" in out


def test_resume_finishes_paused_run(tmp_workspace, fake_llm, tmp_path, capsys):
    rc, rid = _paused(tmp_path, capsys)
    assert rc == 3
    assert main(["resume", rid, "--choice", "approve"]) == 0
    assert read_run_record(rid)["status"] == "done"


def test_resume_rejects_unknown_choice(tmp_workspace, fake_llm, tmp_path, capsys):
    rc, rid = _paused(tmp_path, capsys)
    assert main(["resume", rid, "--choice", "maybe"]) == 1
    assert "approve" in capsys.readouterr().err
    assert read_run_record(rid)["status"] == "paused"


def test_resume_rejects_non_paused_run(tmp_workspace, fake_llm, tmp_path, capsys):
    p = _write(tmp_path, LINEAR_YAML)
    main(["run", str(p), "--task", "t", "--json"])
    rid = json.loads(capsys.readouterr().out)["runId"]
    assert main(["resume", rid, "--choice", "approve"]) == 1
    assert "not paused" in capsys.readouterr().err


def test_resume_unknown_run_id(tmp_workspace, capsys):
    assert main(["resume", "nope", "--choice", "approve"]) == 1
    assert "unknown run" in capsys.readouterr().err


def test_run_exit_code_on_node_error(tmp_workspace, fake_llm, tmp_path, capsys):
    fake_llm.fail.add("draft")
    p = _write(tmp_path, LINEAR_YAML)
    assert main(["run", str(p), "--task", "t"]) == 1
    assert "failed" in capsys.readouterr().out


def test_show_node_prints_full_output(tmp_workspace, fake_llm, tmp_path, capsys):
    p = _write(tmp_path, LINEAR_YAML)
    main(["run", str(p), "--task", "t", "--json"])
    rid = json.loads(capsys.readouterr().out)["runId"]
    assert main(["show", rid, "draft"]) == 0
    assert "draft:answer" in capsys.readouterr().out
    assert main(["show", rid, "nope"]) == 1
    assert main(["show", rid]) == 0


def test_summarize_reads_route_from_branch_output():
    events = [
        {"eventType": "node_start", "nodeId": "review"},
        {
            "eventType": "node_end",
            "nodeId": "review",
            "output": {"feedback": "f", "__route__review": "ok"},
        },
    ]
    assert summarize(events, set())["visits"][0]["route"] == "ok"
