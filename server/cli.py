"""Headless CLI: agentforge check / run / resume / discard / replay / show / eval / compare."""

from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")  # explicit path: works from any cwd

import argparse  # noqa: E402
import asyncio  # noqa: E402
import json  # noqa: E402
import sys  # noqa: E402
import uuid  # noqa: E402

import gitfiles  # noqa: E402
import workspace  # noqa: E402
from archfile import AGENT_NODE_TYPE, ArchError, parse_arch  # noqa: E402
from evaluate import (  # noqa: E402
    EvalError,
    apply_sets,
    check_eval,
    compare_report,
    load_eval,
    render_compare,
    render_report,
    run_eval,
)
from events import FileEventEmitter, ListEventEmitter  # noqa: E402
from graphs.compile import PASSTHROUGH_TYPES, compile_graph  # noqa: E402
from logging_config import setup_logging  # noqa: E402
from replay import ReplayError  # noqa: E402
from runner import (  # noqa: E402
    DEFAULT_MODEL_CFG,
    discard_run,
    open_checkpointer,
    replay_run,
    resume_run,
    start_run,
    summarize,
    usd,
)

setup_logging()

EXIT = {"done": 0, "paused": 3, "error": 1}


def _out(s: str) -> None:
    sys.stdout.write(s + "\n")


def _err(s: str) -> None:
    sys.stderr.write(f"error: {s}\n")


def _short(s: str) -> str:
    s = " ".join(s.split())
    return s[:60] + "…" if len(s) > 60 else s


def render_summary(summary: dict, run_id: str, status: str) -> str:
    lines = [f"run {run_id}"]
    if "parent" in summary:
        lines.append(
            f"replay of {summary['parent']['runId']} from {summary['fromNode']}: "
            f"reused {len(summary['reused'])} nodes, saved {usd(summary['savedCost'])}"
        )
    visits = summary["visits"]
    w = max([len(v["node"]) for v in visits] + [5])
    for v in visits:
        tail = (
            f"-> {v['route']}"
            if v["route"]
            else (f'"{_short(v["preview"])}"' if v["preview"] else "")
        )
        lines.append(
            f"{v['node']:<{w}}  {v['status']:<7} {v['tokens']:>5} tok  "
            f"{usd(v['cost']):<9} {tail}".rstrip()
        )
    lines.append(
        f"{'total':<{w}}  {'':<7} {summary['totalTokens']:>5} tok  {usd(summary['totalCost'])}"
    )
    if summary["unpricedModels"]:
        lines.append(f"cost unknown (no price for {', '.join(summary['unpricedModels'])})")
    if summary["result"] is not None:
        r = summary["result"]
        if len(r) > 500:
            r = f"{r[:500]}… (full: agentforge show {run_id} <node>)"
        lines.append(f"result: {r}")
    if r := summary.get("repo"):
        if status == "paused":
            lines.append(f"branch {r['branch']} (worktree kept until the run finishes)")
        else:
            lines.append(
                f"branch {r['branch']} in {r['path']}: {r.get('diffstat') or 'no changes'} "
                "— review and merge it yourself"
            )
    if (i := summary["interrupt"]) and status == "paused":
        lines += [
            f"paused at {i['node']}: {i['question']}",
            f"choices: {' | '.join(i['choices'])}",
            f'next: agentforge resume {run_id} --choice <label> [--note "..."]',
        ]
    return "\n".join(lines)


def _hidden(run_id: str) -> set[str]:
    rec = workspace.read_run_record(run_id) or {}
    nodes = (rec.get("architecture") or {}).get("nodes", [])
    return {n["id"] for n in nodes if n["type"] in PASSTHROUGH_TYPES}


def _summary(run_id: str, rec: dict) -> dict:
    summary = summarize(workspace.read_events(run_id), _hidden(run_id))
    if "parent" in rec:
        for k in ("parent", "fromNode", "reused", "savedCost"):
            summary[k] = rec[k]
    if rec.get("repo"):
        summary["repo"] = rec["repo"]
    return summary


def _report(run_id: str, status: str, as_json: bool) -> int:
    summary = _summary(run_id, workspace.read_run_record(run_id) or {})
    if status == "error":  # node raised without emitting an error event: blame the open visit
        err = (workspace.read_run_record(run_id) or {}).get("error") or ""
        _err(err)
        for v in summary["visits"]:
            if v["status"] == "running":
                v["status"], v["preview"] = "failed", err
    if as_json:
        _out(json.dumps({**summary, "runId": run_id, "status": status}, ensure_ascii=False))
    else:
        _out(render_summary(summary, run_id, status))
    return EXIT[status]


def _parse(path: str, model: str | None):
    return parse_arch(Path(path).read_text(encoding="utf-8"), default_model=model)


