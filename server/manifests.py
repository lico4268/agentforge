"""
v0.1 빌트인 노드 매니페스트. /api/nodes 엔드포인트에서 반환.
"""

from typing import Any

BUILTIN_MANIFESTS: list[dict[str, Any]] = [
    {
        "type": "io.input",
        "runtime": "io",
        "category": "io",
        "label": "Input",
        "description": "그래프 진입점. task와 tag를 시드.",
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
        "description": "그래프 종단.",
        "inputs": [{"id": "result", "label": "Result", "dataType": "any", "required": True}],
        "outputs": [],
        "config": [],
    },
    {
        "type": "custom.node",
        "runtime": "llm_step",
        "category": "cognitive",
        "label": "Custom",
        "description": "완전히 빈 노드 — Inspector에서 이름·입출력 포트·프롬프트를 직접 정의한다.",
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
        "description": "루프 재진입/탈출 지점과 5축 가드를 정의.",
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
                "description": "서술 전용 — 컴파일러 라우팅/가드 판정에는 쓰이지 않는다.",
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
        "description": "실행 정지 + 인간 검토·수정·재실행.",
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
