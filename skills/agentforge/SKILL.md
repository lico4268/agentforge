---
name: agentforge
description: Build, run, and resume LLM agent pipelines written as arch.yaml with the agentforge CLI. Use when the same multi-step flow will run many times, needs cheap or mixed (non-Claude) models per step, or needs per-node cost numbers. Do not use for one-off tasks — do those directly.
---

# agentforge

agentforge runs an LLM pipeline described in a single `arch.yaml` file and reports
per-node tokens and cost.

## When to use / when not to

Use it when the flow will run many times, when steps should use cheap or non-Claude models,
or when you need per-node cost numbers.

Do not use it for a one-off task: if the work will run once, just do it directly.

## arch.yaml grammar

```yaml
name: My pipeline
model: anthropic/claude-haiku-4-5-20251001   # default model, provider/model

flow: |                    # plain mermaid; input and output are built in
  input --> draft --> gate
  gate -->|approve| output
  gate -->|reject| output

nodes:
  draft:
    in:  [task]            # state keys read; `task` is prefilled with --task
    out: [answer]          # state keys written
    prompt: |
      Write a short answer to the task.
    # optional: model, temperature, max_tokens, join: all|any
  gate: {run: human.checkpoint}
```

- `flow:` is mermaid `a --> b` / `a -->|label| b`. Nodes not listed under `nodes:` must be a built-in:
  `input`, `output`, `human.checkpoint` or `loop.guard`.
- Node keys: `in`, `out`, `prompt`, `model` (`provider/model`), `temperature`, `max_tokens`,
  `join`.
- A node with 2 or more labelled outgoing edges is an LLM branch: the model picks one label.
- A node with 2 or more plain incoming edges needs `join: all` (wait for every one) or
  `join: any` (run on each).
- `run: human.checkpoint` pauses for a person; the choices offered are the edge labels
  wired from it (e.g. only `approve` / `reject`). `--note` is recorded in the run log but not fed
  to any node. In `draft-approve.yaml` a `reject` still flows to `output`.
- `run: loop.guard` with `max: N` bounds a loop (labels `loopBack` / `exit`). Cycles get a
  guard inserted automatically if you do not write one.

Examples: `server/arch/gsm8k.yaml` (branch + retry loop, with an `eval:` block),
`server/arch/draft-approve.yaml` (human checkpoint), `server/arch/fib-agent.yaml` (agent node).

### run: agent (shell work)

```yaml
  coder:
    run: agent
    in:  [task, plan]
    out: [result]          # exactly one: the agent's final answer
    prompt: Implement the plan. Run the tests before finishing.
    model: openrouter/qwen/qwen3-coder
    limits: {steps: 30, cost: 0.50}   # defaults; hitting one fails the node
    network: false         # default; true lets commands reach the internet
    secrets: [TAVILY_API_KEY]          # env vars from server/.env passed into the sandbox
    files: {read: [notes], write: [src]}   # optional; without it the node sees all of files/
```

An agent node is a mini-swe-agent loop: the model runs bash commands until it submits an answer.
Every command runs in a bwrap sandbox: empty environment (LLM API keys never enter it), no
network unless `network: true`, read-only system, and only the run's
`server/workspace/<run_id>/files/` writable. All agent nodes of a run share that folder; it is a
git repo and each agent visit ends in a commit (`agentforge: <node> visit <n>`). The node's
output lists `changedFiles`, the `commit`, `steps`, and the `trajectory` file
(`agent/<node>-<n>.json`, the full conversation). Web search: `search "<query>"` is on the
sandbox PATH; it needs `network: true` and `secrets: [TAVILY_API_KEY]`. Agent nodes need
`bwrap` installed and cannot branch.

`files:` narrows what a node sees inside `files/`: it can read the `read` and `write` folders and
write only the `write` ones. Anything else it writes there is discarded (not committed). It sees
no `.git` unless `"."` is listed (`.` means the whole folder); a path in both lists is an error.
A scope folder that is or sits under a symlink fails the node. `.git` is read-only in the sandbox
for every node, so git can read history but not change it.