def cmd_check(a) -> int:
    try:
        arch, warnings = _parse(a.yaml, a.model)
        compile_graph(arch, DEFAULT_MODEL_CFG, ListEventEmitter(), "check")
        check_eval(Path(a.yaml).read_text(encoding="utf-8"), Path(a.yaml))
    except (ArchError, ValueError, OSError) as e:
        _err(str(e))
        return 1
    for w in warnings:
        _out(f"warning: {w}")
    _out(f"ok: {len(arch['nodes'])} nodes")
    return 0


async def _run(a, arch, text, repo=None) -> int:
    run_id = str(uuid.uuid4())
    async with open_checkpointer() as cp:
        outcome = await start_run(
            arch,
            run_id=run_id,
            task=a.task,
            model_cfg={},
            emit=FileEventEmitter(run_id),
            checkpointer=cp,
            arch_path=str(Path(a.yaml).resolve()),
            arch_text=text,
            default_model=a.model,
            repo=repo,
        )
    return _report(run_id, outcome.status, a.json)


def _repo(a, arch) -> Path | None:
    """--repo <path> → the repo's top level; warns that uncommitted changes are left out."""
    if not a.repo:
        return None
    if not any(n["type"] == AGENT_NODE_TYPE for n in arch["nodes"]):
        raise ValueError("--repo needs a run: agent node")
    top = gitfiles.toplevel(Path(a.repo))
    if gitfiles.dirty(top):
        sys.stderr.write(f"warning: {top} has uncommitted changes; the run starts from HEAD\n")
    return top


def cmd_run(a) -> int:
    try:
        text = Path(a.yaml).read_text(encoding="utf-8")
        arch, warnings = parse_arch(text, default_model=a.model)
        repo = _repo(a, arch)
    except (ArchError, OSError, ValueError, RuntimeError) as e:
        _err(str(e))
        return 1
    for w in warnings:
        sys.stderr.write(f"warning: {w}\n")
    return asyncio.run(_run(a, arch, text, repo))


async def _resume(a) -> int:
    async with open_checkpointer() as cp:
        outcome = await resume_run(
            a.run_id,
            {"action": a.choice, "reason": a.note or ""},
            emit=FileEventEmitter(a.run_id),
            checkpointer=cp,
        )
    return _report(a.run_id, outcome.status, a.json)


def cmd_resume(a) -> int:
    rec = workspace.read_run_record(a.run_id)
    if rec is None:
        _err("unknown run")
        return 1
    if rec.get("status") != "paused":
        _err(f"run {a.run_id} is {rec.get('status')}, not paused")
        return 1
    pending = [e for e in workspace.read_events(a.run_id) if e.get("eventType") == "interrupt"]
    allowed = pending[-1]["output"]["actions"] if pending else []
    if a.choice not in allowed:
        _err(f"choice must be one of {' | '.join(allowed)}")
        return 1
    return asyncio.run(_resume(a))


def cmd_discard(a) -> int:
    try:
        discard_run(a.run_id)
    except LookupError:
        _err("unknown run")
        return 1
    except ValueError as e:
        _err(str(e))
        return 1
    if a.json:
        _out(json.dumps({"runId": a.run_id, "status": "abandoned"}, ensure_ascii=False))
    else:
        _out(f"abandoned {a.run_id}")
    return 0


async def _replay(a, arch, path, text, default_model) -> int:
    run_id = str(uuid.uuid4())
    async with open_checkpointer() as cp:
        outcome = await replay_run(
            a.run_id,
            arch,
            run_id=run_id,
            from_node=a.from_node,
            emit=FileEventEmitter(run_id),
            checkpointer=cp,
            arch_path=path,
            arch_text=text,
            default_model=default_model,
        )
    return _report(run_id, outcome.status, a.json)


def cmd_replay(a) -> int:
    rec = workspace.read_run_record(a.run_id)
    if rec is None:
        _err("unknown run")
        return 1
    if a.model and not a.arch:
        _err("--model needs --arch")
        return 1
    model = a.model or rec.get("defaultModel")
    try:
        if a.arch:
            path = str(Path(a.arch).resolve())
            text = Path(path).read_text(encoding="utf-8")
            arch, warnings = parse_arch(text, default_model=model)
            for w in warnings:
                sys.stderr.write(f"warning: {w}\n")
        else:
            arch, path, text = rec["architecture"], rec.get("archPath"), rec.get("archText")
        return asyncio.run(_replay(a, arch, path, text, model))
    except (ArchError, OSError, ReplayError, LookupError, ValueError, RuntimeError) as e:
        _err(str(e))
        return 1


