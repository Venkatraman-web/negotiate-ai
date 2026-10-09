from __future__ import annotations

import json
import logging
import os
import re
import time
from datetime import datetime
from typing import Any, Dict, Final

from google import genai
from google.genai import errors as genai_errors
from google.genai import types

try:  # optional: load GEMINI_API_KEY / GEMINI_MODEL from a local .env file
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:  # pragma: no cover - python-dotenv is optional
    pass

try:
    from ..core.logging_config import setup_logging
except ImportError:  # pragma: no cover - allows running the module directly from the backend folder
    from core.logging_config import setup_logging

setup_logging()
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
GEMINI_MODEL: Final[str] = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
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
    """Raised when the LLM service fails to respond correctly."""


class LLMService:
    """Single backend gateway for all LLM communication via the Gemini API.

    This module handles transport to the model only. It does not build
    negotiation prompts, mutate session state, or apply negotiation logic.
    """

    def __init__(
        self,
        model: str = GEMINI_MODEL,
        api_key: str | None = None,
        timeout: float = REQUEST_TIMEOUT_SECONDS,
    ) -> None:
        self.model = model
        self.timeout = timeout
        self._api_key = api_key
        # The client is created lazily so the backend can start (and report a
        # clear error on the first request) even if no API key is configured.
        self._client: genai.Client | None = None

    def _get_client(self) -> genai.Client:
        """Create the Gemini client on first use."""
        if self._client is None:
            api_key = (
                self._api_key
                or os.getenv("GEMINI_API_KEY")
                or os.getenv("GOOGLE_API_KEY")
            )
            if not api_key:
                raise LLMServiceError(
                    "Gemini API key not found. Set the GEMINI_API_KEY "
                    "environment variable (see .env.example)."
                )
            self._client = genai.Client(
                api_key=api_key,
                http_options=types.HttpOptions(timeout=int(self.timeout * 1000)),
            )
        return self._client

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
            response_format: Optional output format constraint.
                Pass "json" to force Gemini's JSON response mode
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
        """Send a prompt to Gemini and return trimmed model output."""
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
            config = types.GenerateContentConfig(
                temperature=temperature,
                response_mime_type=(
                    "application/json" if response_format == "json" else None
                ),
            )
            response = self._get_client().models.generate_content(
                model=self.model,
                contents=prompt,
                config=config,
            )
        except LLMServiceError:
            raise
        except genai_errors.APIError as exc:
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
            raise _map_api_error(exc, self.model) from exc
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
                "Could not connect to the Gemini API. Check your network connection."
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
            raise LLMServiceError(f"Unexpected Gemini error: {exc}") from exc

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
            raise LLMServiceError("Gemini returned an empty response.")

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
    """Extract generated text from a Gemini response object or dict."""
    if isinstance(response, dict):
        text = response.get("text", "")
    else:
        text = getattr(response, "text", "")

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


def _map_api_error(exc: genai_errors.APIError, model: str) -> LLMServiceError:
    """Convert Gemini API errors into clearer application exceptions."""
    status = getattr(exc, "code", None)
    message = str(exc).lower()

    if status == 404 or ("model" in message and "not found" in message):
        return LLMServiceError(
            f"Gemini model '{model}' was not found. Set GEMINI_MODEL to a "
            "model available to your API key."
        )

    if status in (401, 403) or "api key" in message:
        return LLMServiceError(
            "Gemini rejected the API key. Check the GEMINI_API_KEY value."
        )

    if status == 429:
        return LLMServiceError(
            "Gemini rate limit or quota exceeded. Wait a moment and retry."
        )

    return LLMServiceError(f"Gemini request failed: {exc}")
