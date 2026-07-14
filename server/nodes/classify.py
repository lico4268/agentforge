"""판단 카드 분류 노드 — 카드 껍질 매칭 → 본문 로드 → criteria/intent 주입.

카드가 없거나 LLM 호출이 실패하면 카드 없이 진행한다 (Phase 1 동작으로 폴백).
"""

from pathlib import Path
from typing import Any

from langchain_core.language_models import BaseChatModel

from cards import CARDS_DIR, load_cards, load_shells
from events import EventEmitter, make_event
from logging_config import logger
from models import ClassifyOut, Criterion
from nodes.llm_step import run_llm_step
from state import AgentState

CLASSIFY_SYSTEM_PROMPT = """\
You are a task classifier. Given a task and a catalog of judgment cards,
return the card_ids of ALL cards whose when_to_use / match_signals match the task.
Return an empty list if no card clearly matches. Do not guess — only include
cards whose description genuinely covers this kind of task."""


def make_classify(
    model: BaseChatModel,
    emit: EventEmitter,
    run_id: str,
    node_id: str = "classify",
    cards_dir: Path | None = None,
):
    """classify 클로저 노드 팩토리."""
    dir_arg = cards_dir if cards_dir is not None else CARDS_DIR

    async def classify(state: AgentState) -> dict:
        await emit(make_event(run_id, node_id, "node_start"))

        shells = load_shells(dir_arg)
        if not shells:
            output = {"matched_cards": [], "reason": "no cards"}
            await emit(make_event(run_id, node_id, "node_end", output=output))
            return {"matched_cards": []}

        catalog_lines: list[str] = []
        for s in shells:
            catalog_lines.append(f"- card_id: {s.card_id}")
            catalog_lines.append(f"  when_to_use: {s.when_to_use}")
            catalog_lines.append(f"  match_signals: {', '.join(s.match_signals)}")
        catalog_text = "\n".join(catalog_lines)

        probe: Any = {**state, "card_catalog": catalog_text}
        try:
            result = await run_llm_step(
                probe,
                node_id=node_id,
                system_prompt=CLASSIFY_SYSTEM_PROMPT,
                input_keys=[
                    ("task", "Task"),
                    ("task_tags", "Task Tags"),
                    ("card_catalog", "Card Catalog"),
                ],
                output_model=ClassifyOut,
                model=model,
                emit=emit,
                run_id=run_id,
            )
        except Exception:
            logger.warning("classify LLM 호출 실패 — 카드 없이 폴백")
            output = {"matched_cards": [], "reason": "classify failed"}
            await emit(make_event(run_id, node_id, "node_end", output=output))
            return {"matched_cards": []}

        classify_out = ClassifyOut(**result)
        valid_ids = {s.card_id for s in shells}
        llm_ids = [cid for cid in classify_out.card_ids if cid in valid_ids]
        always_ids = [s.card_id for s in shells if s.pin == "always"]
        # pin-always 먼저, 그다음 LLM 순서, 중복 제거
        matched_ids: list[str] = []
        seen: set[str] = set()
        for cid in always_ids + llm_ids:
            if cid not in seen:
                seen.add(cid)
                matched_ids.append(cid)

        cards = load_cards(matched_ids, dir_arg)

        # 카드 criteria를 네임스페이스드 id(card_id:criterion_id)로 검증·보강
        card_criteria: list[dict] = []
        for card in cards:
            for c in card.criteria:
                namespaced = f"{card.card_id}:{c.get('id', '')}"
                card_criteria.append(Criterion(**{**c, "id": namespaced}).model_dump())

        # 병합: 카드 criteria가 베이스, 같은 id면 state 쪽이 이김 (review 노드 관례와 동일)
        merged: dict[str, dict] = {c["id"]: c for c in card_criteria}
        merged.update({c["id"]: c for c in (state.get("criteria") or [])})

        updates: dict[str, Any] = {
            "matched_cards": matched_ids,
            "criteria": list(merged.values()),
        }

        # intent 폴백: 기존 intent가 None이고 매칭 카드가 있으면 representation으로 채움
        if state.get("intent") is None and cards:
            reps = [card.representation for card in cards if card.representation]
            if reps:
                updates["intent"] = "\n\n".join(reps)

        await emit(
            make_event(
                run_id,
                node_id,
                "node_end",
                output={
                    "matched_cards": matched_ids,
                    "rationale": classify_out.rationale,
                    "criteria_count": len(merged),
                },
            )
        )
        return updates

    return classify
