"""LangGraph task graph for subtask selection and verification.

Extended with Subtask Path Planning and Adaptive Replanning.
"""

from typing import Literal

from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import MemorySaver

from graphs.state import TaskState
from graphs.nodes.supervisor import supervisor_node
from graphs.nodes.memory_node import memory_node
from graphs.nodes.planner_node import planner_node
from graphs.nodes.selector_node import selector_node
from graphs.nodes.verifier_node import verifier_node
from graphs.nodes.deriver_node import deriver_node


def route_next_agent(state: TaskState) -> Literal["memory", "planner", "selector", "verifier", "deriver", "FINISH"]:
    """Route to the next agent based on state.

    Args:
        state: Current task state

    Returns:
        str: Name of the next node to execute
    """
    next_agent = state.get("next_agent", "memory")

    # Map FINISH to END
    if next_agent == "FINISH":
        return "FINISH"

    return next_agent


def build_task_graph() -> StateGraph:
    """Build the task workflow graph.

    Graph structure (6-step process):
        START -> supervisor -> (conditional routing)
                    |
                    ├── memory -> supervisor      # Page matching, Subtask Graph loading
                    ├── planner -> supervisor     # [NEW] Path planning
                    ├── selector -> supervisor    # [MODIFIED] planned_path-based selection
                    ├── verifier -> supervisor    # [EXTENDED] Adaptive Replanning
                    ├── deriver -> END            # Action derivation
                    └── FINISH -> END

    Flow:
        1. supervisor decides next agent
        2. memory: load page/state and available subtasks
        3. planner: plan optimal subtask path using Subtask Graph
           - If Subtask Graph has path: create planned_path
           - If no path: fallback to selector
        4. selector: select subtask from planned_path or use LLM
        5. verifier: verify selected subtask
           - PROCEED: continue to deriver
           - SKIP: jump ahead in path
           - REPLAN: trigger replanning
        6. deriver: derive concrete action and END

    Returns:
        StateGraph: Compiled task graph
    """
    graph = StateGraph(TaskState)

    # Add nodes (including new planner node)
    graph.add_node("supervisor", supervisor_node)
    graph.add_node("memory", memory_node)
    graph.add_node("planner", planner_node)  # Path planning
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
            "planner": "planner",  # NEW: planner routing
            "selector": "selector",
            "verifier": "verifier",
            "deriver": "deriver",
            "FINISH": END,
        }
    )

    # All agents return to supervisor for next routing decision
    graph.add_edge("memory", "supervisor")
    graph.add_edge("planner", "supervisor")  # NEW: planner -> supervisor
    graph.add_edge("selector", "supervisor")
    graph.add_edge("verifier", "supervisor")

    # Deriver goes directly to END (final action derived)
    graph.add_edge("deriver", END)

    return graph


def compile_task_graph(checkpointer: bool = True):
    """Compile the task graph.

    Args:
        checkpointer: Whether to use memory checkpointer for state persistence

    Returns:
        Compiled graph ready for execution
    """
    graph = build_task_graph()
    memory = MemorySaver() if checkpointer else None

    return graph.compile(checkpointer=memory)
