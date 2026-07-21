from __future__ import annotations

import json
import logging
import re
import time
from datetime import datetime
from typing import Any, Dict, Final

from ollama import Client, ResponseError

try:
    from ..core.logging_config import setup_logging
except ImportError:  # pragma: no cover - allows running the module directly from the backend folder
    from core.logging_config import setup_logging

setup_logging()
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
OLLAMA_MODEL: Final[str] = "llama3.2"
OLLAMA_HOST: Final[str] = "http://localhost:11434"
REQUEST_TIMEOUT_SECONDS: Final[float] = 180.0

# Lower temperature for structured JSON; slightly higher for natural replies.
ANALYSIS_TEMPERATURE: Final[float] = 0.1
REPLY_TEMPERATURE: Final[float] = 0.7

REQUIRED_ANALYSIS_KEYS: Final[tuple[str, ...]] = (
    "politeness",
    "confidence",
    "reasoning_quality",
    "aggression",
    "flexibility",
)


class LLMServiceError(Exception):
    """Raised when the local LLM service fails to respond correctly."""


class LLMService:
    """Single backend gateway for all LLM communication via local Ollama.

    This module handles transport to the model only. It does not build
    negotiation prompts, mutate session state, or apply negotiation logic.
    """

    def __init__(
        self,
        model: str = OLLAMA_MODEL,
        host: str = OLLAMA_HOST,
        timeout: float = REQUEST_TIMEOUT_SECONDS,
    ) -> None:
        self.model = model
        self.timeout = timeout
        self._client = Client(host=host, timeout=timeout)

    def analyze_message(self, message: str) -> Dict[str, int]:
        """Analyze a user negotiation message and return validated metric scores.

        Args:
            message: The latest user message from the negotiation.

        Returns:
            A dict with integer scores from 0-10 for each required metric.

        Raises:
            LLMServiceError: If input, transport, parsing, or validation fails.
        """
        if not isinstance(message, str) or not message.strip():
            raise LLMServiceError("Message must be a non-empty string.")

        prompt = _build_analysis_prompt(message.strip())
        raw_output = self._generate_text(
            prompt, temperature=ANALYSIS_TEMPERATURE, request_type="analyze_message"
        )

        # Explicitly required for debugging the analyzer stage: the raw
        # model output before any parsing/validation is applied.
        logger.info(
            "Raw LLM response | request_type=analyze_message raw_response=%r",
            raw_output,
        )

        try:
            validated = _parse_and_validate_analysis(raw_output)
        except LLMServiceError as exc:
            logger.error(
                "Validation failure | request_type=analyze_message "
                "exception_type=%s message=%s",
                type(exc).__name__,
                str(exc),
                exc_info=True,
            )
            raise

        logger.info(
            "Validation success | request_type=analyze_message parsed_metrics=%s",
            validated,
        )
        return validated

    def generate_reply(self, prompt: str, *, response_format: str | None = None) -> str:
        """Generate the negotiator's next reply from a complete prompt.

        The prompt is passed through unchanged. No session or strategy logic
        is applied here.

        Args:
            prompt: Full prompt produced by ``prompt_builder.py``.
            response_format: Optional Ollama output format constraint.
                Pass "json" to force Ollama's grammar-constrained JSON mode
                (used by the report generator's AI evaluation, which needs
                guaranteed-valid JSON). Leave as None for ordinary free-text
                negotiation replies -- this is the default and preserves
                existing chat behavior exactly.

        Returns:
            The model's generated reply text.

        Raises:
            LLMServiceError: If input or model generation fails.
        """
        if not isinstance(prompt, str) or not prompt.strip():
            raise LLMServiceError("Prompt must be a non-empty string.")

        return self._generate_text(
            prompt,
            temperature=REPLY_TEMPERATURE,
            request_type="generate_reply",
            response_format=response_format,
        )

    def _generate_text(
        self,
        prompt: str,
        *,
        temperature: float,
        request_type: str = "generate",
        response_format: str | None = None,
    ) -> str:
        """Send a prompt to Ollama and return trimmed model output."""
        start_wall_clock = datetime.now()
        start_perf = time.perf_counter()

        logger.info(
            "LLM request started | request_type=%s model=%s temperature=%s "
            "prompt_size_chars=%d start_timestamp=%s response_format=%s",
            request_type,
            self.model,
            temperature,
            len(prompt),
            start_wall_clock.isoformat(),
            response_format,
        )

        try:
            response = self._client.generate(
                model=self.model,
                prompt=prompt,
                options={"temperature": temperature},
                format=response_format,
            )
        except ResponseError as exc:
            duration = time.perf_counter() - start_perf
            logger.error(
                "LLM request failed | request_type=%s model=%s "
                "total_inference_time=%.4fs success=False exception_type=%s message=%s",
                request_type,
                self.model,
                duration,
                type(exc).__name__,
                str(exc),
                exc_info=True,
            )
            raise _map_response_error(exc) from exc
        except ConnectionError as exc:
            duration = time.perf_counter() - start_perf
            logger.error(
                "LLM request failed | request_type=%s model=%s "
                "total_inference_time=%.4fs success=False exception_type=%s message=%s",
                request_type,
                self.model,
                duration,
                type(exc).__name__,
                str(exc),
                exc_info=True,
            )
            raise LLMServiceError(
                "Could not connect to Ollama. Ensure the Ollama service is running."
            ) from exc
        except Exception as exc:
            duration = time.perf_counter() - start_perf
            logger.error(
                "LLM request failed | request_type=%s model=%s "
                "total_inference_time=%.4fs success=False exception_type=%s message=%s",
                request_type,
                self.model,
                duration,
                type(exc).__name__,
                str(exc),
                exc_info=True,
            )
            raise LLMServiceError(f"Unexpected Ollama error: {exc}") from exc

        end_wall_clock = datetime.now()
        duration = time.perf_counter() - start_perf

        generated_text = _extract_response_text(response)
        if not generated_text:
            logger.error(
                "LLM request failed | request_type=%s model=%s "
                "total_inference_time=%.4fs success=False reason=empty response "
                "end_timestamp=%s",
                request_type,
                self.model,
                duration,
                end_wall_clock.isoformat(),
            )
            raise LLMServiceError("Ollama returned an empty response.")

        logger.info(
            "LLM request finished | request_type=%s model=%s temperature=%s "
            "end_timestamp=%s total_inference_time=%.4fs success=True "
            "response_size_chars=%d",
            request_type,
            self.model,
            temperature,
            end_wall_clock.isoformat(),
            duration,
            len(generated_text),
        )

        return generated_text


