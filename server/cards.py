"""Judgment card store.

All card file I/O goes through this module only. When this becomes a writable store in
Phase 3/4, only this module needs to change.
"""

from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel

from logging_config import logger

CARDS_DIR = Path(__file__).parent / "cards"


class CardShell(BaseModel):
    card_id: str
    when_to_use: str
    match_signals: list[str] = []
    pin: Literal["always", "task_type", "match_only"] = "match_only"


class JudgmentCard(CardShell):
    version: int = 1
    representation: str = ""
    criteria: list[dict] = []


def _parse_card(path: Path) -> JudgmentCard:
    """Parse a single card md file and return a JudgmentCard."""
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---"):
        raise ValueError(f"missing frontmatter delimiter: {path}")
    rest = text[3:]
    end = rest.find("\n---")
    if end == -1:
        raise ValueError(f"missing frontmatter closing delimiter: {path}")
    front_text = rest[:end]
    body = rest[end + 4 :].strip()
    fm = yaml.safe_load(front_text)
    if not isinstance(fm, dict):
        raise ValueError(f"frontmatter is not a dict: {path}")
    return JudgmentCard(
        card_id=fm["card_id"],
        version=fm.get("version", 1),
        when_to_use=fm.get("when_to_use", ""),
        match_signals=fm.get("match_signals", []) or [],
        pin=fm.get("pin", "match_only"),
        representation=body,
        criteria=fm.get("criteria", []) or [],
    )


def load_shells(cards_dir: Path = CARDS_DIR) -> list[CardShell]:
    """Parse every *.md in the directory, return shells only (filename order). Empty if no dir."""
    if not cards_dir.is_dir():
        return []
    shells: list[CardShell] = []
    for path in sorted(cards_dir.glob("*.md")):
        try:
            card = _parse_card(path)
        except Exception:
            logger.warning("card parse failed, skipping: %s", path)
            continue
        shell_fields = {"card_id", "when_to_use", "match_signals", "pin"}
        shells.append(CardShell(**card.model_dump(include=shell_fields)))
    return shells


def load_cards(card_ids: list[str], cards_dir: Path = CARDS_DIR) -> list[JudgmentCard]:
    """Parse all, return cards whose card_id is in card_ids, in that order. Unknown ids skipped."""
    if not cards_dir.is_dir():
        return []
    by_id: dict[str, JudgmentCard] = {}
    for path in sorted(cards_dir.glob("*.md")):
        try:
            card = _parse_card(path)
        except Exception:
            logger.warning("card parse failed, skipping: %s", path)
            continue
        by_id[card.card_id] = card
    return [by_id[cid] for cid in card_ids if cid in by_id]
