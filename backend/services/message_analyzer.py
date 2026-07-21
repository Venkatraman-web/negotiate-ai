from __future__ import annotations

import logging
import time
from typing import Dict, Protocol

try:
    from .llm_service import LLMService
except ImportError:  # pragma: no cover - allows running the module directly from the backend folder
    from llm_service import LLMService

try:
    from ..core.logging_config import setup_logging
except ImportError:  # pragma: no cover - allows running the module directly from the backend folder
    from core.logging_config import setup_logging

setup_logging()
logger = logging.getLogger(__name__)


class MessageAnalyzer(Protocol):
    """Small interface for message analysis providers."""

    def analyze_message(self, message: str) -> Dict[str, int]:
        """Return numeric negotiation metrics for a user message."""
        ...


class LLMMessageAnalyzer:
    """Analyze negotiation messages through the shared LLM service."""

    def __init__(self, llm_service: LLMService | None = None) -> None:
        self._llm_service = llm_service or LLMService()

    def analyze_message(self, message: str) -> Dict[str, int]:
        """Return structured negotiation metrics for the latest user message."""
        logger.info("Analysis started | message_length=%d", len(message))

        start = time.perf_counter()
        metrics = self._llm_service.analyze_message(message)
        duration = time.perf_counter() - start

        logger.info("Analysis finished | duration=%.4fs", duration)

        # Note: analyze_message() here only receives the already-parsed
        # metrics dict from LLMService, not the raw LLM text. Raw-response
        # logging happens inside LLMService.analyze_message() itself.
        logger.info("Parsed metrics | metrics=%s", metrics)

        is_valid = isinstance(metrics, dict) and all(
            isinstance(value, int) for value in metrics.values()
        )
        if is_valid:
            logger.info("Validation success | metrics conform to Dict[str, int]")
        else:
            logger.error(
                "Validation failure | metrics do not conform to Dict[str, int] | metrics=%r",
                metrics,
            )

        return metrics


_ANALYZER: MessageAnalyzer = LLMMessageAnalyzer()


def get_analyzer() -> MessageAnalyzer:
    """Return the active analyzer implementation."""
    return _ANALYZER


def set_analyzer(analyzer: MessageAnalyzer) -> None:
    """Swap the active analyzer implementation at runtime."""
    global _ANALYZER
    logger.info(
        "Analyzer implementation swapped | previous=%s new=%s",
        type(_ANALYZER).__name__,
        type(analyzer).__name__,
    )
    _ANALYZER = analyzer


def analyze_message(message: str) -> Dict[str, int]:
    """Analyze the latest user message and return structured negotiation metrics."""
    return get_analyzer().analyze_message(message)