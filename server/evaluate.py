"""agentforge eval: run an arch.yaml over a dataset and report success rate and cost."""

import json
import uuid
from collections import Counter
from pathlib import Path

import yaml
from langchain_core.messages import HumanMessage
from pydantic import BaseModel

import workspace
from archfile import ArchError, _split_model
from events import FileEventEmitter
from graphs.compile import PASSTHROUGH_TYPES
from harness import gsm8k_grader
from models import ModelSettings, build_model
from runner import resume_run, start_run, summarize, usd

MAX_RESUMES = 20  # a checkpoint inside a loop is answered again each pass


class EvalError(ValueError):
    """Bad eval: block or dataset. Message goes to the user as-is."""


def _exact(answer: str | None, gold: str) -> bool:
    return answer is not None and answer.strip() == gold.strip()


def _contains(answer: str | None, gold: str) -> bool:
    return answer is not None and gold.strip().lower() in answer.lower()


GRADERS = {"number": gsm8k_grader, "exact": _exact, "contains": _contains}


class Verdict(BaseModel):
    passed: bool
    reason: str


def make_grader(spec):
    """Grader spec → async (answer, gold, task) -> bool."""
    if isinstance(spec, str):
        fn = GRADERS[spec]

        async def grade(answer, gold, task):
            return fn(answer, gold)

        return grade

    llm = spec["llm"]
    provider, model = _split_model(llm["model"])
    judge = build_model(ModelSettings(provider=provider, model=model)).with_structured_output(
        Verdict
    )

    # ponytail: grading calls are not counted in the report's cost
    async def grade(answer, gold, task):
        prompt = (
            f"Grade the answer.\n\n## Task\n{task}\n\n## Reference answer\n{gold}\n\n"
            f"## Answer\n{answer}\n\n## Rubric\n{llm.get('rubric') or 'Matches the reference.'}"
        )
        verdict = await judge.ainvoke([HumanMessage(content=prompt)])
        return verdict.passed

    return grade


def load_eval(text: str, yaml_path: Path) -> dict:
    """Validate the eval: block and load its dataset (path relative to the yaml file)."""
    spec = (yaml.safe_load(text) or {}).get("eval")
    if not isinstance(spec, dict):
        raise EvalError("no eval: block in this arch.yaml")
    grader = spec.get("grader")
    if isinstance(grader, dict):
        if not (grader.get("llm") or {}).get("model"):
            raise EvalError("llm grader needs model: {llm: {model: provider/model, rubric: ...}}")
    elif grader not in GRADERS:
        raise EvalError(f"grader must be one of {sorted(GRADERS)} or {{llm: ...}}, got {grader!r}")
    repeat = spec.get("repeat", 1)
    if not isinstance(repeat, int) or repeat < 1:
        raise EvalError(f"repeat must be a positive integer, got {repeat!r}")
    path = Path(yaml_path).parent / str(spec.get("dataset"))
    if not path.is_file():
        raise EvalError(f"dataset not found: {path}")
    items = []
    for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
            items.append({"task": row.get("task", row.get("question")), "gold": str(row["gold"])})
        except (json.JSONDecodeError, KeyError, AttributeError) as e:
            raise EvalError(f'{path}:{n}: expected {{"task": ..., "gold": ...}}') from e
    return {"items": items, "grader": grader, "repeat": repeat}


async def _one(arch, item, *, checkpoint, checkpointer, arch_path, arch_text, default_model):
    run_id = str(uuid.uuid4())
    emit = FileEventEmitter(run_id)
    outcome = await start_run(
        arch,
        run_id=run_id,
        task=item["task"],
        model_cfg={},
        emit=emit,
        checkpointer=checkpointer,
        arch_path=arch_path,
        arch_text=arch_text,
        default_model=default_model,
    )
    hidden = {n["id"] for n in arch["nodes"] if n["type"] in PASSTHROUGH_TYPES}
    summary = summarize(workspace.read_events(run_id), hidden)
    for _ in range(MAX_RESUMES):
        pending = summary["interrupt"]
        if outcome.status != "paused" or not pending or checkpoint not in pending["choices"]:
            break
        decision = {"action": checkpoint, "reason": "agentforge eval --checkpoint"}
        outcome = await resume_run(run_id, decision, emit=emit, checkpointer=checkpointer)
        summary = summarize(workspace.read_events(run_id), hidden)
    return run_id, outcome.status, summary


