from typing import Annotated, Any, TypedDict


class LoopRuntimeState(TypedDict):
    iteration: int
    total_tokens: int
    total_cost_usd: float
    started_at: float
    last_feedback: str | None
    progress_history: list[float]


def empty_loop_runtime() -> LoopRuntimeState:
    return LoopRuntimeState(
        iteration=0,
        total_tokens=0,
        total_cost_usd=0.0,
        started_at=0.0,
        last_feedback=None,
        progress_history=[],
    )


def merge_loop_runtime(
    existing: dict[str, LoopRuntimeState], new: dict[str, LoopRuntimeState]
) -> dict[str, LoopRuntimeState]:
    """Merge reducer for per-LoopPolicy loop_runtime.

    iteration/started_at/last_feedback are replaced when a new value is present (single writer —
    the guard node writes iteration/started_at, the review node writes last_feedback).
    total_tokens/total_cost_usd/progress_history are accumulated (summed/appended) because each
    loop member node sends only its own contribution as a partial update.
    """
    merged = dict(existing)
    for policy_id, update in new.items():
        current = merged.get(policy_id, empty_loop_runtime())
        merged[policy_id] = LoopRuntimeState(
            iteration=update.get("iteration", current["iteration"]),
            total_tokens=current["total_tokens"] + update.get("total_tokens", 0),
            total_cost_usd=current["total_cost_usd"] + update.get("total_cost_usd", 0.0),
            started_at=update.get("started_at", current["started_at"]),
            last_feedback=update.get("last_feedback", current["last_feedback"]),
            progress_history=current["progress_history"] + update.get("progress_history", []),
        )
    return merged


def merge_vars(existing: dict[str, Any], new: dict[str, Any]) -> dict[str, Any]:
    """Merge reducer for the custom-role value bucket (vars) — shallow merge; on key overlap the new
    value wins. Multiple nodes writing different keys in the same superstep don't conflict."""
    return {**existing, **new}


class AgentState(TypedDict):
    task: str
    task_tags: list[str]
    intent: str | None  # original intent — if absent, review treats the task itself as the intent
    plan: list[str] | None
    answer: str | None
    confidence: float | None
    criteria: list[dict]
    review_delta: dict | None
    review_branch: str | None  # accept/refine/clarify set by the review node (read by the router)
    retries: int
    feedback: str | None  # unmet delta from the previous review → rework input
    batch_mode: bool  # if True, demote clarify → accept (envs where interrupt is impossible)
    loop_runtime: Annotated[dict[str, LoopRuntimeState], merge_loop_runtime]
    # Role values for custom node types (Phase B) — keys not listed here have no LangGraph channel
    # and would be silently dropped, so every role not listed above lives in this bucket.
    vars: Annotated[dict[str, Any], merge_vars]


# Set of keys that have an actual channel in AgentState — the criterion read_state_value/
# write_state_value use to split "known top-level keys vs custom keys stored in vars".
KNOWN_STATE_KEYS = frozenset(AgentState.__annotations__.keys())


def read_state_value(state: AgentState, key: str) -> Any:
    """Read known keys from the top level, otherwise from vars."""
    if key in KNOWN_STATE_KEYS:
        return state.get(key)
    return (state.get("vars") or {}).get(key)


def write_state_value(updates: dict[str, Any], key: str, value: Any) -> None:
    """Inverse of read_state_value — write known keys at the top level of updates, otherwise into
    updates['vars'] (accumulates across multiple calls on the same updates dict)."""
    if key in KNOWN_STATE_KEYS:
        updates[key] = value
    else:
        updates.setdefault("vars", {})[key] = value


def initial_state(
    task: str,
    task_tags: list[str] | None = None,
    batch_mode: bool = False,
    intent: str | None = None,
    criteria: list[dict] | None = None,
) -> AgentState:
    return AgentState(
        task=task,
        task_tags=task_tags or [],
        intent=intent,
        plan=None,
        answer=None,
        confidence=None,
        criteria=criteria or [],
        review_delta=None,
        review_branch=None,
        retries=0,
        feedback=None,
        batch_mode=batch_mode,
        loop_runtime={},
        vars={},
    )