To work on an existing repo, add `--repo <path>` to `run`: `files/` becomes a git worktree on a
new branch `agentforge/<run_id>` from the repo's `HEAD`, so the user's checkout is never touched
and uncommitted changes are not included (the CLI warns). Inside the sandbox `git` works
read-only. When the run finishes the worktree folder is removed and the branch stays; the summary
prints its diffstat. Tell the user the branch name; merging is their call.

### eval: (optional)

```yaml
eval:
  dataset: data.jsonl   # relative to the yaml; one {"task": ..., "gold": ...} per line
  grader: number        # number | exact | contains | {llm: {model: provider/model, rubric: "..."}}
  repeat: 1             # runs per item
```

`agentforge eval <file.yaml> [--limit N] [--checkpoint <label>] [--model provider/model] [--json]`
runs every item and prints the success rate, cost per success, per-node average tokens and
cost, and branch-label counts. A run that pauses at a checkpoint counts as a failure unless
`--checkpoint <label>` answers every pause with that label. Each item is a normal run:
`agentforge show <run_id>` works on the failed ones it lists.

### compare

`agentforge compare a.yaml b.yaml [--limit N] [--checkpoint <label>] [--json]`, or change one field
without copying the file: `agentforge compare a.yaml --set reviewer.model=google/gemini-3.1-flash-lite`
(`--set` repeats; `model=...` without a dot sets the top-level default). Both variants run A's
`eval:` dataset on the same items. It prints both reports side by side, per-node cost, and paired
wins/losses/ties. When it warns that the success-rate difference is within noise, trust the cost
numbers only: with few items, cost is the reliable signal.

## Working loop

1. Write the arch.yaml.
2. `agentforge check <file.yaml>` until it prints `ok`. Add `--model provider/m` to also catch a missing provider API key
   before running.
3. `agentforge run <file.yaml> --task "<text>" [--model provider/model] [--repo <path>] [--json]`.
4. If it exits 3 (paused), read the `question` and `choices` it prints, ask the user in chat,
   then `agentforge resume <run_id> --choice <label> [--note "<text>"] [--json]`.
5. Read only the summary. For a specific node's full output:
   `agentforge show <run_id> <node>` (`agentforge show <run_id>` reprints the summary).
6. If the result is not what you wanted, edit the YAML and run
   `agentforge replay <run_id> --arch <file.yaml> [--from <node>] [--json]`: it re-runs from the first
   changed node and reuses the earlier nodes' outputs. `flow changed — run it fresh` means the wiring
   changed: use `run` instead. `upstream node … changed` means start earlier: pass the `--from` it
   suggests. `replay` also works on a failed run. Agent nodes' `files/` is rewound too: the replay
   starts from the parent's last agent commit before the start node (with `--repo`, on a new
   branch).
7. When the flow will be reused, measure it: `agentforge eval` on a small dataset (`--limit 5`
   first). Report success rate and cost per success, not a single run. To make it cheaper, change
   one thing and `agentforge compare`; adopt the cheaper variant if the success rate did not drop.
8. Report the result and the per-node cost to the user. `$?` with `cost unknown (no price for <model>)`
   means that model has no price: say so rather than reporting $0. OpenRouter models report their
   own cost; for others, add the price to `models.pricing` in `config.yaml`.

Run long pipelines with a long Bash timeout or in the background: a killed run stays
`running` and cannot be resumed.

Runs are stored under `server/workspace/<run_id>/` (`run.json`, `events.jsonl`, per-node `.md`,
and for agent nodes `files/` and `agent/`).

## Exit codes

| Code | Meaning |
|------|---------|
| 0 | done |
| 3 | paused at a checkpoint — ask the user, then `resume` |
| 1 | error (bad yaml, unknown run, disallowed `--choice`, node failure) |
