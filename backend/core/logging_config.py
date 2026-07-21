"""
core/logging_config.py

Centralized logging configuration for the negotiation backend.

Every module in the pipeline (routes, message analyzer, negotiation
engine, prompt builder, LLM service, report generator) calls
`setup_logging()` on import and then does `logger = logging.getLogger(__name__)`.
This gives every log line a consistent format:

    2026-07-19 10:03:41 | INFO     | routes.negotiate | Chat request received

`setup_logging()` is idempotent -- safe to call from every module without
installing duplicate handlers, regardless of import order.
"""

import logging

_CONFIGURED = False


def setup_logging(level: int = logging.INFO) -> None:
    global _CONFIGURED
    if _CONFIGURED:
        return

    logging.basicConfig(
        level=level,
        format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        force=True,   # <-- add this
    )
    _CONFIGURED = True