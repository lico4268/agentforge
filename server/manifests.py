"""
v0.1 built-in node manifests. Returned by the /api/nodes endpoint.
"""

from typing import Any

BUILTIN_MANIFESTS: list[dict[str, Any]] = [
    {
        "type": "io.input",
        "runtime": "io",
        "category": "io",
        "label": "Input",
        "description": "Graph entry point. Seeds task and tag.",
        "inputs": [],
        "outputs": [
            {"id": "task", "label": "Task", "dataType": "text"},
            {"id": "tags", "label": "Tags", "dataType": "any"},
        ],
        "config": [
            {"key": "sample", "label": "Sample task", "type": "text"},
            {"key": "taskTags", "label": "Task tags", "type": "string[]"},
        ],
    },
    {
        "type": "io.output",
        "runtime": "io",
        "category": "io",
        "label": "Output",
        "description": "Graph terminal.",
        "inputs": [{"id": "result", "label": "Result", "dataType": "any", "required": True}],
        "outputs": [],
        "config": [],
    },
    {
        "type": "custom.node",
        "runtime": "llm_step",
        "category": "cognitive",
        "label": "Custom",
        "description": "A blank node — define name, I/O ports, and prompt in the Inspector.",
        "maxModelSlots": 2,
        "inputs": [],
        "outputs": [],
        "config": [],
    },
    {
        "type": "loop.guard",
        "runtime": "loop_guard",
        "category": "policy",
        "label": "Loop",
        "description": "Defines the loop re-entry/exit point and the 5-axis guard.",
        "inputs": [{"id": "in", "label": "Feedback", "dataType": "any", "required": True}],
        "outputs": [
            {"id": "loopBack", "label": "Loop back", "dataType": "any"},
            {"id": "exit", "label": "Exit", "dataType": "any"},
        ],
        "config": [
            {
                "key": "kind",
                "label": "Kind",
                "type": "select",
                "default": "critiqueRevise",
                "options": [
                    {"label": "Evaluator-Optimizer", "value": "evaluatorOptimizer"},
                    {"label": "Critique-Revise", "value": "critiqueRevise"},
                    {"label": "Human Review", "value": "humanReview"},
                ],
                "description": "Descriptive only — not used by the compiler for routing or guards.",
            },
            {"key": "maxIterations", "label": "Max iterations", "type": "number"},
            {"key": "maxTokens", "label": "Max tokens", "type": "number"},
            {"key": "maxCostUsd", "label": "Max cost (USD)", "type": "number"},
            {"key": "maxDurationSec", "label": "Max duration (sec)", "type": "number"},
            {"key": "stuckWindow", "label": "Stuck window", "type": "number"},
            {"key": "stuckThreshold", "label": "Stuck threshold", "type": "number"},
            {
                "key": "onExhaustion",
                "label": "On exhaustion",
                "type": "select",
                "default": "exit",
                "options": [
                    {"label": "Exit", "value": "exit"},
                    {"label": "Escalate", "value": "escalate"},
                    {"label": "Fail", "value": "fail"},
                ],
            },
        ],
    },
    {
        "type": "human.checkpoint",
        "runtime": "checkpoint",
        "category": "human",
        "label": "Human Checkpoint",
        "description": "Halts execution + human review, edit, and re-run.",
        "inputs": [{"id": "review", "label": "Review", "dataType": "any"}],
        "outputs": [
            {"id": "approve", "label": "Approve", "dataType": "any"},
            {"id": "revise", "label": "Revise", "dataType": "any"},
            {"id": "reject", "label": "Reject", "dataType": "any"},
        ],
        "config": [
            {
                "key": "summarize",
                "label": "Summarize",
                "type": "select",
                "default": "off",
                "options": [
                    {"label": "Off", "value": "off"},
                    {"label": "Fields", "value": "fields"},
                    {"label": "LLM", "value": "llm"},
                ],
            },
            {
                "key": "blockUntil",
                "label": "Block until",
                "type": "select",
                "default": "always",
                "options": [
                    {"label": "Always", "value": "always"},
                    {"label": "When flagged", "value": "when-flagged"},
                ],
            },
        ],
    },
]
