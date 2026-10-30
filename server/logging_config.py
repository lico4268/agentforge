"""Standard application logging setup.

Server code uses `from logging_config import logger` instead of `print` (AGENTS.md §7).
The level follows config.LOG_LEVEL (a string such as "info").
"""

import logging

import config as cfg

logger = logging.getLogger("agentforge")

_configured = False


def setup_logging() -> logging.Logger:
    """Call once at app startup. Configures handler/format/level and returns the logger."""
    global _configured
    if _configured:
        return logger

    level = getattr(logging, str(cfg.LOG_LEVEL).upper(), logging.INFO)

    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)-7s %(name)s: %(message)s"))

    logger.setLevel(level)
    logger.addHandler(handler)
    logger.propagate = False  # prevent duplicate output via the root handler

    _configured = True
    return logger
