"""Discover node for screen discovery and new page registration."""

from typing import Any

from graphs.state import ExploreState
from utils.utils import log


def discover_node(state: ExploreState) -> dict:
    """Discover node: search page and learn new screens.

    Handles:
    1. memory.search_node() to find current page
    2. explore_agent.explore() for new screens
    3. Updating visited_pages set
    4. Updating end_page for last explored subtask

    Args:
        state: Current explore state

    Returns:
        dict: Updated state with page_index, is_new_screen
    """
    memory = state["memory"]
    explore_agent = state["explore_agent"]
    current_xml = state["current_xml"]
    hierarchy_xml = state.get("hierarchy_xml", "")
    encoded_xml = state.get("encoded_xml", "")
    visited_pages = state.get("visited_pages", set())
    last_action_was_back = state.get("last_action_was_back", False)

    # Get last explored info for end_page update
    last_explored_page = state.get("last_explored_page_index")
    last_explored_subtask = state.get("last_explored_subtask_name")
    last_explored_ui = state.get("last_explored_ui_index")

    log(":::DISCOVER::: Searching for page...", "blue")

    # Search for matching page
    page_index, similarity = memory.search_node(
        current_xml, hierarchy_xml, encoded_xml
    )

    if page_index < 0:
        # New screen - explore and register
        log(f":::DISCOVER::: No matching page found (similarity: {similarity}), exploring new screen", "yellow")

        explore_result = explore_agent.explore(
            encoded_xml, hierarchy_xml, current_xml
        )

        # Re-search after exploration
        page_index, similarity = memory.search_node(
            current_xml, hierarchy_xml, encoded_xml
        )

        if page_index < 0:
            log(":::DISCOVER::: Failed to register new screen", "red")
            return {
                "page_index": -1,
                "is_new_screen": False,
                "status": "discover_failed",
                "next_agent": "FINISH",
            }

    log(f":::DISCOVER::: Found page {page_index} (similarity: {similarity:.3f})", "green")

    # Update end_page for last explored subtask (if any)
    # This happens after action execution when we know the destination page
    if last_explored_page is not None and last_explored_subtask and last_explored_ui is not None:
        if not last_action_was_back:  # Don't update end_page for back actions
            memory.update_end_page(
                page_index=last_explored_page,
                subtask_name=last_explored_subtask,
                trigger_ui_index=last_explored_ui,
                end_page=page_index
            )
            log(f":::DISCOVER::: Updated end_page={page_index} for subtask '{last_explored_subtask}'", "cyan")

    # Initialize page manager
    memory.init_page_manager(page_index)

    # Check if this is a new page
    is_new = page_index not in visited_pages

    # Clear last explored info after processing
    clear_last_explored = {
        "last_explored_page_index": None,
        "last_explored_subtask_name": None,
        "last_explored_ui_index": None,
    }

    if is_new:
        log(f":::DISCOVER::: New page {page_index}, will register subtasks", "cyan")
        # Add to visited set
        new_visited = visited_pages.copy()
        new_visited.add(page_index)

        return {
            "page_index": page_index,
            "is_new_screen": False,  # We've now processed it
            "visited_pages": new_visited,
            "status": "page_discovered",
            "next_agent": "explore_action",
            **clear_last_explored,
        }

    log(f":::DISCOVER::: Existing page {page_index}", "blue")

    return {
        "page_index": page_index,
        "is_new_screen": False,
        "status": "page_found",
        "next_agent": "explore_action",
        **clear_last_explored,
    }
