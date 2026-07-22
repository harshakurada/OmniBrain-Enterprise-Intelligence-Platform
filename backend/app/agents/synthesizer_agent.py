import logging
from typing import Any, Dict, List, Optional, Tuple
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from backend.app.config.settings import settings

logger = logging.getLogger("omnibrain.agents.synthesizer")

_SYSTEM_PROMPT = (
    "You are the Response Synthesizer of the OmniBrain multi-agent orchestrator. "
    "Answer the user's question using ONLY the provided context excerpts. "
    "Do not invent facts that are not present in the context. "
    "If the context does not contain enough information to answer, say so plainly. "
    "Keep the answer concise and reference sources inline as [filename p.page_number] for "
    "document excerpts, or as [OmniBrain Database] for structured database query results. "
    "Clearly distinguish database-derived information from document excerpts."
)

_DATABASE_CITATION_FILENAME = "OmniBrain Database"


class ResponseSynthesizer:
    """Combines Retrieval / Vision / SQL agent outputs into a single,
    citation-grounded final response.

    Vision Agent hits are shaped identically to Retrieval Agent hits (both
    are `SemanticSearchResult`-derived dicts), so they are merged into the
    same list before deduplication, context-building, and citation
    generation -- giving multi-modal (text + image + table) grounding for
    free through the existing single-pass pipeline. SQL Agent output has no
    document/page of its own, so it is kept as a separate context block and
    a distinct `chunk_type="database"` citation, clearly marking it as
    database-derived rather than a document excerpt.
    """

    def __init__(self, llm: Optional[BaseChatModel] = None):
        self.llm = llm or ChatOpenAI(
            model=settings.OPENAI_MODEL, api_key=settings.OPENAI_API_KEY, temperature=0.2,
            timeout=settings.LLM_REQUEST_TIMEOUT_SECONDS, max_retries=settings.LLM_MAX_RETRIES,
        )

    def synthesize(
        self,
        query: str,
        retrieval_results: List[Dict[str, Any]],
        vision_result: Optional[Dict[str, Any]] = None,
        sql_result: Optional[Dict[str, Any]] = None,
    ) -> Tuple[str, List[Dict[str, Any]]]:
        """Returns `(final_response_text, citations)` for the given agent outputs."""
        combined_results = list(retrieval_results)
        if vision_result and vision_result.get("status") == "success" and vision_result.get("data"):
            combined_results.extend(vision_result["data"].get("results", []))

        deduped = self._deduplicate(combined_results)

        sql_data = sql_result.get("data") if sql_result and sql_result.get("status") == "success" else None
        sql_context = self._format_sql_context(sql_data) if sql_data else None

        if not deduped and not sql_context:
            message = "I couldn't find grounded information in the ingested documents to answer that."
            note = self._placeholder_note(vision_result, sql_result)
            if note:
                message = f"{message} {note}"
            return message, []

        context_parts = []
        if deduped:
            context_parts.append(self._build_context(deduped))
        if sql_context:
            context_parts.append(sql_context)
        context = "\n\n".join(context_parts)

        try:
            ai_message = self.llm.invoke(
                [
                    SystemMessage(content=_SYSTEM_PROMPT),
                    HumanMessage(content=f"Context:\n{context}\n\nQuestion: {query}"),
                ]
            )
            response_text = ai_message.content
        except Exception:
            logger.exception("Response synthesis LLM call failed; returning extractive fallback.")
            response_text = self._extractive_fallback(deduped) if deduped else (
                f"(Generation temporarily unavailable -- showing the database query result.)\n{sql_context}"
            )

        citations = [
            {
                "document_id": r["document_id"],
                "filename": r["filename"],
                "page_number": r["page_number"],
                "chunk_index": r["chunk_index"],
                "similarity_score": r["score"],
                "chunk_type": r.get("chunk_type", "text"),
            }
            for r in deduped
        ]
        if sql_data:
            citations.append(
                {
                    "document_id": 0,
                    "filename": _DATABASE_CITATION_FILENAME,
                    "page_number": 0,
                    "chunk_index": 0,
                    "similarity_score": 1.0,
                    "chunk_type": "database",
                }
            )
        return response_text, citations

    @staticmethod
    def _deduplicate(results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Removes duplicate chunks (same document/page/chunk) while
        preserving the original relevance ordering.
        """
        seen = set()
        deduped: List[Dict[str, Any]] = []
        for r in results:
            key = (r.get("document_id"), r.get("page_number"), r.get("chunk_index"))
            if key in seen:
                continue
            seen.add(key)
            deduped.append(r)
        return deduped

    @staticmethod
    def _build_context(results: List[Dict[str, Any]]) -> str:
        def _label(r: Dict[str, Any]) -> str:
            modality = r.get("chunk_type", "text")
            suffix = f" | {modality}" if modality != "text" else ""
            return f"[{r['filename']} p.{r['page_number']}{suffix}]"

        return "\n\n".join(f"{_label(r)} {r['content']}" for r in results)

    @staticmethod
    def _extractive_fallback(results: List[Dict[str, Any]]) -> str:
        top = results[0]
        return (
            "(Generation temporarily unavailable -- showing the most relevant excerpt.)\n"
            f"[{top['filename']} p.{top['page_number']}] {top['content']}"
        )

    @staticmethod
    def _format_sql_context(sql_data: Dict[str, Any]) -> str:
        """Renders a SQL Agent result's rows as a Markdown table, labeled so
        the LLM (and downstream citation) can clearly attribute it to the
        structured database rather than a document excerpt.
        """
        columns = sql_data.get("columns", [])
        rows = sql_data.get("rows", [])
        sql = sql_data.get("sql", "")
        if not rows or not columns:
            return ""

        preview = rows[:20]
        header = "| " + " | ".join(columns) + " |"
        separator = "| " + " | ".join(["---"] * len(columns)) + " |"
        body = "\n".join("| " + " | ".join(str(row.get(c, "")) for c in columns) + " |" for row in preview)
        table = "\n".join([header, separator, body])
        return f"[{_DATABASE_CITATION_FILENAME}]\nSQL: {sql}\n{table}"

    @staticmethod
    def _placeholder_note(vision_result: Optional[Dict[str, Any]], sql_result: Optional[Dict[str, Any]]) -> str:
        notes = []
        if vision_result and vision_result.get("status") == "no_visual_content":
            notes.append("No relevant visual content was found either.")
        if sql_result:
            sql_status = sql_result.get("status")
            if sql_status == "unanswerable":
                notes.append("The question could not be answered from the structured database either.")
            elif sql_status == "no_results":
                notes.append("A database query ran successfully but returned no matching rows.")
            elif sql_status == "error":
                notes.append("A database query was attempted but failed.")
        return " ".join(notes)
