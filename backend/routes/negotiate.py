import logging
import time

from fastapi import APIRouter, HTTPException

try:
    from ..core.logging_config import setup_logging
except ImportError:  # pragma: no cover - allows running the module directly from the backend folder
    from core.logging_config import setup_logging

try:
    from ..models.negotiation import (
        ChatRequest,
        ChatResponse,
        FinishNegotiationRequest,
        ReportResponse,
        StartNegotiationRequest,
        StartNegotiationResponse,
    )
except ImportError:  # pragma: no cover - allows running the module directly from the backend folder
    from models.negotiation import (
        ChatRequest,
        ChatResponse,
        FinishNegotiationRequest,
        ReportResponse,
        StartNegotiationRequest,
        StartNegotiationResponse,
    )

try:
    from ..services.llm_service import LLMService, LLMServiceError
    from ..services.message_analyzer import analyze_message
    from ..services.negotiation_engine import (
        NegotiationSessionError,
        add_message,
        create_session,
        end_negotiation,
        get_session,
        update_session_state,
    )
    from ..services.prompt_builder import build_chat_prompt
    from ..services.report_generator import (
        InvalidFieldTypeError,
        InvalidLLMResponseError,
        InvalidSessionDataError,
        LLMInvocationError,
        MissingRequiredKeyError,
        generate_report,
    )
except ImportError:  # pragma: no cover - allows running the module directly from the backend folder
    from services.llm_service import LLMService, LLMServiceError
    from services.message_analyzer import analyze_message
    from services.negotiation_engine import (
        NegotiationSessionError,
        add_message,
        create_session,
        end_negotiation,
        get_session,
        update_session_state,
    )
    from services.prompt_builder import build_chat_prompt
    from services.report_generator import (
        InvalidFieldTypeError,
        InvalidLLMResponseError,
        InvalidSessionDataError,
        LLMInvocationError,
        MissingRequiredKeyError,
        generate_report,
    )

setup_logging()
logger = logging.getLogger(__name__)

router = APIRouter(prefix="", tags=["Negotiation"])
_llm_service = LLMService()


def _public_status(status: str) -> str:
    """Map internal session status values to frontend-friendly labels."""
    if status == "ongoing":
        return "active"
    return status


@router.post("/start-negotiation", response_model=StartNegotiationResponse)
def start_negotiation(request: StartNegotiationRequest) -> StartNegotiationResponse:
    """Start a negotiation session and keep it in the in-memory engine."""
    request_start = time.perf_counter()
    logger.info(
        "Incoming request | endpoint=/start-negotiation scenario=%r personality=%r",
        request.scenario,
        request.personality,
    )

    try:
        session = create_session(request.scenario, request.personality)

        response = StartNegotiationResponse(
            session_id=session["session_id"],
            message="Negotiation started successfully.",
            scenario=request.scenario,
            personality=request.personality,
            round=session["round"],
        )

        total_time = time.perf_counter() - request_start
        logger.info(
            "Response generated | endpoint=/start-negotiation session_id=%s "
            "total_request_time=%.4fs",
            session["session_id"],
            total_time,
        )
        return response
    except Exception as exc:
        logger.error(
            "Unhandled exception in /start-negotiation | exception_type=%s message=%s",
            type(exc).__name__,
            str(exc),
            exc_info=True,
        )
        raise


