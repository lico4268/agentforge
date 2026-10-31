import pytest
from arch_samples import CHECKPOINT_YAML, FAN_IN, LINEAR_YAML, LOOP_YAML, THREE_YAML

from archfile import parse_arch
from events import FileEventEmitter
from replay import ReplayError
from runner import open_checkpointer, replay_run, resume_run, start_run
from workspace import read_events, read_run_record


async def test_start_run_records_done_status_and_events(tmp_workspace, fake_llm):
    arch, _ = parse_arch(LINEAR_YAML)
    async with open_checkpointer() as cp:
        out = await start_run(
            arch, run_id="r1", task="t", model_cfg={}, emit=FileEventEmitter("r1"), checkpointer=cp
        )
    assert out.status == "done"
    rec = read_run_record("r1")
    assert rec["status"] == "done" and rec["architecture"] == arch and rec["task"] == "t"
    assert any(e["eventType"] == "node_end" and e["nodeId"] == "draft" for e in read_events("r1"))
    assert any(e["eventType"] == "log" and "tokenUsage" in e for e in read_events("r1"))


async def test_paused_run_resumes_in_a_fresh_checkpointer(tmp_workspace, fake_llm):
    arch, _ = parse_arch(CHECKPOINT_YAML)
    async with open_checkpointer() as cp:
        first = await start_run(
            arch, run_id="r2", task="t", model_cfg={}, emit=FileEventEmitter("r2"), checkpointer=cp
        )
    assert first.status == "paused"
    async with open_checkpointer() as cp:  # new connection = new process
        second = await resume_run(
            "r2", {"action": "approve"}, emit=FileEventEmitter("r2"), checkpointer=cp
        )
    assert second.status == "done" and read_run_record("r2")["status"] == "done"
    assert fake_llm.calls.count("draft") == 1


async def test_resume_ignores_current_arch_file(tmp_workspace, fake_llm, tmp_path):
    path = tmp_path / "x.yaml"
    path.write_text(CHECKPOINT_YAML)
    arch, _ = parse_arch(path.read_text())
    async with open_checkpointer() as cp:
        await start_run(
            arch,
            run_id="r3",
            task="t",
            model_cfg={},
            emit=FileEventEmitter("r3"),
            checkpointer=cp,
            arch_path=str(path),
            arch_text=CHECKPOINT_YAML,
        )
    path.unlink()
    async with open_checkpointer() as cp:
        out = await resume_run(
            "r3", {"action": "approve"}, emit=FileEventEmitter("r3"), checkpointer=cp
        )
    assert out.status == "done"


async def test_node_exception_marks_run_error(tmp_workspace, fake_llm):
    fake_llm.fail.add("draft")
    arch, _ = parse_arch(LINEAR_YAML)
    async with open_checkpointer() as cp:
        out = await start_run(
            arch, run_id="r4", task="t", model_cfg={}, emit=FileEventEmitter("r4"), checkpointer=cp
        )
    assert out.status == "error" and "boom" in out.error
    assert read_run_record("r4")["status"] == "error"


async def test_resume_unknown_run_raises(tmp_workspace):
    async with open_checkpointer() as cp:
        with pytest.raises(LookupError):
            await resume_run(
                "nope", {"action": "approve"}, emit=FileEventEmitter("nope"), checkpointer=cp
            )


async def test_resume_without_checkpoint_errors_without_llm(tmp_workspace, fake_llm):
    arch, _ = parse_arch(CHECKPOINT_YAML)
    async with open_checkpointer() as cp:
        await start_run(
            arch, run_id="r9", task="t", model_cfg={}, emit=FileEventEmitter("r9"), checkpointer=cp
        )
    from runner import checkpoint_db

    checkpoint_db().unlink()
    calls = list(fake_llm.calls)
    async with open_checkpointer() as cp:
        out = await resume_run(
            "r9", {"action": "approve"}, emit=FileEventEmitter("r9"), checkpointer=cp
        )
    assert out.status == "error" and "no checkpoint" in out.error
    assert fake_llm.calls == calls and read_run_record("r9")["status"] == "error"


async def _start(yaml_text, run_id, cp):
    arch, _ = parse_arch(yaml_text)
    return await start_run(
        arch, run_id=run_id, task="t", model_cfg={}, emit=FileEventEmitter(run_id), checkpointer=cp
    )


async def _replay(yaml_text, parent, run_id, cp, from_node=None):
    arch, _ = parse_arch(yaml_text)
    return await replay_run(
        parent,
        arch,
        run_id=run_id,
        from_node=from_node,
        emit=FileEventEmitter(run_id),
        checkpointer=cp,
    )


