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
    screenshot_path = state.get("screenshot_path")  # Vision API용
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
            encoded_xml, hierarchy_xml, current_xml,
            screenshot_path=screenshot_path  # Vision API 활용
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

            # UICompass: Update STG with new transition
            # Get action sequence from the last explored action
            last_action = state.get("last_explored_action")
            action_sequence = [last_action] if last_action else []

            memory.add_transition(
                from_page=last_explored_page,
                to_page=page_index,
                subtask_name=last_explored_subtask,
                trigger_ui_index=last_explored_ui,
                action_sequence=action_sequence
            )
            log(f":::DISCOVER::: Added STG transition: {last_explored_page} -> {page_index} via '{last_explored_subtask}'", "cyan")

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

        # Initialize unexplored_subtasks for GREEDY algorithms
        new_unexplored = state.get("unexplored_subtasks", {}).copy()
        available_subtasks = memory.get_available_subtasks(page_index)
        new_unexplored[page_index] = available_subtasks
        log(f":::DISCOVER::: Initialized {len(available_subtasks)} unexplored subtasks for page {page_index}", "cyan")

        return {
            "page_index": page_index,
            "is_new_screen": False,  # We've now processed it
            "visited_pages": new_visited,
            "unexplored_subtasks": new_unexplored,
            "status": "page_discovered",
            "next_agent": "explore_action",
            **clear_last_explored,
        }

    log(f":::DISCOVER::: Existing page {page_index}", "blue")

    # Initialize unexplored_subtasks if not present (for GREEDY algorithms)
    unexplored_subtasks = state.get("unexplored_subtasks", {})
    if page_index not in unexplored_subtasks:
        new_unexplored = unexplored_subtasks.copy()
        available_subtasks = memory.get_available_subtasks(page_index)
        explored_subtasks = state.get("explored_subtasks", {})
        explored_set = set(explored_subtasks.get(page_index, []))
        unexplored_list = [
            s for s in available_subtasks
            if (s.get("name"), s.get("trigger_ui_index", -1)) not in explored_set
        ]
        new_unexplored[page_index] = unexplored_list
        log(f":::DISCOVER::: Initialized {len(unexplored_list)} unexplored subtasks for existing page {page_index}", "cyan")
    else:
        new_unexplored = unexplored_subtasks

    return {
        "page_index": page_index,
        "is_new_screen": False,
        "unexplored_subtasks": new_unexplored,
        "status": "page_found",
        "next_agent": "explore_action",
        **clear_last_explored,
    }