async def run_eval(
    arch: dict,
    spec: dict,
    *,
    limit: int | None,
    checkpoint: str | None,
    checkpointer,
    arch_path: str | None = None,
    arch_text: str | None = None,
    default_model: str | None = None,
) -> dict:
    items = spec["items"][:limit] if limit else spec["items"]
    grade = make_grader(spec["grader"])
    results = []
    # ponytail: items run one at a time; add concurrency if eval wall time hurts
    for i, item in enumerate(items):
        for _ in range(spec["repeat"]):
            run_id, status, summary = await _one(
                arch,
                item,
                checkpoint=checkpoint,
                checkpointer=checkpointer,
                arch_path=arch_path,
                arch_text=arch_text,
                default_model=default_model,
            )
            answer = summary["result"]
            passed = status == "done" and await grade(answer, item["gold"], item["task"])
            results.append(
                {
                    "item": i,
                    "runId": run_id,
                    "status": status,
                    "passed": passed,
                    "answer": answer,
                    "gold": item["gold"],
                    "tokens": summary["totalTokens"],
                    "cost": summary["totalCost"],
                    "visits": summary["visits"],
                    "unpricedModels": summary["unpricedModels"],
                }
            )
    return report(results, len(items))


def _sum(costs):
    return None if None in costs else sum(costs)


def report(results: list[dict], n_items: int) -> dict:
    runs = len(results) or 1
    passed = sum(r["passed"] for r in results)
    total_cost = _sum([r["cost"] for r in results])
    nodes: dict[str, dict] = {}
    routes: Counter = Counter()
    for r in results:
        for v in r["visits"]:
            n = nodes.setdefault(v["node"], {"tokens": 0, "costs": []})
            n["tokens"] += v["tokens"]
            n["costs"].append(v["cost"])
            if v["route"]:
                routes[f"{v['node']} -> {v['route']}"] += 1
    errors = sum(r["status"] == "error" for r in results)
    return {
        "items": n_items,
        "runs": len(results),
        "passed": passed,
        "successRate": passed / runs,
        "paused": sum(r["status"] == "paused" for r in results),
        "errors": errors,
        "errorRate": errors / runs,
        "totalCost": total_cost,
        "costPerSuccess": total_cost / passed if passed and total_cost is not None else None,
        "avgTokens": sum(r["tokens"] for r in results) / runs,
        "unpricedModels": sorted({m for r in results for m in r["unpricedModels"]}),
        "nodes": {
            k: {
                "avgTokens": v["tokens"] / runs,
                "avgCost": None if (c := _sum(v["costs"])) is None else c / runs,
            }
            for k, v in nodes.items()
        },
        "routes": dict(routes),
        "results": [{k: v for k, v in r.items() if k != "visits"} for r in results],
    }


def render_report(r: dict, title: str) -> str:
    lines = [
        f"eval {title}: {r['items']} items, {r['runs']} runs",
        f"passed {r['passed']}/{r['runs']} ({r['successRate']:.1%})  paused {r['paused']}  "
        f"errors {r['errors']} ({r['errorRate']:.1%})",
        f"cost {usd(r['totalCost'])} total, {usd(r['costPerSuccess'])} per success, "
        f"{r['avgTokens']:.0f} tok/run",
    ]
    if r["unpricedModels"]:
        lines.append(f"cost unknown (no price for {', '.join(r['unpricedModels'])})")
    w = max([len(k) for k in r["nodes"]] + [4])
    lines.append(f"{'node':<{w}}  {'avg tok':>8}  avg cost")
    for k, v in r["nodes"].items():
        lines.append(f"{k:<{w}}  {v['avgTokens']:>8.0f}  {usd(v['avgCost'])}")
    if r["routes"]:
        lines.append("routes: " + ", ".join(f"{k}: {n}" for k, n in r["routes"].items()))
    failed = [x for x in r["results"] if not x["passed"]]
    for x in failed[:10]:
        why = "wrong answer" if x["status"] == "done" else x["status"]
        lines.append(f"failed item {x['item']} ({why}): agentforge show {x['runId']}")
    if len(failed) > 10:
        lines.append(f"… {len(failed) - 10} more failed runs (see --json)")
    return "\n".join(lines)


def check_eval(text: str, yaml_path: Path) -> None:
    """Raise EvalError if a present eval: block is invalid (used by `agentforge check`)."""
    try:
        has_eval = "eval" in (yaml.safe_load(text) or {})
    except yaml.YAMLError as e:
        raise ArchError(str(e)) from e
    if has_eval:
        load_eval(text, yaml_path)
