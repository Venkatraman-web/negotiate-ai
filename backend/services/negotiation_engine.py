import logging
import uuid
from typing import Any, Dict, List, Optional

try:
    from ..core.logging_config import setup_logging
except ImportError:  # pragma: no cover - allows running the module directly from the backend folder
    from core.logging_config import setup_logging

setup_logging()
logger = logging.getLogger(__name__)


class NegotiationSessionError(Exception):
    """Raised when a negotiation session cannot be used safely."""


def generate_session_id() -> str:
    """Create a unique session identifier for a negotiation."""
    return str(uuid.uuid4())


def clamp_value(value: int | float, minimum: int | float, maximum: int | float) -> int | float:
    """Clamp a numeric value to a valid range."""
    return max(minimum, min(maximum, value))


def create_session(
    scenario: str,
    personality: str,
    current_offer: int = 12,
    target_offer: int = 16,
    minimum_offer: int = 10,
    maximum_offer: int = 20,
) -> Dict[str, Any]:
    """Create and store a new negotiation session in memory."""
    session: Dict[str, Any] = {
        "session_id": generate_session_id(),
        "scenario": scenario,
        "personality": personality,
        "round": 1,
        "status": "ongoing",
        "current_offer": current_offer,
        "initial_offer": current_offer,
        "target_offer": target_offer,
        "minimum_offer": minimum_offer,
        "maximum_offer": maximum_offer,
        "trust": 50,
        "patience": 100,
        "conversation": [],
    }

    _SESSIONS[session["session_id"]] = session
    logger.info(
        "Session created | session_id=%s scenario=%r personality=%r "
        "initial_offer=%s trust=%s patience=%s",
        session["session_id"],
        scenario,
        personality,
        current_offer,
        session["trust"],
        session["patience"],
    )
    return session


_SESSIONS: Dict[str, Dict[str, Any]] = {}


def get_session(session_id: str) -> Dict[str, Any]:
    """Return the session associated with the given identifier."""
    if session_id not in _SESSIONS:
        logger.error("Session lookup failed | session_id=%s not found", session_id)
        raise NegotiationSessionError(f"Session '{session_id}' was not found.")

    return _SESSIONS[session_id]


def add_message(session_id: str, role: str, message: str) -> Dict[str, Any]:
    """Append a message to the conversation history for a session."""
    session = get_session(session_id)

    if session["status"] == "completed":
        logger.error(
            "Rejected add_message | session_id=%s reason=session already completed",
            session_id,
        )
        raise NegotiationSessionError("Cannot add messages to a completed negotiation.")

    session["conversation"].append({"role": role, "content": message})
    logger.info(
        "Message appended | session_id=%s role=%s conversation_length=%d",
        session_id,
        role,
        len(session["conversation"]),
    )
    return session


def update_offer(session_id: str, new_offer: int) -> Dict[str, Any]:
    """Update the current offer for a negotiation session."""
    session = get_session(session_id)

    if session["status"] == "completed":
        logger.error(
            "Rejected update_offer | session_id=%s reason=session already completed",
            session_id,
        )
        raise NegotiationSessionError("Cannot update the offer for a completed negotiation.")

    offer_before = session["current_offer"]
    session["current_offer"] = new_offer
    logger.info(
        "Offer updated | session_id=%s offer_before=%s offer_after=%s",
        session_id,
        offer_before,
        session["current_offer"],
    )
    return session


def update_trust(session_id: str, delta: int) -> Dict[str, Any]:
    """Increase or decrease trust, clamped between 0 and 100."""
    session = get_session(session_id)

    if session["status"] == "completed":
        logger.error(
            "Rejected update_trust | session_id=%s reason=session already completed",
            session_id,
        )
        raise NegotiationSessionError("Cannot update trust for a completed negotiation.")

    trust_before = session["trust"]
    session["trust"] = clamp_value(session["trust"] + delta, 0, 100)
    logger.info(
        "Trust updated | session_id=%s trust_before=%s delta=%s trust_after=%s",
        session_id,
        trust_before,
        delta,
        session["trust"],
    )
    return session


def update_patience(session_id: str, delta: int) -> Dict[str, Any]:
    """Increase or decrease patience, clamped between 0 and 100."""
    session = get_session(session_id)

    if session["status"] == "completed":
        logger.error(
            "Rejected update_patience | session_id=%s reason=session already completed",
            session_id,
        )
        raise NegotiationSessionError("Cannot update patience for a completed negotiation.")

    patience_before = session["patience"]
    session["patience"] = clamp_value(session["patience"] + delta, 0, 100)
    logger.info(
        "Patience updated | session_id=%s patience_before=%s delta=%s patience_after=%s",
        session_id,
        patience_before,
        delta,
        session["patience"],
    )
    return session


