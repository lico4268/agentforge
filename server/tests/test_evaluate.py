import json

import pytest

import evaluate
from cli import main
from evaluate import EvalError, load_eval
from tests.arch_samples import CHECKPOINT_YAML, LINEAR_YAML


def _setup(tmp_path, arch, grader="contains", golds=("draft", "zzz"), extra=""):
    (tmp_path / "data.jsonl").write_text(
        "".join(json.dumps({"task": f"t{i}", "gold": g}) + "\n" for i, g in enumerate(golds))
    )
    p = tmp_path / "a.yaml"
    p.write_text(arch + f"eval:\n  dataset: data.jsonl\n  grader: {grader}\n{extra}")
    return p


def _eval_json(capsys, *args):
    code = main(["eval", *args, "--json"])
    return code, json.loads(capsys.readouterr().out)


def test_graders():
    g = evaluate.GRADERS
    assert g["number"]("so the answer is 72.0", "72")
    assert not g["number"]("71", "72")
    assert g["exact"](" Paris ", "Paris")
    assert not g["exact"]("Paris, France", "Paris")
    assert g["contains"]("It is PARIS.", "paris")
    assert not g["contains"](None, "paris")


def test_load_eval_resolves_dataset_next_to_yaml(tmp_path):
    p = _setup(tmp_path, LINEAR_YAML, extra="  repeat: 2\n")
    spec = load_eval(p.read_text(), p)
    assert [i["task"] for i in spec["items"]] == ["t0", "t1"]
    assert spec["repeat"] == 2


def test_load_eval_accepts_question_key(tmp_path):
    (tmp_path / "d.jsonl").write_text('{"question": "q", "gold": "1"}\n')
    spec = load_eval("eval: {dataset: d.jsonl, grader: number}", tmp_path / "a.yaml")
    assert spec["items"] == [{"task": "q", "gold": "1"}]


@pytest.mark.parametrize(
    "block, msg",
    [
        ("", "no eval: block"),
        ("eval: {dataset: nope.jsonl, grader: number}", "dataset not found"),
        ("eval: {dataset: d.jsonl, grader: fuzzy}", "grader must be"),
        ("eval: {dataset: d.jsonl, grader: number, repeat: 0}", "repeat must be"),
        ("eval: {dataset: d.jsonl, grader: {llm: {rubric: r}}}", "llm grader needs model"),
    ],
)
def test_load_eval_rejects_bad_spec(tmp_path, block, msg):
    (tmp_path / "d.jsonl").write_text('{"task": "q", "gold": "1"}\n')
    with pytest.raises(EvalError, match=msg):
        load_eval(block, tmp_path / "a.yaml")


def test_eval_reports_success_cost_and_nodes(tmp_workspace, fake_llm, tmp_path, capsys):
    p = _setup(tmp_path, LINEAR_YAML)
    code, r = _eval_json(capsys, str(p))
    assert code == 0
    assert (r["runs"], r["passed"], r["successRate"]) == (2, 1, 0.5)
    assert r["totalCost"] == pytest.approx(0.002)
    assert r["costPerSuccess"] == pytest.approx(0.002)
    assert r["nodes"]["draft"]["avgTokens"] == 15
    assert [x["passed"] for x in r["results"]] == [True, False]


def test_eval_limit_and_repeat(tmp_workspace, fake_llm, tmp_path, capsys):
    p = _setup(tmp_path, LINEAR_YAML, golds=("draft", "draft", "draft"), extra="  repeat: 2\n")
    _, r = _eval_json(capsys, str(p), "--limit", "1")
    assert (r["items"], r["runs"]) == (1, 2)


def test_eval_pause_counts_as_failure(tmp_workspace, fake_llm, tmp_path, capsys):
    p = _setup(tmp_path, CHECKPOINT_YAML, golds=("draft",))
    _, r = _eval_json(capsys, str(p))
    assert (r["passed"], r["paused"]) == (0, 1)
    assert r["results"][0]["status"] == "paused"


def test_eval_checkpoint_label_answers_pauses(tmp_workspace, fake_llm, tmp_path, capsys):
    p = _setup(tmp_path, CHECKPOINT_YAML, golds=("draft",))
    _, r = _eval_json(capsys, str(p), "--checkpoint", "approve")
    assert (r["passed"], r["paused"]) == (1, 0)
    assert r["routes"] == {"gate -> approve": 1}


