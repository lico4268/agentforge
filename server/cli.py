"""Headless CLI: agentforge check / run / resume / show."""

from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")  # explicit path: works from any cwd

import argparse  # noqa: E402
import asyncio  # noqa: E402
import json  # noqa: E402
import sys  # noqa: E402
import uuid  # noqa: E402

import workspace  # noqa: E402
from archfile import ArchError, parse_arch  # noqa: E402
from events import FileEventEmitter, ListEventEmitter  # noqa: E402
from graphs.compile import PASSTHROUGH_TYPES, compile_graph  # noqa: E402
from logging_config import setup_logging  # noqa: E402
from runner import DEFAULT_MODEL_CFG, open_checkpointer, resume_run, start_run  # noqa: E402

setup_logging()

EXIT = {"done": 0, "paused": 3, "error": 1}


def _out(s: str) -> None:
    sys.stdout.write(s + "\n")


def _err(s: str) -> None:
    sys.stderr.write(f"error: {s}\n")


def _body(output) -> str | None:
    body = workspace._extract_body(output)
    if body is None and isinstance(output, dict):
        body = next((v for v in output.values() if isinstance(v, str)), None)
    return body


def summarize(events: list[dict], hidden: set[str]) -> dict:
    visits: list[dict] = []
    current: dict[str, dict] = {}  # node id -> its open visit
    interrupt = None
    result = None

    def visit(node: str) -> dict:
        if node not in current:
            v = {
                "node": node,
                "status": "running",
                "tokens": 0,
                "cost": 0.0,
                "preview": "",
                "route": None,
            }
            current[node] = v
            visits.append(v)
        return current[node]

    for ev in events:
        t, node, out = ev.get("eventType"), ev.get("nodeId"), ev.get("output")
        if t == "node_start":
            current.pop(node, None)
            visit(node)
        elif t == "log" and ev.get("tokenUsage"):
            u, v = ev["tokenUsage"], visit(node)
            v["tokens"] += u.get("total_tokens", 0)
            v["cost"] += u.get("cost", 0.0)
        elif t == "node_end":
            v = visit(node)
            v["status"] = "done"
            v["preview"] = _body(out) or ""
            if isinstance(out, dict):
                v["route"] = next((x for k, x in out.items() if k.startswith("__route__")), None)
            if node not in hidden:
                result = _body(out)
        elif t == "error":
            v = visit(node)
            v["status"], v["preview"] = "failed", ev.get("message") or ""
        elif t == "interrupt":
            visit(node)["status"] = "paused"
            interrupt = {"node": node, "question": out["summary"], "choices": out["actions"]}
        elif t == "decision_record":
            v = visit(node)
            v["status"], v["route"] = "done", out["decision"]
    visits = [v for v in visits if v["node"] not in hidden]
    if interrupt and interrupt["node"] in hidden:
        interrupt = None
    # an interrupt that was later resolved is no longer pending
    if interrupt and current.get(interrupt["node"], {}).get("status") != "paused":
        interrupt = None
    return {
        "visits": visits,
        "totalTokens": sum(v["tokens"] for v in visits),
        "totalCost": sum(v["cost"] for v in visits),
        "interrupt": interrupt,
        "result": result,
    }


def _short(s: str) -> str:
    s = " ".join(s.split())
    return s[:60] + "…" if len(s) > 60 else s


def render_summary(summary: dict, run_id: str, status: str) -> str:
    lines = [f"run {run_id}"]
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
            f"${v['cost']:.4f}  {tail}".rstrip()
        )
    lines.append(
        f"{'total':<{w}}  {'':<7} {summary['totalTokens']:>5} tok  ${summary['totalCost']:.4f}"
    )
    if summary["result"] is not None:
        r = summary["result"]
        if len(r) > 500:
            r = f"{r[:500]}… (full: agentforge show {run_id} <node>)"
        lines.append(f"result: {r}")
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


def _report(run_id: str, status: str, as_json: bool) -> int:
    summary = summarize(workspace.read_events(run_id), _hidden(run_id))
    if status == "error":  # node raised without emitting an error event: blame the open visit
        err = (workspace.read_run_record(run_id) or {}).get("error") or ""
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
    except (ArchError, ValueError, OSError) as e:
        _err(str(e))
        return 1
    for w in warnings:
        _out(f"warning: {w}")
    _out(f"ok: {len(arch['nodes'])} nodes")
    return 0


async def _run(a, arch, text) -> int:
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
        )
    return _report(run_id, outcome.status, a.json)


def cmd_run(a) -> int:
    try:
        text = Path(a.yaml).read_text(encoding="utf-8")
        arch, warnings = parse_arch(text, default_model=a.model)
    except (ArchError, OSError) as e:
        _err(str(e))
        return 1
    for w in warnings:
        sys.stderr.write(f"warning: {w}\n")
    return asyncio.run(_run(a, arch, text))


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


def cmd_show(a) -> int:
    rec = workspace.read_run_record(a.run_id)
    if rec is None:
        _err("unknown run")
        return 1
    if a.node is None:
        _out(f"status: {rec.get('status')}")
        _out(
            render_summary(
                summarize(workspace.read_events(a.run_id), _hidden(a.run_id)),
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
    r.add_argument("--json", action="store_true")
    s = sub.add_parser("resume")
    s.add_argument("run_id")
    s.add_argument("--choice", required=True)
    s.add_argument("--note")
    s.add_argument("--json", action="store_true")
    w = sub.add_parser("show")
    w.add_argument("run_id")
    w.add_argument("node", nargs="?")
    a = p.parse_args(argv)
    return {"check": cmd_check, "run": cmd_run, "resume": cmd_resume, "show": cmd_show}[a.cmd](a)


if __name__ == "__main__":
    sys.exit(main())