def next_round(session_id: str) -> Dict[str, Any]:
    """Advance the negotiation to the next round, up to a maximum of 8."""
    session = get_session(session_id)

    if session["status"] == "completed":
        logger.error(
            "Rejected next_round | session_id=%s reason=session already completed",
            session_id,
        )
        raise NegotiationSessionError("Cannot advance a completed negotiation.")

    round_before = session["round"]
    session["round"] += 1

    if session["round"] > 8:
        session["round"] = 8
        session["status"] = "completed"
        logger.info(
            "Round capped at maximum | session_id=%s round_before=%s round_after=%s status=%s",
            session_id,
            round_before,
            session["round"],
            session["status"],
        )
    else:
        logger.info(
            "Round advanced | session_id=%s round_before=%s round_after=%s",
            session_id,
            round_before,
            session["round"],
        )

    return session


def calculate_next_offer(session: Dict[str, Any], analysis: Dict[str, int]) -> float:
    """Calculate the next offer using trust, patience, reasoning, confidence,
    and aggression signals.

    Design notes (replaces the old round-based hard cutoffs):
    - A single continuous "concession score" (0-100) is derived from the
      negotiation signals. Trust, patience, reasoning_quality, and confidence
      push the score up (more willing to concede); aggression pushes it down.
    - Below the target offer, any round that clears a moderate score
      threshold earns a small, steady step toward the target. This produces
      a smooth, consistent climb in a strong negotiation instead of stopping
      dead once a fixed round number is reached.
    - Once the offer has reached or passed the target, a much higher
      "exceptional" threshold is required to move further, and the step size
      tapers smoothly the closer the offer gets to maximum_offer -- so it
      drifts toward the ceiling instead of jumping to it.
    - The offer never decreases and never exceeds maximum_offer.
    """
    session_id = session.get("session_id")

    if session["status"] == "completed":
        logger.info(
            "Offer unchanged | session_id=%s reason=negotiation_completed offer=%s",
            session_id, session["current_offer"],
        )
        return session["current_offer"]

    current_offer = session["current_offer"]
    maximum_offer = session["maximum_offer"]
    target_offer = session.get("target_offer", maximum_offer)

    if current_offer >= maximum_offer:
        logger.info(
            "Offer unchanged | session_id=%s reason=at_maximum_offer offer=%s",
            session_id, current_offer,
        )
        return current_offer

    trust = session["trust"]
    patience = session["patience"]
    round_number = session["round"]

    reasoning = analysis.get("reasoning_quality", 0)
    confidence = analysis.get("confidence", 0)
    aggression = analysis.get("aggression", 0)

    # Continuous concession score, roughly 0-100. Positive signals push it
    # up, aggression pulls it down. No dependence on round number -- the
    # progression is driven purely by negotiation quality, so it never stalls
    # just because a fixed round count was reached.
    concession_score = (
        0.30 * trust
        + 0.25 * patience
        + 2.5 * reasoning      # reasoning_quality is 0-10 -> scaled to 0-25
        + 2.0 * confidence     # confidence is 0-10 -> scaled to 0-20
        - 3.5 * aggression     # aggression is 0-10 -> penalty up to -35
    )
    concession_score = max(0.0, min(100.0, concession_score))

    BASE_STEP = 0.5
    BELOW_TARGET_THRESHOLD = 55.0
    BEYOND_TARGET_THRESHOLD = 85.0

    below_target = current_offer < target_offer

    if below_target:
        if concession_score < BELOW_TARGET_THRESHOLD:
            logger.info(
                "Offer unchanged | session_id=%s reason=score_below_threshold "
                "score=%.1f threshold=%.1f trust=%s patience=%s reasoning=%s "
                "confidence=%s aggression=%s round=%s offer=%s",
                session_id, concession_score, BELOW_TARGET_THRESHOLD,
                trust, patience, reasoning, confidence, aggression,
                round_number, current_offer,
            )
            return current_offer

        new_offer = round(min(current_offer + BASE_STEP, maximum_offer), 2)
        logger.info(
            "Offer increased | session_id=%s reason=concession_below_target "
            "score=%.1f threshold=%.1f increment=%.2f trust=%s patience=%s "
            "reasoning=%s confidence=%s aggression=%s round=%s "
            "old_offer=%s new_offer=%s",
            session_id, concession_score, BELOW_TARGET_THRESHOLD, BASE_STEP,
            trust, patience, reasoning, confidence, aggression, round_number,
            current_offer, new_offer,
        )
        return new_offer

    # At or beyond target: require an exceptional score, and taper the step
    # smoothly as the offer approaches maximum_offer so it never jumps
    # straight to the ceiling.
    if concession_score < BEYOND_TARGET_THRESHOLD:
        logger.info(
            "Offer unchanged | session_id=%s reason=beyond_target_score_not_exceptional "
            "score=%.1f threshold=%.1f trust=%s patience=%s reasoning=%s "
            "confidence=%s aggression=%s round=%s offer=%s",
            session_id, concession_score, BEYOND_TARGET_THRESHOLD, trust,
            patience, reasoning, confidence, aggression, round_number,
            current_offer,
        )
        return current_offer

    room_beyond_target = max(maximum_offer - target_offer, 0.01)
    remaining_room = max(maximum_offer - current_offer, 0.0)
    # Shrinks toward 0 as current_offer approaches maximum_offer.
    proximity_factor = max(0.0, min(1.0, remaining_room / room_beyond_target))

    increment = round(min(BASE_STEP * (0.3 + 0.7 * proximity_factor), remaining_room), 2)
    if increment <= 0:
        logger.info(
            "Offer unchanged | session_id=%s reason=negligible_room_near_maximum "
            "score=%.1f offer=%s maximum_offer=%s",
            session_id, concession_score, current_offer, maximum_offer,
        )
        return current_offer

    new_offer = round(min(current_offer + increment, maximum_offer), 2)
    logger.info(
        "Offer increased | session_id=%s reason=exceptional_concession_beyond_target "
        "score=%.1f threshold=%.1f increment=%.2f proximity_factor=%.2f "
        "trust=%s patience=%s reasoning=%s confidence=%s aggression=%s "
        "round=%s old_offer=%s new_offer=%s",
        session_id, concession_score, BEYOND_TARGET_THRESHOLD, increment,
        proximity_factor, trust, patience, reasoning, confidence, aggression,
        round_number, current_offer, new_offer,
    )
    return new_offer


