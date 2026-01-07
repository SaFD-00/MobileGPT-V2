"""LangGraph inference graph for subtask selection and verification."""

from typing import Literal

from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import MemorySaver

from inference.schemas.state import InferenceState
from inference.agents.supervisor import supervisor_node
from inference.agents.memory_agent import memory_node
from inference.agents.selector import selector_node
from inference.agents.verifier import verifier_node
from inference.agents.deriver import deriver_node


def route_next_agent(state: InferenceState) -> Literal["memory", "selector", "verifier", "deriver", "FINISH"]:
    """Route to the next agent based on state.

    Args:
        state: Current inference state

    Returns:
        str: Name of the next node to execute
    """
    next_agent = state.get("next_agent", "memory")

    # Map FINISH to END
    if next_agent == "FINISH":
        return "FINISH"

    return next_agent


def build_inference_graph() -> StateGraph:
    """Build the inference workflow graph.

    Graph structure:
        START -> supervisor -> (conditional routing)
                    |
                    ├── memory -> supervisor
                    ├── selector -> supervisor
                    ├── verifier -> supervisor
                    ├── deriver -> END
                    └── FINISH -> END

    Flow:
        1. supervisor decides next agent
        2. memory: load page/state and available subtasks
        3. selector: select best subtask (excluding rejected ones)
        4. verifier: verify if selected subtask leads to good path
           - If rejected: back to selector (via supervisor)
           - If approved: proceed to deriver
        5. deriver: derive concrete action and END

    Returns:
        StateGraph: Compiled inference graph
    """
    graph = StateGraph(InferenceState)

    # Add nodes
    graph.add_node("supervisor", supervisor_node)
    graph.add_node("memory", memory_node)
    graph.add_node("selector", selector_node)
    graph.add_node("verifier", verifier_node)
    graph.add_node("deriver", deriver_node)

    # Start with supervisor
    graph.add_edge(START, "supervisor")

    # Supervisor routes to appropriate agent
    graph.add_conditional_edges(
        "supervisor",
        route_next_agent,
        {
            "memory": "memory",
            "selector": "selector",
            "verifier": "verifier",
            "deriver": "deriver",
            "FINISH": END,
        }
    )

    # All agents return to supervisor for next routing decision
    graph.add_edge("memory", "supervisor")
    graph.add_edge("selector", "supervisor")
    graph.add_edge("verifier", "supervisor")

    # Deriver goes directly to END (final action derived)
    graph.add_edge("deriver", END)

    return graph


def compile_graph(checkpointer: bool = True):
    """Compile the inference graph.

    Args:
        checkpointer: Whether to use memory checkpointer for state persistence

    Returns:
        Compiled graph ready for execution
    """
    graph = build_inference_graph()
    memory = MemorySaver() if checkpointer else None

    return graph.compile(checkpointer=memory)
