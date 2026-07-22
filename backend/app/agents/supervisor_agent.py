import logging
import re
from typing import List, Optional
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field
from backend.app.config.settings import settings

logger = logging.getLogger("omnibrain.agents.supervisor")

_ROUTING_SYSTEM_PROMPT = (
    "You are the Supervisor agent of a multi-agent document intelligence system. "
    "Classify the user's query and decide which specialist agents must run.\n"
    "Available agents:\n"
    "- retrieval: semantic search over ingested document text (use for almost every question).\n"
    "- vision: analysis of images, charts, diagrams, or tables embedded in documents "
    "(routes to indexed image/table descriptions).\n"
    "- sql: natural-language questions about structured data in OmniBrain's own database "
    "(e.g. document counts, ingestion status, per-document page/chunk/table/image statistics) "
    "-- answered via Text-to-SQL over the application's own SQLite schema.\n"
    "Always include 'retrieval' unless the query is exclusively about images or structured data."
)


class RouteDecision(BaseModel):
    """Structured routing decision produced by the Supervisor Agent."""

    intent: str = Field(..., description="Overall classification: 'retrieval', 'vision', 'sql', or 'combined'")
    agents: List[str] = Field(..., description="Subset of {'retrieval','vision','sql'} to invoke, in any order")
    reasoning: str = Field(..., description="One-sentence justification for the routing decision")


class IntentClassifier:
    """Strategy interface for turning a user query into a `RouteDecision`."""

    def classify(self, query: str) -> RouteDecision:
        raise NotImplementedError


class KeywordIntentClassifier(IntentClassifier):
    """Deterministic, fully offline routing fallback based on keyword matching.

    Used whenever the LLM-based classifier is unavailable or fails, and
    directly in tests to keep routing behavior fast and predictable.
    """

    SQL_KEYWORDS = {
        "sql", "database", "table", "row", "rows", "column", "select",
        "how many", "count", "aggregate", "sum of", "average", "group by", "statistics",
    }
    VISION_KEYWORDS = {
        "image", "picture", "photo", "chart", "graph", "diagram", "figure",
        "visual", "screenshot", "plot",
    }

    @staticmethod
    def _contains_any_keyword(text: str, keywords: set) -> bool:
        """Matches keywords on word boundaries so short words like 'row'
        don't spuriously match inside unrelated words (e.g. 'growth').
        """
        return any(re.search(rf"\b{re.escape(kw)}\b", text) for kw in keywords)

    def classify(self, query: str) -> RouteDecision:
        lowered = query.lower()
        agents = ["retrieval"]

        if self._contains_any_keyword(lowered, self.SQL_KEYWORDS):
            agents.append("sql")
        if self._contains_any_keyword(lowered, self.VISION_KEYWORDS):
            agents.append("vision")

        intent = "combined" if len(agents) > 1 else "retrieval"
        return RouteDecision(
            intent=intent,
            agents=agents,
            reasoning="Keyword-based fallback classification (no LLM routing available).",
        )


class LLMIntentClassifier(IntentClassifier):
    """LLM-driven routing using structured output over `RouteDecision`."""

    def __init__(self, llm: BaseChatModel):
        self._structured_llm = llm.with_structured_output(RouteDecision)

    def classify(self, query: str) -> RouteDecision:
        return self._structured_llm.invoke(
            [SystemMessage(content=_ROUTING_SYSTEM_PROMPT), HumanMessage(content=query)]
        )


class SupervisorAgent:
    """Entry point of the orchestrator graph.

    Understands user intent and decides which specialist agents
    (Retrieval / Vision / SQL) should be invoked for a given query,
    preferring an LLM-based classifier and transparently degrading to a
    deterministic keyword classifier if the LLM call is unavailable or fails.
    """

    def __init__(self, classifier: Optional[IntentClassifier] = None):
        self.classifier = classifier or self._build_default_classifier()
        self.fallback_classifier = KeywordIntentClassifier()

    @staticmethod
    def _build_default_classifier() -> IntentClassifier:
        try:
            llm = ChatOpenAI(
                model=settings.OPENAI_MODEL, api_key=settings.OPENAI_API_KEY, temperature=0,
                timeout=settings.LLM_REQUEST_TIMEOUT_SECONDS, max_retries=settings.LLM_MAX_RETRIES,
            )
            return LLMIntentClassifier(llm)
        except Exception as exc:
            logger.warning(f"Could not initialize LLM intent classifier, using keyword fallback: {exc}")
            return KeywordIntentClassifier()

    def decide(self, query: str) -> RouteDecision:
        """Returns the routing decision for `query`. Never raises -- any
        classifier failure degrades to the deterministic keyword fallback.
        """
        try:
            return self.classifier.classify(query)
        except Exception as exc:
            logger.warning(f"LLM-based routing failed ({exc}); falling back to keyword classifier.")
            return self.fallback_classifier.classify(query)
