import pytest
from arch_samples import CHECKPOINT_YAML, LINEAR_YAML

from archfile import parse_arch
from events import FileEventEmitter
from runner import open_checkpointer, resume_run, start_run
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