def _build_analysis_prompt(message: str) -> str:
    """Build the instruction prompt for structured message analysis."""
    keys = ", ".join(REQUIRED_ANALYSIS_KEYS)
    return (
        "You are a negotiation analysis assistant.\n"
        "Analyze the user's negotiation message and return ONLY valid JSON.\n"
        "Do not include markdown, code fences, comments, or extra text.\n"
        f"The JSON object must contain exactly these keys: {keys}.\n"
        "Each value must be an integer from 0 to 10.\n"
        f'User message: "{message}"'
    )


def _extract_response_text(response: Any) -> str:
    """Extract generated text from an Ollama response object or dict."""
    if isinstance(response, dict):
        text = response.get("response", "")
    else:
        text = getattr(response, "response", "")

    if not isinstance(text, str):
        return ""

    return text.strip()


def _extract_json_payload(raw_output: str) -> str:
    """Extract JSON from raw model output, including fenced code blocks."""
    stripped = raw_output.strip()

    fenced_match = re.search(
        r"```(?:json)?\s*(.*?)\s*```",
        stripped,
        flags=re.DOTALL | re.IGNORECASE,
    )
    if fenced_match:
        return fenced_match.group(1).strip()

    start = stripped.find("{")
    end = stripped.rfind("}")
    if start != -1 and end != -1 and end > start:
        return stripped[start : end + 1]

    return stripped


def _parse_and_validate_analysis(raw_output: str) -> Dict[str, int]:
    """Parse and validate the analysis JSON returned by the model."""
    json_payload = _extract_json_payload(raw_output)

    try:
        parsed = json.loads(json_payload)
    except json.JSONDecodeError as exc:
        raise LLMServiceError(
            f"Failed to parse LLM JSON response: {raw_output}"
        ) from exc

    if not isinstance(parsed, dict):
        raise LLMServiceError("LLM response must be a JSON object.")

    missing_keys = [key for key in REQUIRED_ANALYSIS_KEYS if key not in parsed]
    if missing_keys:
        raise LLMServiceError(
            f"LLM response is missing required keys: {', '.join(missing_keys)}"
        )

    validated: Dict[str, int] = {}
    for key in REQUIRED_ANALYSIS_KEYS:
        value = parsed[key]

        # Accept whole-number floats like 7.0, but reject non-integers.
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise LLMServiceError(f"LLM score '{key}' must be an integer.")
        if isinstance(value, float) and not value.is_integer():
            raise LLMServiceError(f"LLM score '{key}' must be an integer.")

        score = int(value)
        if not 0 <= score <= 10:
            raise LLMServiceError(
                f"LLM score '{key}' must be between 0 and 10."
            )

        validated[key] = score

    return validated


def _map_response_error(exc: ResponseError) -> LLMServiceError:
    """Convert Ollama API errors into clearer application exceptions."""
    message = str(exc).lower()

    if "model" in message and ("not found" in message or "pull" in message):
        return LLMServiceError(
            f"Model '{OLLAMA_MODEL}' was not found in Ollama. "
            f"Run: ollama pull {OLLAMA_MODEL}"
        )

    if "connection refused" in message or "failed to connect" in message:
        return LLMServiceError(
            "Could not connect to Ollama. Ensure the Ollama service is running."
        )

    return LLMServiceError(f"Ollama request failed: {exc}")