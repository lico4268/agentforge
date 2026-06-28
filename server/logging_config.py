"""애플리케이션 로깅 표준 설정.

서버 코드는 `print` 대신 `from logging_config import logger`를 사용한다 (AGENTS.md §7).
레벨은 config.LOG_LEVEL("info" 등 문자열)을 따른다.
"""
import logging

import config as cfg

logger = logging.getLogger("agentforge")

_configured = False


def setup_logging() -> logging.Logger:
    """앱 시작 시 한 번 호출. 핸들러/포맷/레벨을 설정하고 logger를 반환한다."""
    global _configured
    if _configured:
        return logger

    level = getattr(logging, str(cfg.LOG_LEVEL).upper(), logging.INFO)

    handler = logging.StreamHandler()
    handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)-7s %(name)s: %(message)s")
    )

    logger.setLevel(level)
    logger.addHandler(handler)
    logger.propagate = False  # 루트 핸들러로의 중복 출력 방지

    _configured = True
    return logger
