import logging
import time
from typing import Any, Dict, List, Optional
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph
from backend.app.agents.retrieval_agent import RetrievalAgent
from backend.app.agents.sql_agent import SQLAgent
from backend.app.agents.state import AgentState
from backend.app.agents.supervisor_agent import SupervisorAgent
from backend.app.agents.synthesizer_agent import ResponseSynthesizer
from backend.app.agents.vision_agent import VisionAgent
from backend.app.guardrails.input_guardrail import InputGuardrailService
from backend.app.guardrails.output_guardrail import OutputGuardrailService

logger = logging.getLogger("omnibrain.agents.graph")

AGENT_NODE_NAMES = ["retrieval_agent", "vision_agent", "sql_agent"]


def _trace_entry(agent: str, action: str, status: str, detail: str, started_at: float) -> Dict[str, Any]:
    return {
        "agent": agent,
        "action": action,
        "status": status,
        "detail": detail,
        "duration_ms": round((time.perf_counter() - started_at) * 1000, 2),
    }


def build_orchestrator_graph(
    supervisor: SupervisorAgent,
    retrieval_agent: RetrievalAgent,
    vision_agent: VisionAgent,
    sql_agent: SQLAgent,
    synthesizer: ResponseSynthesizer,
    input_guardrail: Optional[InputGuardrailService] = None,
    output_guardrail: Optional[OutputGuardrailService] = None,
    checkpointer: Optional[BaseCheckpointSaver] = None,
) -> CompiledStateGraph:
    """Builds and compiles the orchestrator workflow:

    START -> guardrails_input -> [blocked? -> guardrails_output -> END]
                                -> supervisor -> conditional routing ->
    {retrieval_agent, vision_agent, sql_agent} -> synthesizer ->
    guardrails_output -> END

    Retrieval/Vision/SQL agents fan out in parallel based on the Supervisor's
    routing decision and fan back in at the Response Synthesizer. Each node
    is defensive: an agent failure is captured in `errors`/`execution_trace`
    rather than aborting the whole run, so the graph always reaches a
    (possibly degraded) final response. The Input Guardrail (Module 6) runs
    before any agent so unsafe queries never reach an LLM; the Output
    Guardrail always runs last to score the final response's grounding.

    `input_guardrail`/`output_guardrail` default to real (but fully offline,
    regex-based) service instances when not supplied, so existing callers
    that don't pass them keep working unchanged.
    """
    input_guardrail = input_guardrail or InputGuardrailService()
    output_guardrail = output_guardrail or OutputGuardrailService()

    def guardrails_input_node(state: AgentState) -> Dict[str, Any]:
        started = time.perf_counter()
        try:
            result = input_guardrail.check(state["query"])
            if not result.passed:
                trace = _trace_entry(
                    "guardrails_input", "input_safety_check", "blocked", result.reason or "blocked", started
                )
                return {
                    "input_guardrail": result.model_dump(),
                    "blocked": True,
                    "final_response": "This request was blocked by safety guardrails and cannot be processed.",
                    "citations": [],
                    "execution_trace": [trace],
                }
            trace = _trace_entry(
                "guardrails_input", "input_safety_check", "success", f"risk_level={result.risk_level}", started
            )
            return {"input_guardrail": result.model_dump(), "blocked": False, "execution_trace": [trace]}
        except Exception as exc:
            logger.exception("Input guardrail check failed; failing open (allowing the request through).")
            trace = _trace_entry("guardrails_input", "input_safety_check", "error", str(exc), started)
            return {"blocked": False, "execution_trace": [trace], "errors": [f"guardrails_input: {exc}"]}

    def route_after_guardrails_input(state: AgentState) -> str:
        return "guardrails_output" if state.get("blocked") else "supervisor"

    def guardrails_output_node(state: AgentState) -> Dict[str, Any]:
        started = time.perf_counter()
        try:
            result = output_guardrail.check(state.get("final_response", ""), state.get("citations", []))
            trace = _trace_entry("guardrails_output", "grounding_check", "success", result.notes, started)
            return {"output_guardrail": result.model_dump(), "execution_trace": [trace]}
        except Exception as exc:
            logger.exception("Output guardrail check failed.")
            trace = _trace_entry("guardrails_output", "grounding_check", "error", str(exc), started)
            return {"execution_trace": [trace], "errors": [f"guardrails_output: {exc}"]}

    def supervisor_node(state: AgentState) -> Dict[str, Any]:
        started = time.perf_counter()
        query = state["query"]
        try:
            decision = supervisor.decide(query)
            agents = [a for a in decision.agents if a in ("retrieval", "vision", "sql")] or ["retrieval"]
            trace = _trace_entry(
                "supervisor", "classify_intent", "success",
                f"intent={decision.intent}, agents={agents}", started,
            )
            return {
                "intent": decision.intent,
                "agents_to_invoke": agents,
                "routing_reasoning": decision.reasoning,
                "execution_trace": [trace],
            }
        except Exception as exc:
            logger.exception("Supervisor routing failed; defaulting to retrieval agent.")
            trace = _trace_entry("supervisor", "classify_intent", "error", str(exc), started)
            return {
                "intent": "retrieval",
                "agents_to_invoke": ["retrieval"],
                "routing_reasoning": "Fallback: routing failure, defaulted to retrieval.",
                "execution_trace": [trace],
                "errors": [f"supervisor: {exc}"],
            }

    def route_after_supervisor(state: AgentState) -> List[str]:
        agents = state.get("agents_to_invoke") or ["retrieval"]
        targets = [f"{a}_agent" for a in agents if f"{a}_agent" in AGENT_NODE_NAMES]
        return targets or ["synthesizer"]

    def retrieval_node(state: AgentState) -> Dict[str, Any]:
        started = time.perf_counter()
        try:
            results = retrieval_agent.run(
                query=state["query"], top_k=state.get("top_k", 5), document_id=state.get("document_id")
            )
            payload = [r.model_dump() for r in results]
            trace = _trace_entry(
                "retrieval_agent", "semantic_search", "success", f"{len(payload)} chunk(s) retrieved", started
            )
            return {"retrieval_results": payload, "execution_trace": [trace]}
        except Exception as exc:
            logger.exception("Retrieval agent failed.")
            trace = _trace_entry("retrieval_agent", "semantic_search", "error", str(exc), started)
            return {
                "retrieval_results": [],
                "execution_trace": [trace],
                "errors": [f"retrieval_agent: {exc}"],
            }

    def vision_node(state: AgentState) -> Dict[str, Any]:
        started = time.perf_counter()
        try:
            result = vision_agent.run(
                query=state["query"], document_id=state.get("document_id"), top_k=state.get("top_k", 5)
            )
            trace = _trace_entry("vision_agent", "analyze", "success", result.message, started)
            return {"vision_result": result.model_dump(), "execution_trace": [trace]}
        except Exception as exc:
            logger.exception("Vision agent failed.")
            trace = _trace_entry("vision_agent", "analyze", "error", str(exc), started)
            return {"vision_result": None, "execution_trace": [trace], "errors": [f"vision_agent: {exc}"]}

    def sql_node(state: AgentState) -> Dict[str, Any]:
        started = time.perf_counter()
        try:
            result = sql_agent.run(query=state["query"], document_id=state.get("document_id"))
            trace = _trace_entry("sql_agent", "analyze", "success", result.message, started)
            return {"sql_result": result.model_dump(), "execution_trace": [trace]}
        except Exception as exc:
            logger.exception("SQL agent failed.")
            trace = _trace_entry("sql_agent", "analyze", "error", str(exc), started)
            return {"sql_result": None, "execution_trace": [trace], "errors": [f"sql_agent: {exc}"]}

    def synthesizer_node(state: AgentState) -> Dict[str, Any]:
        started = time.perf_counter()
        try:
            response_text, citations = synthesizer.synthesize(
                query=state["query"],
                retrieval_results=state.get("retrieval_results", []),
                vision_result=state.get("vision_result"),
                sql_result=state.get("sql_result"),
            )
            trace = _trace_entry(
                "synthesizer", "generate_response", "success", f"{len(citations)} citation(s)", started
            )
            return {"final_response": response_text, "citations": citations, "execution_trace": [trace]}
        except Exception as exc:
            logger.exception("Response synthesis failed.")
            trace = _trace_entry("synthesizer", "generate_response", "error", str(exc), started)
            return {
                "final_response": "I encountered an error while generating a response. Please try again.",
                "citations": [],
                "execution_trace": [trace],
                "errors": [f"synthesizer: {exc}"],
            }

    graph = StateGraph(AgentState)
    graph.add_node("guardrails_input", guardrails_input_node)
    graph.add_node("supervisor", supervisor_node)
    graph.add_node("retrieval_agent", retrieval_node)
    graph.add_node("vision_agent", vision_node)
    graph.add_node("sql_agent", sql_node)
    graph.add_node("synthesizer", synthesizer_node)
    graph.add_node("guardrails_output", guardrails_output_node)

    graph.add_edge(START, "guardrails_input")
    graph.add_conditional_edges("guardrails_input", route_after_guardrails_input, ["supervisor", "guardrails_output"])
    graph.add_conditional_edges("supervisor", route_after_supervisor, AGENT_NODE_NAMES + ["synthesizer"])
    graph.add_edge("retrieval_agent", "synthesizer")
    graph.add_edge("vision_agent", "synthesizer")
    graph.add_edge("sql_agent", "synthesizer")
    graph.add_edge("synthesizer", "guardrails_output")
    graph.add_edge("guardrails_output", END)

    return graph.compile(checkpointer=checkpointer)