def update_session_state(session_id: str, analysis: Dict[str, int]) -> Dict[str, Any]:
    """Update trust, patience, offer, round, and status from analyzer output."""
    session = get_session(session_id)

    if session["status"] == "completed":
        logger.error(
            "Rejected update_session_state | session_id=%s reason=session already completed",
            session_id,
        )
        raise NegotiationSessionError("Cannot update a completed negotiation.")

    logger.info(
        "Negotiation engine update started | session_id=%s round=%s analysis=%s",
        session_id,
        session["round"],
        analysis,
    )

    trust_delta = (
        analysis.get("politeness", 0)
        + analysis.get("reasoning_quality", 0)
        + analysis.get("flexibility", 0) // 2
        - analysis.get("aggression", 0)
    )
    update_trust(session_id, trust_delta)

    patience_delta = -1
    if analysis.get("aggression", 0) >= 6:
        patience_delta -= 3
    if analysis.get("flexibility", 0) >= 7:
        patience_delta += 1

    update_patience(session_id, patience_delta)

    next_offer = calculate_next_offer(session, analysis)
    if next_offer != session["current_offer"]:
        update_offer(session_id, next_offer)

    next_round(session_id)

    if session["patience"] <= 0:
        session["status"] = "completed"
        logger.info(
            "Negotiation status changed | session_id=%s status=completed reason=patience depleted",
            session_id,
        )
    elif session["round"] >= 8:
        session["status"] = "completed"
        logger.info(
            "Negotiation status changed | session_id=%s status=completed reason=max rounds reached",
            session_id,
        )

    logger.info(
        "Negotiation engine update finished | session_id=%s round=%s status=%s "
        "trust=%s patience=%s current_offer=%s",
        session_id,
        session["round"],
        session["status"],
        session["trust"],
        session["patience"],
        session["current_offer"],
    )

    return session


def end_negotiation(session_id: str) -> Dict[str, Any]:
    """Mark a negotiation session as completed."""
    session = get_session(session_id)

    status_before = session["status"]
    session["status"] = "completed"
    logger.info(
        "Negotiation ended | session_id=%s status_before=%s status_after=%s "
        "round=%s trust=%s patience=%s current_offer=%s",
        session_id,
        status_before,
        session["status"],
        session["round"],
        session["trust"],
        session["patience"],
        session["current_offer"],
    )
    return session