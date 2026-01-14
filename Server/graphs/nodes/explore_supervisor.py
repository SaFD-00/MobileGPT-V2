"""Supervisor node for routing decisions in the explore graph."""

from typing import Any

from graphs.state import ExploreState
from utils.utils import log


def explore_supervisor_node(state: ExploreState) -> dict:
    """Explore supervisor node: decide which agent to call next.

    Implements the routing logic for the explore graph:
    1. page_index == -1 -> discover (need to search screen)
    2. is_new_screen == True -> discover (new screen to learn)
    3. Otherwise -> explore_action (determine next action)
    4. action != None -> END (action ready)
    5. Exploration complete -> FINISH

    Args:
        state: Current explore state

    Returns:
        dict: Updated state with next_agent routing decision
    """
    page_index = state.get("page_index", -1)
    is_new_screen = state.get("is_new_screen", False)
    action = state.get("action")
    status = state.get("status", "")

    log(f":::EXPLORE_SUPERVISOR::: page={page_index}, is_new={is_new_screen}, status={status}", "magenta")

    # Check for terminal states
    if status == "exploration_complete":
        log(":::EXPLORE_SUPERVISOR::: Exploration complete -> FINISH", "green")
        return {
            "next_agent": "FINISH",
        }

    # Action ready - end exploration iteration
    if action is not None:
        log(f":::EXPLORE_SUPERVISOR::: Action ready -> END", "green")
        return {
            "next_agent": "END",
        }

    # Need to discover screen
    if page_index < 0:
        log(":::EXPLORE_SUPERVISOR::: Page unknown -> discover", "blue")
        return {
            "next_agent": "discover",
        }

    # New screen needs learning
    if is_new_screen:
        log(":::EXPLORE_SUPERVISOR::: New screen -> discover", "blue")
        return {
            "next_agent": "discover",
        }

    # Ready to determine action
    log(":::EXPLORE_SUPERVISOR::: Ready for action -> explore_action", "blue")
    return {
        "next_agent": "explore_action",
    }
