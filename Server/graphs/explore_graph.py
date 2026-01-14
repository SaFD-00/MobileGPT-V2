"""LangGraph explore graph for automatic app exploration."""

from typing import Literal

from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import MemorySaver

from graphs.state import ExploreState
from graphs.nodes.explore_supervisor import explore_supervisor_node
from graphs.nodes.discover_node import discover_node
from graphs.nodes.explore_action_node import explore_action_node


def route_explore(state: ExploreState) -> Literal["discover", "explore_action", "END", "FINISH"]:
    """Route to the next node based on state.

    Args:
        state: Current explore state

    Returns:
        str: Name of the next node to execute
    """
    next_agent = state.get("next_agent", "discover")

    if next_agent == "FINISH":
        return "FINISH"
    if next_agent == "END":
        return "END"

    return next_agent


def build_explore_graph() -> StateGraph:
    """Build the explore workflow graph.

    Graph structure:
        START -> supervisor -> (conditional routing)
                    |
                    ├── discover -> supervisor
                    ├── explore_action -> (conditional)
                    │       ├── END (action ready)
                    │       └── supervisor (continue)
                    └── FINISH -> END

    Flow:
        1. supervisor decides next agent based on page state
        2. discover: find/learn current screen
        3. explore_action: determine next exploration action
           - Returns action to execute
           - Or returns to supervisor for more exploration
        4. When action is ready, END to return result
        5. When exploration complete, FINISH

    Returns:
        StateGraph: Compiled explore graph
    """
    graph = StateGraph(ExploreState)

    # Add nodes
    graph.add_node("supervisor", explore_supervisor_node)
    graph.add_node("discover", discover_node)
    graph.add_node("explore_action", explore_action_node)

    # Start with supervisor
    graph.add_edge(START, "supervisor")

    # Supervisor routes to appropriate node
    graph.add_conditional_edges(
        "supervisor",
        route_explore,
        {
            "discover": "discover",
            "explore_action": "explore_action",
            "END": END,
            "FINISH": END,
        }
    )

    # Discover returns to explore_action or ends
    graph.add_conditional_edges(
        "discover",
        route_explore,
        {
            "discover": "discover",  # Allow self-loop if re-discovery needed
            "explore_action": "explore_action",
            "END": END,
            "FINISH": END,
        }
    )

    # Explore action can end or continue
    graph.add_conditional_edges(
        "explore_action",
        route_explore,
        {
            "END": END,
            "FINISH": END,
            "explore_action": "explore_action",  # For navigation re-entry
        }
    )

    return graph


def compile_explore_graph(checkpointer: bool = True):
    """Compile the explore graph.

    Args:
        checkpointer: Whether to use memory checkpointer for state persistence

    Returns:
        Compiled graph ready for execution
    """
    graph = build_explore_graph()
    memory = MemorySaver() if checkpointer else None

    return graph.compile(checkpointer=memory)
