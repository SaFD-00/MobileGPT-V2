"""Supervisor node for routing decisions in the explore graph."""

from graphs.state import ExploreState
from loguru import logger


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

    logger.debug(f"page={page_index}, is_new={is_new_screen}, status={status}")

    # Check for terminal states
    if status == "exploration_complete":
        logger.info("Exploration complete -> FINISH")
        return {
            "next_agent": "FINISH",
        }

    # Action ready - end exploration iteration
    if action is not None:
        logger.info(f"Action ready -> END")
        return {
            "next_agent": "END",
        }

    # Need to discover screen
    if page_index < 0:
        logger.info("Page unknown -> discover")
        return {
            "next_agent": "discover",
        }

    # New screen needs learning
    if is_new_screen:
        logger.info("New screen -> discover")
        return {
            "next_agent": "discover",
        }

    # Ready to determine action
    logger.info("Ready for action -> explore_action")
    return {
        "next_agent": "explore_action",
    }