def cmd_show(a) -> int:
    rec = workspace.read_run_record(a.run_id)
    if rec is None:
        _err("unknown run")
        return 1
    if a.node is None:
        _out(f"status: {rec.get('status')}")
        _out(
            render_summary(
                _summary(a.run_id, rec),
                a.run_id,
                rec["status"],
            )
        )
        return 0
    files = [f for f in workspace.list_run_files(a.run_id) if f["nodeId"] == a.node]
    if not files:
        _err(f"no output for node {a.node}")
        return 1
    _out(workspace.read_run_file(a.run_id, files[-1]["name"])["content"])
    return 0


async def _eval(a, arch, spec, text, path=None) -> dict:
    async with open_checkpointer() as cp:
        return await run_eval(
            arch,
            spec,
            limit=a.limit,
            checkpoint=a.checkpoint,
            checkpointer=cp,
            arch_path=str(Path(path or a.yaml).resolve()),
            arch_text=text,
            default_model=a.model,
        )


def cmd_eval(a) -> int:
    try:
        text = Path(a.yaml).read_text(encoding="utf-8")
        arch, warnings = parse_arch(text, default_model=a.model)
        spec = load_eval(text, Path(a.yaml))
        compile_graph(arch, DEFAULT_MODEL_CFG, ListEventEmitter(), "check")
        r = asyncio.run(_eval(a, arch, spec, text))
    except (ArchError, EvalError, ValueError, OSError) as e:
        _err(str(e))
        return 1
    for w in warnings:
        sys.stderr.write(f"warning: {w}\n")
    _out(json.dumps(r, ensure_ascii=False) if a.json else render_report(r, a.yaml))
    return 0


def cmd_compare(a) -> int:
    if not a.yaml_b and not a.set:
        _err("compare needs a second yaml or --set node.field=value")
        return 1
    try:
        text_a = Path(a.yaml).read_text(encoding="utf-8")
        path_b = a.yaml_b or a.yaml
        text_b = apply_sets(Path(path_b).read_text(encoding="utf-8"), a.set or [])
        arch_a, _ = parse_arch(text_a, default_model=a.model)
        arch_b, _ = parse_arch(text_b, default_model=a.model)
        spec = load_eval(text_a, Path(a.yaml))  # both variants run A's dataset
        for arch in (arch_a, arch_b):
            compile_graph(arch, DEFAULT_MODEL_CFG, ListEventEmitter(), "check")
        ra = asyncio.run(_eval(a, arch_a, spec, text_a))
        rb = asyncio.run(_eval(a, arch_b, spec, text_b, path_b))
    except (ArchError, EvalError, ValueError, OSError) as e:
        _err(str(e))
        return 1
    c = compare_report(ra, rb)
    name_b = " ".join([path_b, *(f"--set {s}" for s in a.set or [])])
    _out(json.dumps(c, ensure_ascii=False) if a.json else render_compare(c, a.yaml, name_b))
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="agentforge")
    sub = p.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("check")
    c.add_argument("yaml")
    c.add_argument("--model")
    r = sub.add_parser("run")
    r.add_argument("yaml")
    r.add_argument("--task", required=True)
    r.add_argument("--model")
    r.add_argument("--repo", help="work on a branch of this git repo (agent nodes)")
    r.add_argument("--json", action="store_true")
    s = sub.add_parser("resume")
    s.add_argument("run_id")
    s.add_argument("--choice", required=True)
    s.add_argument("--note")
    s.add_argument("--json", action="store_true")
    d = sub.add_parser("discard", help="abandon a paused run and drop its --repo worktree")
    d.add_argument("run_id")
    d.add_argument("--json", action="store_true")
    q = sub.add_parser("replay")
    q.add_argument("run_id")
    q.add_argument("--arch")
    q.add_argument("--from", dest="from_node")
    q.add_argument("--model")
    q.add_argument("--json", action="store_true")
    e = sub.add_parser("eval")
    e.add_argument("yaml")
    e.add_argument("--limit", type=int)
    e.add_argument("--checkpoint")
    e.add_argument("--model")
    e.add_argument("--json", action="store_true")
    m = sub.add_parser("compare")
    m.add_argument("yaml")
    m.add_argument("yaml_b", nargs="?")
    m.add_argument("--set", action="append")
    m.add_argument("--limit", type=int)
    m.add_argument("--checkpoint")
    m.add_argument("--model")
    m.add_argument("--json", action="store_true")
    w = sub.add_parser("show")
    w.add_argument("run_id")
    w.add_argument("node", nargs="?")
    a = p.parse_args(argv)
    cmds = {
        "check": cmd_check,
        "run": cmd_run,
        "resume": cmd_resume,
        "discard": cmd_discard,
        "replay": cmd_replay,
        "show": cmd_show,
        "eval": cmd_eval,
        "compare": cmd_compare,
    }
    return cmds[a.cmd](a)


if __name__ == "__main__":
    sys.exit(main())
