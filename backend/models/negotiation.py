from typing import List, Optional

from pydantic import BaseModel, Field


class StartNegotiationRequest(BaseModel):
    """Payload for starting a negotiation session."""

    scenario: str = Field(..., example="Salary Negotiation")
    personality: str = Field(..., example="Aggressive")


class StartNegotiationResponse(BaseModel):
    """Response returned when a negotiation session is created."""

    session_id: str
    message: str
    scenario: str
    personality: str
    round: int


class ChatRequest(BaseModel):
    """Payload for sending a chat message in an active negotiation."""

    session_id: str = Field(..., example="abc123")
    message: str = Field(..., example="I want 12 LPA.")


class ChatResponse(BaseModel):
    """Negotiation reply and updated session state returned to the frontend."""

    reply: str
    current_offer: float
    trust: int
    patience: int
    round: int
    status: str


class FinishNegotiationRequest(BaseModel):
    """Payload for finishing a negotiation session."""

    session_id: str = Field(..., example="abc123")


class ObjectiveMetrics(BaseModel):
    """PART 1 of the report: metrics read directly from the session, no LLM involved."""

    scenario: str
    personality: str
    initial_offer: float
    final_offer: float
    offer_improvement: float
    offer_improvement_percent: Optional[float] = None
    number_of_rounds: int
    final_trust: float
    final_patience: float
    negotiation_outcome: str


class CommunicationEvaluation(BaseModel):
    """Communication sub-scores within the AI evaluation."""

    clarity: str
    professionalism: str
    tone: str


class NegotiationSkillsEvaluation(BaseModel):
    """Negotiation-skill sub-scores within the AI evaluation."""

    confidence: str
    persuasiveness: str
    reasoning: str
    flexibility: str


class StrategyEvaluation(BaseModel):
    """Strategy sub-scores within the AI evaluation."""

    opening_strategy: str
    counter_offers: str
    concessions: str
    closing_strategy: str


class AIEvaluation(BaseModel):
    """PART 2 of the report: the AI-generated performance evaluation."""

    communication: CommunicationEvaluation
    negotiation_skills: NegotiationSkillsEvaluation
    strategy: StrategyEvaluation
    overall_score: float
    strengths: List[str]
    weaknesses: List[str]
    personalized_suggestions: List[str]
    overall_summary: str


class ReportResponse(BaseModel):
    """Structured negotiation report returned to the frontend."""

    objective_metrics: ObjectiveMetrics
    ai_evaluation: AIEvaluation
