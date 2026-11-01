"""`run: agent` — mini-swe-agent's loop driving our LangChain model; shell commands run in bwrap.

LLM calls happen here in the server process (API keys never enter the sandbox). Each command
runs in a fresh bwrap sandbox: empty environment, no network unless the node sets
`network: true`, read-only system dirs, and only the run's files/ folder writable.
"""

import asyncio
import json
import os
import shutil
from pathlib import Path
from types import SimpleNamespace

import yaml

import gitfiles
import workspace
from events import EventEmitter, make_error_event, make_event
from models import cost_for_usage
from nodes.llm_step import UsageCostHandler, _emit_token_usage, _model_name, _render
from state import AgentState, read_state_value, write_state_value

os.environ.setdefault("MSWEA_SILENT_STARTUP", "1")
# Keep mini-swe-agent from loading a global .env of its own into this process.
_MSWEA_DIR = Path(__file__).parent.parent / "workspace" / ".mswea"
os.environ.setdefault("MSWEA_GLOBAL_CONFIG_DIR", str(_MSWEA_DIR))

from minisweagent import package_dir  # noqa: E402
from minisweagent.agents.default import DefaultAgent  # noqa: E402
from minisweagent.environments.extra.bubblewrap import BubblewrapEnvironment  # noqa: E402
from minisweagent.models.utils.actions_toolcall import (  # noqa: E402
    BASH_TOOL,
    format_toolcall_observation_messages,
    parse_toolcall_actions,
)

DEFAULT_LIMITS = {"steps": 30, "cost": 0.50}
COMMAND_TIMEOUT = 120  # seconds per shell command
TOOLS_DIR = Path(__file__).parent.parent / "agent_tools"
SANDBOX_BIN = "/opt/agentforge/bin"
SUBMIT = "COMPLETE_TASK_AND_SUBMIT_FINAL_OUTPUT"

_MINI = yaml.safe_load((package_dir / "config" / "mini.yaml").read_text())

INSTANCE_TEMPLATE = f"""{{{{task}}}}

You work in {{{{cwd}}}} through bash. Each command runs in a fresh subshell inside a sandbox:
{{% if network %}}the network is on{{% else %}}there is no network{{% endif %}}, only {{{{cwd}}}}
and /tmp are writable, and environment changes do not persist between commands.
Extra tools on PATH: {{{{tools or "none"}}}}.

When you are done, run one command (and nothing else) whose output starts with the line
{SUBMIT} followed by your final answer for the next step:

cat <<'EOF'
{SUBMIT}
<your final answer>
EOF
"""


def sandbox_tools() -> dict[str, str]:
    """name → host path of each tool put on the sandbox PATH."""
    tools = {p.name: str(p) for p in sorted(TOOLS_DIR.iterdir()) if os.access(p, os.X_OK)}
    if obscura := shutil.which("obscura"):
        tools["obscura"] = obscura
    return tools


def bwrap_args(network: bool, tools: dict[str, str], ro: tuple[Path, ...] = ()) -> list[str]:
    args = ["--clearenv", "--unshare-all", "--die-with-parent", "--new-session"]
    if network:
        args.append("--share-net")
        # /etc/resolv.conf is often a symlink into /run (systemd-resolved); bind its target
        resolv = Path("/etc/resolv.conf").resolve()
        if not resolv.is_relative_to("/etc") and resolv.exists():
            args += ["--ro-bind", str(resolv), str(resolv)]
    args += ["--ro-bind", "/usr", "/usr"]
    for d in ("/bin", "/lib", "/lib64", "/sbin", "/etc"):
        args += ["--ro-bind-try", d, d]
    args += ["--tmpfs", "/tmp", "--proc", "/proc", "--dev", "/dev", "--tmpfs", SANDBOX_BIN]
    for name, path in tools.items():
        args += ["--ro-bind", path, f"{SANDBOX_BIN}/{name}"]
    for p in ro:
        args += ["--ro-bind", str(p), str(p)]
    return args


def resolve_secrets(node_id: str, names: list[str]) -> dict[str, str]:
    missing = [n for n in names if not os.environ.get(n)]
    if missing:
        raise ValueError(f"node {node_id!r}: secrets not set in server/.env: {', '.join(missing)}")
    return {n: os.environ[n] for n in names}


