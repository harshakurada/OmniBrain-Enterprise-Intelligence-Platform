import operator
from typing import Annotated, Any, Dict, List, Optional, TypedDict


class AgentState(TypedDict, total=False):
    """Shared state threaded through every node of the orchestrator graph.

    Fields written by exactly one node (e.g. `intent`, `retrieval_results`)
    use LangGraph's default last-write-wins behavior. `execution_trace` and
    `errors` are written by multiple nodes -- including nodes that run in
    parallel during Retrieval/Vision/SQL fan-out -- so they use an
    `operator.add` reducer to accumulate across the whole run instead of
    overwriting each other.
    """

    query: str
    document_id: Optional[int]
    top_k: int
    intent: str
    agents_to_invoke: List[str]
    routing_reasoning: str
    retrieval_results: List[Dict[str, Any]]
    vision_result: Optional[Dict[str, Any]]
    sql_result: Optional[Dict[str, Any]]
    final_response: str
    citations: List[Dict[str, Any]]
    execution_trace: Annotated[List[Dict[str, Any]], operator.add]
    errors: Annotated[List[str], operator.add]
    input_guardrail: Optional[Dict[str, Any]]
    output_guardrail: Optional[Dict[str, Any]]
    blocked: bool
