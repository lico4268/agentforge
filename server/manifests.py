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
        "type": "model.binding",
        "runtime": "model",
        "category": "model",
        "label": "Model",
        "description": "공유 LLM 부품. llm_step의 model 포트에 연결.",
        "inputs": [],
        "outputs": [{"id": "model", "label": "Model", "dataType": "model"}],
        "config": [
            {"key": "provider", "label": "Provider", "type": "select", "options": ["anthropic", "openai", "google", "local"]},
            {"key": "model", "label": "Model ID", "type": "text"},
            {"key": "temperature", "label": "Temperature", "type": "number", "default": 0},
        ],
    },
    {
        "type": "planning.decompose",
        "runtime": "llm_step",
        "category": "cognitive",
        "label": "Planning",
        "description": "task를 단계로 분해.",
        "inputs": [
            {"id": "task", "label": "Task", "dataType": "text", "required": True},
            {"id": "model", "label": "Model", "dataType": "model", "required": False},
        ],
        "outputs": [{"id": "plan", "label": "Plan", "dataType": "plan"}],
        "config": [
            {"key": "strategy", "label": "Strategy", "type": "select", "options": ["decompose", "goal", "multistep"]},
        ],
        "defaults": {
            "systemPrompt": "Decompose the task into ordered steps and return as JSON.",
            "outputSchema": {"steps": "string[]"},
        },
    },
    {
        "type": "reasoning.cot",
        "runtime": "llm_step",
        "category": "cognitive",
        "label": "Reasoning",
        "description": "Chain-of-thought 추론.",
        "inputs": [
            {"id": "task", "label": "Task", "dataType": "text", "required": True},
            {"id": "plan", "label": "Plan", "dataType": "plan", "required": False},
            {"id": "model", "label": "Model", "dataType": "model", "required": False},
        ],
        "outputs": [
            {"id": "answer", "label": "Answer", "dataType": "text"},
            {"id": "confidence", "label": "Confidence", "dataType": "number"},
        ],
        "config": [
            {"key": "style", "label": "Style", "type": "select", "options": ["chain_of_thought", "direct"]},
        ],
        "defaults": {
            "systemPrompt": "Solve the task step by step. Return your answer and confidence (0-1).",
            "outputSchema": {"answer": "string", "confidence": "number"},
        },
    },
    {
        "type": "policy.review",
        "runtime": "policy",
        "category": "policy",
        "label": "Review Policy",
        "description": "confidence·태그 기반 3분기 라우터.",
        "inputs": [
            {"id": "answer", "label": "Answer", "dataType": "text"},
            {"id": "confidence", "label": "Confidence", "dataType": "number"},
        ],
        "outputs": [
            {"id": "pass", "label": "Pass", "dataType": "any"},
            {"id": "auto", "label": "Auto-verify", "dataType": "any"},
            {"id": "human", "label": "Human", "dataType": "any"},
        ],
        "config": [
            {"key": "passThreshold", "label": "Pass threshold", "type": "number", "default": 0.85},
            {"key": "autoThreshold", "label": "Auto threshold", "type": "number", "default": 0.6},
            {"key": "escalateTags", "label": "Escalate tags", "type": "string[]"},
        ],
    },
    {
        "type": "verification.auto",
        "runtime": "llm_step",
        "category": "cognitive",
        "label": "Auto-Verify",
        "description": "LLM 자동 검증. 실패 시 재시도 루프.",
        "inputs": [
            {"id": "answer", "label": "Answer", "dataType": "text", "required": True},
            {"id": "task", "label": "Task", "dataType": "text"},
            {"id": "model", "label": "Model", "dataType": "model", "required": False},
        ],
        "outputs": [{"id": "verdict", "label": "Verdict", "dataType": "judgement"}],
        "config": [
            {"key": "criteria", "label": "Criteria", "type": "string[]"},
            {"key": "maxRetries", "label": "Max retries", "type": "number", "default": 2},
        ],
        "defaults": {
            "systemPrompt": "Verify the answer for correctness. Return passed (bool) and feedback.",
            "outputSchema": {"passed": "boolean", "feedback": "string"},
        },
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
            {"key": "summarize", "label": "Summarize", "type": "select", "options": ["off", "fields", "llm"]},
            {"key": "blockUntil", "label": "Block until", "type": "select", "options": ["always", "when-flagged"]},
        ],
    },
]
