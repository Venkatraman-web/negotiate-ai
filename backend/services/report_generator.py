"""
services/report_generator.py

Report Generator for the AI Negotiation Simulator.

This module runs *after* a negotiation session has been marked as completed
by the Negotiation Engine. It is a **read-only** consumer of the session: it
never mutates trust, patience, offers, round counters, conversation history,
or negotiation status. It only reads them to build a report.

Pipeline (per project architecture):

    Negotiation Engine (marks session completed)
            -> Report Generator (this module)
                -> LLMService.generate_reply()
                    -> Structured Negotiation Report
                        -> Frontend

The generated report has two parts:

    PART 1 - Objective Metrics
        Derived directly from the session object, no LLM involved. This now
        also includes a few extra session statistics, still computed with
        plain Python -- no LLM.

    PART 2 - AI Evaluation
        Produced by prompting the existing LLMService.generate_reply()
        method and validating that it returns well-formed JSON matching
        the expected evaluation schema. The prompt is now heavily
        constrained ("Important Evaluation Rules") so the model grounds
        every claim in the supplied transcript/stats instead of producing
        generic or hallucinated feedback, and every strength/weakness must
        carry a concrete `evidence` string pulled from the negotiation.

Both parts are merged into a single structured dictionary that the API
layer can serialize straight to the frontend.

Integration notes
------------------
This module expects an ``LLMService`` instance to be injected (dependency
injection), matching the existing architecture where the Negotiation
Engine / Prompt Builder already depend on ``LLMService.generate_reply()``.
It does NOT talk to Ollama (or any model backend) directly.

If your concrete ``LLMService.generate_reply`` signature differs slightly
from the one assumed here (e.g. keyword name, or returns a dict instead of
a str), only ``_invoke_llm`` needs to change -- everything else in this
module is agnostic to that detail.

Backward compatibility
-----------------------
The top-level shape of ``generate_report``'s return value is unchanged:

    {
        "objective_metrics": { ... PART 1 ... },
        "ai_evaluation": { ... PART 2 ... },
    }

``objective_metrics`` gained a few new *additive* keys
(``target_offer``, ``maximum_offer``). Existing keys were not renamed or
removed.

``ai_evaluation`` keeps ``communication``, ``negotiation_skills``,
``strategy``, ``overall_score`` and ``overall_summary`` exactly as before.
Two things changed there, both intentionally per the updated requirements:

  * ``strengths`` / ``weaknesses`` are now lists of
    ``{"point": str, "evidence": str}`` objects instead of bare strings,
    so every claim is traceable to something that actually happened in
    the negotiation.
  * A new ``scores`` object was added with five 0-100 numeric fields
    (communication, persuasion, confidence, professionalism,
    emotional_intelligence) so the frontend can render dynamic score bars
    instead of fixed placeholder values.

If your frontend currently reads ``ai_evaluation.strengths[i]`` as a plain
string, it needs to switch to ``ai_evaluation.strengths[i].point`` (and can
optionally show ``.evidence`` too). That is the only breaking change, and
it is required to satisfy "every strength/weakness must be supported by
evidence."
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Protocol

try:
    from ..core.logging_config import setup_logging
except ImportError:  # pragma: no cover - allows running the module directly from the backend folder
    from core.logging_config import setup_logging

setup_logging()
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class ReportGenerationError(Exception):
    """Base exception for all report-generation failures."""


class InvalidSessionDataError(ReportGenerationError):
    """Raised when the completed session is missing data needed for the report."""


class LLMInvocationError(ReportGenerationError):
    """Raised when the underlying LLMService call fails or is unreachable."""


class InvalidLLMResponseError(ReportGenerationError):
    """Raised when the LLM response is not valid JSON."""


class MissingRequiredKeyError(ReportGenerationError):
    """Raised when the parsed LLM JSON is missing one or more required keys."""

    def __init__(self, missing_keys: List[str]):
        self.missing_keys = missing_keys
        super().__init__(f"AI evaluation JSON is missing required keys: {missing_keys}")


class InvalidFieldTypeError(ReportGenerationError):
    """Raised when a field in the parsed LLM JSON has the wrong data type."""

    def __init__(self, field_name: str, expected_type: Any, actual_value: Any):
        self.field_name = field_name
        self.expected_type = expected_type
        self.actual_value = actual_value

        if isinstance(expected_type, tuple):
            expected_name = " or ".join(t.__name__ for t in expected_type)
        else:
            expected_name = expected_type.__name__

        super().__init__(
            f"Field '{field_name}' expected type {expected_name}, "
            f"got {type(actual_value).__name__} ({actual_value!r})"
        )


# ---------------------------------------------------------------------------
# LLMService protocol (structural typing only -- not a redefinition)
# ---------------------------------------------------------------------------


class LLMServiceProtocol(Protocol):
    """
    Structural contract for the existing LLMService.

    This is NOT a new implementation -- it documents the method this module
    relies on so the report generator can be type-checked and unit-tested
    with a mock, without importing the concrete backend-specific class.
    """

    def generate_reply(self, prompt: str, **kwargs: Any) -> str:
        ...


# ---------------------------------------------------------------------------
# Expected shape of a completed negotiation session
# ---------------------------------------------------------------------------


@dataclass
class NegotiationSessionView:
    """
    Read-only view of the fields the Report Generator needs from a
    completed negotiation session.

    Construct this via `NegotiationSessionView.from_session(session)` so the
    generator can accept either a dict-like session or an ORM/session object
    without caring about the concrete session class used elsewhere in the
    backend.
    """

    scenario: str
    personality: str
    conversation_history: List[Dict[str, Any]]
    initial_offer: float
    final_offer: float
    trust: float
    patience: float
    total_rounds: int
    negotiation_status: str
    # Optional, best-effort fields. These are NOT required -- they are only
    # used (when present) to enrich the report's extra statistics.
    # Different session shapes may or may not carry them, so every read is
    # defaulted and every downstream use tolerates None.
    target_offer: Optional[float] = None
    maximum_offer: Optional[float] = None

    @staticmethod
    def from_session(session: Any) -> "NegotiationSessionView":
        """
        Build a `NegotiationSessionView` from an arbitrary session object.

        Supports both dict-like sessions (``session["field"]`` /
        ``session.get("field")``) and attribute-based session objects
        (``session.field``), so this module can plug into whatever session
        representation the Negotiation Engine already uses.

        Raises:
            InvalidSessionDataError: if required fields are missing or of
                an unusable type.
        """

        def read(name: str, default: Any = None) -> Any:
            if isinstance(session, dict):
                return session.get(name, default)
            return getattr(session, name, default)

        required_fields = {
            "scenario": read("scenario"),
            "personality": read("personality"),
            "conversation_history": read(
                "conversation_history", read("conversation", [])
            ),
            "initial_offer": read("initial_offer"),
            "final_offer": read("final_offer", read("current_offer", None)),
            "trust": read("trust"),
            "patience": read("patience"),
            "total_rounds": read("total_rounds", read("round", None)),
            "negotiation_status": read("negotiation_status", read("status", None)),
        }

        missing = [
            key
            for key, value in required_fields.items()
            if value is None and key != "conversation_history"
        ]
        if missing:
            raise InvalidSessionDataError(
                f"Completed session is missing required field(s): {missing}"
            )

        # Best-effort optional fields. Different session models may expose
        # these under different names (or not at all) -- absence is fine.
        target_offer_raw = read("target_offer", read("target", None))
        maximum_offer_raw = read(
            "maximum_offer", read("max_offer", read("ceiling_offer", None))
        )

        try:
            return NegotiationSessionView(
                scenario=str(required_fields["scenario"]),
                personality=str(required_fields["personality"]),
                conversation_history=list(required_fields["conversation_history"] or []),
                initial_offer=float(required_fields["initial_offer"]),
                final_offer=float(required_fields["final_offer"]),
                trust=float(required_fields["trust"]),
                patience=float(required_fields["patience"]),
                total_rounds=int(required_fields["total_rounds"]),
                negotiation_status=str(required_fields["negotiation_status"]),
                target_offer=(
                    float(target_offer_raw) if target_offer_raw is not None else None
                ),
                maximum_offer=(
                    float(maximum_offer_raw) if maximum_offer_raw is not None else None
                ),
            )
        except (TypeError, ValueError) as exc:
            raise InvalidSessionDataError(
                f"Completed session contains fields of an unexpected type: {exc}"
            ) from exc


# ---------------------------------------------------------------------------
# PART 1 - Objective metrics (no LLM involved)
# ---------------------------------------------------------------------------


def _determine_outcome(negotiation_status: str) -> str:
    """
    Normalize the raw negotiation status into a human-readable outcome label.

    This performs a read-only mapping; it never mutates the session's
    original ``negotiation_status`` value.
    """
    normalized = negotiation_status.strip().lower()

    outcome_map = {
        "completed": "Deal Reached",
        "deal_reached": "Deal Reached",
        "accepted": "Deal Reached",
        "success": "Deal Reached",
        "failed": "No Deal",
        "rejected": "No Deal",
        "walked_away": "No Deal",
        "timeout": "Negotiation Timed Out",
        "abandoned": "Negotiation Abandoned",
    }

    return outcome_map.get(normalized, negotiation_status.title())


def build_objective_metrics(session: NegotiationSessionView) -> Dict[str, Any]:
    """
    Build PART 1 of the report: objective metrics read directly from the
    completed session, with no LLM involvement.

    Args:
        session: A validated read-only view of the completed session.

    Returns:
        A dictionary of objective negotiation metrics.
    """
    offer_improvement = session.final_offer - session.initial_offer
    offer_improvement_pct: Optional[float]
    if session.initial_offer != 0:
        offer_improvement_pct = round(
            (offer_improvement / abs(session.initial_offer)) * 100, 2
        )
    else:
        offer_improvement_pct = None

    return {
        "scenario": session.scenario,
        "personality": session.personality,
        "initial_offer": session.initial_offer,
        "final_offer": session.final_offer,
        "offer_improvement": round(offer_improvement, 2),
        "offer_improvement_percent": offer_improvement_pct,
        "number_of_rounds": session.total_rounds,
        "final_trust": session.trust,
        "final_patience": session.patience,
        "negotiation_outcome": _determine_outcome(session.negotiation_status),
        # New, additive fields -- existing keys above are unchanged.
        "target_offer": session.target_offer,
        "maximum_offer": session.maximum_offer,
    }


# ---------------------------------------------------------------------------
# PART 2 - AI evaluation (via LLMService.generate_reply)
# ---------------------------------------------------------------------------

# Schema of the JSON object the LLM must return for the AI evaluation half
# of the report. Used for validation after parsing.
_REQUIRED_EVALUATION_SCHEMA: Dict[str, type] = {
    "communication": dict,
    "negotiation_skills": dict,
    "strategy": dict,
    "scores": dict,
    "overall_score": (int, float),  # validated specially, see _validate_evaluation
    "strengths": list,  # list of {point, evidence} objects, validated specially
    "weaknesses": list,  # list of {point, evidence} objects, validated specially
    "personalized_suggestions": list,
    "overall_summary": str,
}

_REQUIRED_COMMUNICATION_KEYS = ["clarity", "professionalism", "tone"]
_REQUIRED_SKILLS_KEYS = ["confidence", "persuasiveness", "reasoning", "flexibility"]
_REQUIRED_STRATEGY_KEYS = [
    "opening_strategy",
    "counter_offers",
    "concessions",
    "closing_strategy",
]
# Dynamic 0-100 scores the frontend can render as bars/gauges, generated
# from conversation analysis rather than fixed placeholder values.
_REQUIRED_SCORE_KEYS = [
    "communication",
    "persuasion",
    "confidence",
    "professionalism",
    "emotional_intelligence",
]


def _format_conversation_history(history: List[Dict[str, Any]]) -> str:
    """
    Render the conversation history as compact, LLM-friendly transcript text,
    numbering each turn so the model can cite a specific turn as evidence
    (e.g. "Turn 4") instead of vague, unverifiable claims.

    Read-only formatting: does not alter the original history list.
    """
    if not history:
        return "(no conversation recorded)"

    lines = []
    for i, turn in enumerate(history, start=1):
        speaker = turn.get("role") or turn.get("speaker") or "unknown"
        text = turn.get("message") or turn.get("content") or ""
        lines.append(f"Turn {i} [{speaker}]: {text}")
    return "\n".join(lines)


def build_evaluation_prompt(session: NegotiationSessionView) -> str:
    """
    Build the prompt sent to LLMService.generate_reply() to produce PART 2
    of the report (the AI evaluation).

    The prompt strictly instructs the model to return ONLY valid JSON
    matching the required schema, with no extra commentary or markdown
    fences, so the response can be parsed deterministically. It also
    includes an explicit "Important Evaluation Rules" section and requires
    every strength/weakness to cite concrete evidence from the transcript,
    to stop the model (particularly smaller local models such as Llama 3.2
    via Ollama) from producing generic or fabricated feedback.

    Args:
        session: A validated read-only view of the completed session.

    Returns:
        The full evaluation prompt string.
    """
    transcript = _format_conversation_history(session.conversation_history)

    offer_moved = session.final_offer - session.initial_offer
    if session.initial_offer != 0:
        offer_moved_pct = round((offer_moved / abs(session.initial_offer)) * 100, 2)
    else:
        offer_moved_pct = None

    prompt = f"""You are an expert negotiation coach evaluating a completed negotiation.
