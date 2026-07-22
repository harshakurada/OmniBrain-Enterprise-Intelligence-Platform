from functools import lru_cache
from fastapi import Depends
from langgraph.checkpoint.memory import MemorySaver
from sqlalchemy.orm import Session
from backend.app.agents.graph import build_orchestrator_graph
from backend.app.agents.orchestrator_service import OrchestratorService
from backend.app.agents.retrieval_agent import RetrievalAgent
from backend.app.agents.sql_agent import SQLAgent
from backend.app.agents.supervisor_agent import SupervisorAgent
from backend.app.agents.synthesizer_agent import ResponseSynthesizer
from backend.app.agents.vision_agent import VisionAgent
from backend.app.database.connection import get_db, get_readonly_db
from backend.app.evaluation.evaluation_service import EvaluationHistoryStore, EvaluationService
from backend.app.guardrails.input_guardrail import InputGuardrailService
from backend.app.guardrails.output_guardrail import OutputGuardrailService
from backend.app.observability.metrics_service import MetricsService
from backend.app.services.chunking_service import RecursiveChunkingService
from backend.app.services.document_service import DocumentIngestionService
from backend.app.services.embedding_service import EmbeddingService
from backend.app.services.pdf_parser import PDFParserService
from backend.app.services.search_service import SemanticSearchService
from backend.app.services.sql_database_service import SQLDatabaseService
from backend.app.services.text_to_sql_service import TextToSQLService
from backend.app.services.vector_store_service import VectorStoreBase, get_vector_store
from backend.app.services.vision_analysis_service import VisionAnalysisService
from backend.app.services.visual_asset_service import VisualAssetService


def get_pdf_parser_service() -> PDFParserService:
    return PDFParserService()


def get_chunking_service() -> RecursiveChunkingService:
    return RecursiveChunkingService()


def get_embedding_service() -> EmbeddingService:
    return EmbeddingService()


def get_active_vector_store() -> VectorStoreBase:
    return get_vector_store()


def get_semantic_search_service(
    embedder: EmbeddingService = Depends(get_embedding_service),
    vector_store: VectorStoreBase = Depends(get_active_vector_store),
) -> SemanticSearchService:
    return SemanticSearchService(embedder=embedder, vector_store=vector_store)


# ---------------------------------------------------------------------------
# Module 4: Vision Intelligence dependencies
# ---------------------------------------------------------------------------


def get_vision_analysis_service() -> VisionAnalysisService:
    return VisionAnalysisService()


def get_visual_asset_service(
    vision_analyzer: VisionAnalysisService = Depends(get_vision_analysis_service),
) -> VisualAssetService:
    return VisualAssetService(vision_analyzer=vision_analyzer)


def get_document_ingestion_service(
    db: Session = Depends(get_db),
    pdf_parser: PDFParserService = Depends(get_pdf_parser_service),
    chunker: RecursiveChunkingService = Depends(get_chunking_service),
    embedder: EmbeddingService = Depends(get_embedding_service),
    vector_store: VectorStoreBase = Depends(get_active_vector_store),
    visual_asset_service: VisualAssetService = Depends(get_visual_asset_service),
) -> DocumentIngestionService:
    return DocumentIngestionService(
        db=db,
        pdf_parser=pdf_parser,
        chunker=chunker,
        embedder=embedder,
        vector_store=vector_store,
        visual_asset_service=visual_asset_service,
    )


# ---------------------------------------------------------------------------
# Module 5: SQL Intelligence dependencies
# ---------------------------------------------------------------------------


def get_sql_database_service(readonly_db: Session = Depends(get_readonly_db)) -> SQLDatabaseService:
    return SQLDatabaseService(readonly_db=readonly_db)


def get_text_to_sql_service() -> TextToSQLService:
    return TextToSQLService()


# ---------------------------------------------------------------------------
# Module 3: Agentic Orchestrator dependencies
# ---------------------------------------------------------------------------


def get_supervisor_agent() -> SupervisorAgent:
    return SupervisorAgent()


def get_retrieval_agent(
    search_service: SemanticSearchService = Depends(get_semantic_search_service),
) -> RetrievalAgent:
    return RetrievalAgent(search_service=search_service)


def get_vision_agent(
    search_service: SemanticSearchService = Depends(get_semantic_search_service),
) -> VisionAgent:
    return VisionAgent(search_service=search_service)


def get_sql_agent(
    text_to_sql: TextToSQLService = Depends(get_text_to_sql_service),
    database_service: SQLDatabaseService = Depends(get_sql_database_service),
) -> SQLAgent:
    return SQLAgent(text_to_sql=text_to_sql, database_service=database_service)


def get_response_synthesizer() -> ResponseSynthesizer:
    return ResponseSynthesizer()


@lru_cache(maxsize=1)
def get_checkpoint_saver() -> MemorySaver:
    """Process-wide singleton checkpointer so conversation state and
    execution history persist across requests that share a `thread_id`.
    """
    return MemorySaver()


# ---------------------------------------------------------------------------
# Module 6: Guardrails, Evaluation & Observability dependencies
# ---------------------------------------------------------------------------


def get_input_guardrail_service() -> InputGuardrailService:
    return InputGuardrailService()


def get_output_guardrail_service() -> OutputGuardrailService:
    return OutputGuardrailService()


@lru_cache(maxsize=1)
def get_metrics_service() -> MetricsService:
    """Process-wide singleton so metrics accumulate across requests."""
    return MetricsService()


@lru_cache(maxsize=1)
def get_evaluation_history_store() -> EvaluationHistoryStore:
    """Process-wide singleton so evaluation reports accumulate across requests."""
    return EvaluationHistoryStore()


def get_evaluation_service() -> EvaluationService:
    return EvaluationService()


def get_orchestrator_service(
    supervisor: SupervisorAgent = Depends(get_supervisor_agent),
    retrieval_agent: RetrievalAgent = Depends(get_retrieval_agent),
    vision_agent: VisionAgent = Depends(get_vision_agent),
    sql_agent: SQLAgent = Depends(get_sql_agent),
    synthesizer: ResponseSynthesizer = Depends(get_response_synthesizer),
    input_guardrail: InputGuardrailService = Depends(get_input_guardrail_service),
    output_guardrail: OutputGuardrailService = Depends(get_output_guardrail_service),
    checkpointer: MemorySaver = Depends(get_checkpoint_saver),
    metrics_service: MetricsService = Depends(get_metrics_service),
    evaluation_service: EvaluationService = Depends(get_evaluation_service),
    evaluation_history: EvaluationHistoryStore = Depends(get_evaluation_history_store),
) -> OrchestratorService:
    graph = build_orchestrator_graph(
        supervisor=supervisor,
        retrieval_agent=retrieval_agent,
        vision_agent=vision_agent,
        sql_agent=sql_agent,
        synthesizer=synthesizer,
        input_guardrail=input_guardrail,
        output_guardrail=output_guardrail,
        checkpointer=checkpointer,
    )
    return OrchestratorService(
        graph=graph,
        metrics_service=metrics_service,
        evaluation_service=evaluation_service,
        evaluation_history=evaluation_history,
    )