class _ChatModel:
    """mini-swe-agent Model protocol over a LangChain chat model, so agent nodes use the same
    providers, keys, and cost records as llm nodes (no litellm at runtime)."""

    def __init__(self, chat):
        self.chat = chat.bind_tools([BASH_TOOL])
        self.name = _model_name(chat)
        self.usage = UsageCostHandler()
        self.config = SimpleNamespace(
            observation_template=_MINI["model"]["observation_template"],
            format_error_template=_MINI["model"]["format_error_template"],
        )

    def query(self, messages: list[dict], **kwargs) -> dict:
        from langchain_core.messages import convert_to_messages, convert_to_openai_messages

        api = convert_to_messages([{k: v for k, v in m.items() if k != "extra"} for m in messages])
        call = UsageCostHandler()
        ai = self.chat.invoke(api, config={"callbacks": [call, self.usage]})
        cost = 0.0
        for name, u in call.usage_metadata.items():
            c = call.reported_cost.get(name)
            if c is None:
                c = cost_for_usage(name, u["input_tokens"], u["output_tokens"])
            # ponytail: unpriced calls count $0 toward limits.cost; limits.steps still applies
            cost += c or 0.0
        calls = [
            SimpleNamespace(
                id=tc["id"],
                function=SimpleNamespace(name=tc["name"], arguments=json.dumps(tc["args"])),
            )
            for tc in ai.tool_calls
        ]
        meta = ai.response_metadata
        finish = meta.get("finish_reason") or meta.get("stop_reason")
        try:
            actions = parse_toolcall_actions(
                calls,
                format_error_template=self.config.format_error_template,
                template_kwargs={"finish_reason": finish},
            )
        except Exception as e:  # FormatError: the call was billed, keep its cost
            if getattr(e, "messages", None):
                e.messages[0]["extra"]["cost"] = cost
            raise
        msg = convert_to_openai_messages(ai)
        msg["extra"] = {"actions": actions, "cost": cost}
        return msg

    def format_message(self, **kwargs) -> dict:
        return kwargs

    def format_observation_messages(self, message, outputs, template_vars=None) -> list[dict]:
        return format_toolcall_observation_messages(
            actions=message.get("extra", {}).get("actions", []),
            outputs=outputs,
            observation_template=self.config.observation_template,
            template_vars=template_vars,
        )

    def get_template_vars(self, **kwargs) -> dict:
        return {}

    def serialize(self) -> dict:
        return {"info": {"config": {"model": {"model_name": self.name}}}}


def _last_text(messages: list[dict]) -> str:
    for m in reversed(messages):
        if m.get("role") == "assistant" and isinstance(m.get("content"), str) and m["content"]:
            return m["content"]
    return ""


def make_agent_node(node: dict, chat, emit: EventEmitter, run_id: str, policy_ids=None):
    node_id = node["id"]
    cfg = node.get("config") or {}
    out_key = cfg["outputs"][0]["id"]
    input_keys = [(p["id"], p["label"]) for p in cfg.get("inputs") or []]
    limits = {**DEFAULT_LIMITS, **(cfg.get("limits") or {})}
    network = bool(cfg.get("network"))
    secrets = resolve_secrets(node_id, cfg.get("secrets") or [])
    if shutil.which("bwrap") is None:
        raise ValueError(f"node {node_id!r}: run: agent needs bwrap (bubblewrap) installed")
    tools = sandbox_tools()

    async def step(state: AgentState) -> dict:
        await emit(make_event(run_id, node_id, "node_start"))
        files = workspace.files_dir(run_id)
        gitfiles.ensure_repo(files)
        before = gitfiles.head(files)
        traj_dir = workspace._run_dir(run_id) / "agent"
        visit = len(list(traj_dir.glob(f"{node_id}-*.json"))) + 1
        traj = traj_dir / f"{node_id}-{visit}.json"

        blocks = [cfg.get("systemPrompt") or ""]
        for key, label in input_keys:
            value = read_state_value(state, key)
            if value is not None:
                blocks.append(f"## {label}\n{_render(value)}")
        model = _ChatModel(chat)
        env = BubblewrapEnvironment(
            cwd=str(files),
            timeout=COMMAND_TIMEOUT,
            # --repo: files/ is a worktree; its git data lives in the main repo (read-only here)
            wrapper_args=bwrap_args(
                network, tools, tuple(filter(None, [gitfiles.common_dir(files)]))
            ),
            env={
                "PATH": f"{SANDBOX_BIN}:/usr/local/bin:/usr/bin:/bin",
                "HOME": "/tmp",
                "PAGER": "cat",
                **secrets,
            },
        )
        agent = DefaultAgent(
            model,
            env,
            system_template=_MINI["agent"]["system_template"],
            instance_template=INSTANCE_TEMPLATE,
            step_limit=int(limits["steps"]),
            cost_limit=float(limits["cost"]),
            output_path=traj,
        )
        usage: dict = {}
        try:
            result = await asyncio.to_thread(
                agent.run,
                "\n\n".join(b for b in blocks if b),
                network=network,
                tools=", ".join(tools),
            )
        except Exception as e:
            await emit(make_error_event(run_id, node_id, e))
            raise
        finally:
            commit = await asyncio.to_thread(
                gitfiles.commit, files, f"agentforge: {node_id} visit {visit}"
            )
            await _emit_token_usage(
                model.usage,
                emit=emit,
                run_id=run_id,
                node_id=node_id,
                model_name=model.name,
                usage_sink=usage,
            )
        status = result.get("exit_status")
        if status != "Submitted":
            err = RuntimeError(f"agent stopped ({status}) after {agent.n_calls} steps — see {traj}")
            await emit(make_error_event(run_id, node_id, err))
            raise err

        answer = (result.get("submission") or "").strip() or _last_text(agent.messages)
        updates: dict = {}
        write_state_value(updates, out_key, answer)
        if policy_ids and usage:
            updates["loop_runtime"] = {
                pid: {
                    "total_tokens": usage["prompt"] + usage["completion"],
                    "total_cost_usd": usage.get("cost") or 0.0,
                }
                for pid in policy_ids
            }
        output = {
            out_key: answer,
            "changedFiles": gitfiles.changed(files, before, commit),
            "commit": commit,
            "steps": agent.n_calls,
            "trajectory": str(traj.relative_to(workspace._run_dir(run_id))),
        }
        await emit(make_event(run_id, node_id, "node_end", output=output))
        return updates

    return step