def test_eval_checkpoint_label_not_wired_stays_paused(tmp_workspace, fake_llm, tmp_path, capsys):
    p = _setup(tmp_path, CHECKPOINT_YAML, golds=("draft",))
    _, r = _eval_json(capsys, str(p), "--checkpoint", "maybe")
    assert r["paused"] == 1


def test_eval_node_error_counts_as_error(tmp_workspace, fake_llm, tmp_path, capsys):
    fake_llm.fail.add("draft")
    p = _setup(tmp_path, LINEAR_YAML)
    _, r = _eval_json(capsys, str(p))
    assert (r["passed"], r["errors"], r["errorRate"]) == (0, 2, 1.0)


def test_eval_text_report(tmp_workspace, fake_llm, tmp_path, capsys):
    p = _setup(tmp_path, LINEAR_YAML)
    assert main(["eval", str(p)]) == 0
    out = capsys.readouterr().out
    assert "passed 1/2 (50.0%)" in out
    assert "agentforge show" in out  # points at the failed run


def test_eval_bad_spec_exits_1(tmp_path, capsys):
    p = tmp_path / "a.yaml"
    p.write_text(LINEAR_YAML)
    assert main(["eval", str(p)]) == 1
    assert "no eval: block" in capsys.readouterr().err


def test_check_validates_eval_block(tmp_path, capsys, monkeypatch):
    import graphs.compile as gc

    monkeypatch.setattr(gc, "build_model", lambda s: None)
    p = tmp_path / "a.yaml"
    p.write_text(LINEAR_YAML + "eval: {dataset: nope.jsonl, grader: number}\n")
    assert main(["check", str(p)]) == 1
    assert "dataset not found" in capsys.readouterr().err


async def test_llm_grader_asks_model_with_rubric(monkeypatch):
    seen = {}

    class FakeStructured:
        async def ainvoke(self, messages):
            seen["prompt"] = messages[-1].content
            return evaluate.Verdict(passed=True, reason="ok")

    class FakeModel:
        def with_structured_output(self, schema):
            return FakeStructured()

    monkeypatch.setattr(evaluate, "build_model", lambda s: FakeModel())
    grade = evaluate.make_grader({"llm": {"model": "anthropic/claude-x", "rubric": "be kind"}})
    assert await grade("the answer", "the gold", "the task")
    assert "be kind" in seen["prompt"] and "the gold" in seen["prompt"]


# ── compare ────────────────────────────────────────────────────────────────────


def test_apply_sets_edits_node_and_top_level_fields():
    text = evaluate.apply_sets(LINEAR_YAML, ["draft.temperature=0.7", "model=openai/gpt-x"])
    doc = __import__("yaml").safe_load(text)
    assert doc["nodes"]["draft"]["temperature"] == 0.7
    assert doc["model"] == "openai/gpt-x"


@pytest.mark.parametrize(
    "s, msg", [("nope.model=x", "no node 'nope'"), ("draft.model", "expected node.field=value")]
)
def test_apply_sets_rejects_bad_input(s, msg):
    with pytest.raises(EvalError, match=msg):
        evaluate.apply_sets(LINEAR_YAML, [s])


def test_paired_p_value():
    assert evaluate.paired_p(0, 0) == 1.0
    assert evaluate.paired_p(1, 0) == 1.0
    assert evaluate.paired_p(0, 10) == pytest.approx(2 / 1024)


def test_compare_two_files_pairs_items(tmp_workspace, fake_llm, tmp_path, capsys):
    a = _setup(tmp_path, LINEAR_YAML, golds=("draft2", "draft"))
    b = tmp_path / "b.yaml"
    b.write_text(a.read_text().replace("draft", "draft2"))
    code = main(["compare", str(a), str(b), "--json"])
    r = json.loads(capsys.readouterr().out)
    assert code == 0
    assert (r["a"]["passed"], r["b"]["passed"]) == (1, 2)
    assert r["paired"] == {"aWins": 0, "bWins": 1, "ties": 1}
    assert r["noise"] is True  # one discordant pair proves nothing


def test_compare_with_set_uses_same_file(tmp_workspace, fake_llm, tmp_path, capsys):
    a = _setup(tmp_path, LINEAR_YAML, golds=("draft",))
    assert main(["compare", str(a), "--set", "draft.temperature=0.5"]) == 0
    out = capsys.readouterr().out
    assert "draft.temperature=0.5" in out
    assert "within noise" in out


def test_compare_needs_b_or_set(tmp_path, capsys):
    a = _setup(tmp_path, LINEAR_YAML)
    assert main(["compare", str(a)]) == 1
    assert "second yaml or --set" in capsys.readouterr().err
