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

    # Initialize page manager
    memory.init_page_manager(page_index)

    # Check if this is a new page
    is_new = page_index not in visited_pages

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
        }

    log(f":::DISCOVER::: Existing page {page_index}", "blue")

    return {
        "page_index": page_index,
        "is_new_screen": False,
        "status": "page_found",
        "next_agent": "explore_action",
    }
