"""판단 카드 저장소.

카드 파일 I/O는 전부 이 모듈만 통과한다. Phase 3/4에서 쓰기 가능 저장소로 바뀔 때
이 모듈만 수정하면 된다.
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
    """단일 카드 md 파일을 파싱해 JudgmentCard 반환."""
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---"):
        raise ValueError(f"frontmatter 구분자 없음: {path}")
    rest = text[3:]
    end = rest.find("\n---")
    if end == -1:
        raise ValueError(f"frontmatter 종료 구분자 없음: {path}")
    front_text = rest[:end]
    body = rest[end + 4 :].strip()
    fm = yaml.safe_load(front_text)
    if not isinstance(fm, dict):
        raise ValueError(f"frontmatter가 dict가 아님: {path}")
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
    """디렉토리의 모든 *.md를 파싱해 shell만 반환 (파일명 정렬 순). 디렉토리 없으면 빈 리스트."""
    if not cards_dir.is_dir():
        return []
    shells: list[CardShell] = []
    for path in sorted(cards_dir.glob("*.md")):
        try:
            card = _parse_card(path)
        except Exception:
            logger.warning("카드 파싱 실패, 건너뜀: %s", path)
            continue
        shell_fields = {"card_id", "when_to_use", "match_signals", "pin"}
        shells.append(CardShell(**card.model_dump(include=shell_fields)))
    return shells


def load_cards(card_ids: list[str], cards_dir: Path = CARDS_DIR) -> list[JudgmentCard]:
    """전체 파싱 후 card_id가 목록에 있는 것만, card_ids 순서대로 반환. 없는 id는 조용히 생략."""
    if not cards_dir.is_dir():
        return []
    by_id: dict[str, JudgmentCard] = {}
    for path in sorted(cards_dir.glob("*.md")):
        try:
            card = _parse_card(path)
        except Exception:
            logger.warning("카드 파싱 실패, 건너뜀: %s", path)
            continue
        by_id[card.card_id] = card
    return [by_id[cid] for cid in card_ids if cid in by_id]