async def test_replay_runs_only_from_changed_node(tmp_workspace, fake_llm):
    async with open_checkpointer() as cp:
        await _start(THREE_YAML, "p", cp)
        fake_llm.calls.clear()
        out = await _replay(THREE_YAML.replace("prompt: pb", "prompt: NEW"), "p", "c1", cp)
    assert out.status == "done" and fake_llm.calls == ["b", "c"]
    rec = read_run_record("c1")
    assert rec["parent"]["runId"] == "p" and rec["fromNode"] == "b"
    assert rec["reused"] == ["a"] and rec["savedCost"] == pytest.approx(0.001)
    assert rec["task"] == "t"


async def test_replay_refusal_writes_nothing(tmp_workspace, fake_llm):
    async with open_checkpointer() as cp:
        await _start(THREE_YAML, "p", cp)
        fake_llm.calls.clear()
        with pytest.raises(ReplayError):
            await _replay(THREE_YAML, "p", "c1", cp)
    assert read_run_record("c1") is None and fake_llm.calls == []


async def test_replay_fan_out_sibling_reruns(tmp_workspace, fake_llm):
    base = FAN_IN % ", join: all"
    async with open_checkpointer() as cp:
        await _start(base, "p", cp)
        fake_llm.calls.clear()
        edited = base.replace("out: [y], prompt: p", "out: [y], prompt: q")
        await _replay(edited, "p", "c1", cp)
    assert set(fake_llm.calls) == {"a", "b", "judge"}
    assert read_run_record("c1")["reused"] == []


async def test_replay_starts_at_first_visit_of_looped_node(tmp_workspace, fake_llm):
    async with open_checkpointer() as cp:
        assert (await _start(LOOP_YAML, "p", cp)).status == "paused"
        r1 = await resume_run(
            "p", {"action": "revise", "reason": "more"}, emit=FileEventEmitter("p"), checkpointer=cp
        )
        assert r1.status == "paused"
        r2 = await resume_run(
            "p", {"action": "approve"}, emit=FileEventEmitter("p"), checkpointer=cp
        )
        assert r2.status == "done" and fake_llm.calls.count("draft") == 2
        fake_llm.calls.clear()
        out = await _replay(LOOP_YAML.replace("prompt: pd", "prompt: NEW"), "p", "c1", cp)
    assert out.status == "paused" and fake_llm.calls == ["draft"]
    starts = [
        e for e in read_events("c1") if e["eventType"] == "node_start" and e["nodeId"] == "draft"
    ]
    assert len(starts) == 1


async def test_replay_failed_parent_from_failed_node(tmp_workspace, fake_llm):
    fake_llm.fail = {"b"}
    async with open_checkpointer() as cp:
        assert (await _start(THREE_YAML, "p", cp)).status == "error"
        fake_llm.fail.clear()
        fake_llm.calls.clear()
        out = await _replay(THREE_YAML.replace("prompt: pb", "prompt: NEW"), "p", "c1", cp)
    assert out.status == "done" and fake_llm.calls == ["b", "c"]


async def test_paused_replay_can_be_resumed(tmp_workspace, fake_llm):
    async with open_checkpointer() as cp:
        await _start(CHECKPOINT_YAML, "p", cp)
        await resume_run("p", {"action": "approve"}, emit=FileEventEmitter("p"), checkpointer=cp)
        out = await _replay(CHECKPOINT_YAML.replace("prompt: p", "prompt: NEW"), "p", "c1", cp)
        assert out.status == "paused"
        done = await resume_run(
            "c1", {"action": "approve"}, emit=FileEventEmitter("c1"), checkpointer=cp
        )
    assert done.status == "done"


async def test_replay_of_replay_rejects_reused_node(tmp_workspace, fake_llm):
    async with open_checkpointer() as cp:
        await _start(THREE_YAML, "p", cp)
        b_edit = THREE_YAML.replace("prompt: pb", "prompt: NEW")
        await _replay(b_edit, "p", "c1", cp)
        with pytest.raises(ReplayError, match="was reused from run p"):
            await _replay(b_edit.replace("prompt: pa", "prompt: NA"), "c1", "c2", cp)
        out = await _replay(b_edit.replace("prompt: pc", "prompt: NC"), "c1", "c2", cp)
    assert out.status == "done"
    assert read_run_record("c2")["reused"] == ["a", "b"]


async def test_start_run_records_default_model(tmp_workspace, fake_llm):
    arch, _ = parse_arch(LINEAR_YAML)
    async with open_checkpointer() as cp:
        await start_run(
            arch,
            run_id="r1",
            task="t",
            model_cfg={},
            emit=FileEventEmitter("r1"),
            checkpointer=cp,
            default_model="anthropic/x",
        )
    assert read_run_record("r1")["defaultModel"] == "anthropic/x"