@router.post("/chat", response_model=ChatResponse)
def chat(request: ChatRequest) -> ChatResponse:
    """Run one full negotiation turn from user message to AI reply."""
    request_start = time.perf_counter()
    analyzer_time = 0.0
    engine_time = 0.0
    prompt_builder_time = 0.0
    llm_reply_time = 0.0

    logger.info(
        "Chat request received | endpoint=/chat session_id=%s", request.session_id
    )

    try:
        session = get_session(request.session_id)
    except NegotiationSessionError as exc:
        logger.error(
            "Chat request failed | session_id=%s exception_type=%s message=%s",
            request.session_id,
            type(exc).__name__,
            str(exc),
            exc_info=True,
        )
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    logger.info(
        "Chat request context | session_id=%s current_round=%s user_message_length=%d",
        request.session_id,
        session["round"],
        len(request.message),
    )
    logger.info("User message received | session_id=%s", request.session_id)

    try:
        add_message(request.session_id, "user", request.message)

        analyzer_start = time.perf_counter()
        metrics = analyze_message(request.message)
        analyzer_time = time.perf_counter() - analyzer_start
        logger.info(
            "Message analyzer finished | session_id=%s duration=%.4fs",
            request.session_id,
            analyzer_time,
        )

        engine_start = time.perf_counter()
        update_session_state(request.session_id, metrics)
        engine_time = time.perf_counter() - engine_start
        logger.info(
            "Negotiation engine update finished | session_id=%s duration=%.4fs",
            request.session_id,
            engine_time,
        )

        session = get_session(request.session_id)

        prompt_builder_start = time.perf_counter()
        prompt = build_chat_prompt(session)
        prompt_builder_time = time.perf_counter() - prompt_builder_start
        logger.info(
            "Prompt builder finished | session_id=%s duration=%.4fs",
            request.session_id,
            prompt_builder_time,
        )

        llm_start = time.perf_counter()
        reply = _llm_service.generate_reply(prompt)
        llm_reply_time = time.perf_counter() - llm_start
        logger.info(
            "LLM reply generation finished | session_id=%s duration=%.4fs",
            request.session_id,
            llm_reply_time,
        )

        add_message(request.session_id, "assistant", reply)
        session = get_session(request.session_id)

        response = ChatResponse(
            reply=reply,
            current_offer=float(session["current_offer"]),
            trust=session["trust"],
            patience=session["patience"],
            round=session["round"],
            status=_public_status(session["status"]),
        )

        total_time = time.perf_counter() - request_start
        logger.info(
            "\n===============================\n"
            "Chat Request Completed\n"
            "Session: %s\n"
            "Round: %s\n"
            "Analyzer Time: %.2f sec\n"
            "Negotiation Engine Time: %.2f sec\n"
            "Prompt Builder Time: %.2f sec\n"
            "LLM Reply Time: %.2f sec\n"
            "Total Request Time: %.2f sec\n"
            "===============================",
            request.session_id,
            session["round"],
            analyzer_time,
            engine_time,
            prompt_builder_time,
            llm_reply_time,
            total_time,
        )
        logger.info(
            "Response generated | endpoint=/chat session_id=%s total_request_time=%.4fs",
            request.session_id,
            total_time,
        )

        return response
    except NegotiationSessionError as exc:
        logger.error(
            "Chat request failed | session_id=%s exception_type=%s message=%s",
            request.session_id,
            type(exc).__name__,
            str(exc),
            exc_info=True,
        )
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except LLMServiceError as exc:
        logger.error(
            "Chat request failed | session_id=%s exception_type=%s message=%s",
            request.session_id,
            type(exc).__name__,
            str(exc),
            exc_info=True,
        )
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ValueError as exc:
        logger.error(
            "Chat request failed | session_id=%s exception_type=%s message=%s",
            request.session_id,
            type(exc).__name__,
            str(exc),
            exc_info=True,
        )
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        logger.error(
            "Chat request failed with unexpected exception | session_id=%s "
            "exception_type=%s message=%s",
            request.session_id,
            type(exc).__name__,
            str(exc),
            exc_info=True,
        )
        raise HTTPException(status_code=500, detail=f"Unexpected error: {exc}") from exc


@router.post("/finish-negotiation", response_model=ReportResponse)
def finish_negotiation(request: FinishNegotiationRequest) -> ReportResponse:
    """Mark the session as completed and return its structured negotiation report.

    Orchestration only: the Negotiation Engine owns retrieving/completing the
    session, and `services.report_generator` owns all report-generation
    logic (objective metrics + AI evaluation). This route just wires the two
    together and translates failures into HTTP errors.
    """
    request_start = time.perf_counter()
    logger.info(
        "Incoming request | endpoint=/finish-negotiation session_id=%s",
        request.session_id,
    )

    try:
        session = end_negotiation(request.session_id)
    except NegotiationSessionError as exc:
        logger.error(
            "Finish-negotiation failed | session_id=%s exception_type=%s message=%s",
            request.session_id,
            type(exc).__name__,
            str(exc),
            exc_info=True,
        )
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    try:
        report = generate_report(session, _llm_service)
    except InvalidSessionDataError as exc:
        logger.error(
            "Finish-negotiation failed | session_id=%s exception_type=%s message=%s",
            request.session_id,
            type(exc).__name__,
            str(exc),
            exc_info=True,
        )
        raise HTTPException(
            status_code=400, detail=f"Cannot generate report: {exc}"
        ) from exc
    except (
        LLMInvocationError,
        InvalidLLMResponseError,
        MissingRequiredKeyError,
        InvalidFieldTypeError,
    ) as exc:
        logger.error(
            "Finish-negotiation failed | session_id=%s exception_type=%s message=%s",
            request.session_id,
            type(exc).__name__,
            str(exc),
            exc_info=True,
        )
        raise HTTPException(
            status_code=502,
            detail=f"Failed to generate AI evaluation for the negotiation report: {exc}",
        ) from exc
    except Exception as exc:
        logger.error(
            "Finish-negotiation failed with unexpected exception | session_id=%s "
            "exception_type=%s message=%s",
            request.session_id,
            type(exc).__name__,
            str(exc),
            exc_info=True,
        )
        raise HTTPException(
            status_code=500, detail=f"Unexpected error generating report: {exc}"
        ) from exc

    total_time = time.perf_counter() - request_start
    logger.info(
        "Response generated | endpoint=/finish-negotiation session_id=%s "
        "total_request_time=%.4fs",
        request.session_id,
        total_time,
    )

    return ReportResponse(**report)