You must behave like a careful analyst, not a creative writer. You are graded
on FACTUAL ACCURACY, not on how polished or complete your answer sounds.

=== IMPORTANT EVALUATION RULES (read carefully, follow exactly) ===
1. Never hallucinate. Do not invent anything the negotiator did not actually
   say or do.
2. Never assume facts, motivations, or events that are not explicitly present
   in the transcript or session metrics below.
3. Use ONLY the conversation transcript and session metrics provided in this
   prompt as your source of truth. Do not use outside knowledge about how
   "a typical negotiation" goes.
4. Base every conclusion, strength, and weakness on observable evidence you
   can point to in the transcript or the metrics -- not on genre
   expectations (e.g. do not assume a negotiator "accepted the first
   counteroffer" unless the transcript literally shows them accepting the
   first counteroffer they received).
5. If you are uncertain whether something is true, or you cannot find a
   specific turn or metric that supports it, OMIT the point entirely.
   Omitting a point is always better than inventing one. It is completely
   acceptable to return fewer strengths, fewer weaknesses, or an empty
   "personalized_suggestions" list if that is all the evidence supports.
6. The offer moved from {session.initial_offer} to {session.final_offer}
   ({'+' if offer_moved >= 0 else ''}{offer_moved}{f', {offer_moved_pct}%' if offer_moved_pct is not None else ''}).
   If this is a meaningful increase in the negotiator's favor, you MUST
   recognize that as a strength (e.g. "successfully increased the offer from
   {session.initial_offer} to {session.final_offer}"). Do NOT claim the
   negotiator "accepted the first counteroffer" or "failed to negotiate" if
   the final offer is different from the initial offer -- that would
   directly contradict the session metrics and is a serious error.
7. Every entry in "strengths" and "weaknesses" MUST include an "evidence"
   string that references something concrete and checkable -- quote or
   closely paraphrase a specific turn number from the transcript (e.g.
   "Turn 4: negotiator cited market salary data"), or cite a specific
   session metric (e.g. "final trust {session.trust}, final patience
   {session.patience}"). A strength or weakness with vague evidence like
   "throughout the conversation" or "in general" is not acceptable.
8. Do not pad the lists to hit a target length. 1-4 well-evidenced
   strengths and 0-4 well-evidenced weaknesses is normal and expected.
=== END OF RULES ===

SCENARIO:
{session.scenario}

COUNTERPART PERSONALITY:
{session.personality}

SESSION METRICS (ground truth -- treat these as facts):
- Initial offer: {session.initial_offer}
- Final offer: {session.final_offer}
- Net offer movement: {offer_moved}{f' ({offer_moved_pct}%)' if offer_moved_pct is not None else ''}
- Total rounds: {session.total_rounds}
- Final trust level: {session.trust}
- Final patience level: {session.patience}
- Negotiation status: {session.negotiation_status}

FULL CONVERSATION TRANSCRIPT (numbered by turn -- cite turn numbers as evidence):
{transcript}

TASK:
Evaluate the human negotiator's performance across the entire negotiation,
following every rule in "IMPORTANT EVALUATION RULES" above. Respond with
ONLY a single valid JSON object -- no markdown fences, no prose before or
after it, no comments. The JSON object MUST have exactly this structure and
these keys:

{{
  "communication": {{
    "clarity": "<short assessment, grounded in the transcript>",
    "professionalism": "<short assessment, grounded in the transcript>",
    "tone": "<short assessment, grounded in the transcript>"
  }},
  "negotiation_skills": {{
    "confidence": "<short assessment, grounded in the transcript>",
    "persuasiveness": "<short assessment, grounded in the transcript>",
    "reasoning": "<short assessment, grounded in the transcript>",
    "flexibility": "<short assessment, grounded in the transcript>"
  }},
  "strategy": {{
    "opening_strategy": "<short assessment, grounded in the transcript>",
    "counter_offers": "<short assessment, grounded in the transcript>",
    "concessions": "<short assessment, grounded in the transcript>",
    "closing_strategy": "<short assessment, grounded in the transcript>"
  }},
  "scores": {{
    "communication": <integer 0-100, based on the transcript>,
    "persuasion": <integer 0-100, based on the transcript>,
    "confidence": <integer 0-100, based on the transcript>,
    "professionalism": <integer 0-100, based on the transcript>,
    "emotional_intelligence": <integer 0-100, based on the transcript>
  }},
  "overall_score": <integer between 0 and 100>,
  "strengths": [
    {{"point": "<specific strength>", "evidence": "<specific transcript turn or metric>"}}
  ],
  "weaknesses": [
    {{"point": "<specific weakness>", "evidence": "<specific transcript turn or metric>"}}
  ],
  "personalized_suggestions": ["<suggestion tied to an actual observed gap, or omit entirely if none>"],
  "overall_summary": "<2-4 sentence overall summary, grounded in the transcript and metrics>"
}}

Return ONLY the JSON object described above."""
    logger.info(
        "Report prompt built | prompt_length_chars=%d conversation_messages=%d",
        len(prompt),
        len(session.conversation_history),
    )
    return prompt


def _invoke_llm(llm_service: LLMServiceProtocol, prompt: str) -> str:
    """
    Call the existing LLMService to generate the AI evaluation text.

    This is the single integration point with LLMService, so any signature
    differences in the real implementation only need to be adapted here.

    Args:
        llm_service: The shared LLMService instance already used elsewhere
            in the pipeline (e.g. by the Prompt Builder).
        prompt: The evaluation prompt built by `build_evaluation_prompt`.

    Returns:
        The raw text returned by the LLM.

    Raises:
        LLMInvocationError: if the call to LLMService fails.
    """
    try:
        try:
            response = llm_service.generate_reply(
                prompt, response_format="json", temperature=0.1
            )
        except TypeError:
            # Fallback for any LLMService implementation that doesn't
            # support response_format/temperature kwargs (e.g. an
            # older/simpler LLMServiceProtocol implementation used in
            # tests). Behavior degrades to relying on prompt instructions
            # alone, same as before this parameter existed.
            try:
                response = llm_service.generate_reply(prompt, response_format="json")
            except TypeError:
                response = llm_service.generate_reply(prompt)
    except Exception as exc:  # noqa: BLE001 - we deliberately wrap any backend error
        logger.exception("LLMService.generate_reply failed during report generation")
        raise LLMInvocationError(
            f"Failed to generate AI evaluation via LLMService: {exc}"
        ) from exc

    if not isinstance(response, str) or not response.strip():
        raise LLMInvocationError(
            "LLMService.generate_reply returned an empty or non-string response."
        )

    return response


def _strip_markdown_fences(text: str) -> str:
    """Remove ```json ... ``` or ``` ... ``` fences some models still add."""
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = stripped.strip("`")
        if stripped.lower().startswith("json"):
            stripped = stripped[4:]
    return stripped.strip()


def _extract_first_json_object(text: str) -> str:
    """
    Extract the first balanced top-level JSON object from text.

    Smaller local models (e.g. Llama 3.2 via Ollama) sometimes wrap the
    JSON in a sentence or two despite instructions not to. Rather than
    failing outright, find the first ``{`` and its matching ``}`` by
    brace-depth counting (ignoring braces inside string literals) and try
    that slice before giving up.
    """
    start = text.find("{")
    if start == -1:
        return text

    depth = 0
    in_string = False
    escape = False
    for i in range(start, len(text)):
        ch = text[i]
        if in_string:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[start : i + 1]
    return text


def _parse_llm_json(raw_response: str) -> Dict[str, Any]:
    """
    Parse the raw LLM response into a JSON object.

    Raises:
        InvalidLLMResponseError: if the response is not valid JSON, or the
            parsed JSON is not an object at the top level.
    """
    cleaned = _strip_markdown_fences(raw_response)
    try:
        parsed = json.loads(cleaned)
    except json.JSONDecodeError:
        # Second attempt: smaller local models occasionally add stray prose
        # around the JSON despite instructions. Try to salvage the first
        # balanced JSON object before giving up.
        candidate = _extract_first_json_object(cleaned)
        try:
            parsed = json.loads(candidate)
        except json.JSONDecodeError as exc:
            # Show a window of text right around the failure position, since
            # the failure can occur far past the first 500 chars on a long
            # AI-evaluation response, making that alone insufficient to debug.
            window_start = max(0, exc.pos - 100)
            window_end = min(len(candidate), exc.pos + 100)
            context_snippet = candidate[window_start:window_end]
            raise InvalidLLMResponseError(
                f"AI evaluation response was not valid JSON: {exc}. "
                f"Text around the failure point (char {exc.pos}): {context_snippet!r}. "
                f"Raw response (truncated): {raw_response[:500]!r}"
            ) from exc

    if not isinstance(parsed, dict):
        raise InvalidLLMResponseError(
            f"AI evaluation JSON must be an object at the top level, "
            f"got {type(parsed).__name__}."
        )

    return parsed


def _validate_sub_object(
    parent: Dict[str, Any], parent_key: str, required_subkeys: List[str]
) -> None:
    """Validate that a nested dict field contains all its required string subkeys."""
    sub_obj = parent[parent_key]
    if not isinstance(sub_obj, dict):
        raise InvalidFieldTypeError(parent_key, dict, sub_obj)

    missing = [k for k in required_subkeys if k not in sub_obj]
    if missing:
        raise MissingRequiredKeyError([f"{parent_key}.{k}" for k in missing])

    for k in required_subkeys:
        if not isinstance(sub_obj[k], str) or not sub_obj[k].strip():
            raise InvalidFieldTypeError(f"{parent_key}.{k}", str, sub_obj[k])


def _validate_scores(scores: Any) -> None:
    """Validate the 'scores' object: five numeric 0-100 fields."""
    if not isinstance(scores, dict):
        raise InvalidFieldTypeError("scores", dict, scores)

    missing = [k for k in _REQUIRED_SCORE_KEYS if k not in scores]
    if missing:
        raise MissingRequiredKeyError([f"scores.{k}" for k in missing])

    for k in _REQUIRED_SCORE_KEYS:
        value = scores[k]
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise InvalidFieldTypeError(f"scores.{k}", (int, float), value)
        if not (0 <= float(value) <= 100):
            raise InvalidFieldTypeError(
                f"scores.{k}", (int, float), f"{value} (must be between 0 and 100)"
            )


def _validate_evidence_list(field_name: str, items: Any) -> None:
    """
    Validate that a field is a list of {"point": str, "evidence": str}
    objects (the new evidence-backed strengths/weaknesses format).
    """
    if not isinstance(items, list):
        raise InvalidFieldTypeError(field_name, list, items)

    for i, item in enumerate(items):
        if not isinstance(item, dict):
            raise InvalidFieldTypeError(f"{field_name}[{i}]", dict, item)
        if "point" not in item or "evidence" not in item:
            missing = [k for k in ("point", "evidence") if k not in item]
            raise MissingRequiredKeyError([f"{field_name}[{i}].{k}" for k in missing])
        if not isinstance(item["point"], str) or not item["point"].strip():
            raise InvalidFieldTypeError(f"{field_name}[{i}].point", str, item["point"])
        if not isinstance(item["evidence"], str) or not item["evidence"].strip():
            raise InvalidFieldTypeError(
                f"{field_name}[{i}].evidence", str, item["evidence"]
            )


def _validate_evaluation(evaluation: Dict[str, Any]) -> Dict[str, Any]:
    """
    Validate the parsed AI evaluation JSON against the required schema.

    Checks presence of all required top-level keys, correct nested
    structure for communication/negotiation_skills/strategy/scores, correct
    types for score/lists/summary, that every strength/weakness carries
    evidence, and sane bounds for all numeric scores.

    Args:
        evaluation: The parsed JSON dict returned by the LLM.

    Returns:
        The same dictionary, after validation (unmodified on success).

    Raises:
        MissingRequiredKeyError: if any required key (top-level or nested)
            is missing.
        InvalidFieldTypeError: if any field has an unexpected type or the
            overall_score is out of range.
    """
    missing_top_level = [
        key for key in _REQUIRED_EVALUATION_SCHEMA if key not in evaluation
    ]
    if missing_top_level:
        raise MissingRequiredKeyError(missing_top_level)

    _validate_sub_object(evaluation, "communication", _REQUIRED_COMMUNICATION_KEYS)
    _validate_sub_object(evaluation, "negotiation_skills", _REQUIRED_SKILLS_KEYS)
    _validate_sub_object(evaluation, "strategy", _REQUIRED_STRATEGY_KEYS)
    _validate_scores(evaluation["scores"])

    score = evaluation["overall_score"]
    if isinstance(score, bool) or not isinstance(score, (int, float)):
        raise InvalidFieldTypeError("overall_score", (int, float), score)
    if not (0 <= float(score) <= 100):
        raise InvalidFieldTypeError(
            "overall_score", (int, float), f"{score} (must be between 0 and 100)"
        )

    _validate_evidence_list("strengths", evaluation["strengths"])
    _validate_evidence_list("weaknesses", evaluation["weaknesses"])

    suggestions = evaluation["personalized_suggestions"]
    if not isinstance(suggestions, list) or not all(
        isinstance(v, str) for v in suggestions
    ):
        raise InvalidFieldTypeError(
            "personalized_suggestions", list, suggestions
        )

    if not isinstance(evaluation["overall_summary"], str) or not evaluation[
        "overall_summary"
    ].strip():
        raise InvalidFieldTypeError(
            "overall_summary", str, evaluation["overall_summary"]
        )

    return evaluation


def generate_ai_evaluation(
    session: NegotiationSessionView, llm_service: LLMServiceProtocol
) -> Dict[str, Any]:
    """
    Build PART 2 of the report: an AI-generated evaluation of the
    negotiator's performance, produced via LLMService.generate_reply().

    Args:
        session: A validated read-only view of the completed session.
        llm_service: The existing LLMService instance to invoke.

    Returns:
        A validated dictionary matching the AI evaluation schema.

    Raises:
        LLMInvocationError: if the LLM call itself fails.
        InvalidLLMResponseError: if the LLM does not return valid JSON.
        MissingRequiredKeyError: if required keys are missing from the JSON.
        InvalidFieldTypeError: if fields have the wrong type/shape.
    """
    prompt = build_evaluation_prompt(session)

    logger.info("Calling LLMService.generate_reply for AI evaluation")
    raw_response = _invoke_llm(llm_service, prompt)
    logger.info(
        "LLM called | response_length_chars=%d", len(raw_response)
    )

    # Log the FULL raw response (not truncated) so that JSON parsing
    # failures can be diagnosed exactly -- the exception message below
    # only shows the first 500 chars, which isn't enough to see what's
    # malformed later in a long response.
    logger.info("Raw AI evaluation response | raw_response=%r", raw_response)

    parsed = _parse_llm_json(raw_response)
    logger.info("JSON parsed | keys=%s", sorted(parsed.keys()))

    validated = _validate_evaluation(parsed)
    logger.info("AI evaluation validated successfully")
    return validated


# ---------------------------------------------------------------------------
# Public entry point: merge PART 1 + PART 2 into the final report
# ---------------------------------------------------------------------------


def generate_report(
    session: Any,
    llm_service: LLMServiceProtocol,
) -> Dict[str, Any]:
    """
    Generate the complete structured negotiation report for a completed
    session.

    This is the single public entry point Routes should call once the
    Negotiation Engine has marked a session as completed. It:

      1. Builds a read-only view of the session (never mutates it).
      2. Computes PART 1 objective metrics directly from the session.
      3. Requests PART 2 AI evaluation from the existing LLMService.
      4. Validates the AI evaluation JSON.
      5. Merges both parts into a single report dictionary.

    Args:
        session: The completed negotiation session (dict-like or
            attribute-based object) as produced by the Negotiation Engine.
        llm_service: The existing LLMService instance (already used by the
            Prompt Builder / Negotiation Engine) used only via
            `generate_reply()`.

    Returns:
        A dictionary with the shape::

            {
                "objective_metrics": { ... PART 1 ... },
                "ai_evaluation": { ... PART 2 ... },
            }

        ready to be returned as-is by the API layer. See the module
        docstring's "Backward compatibility" section for exactly which
        fields are new vs. unchanged.

    Raises:
        InvalidSessionDataError: if the session is missing required data.
        LLMInvocationError: if the LLMService call fails.
        InvalidLLMResponseError: if the LLM response isn't valid JSON.
        MissingRequiredKeyError: if the AI evaluation JSON is missing keys.
        InvalidFieldTypeError: if the AI evaluation JSON has wrong types.
    """
    logger.info("Report generation started")

    try:
        session_view = NegotiationSessionView.from_session(session)

        objective_metrics = build_objective_metrics(session_view)
        logger.info("Objective metrics computed | outcome=%r", objective_metrics["negotiation_outcome"])

        ai_evaluation = generate_ai_evaluation(session_view, llm_service)

        report = {
            "objective_metrics": objective_metrics,
            "ai_evaluation": ai_evaluation,
        }

        logger.info(
            "Report generation completed | scenario=%r outcome=%r overall_score=%s",
            objective_metrics["scenario"],
            objective_metrics["negotiation_outcome"],
            ai_evaluation.get("overall_score"),
        )

        return report
    except Exception as exc:
        logger.error(
            "Report generation failed | exception_type=%s message=%s",
            type(exc).__name__,
            str(exc),
            exc_info=True,
        )
        raise