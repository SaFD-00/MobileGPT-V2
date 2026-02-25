"""Discover node for screen discovery and new page registration."""

from typing import Any, List, Optional

from agents import history_agent, summary_agent
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
    screenshot_path = state.get("screenshot_path")  # For Vision API
    visited_pages = state.get("visited_pages", set())
    explored_subtasks = state.get("explored_subtasks", {})
    last_action_was_back = state.get("last_action_was_back", False)

    log(f":::DISCOVER::: visited_pages = {visited_pages}", "yellow")
    log(f":::DISCOVER::: explored_subtasks = {explored_subtasks}", "yellow")

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
            screenshot_path=screenshot_path  # Utilize Vision API
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

            # Subtask Graph: Add transition edge
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
            log(f":::DISCOVER::: Added Subtask Graph transition: {last_explored_page} -> {page_index} via '{last_explored_subtask}'", "cyan")

            # Subtask Graph: Generate descriptions for action history
            # (guideline is already generated at exploration time in explore_action_node)
            action_history = state.get("action_history", [])
            if action_history:
                log(f":::DISCOVER::: Processing {len(action_history)} actions for description generation", "cyan")
                _process_action_history(
                    action_history=action_history,
                    after_xml=current_xml,
                    after_screenshot_path=screenshot_path,
                    memory=memory,
                    page_index=last_explored_page,
                    subtask_name=last_explored_subtask,
                    trigger_ui_index=last_explored_ui
                )

    # Update state subtask_graph when a new transition is added
    new_subtask_graph = state.get("subtask_graph", {})
    if last_explored_page is not None and last_explored_subtask and not last_action_was_back:
        new_subtask_graph = new_subtask_graph.copy()
        if last_explored_page not in new_subtask_graph:
            new_subtask_graph[last_explored_page] = []
        if (page_index, last_explored_subtask) not in new_subtask_graph[last_explored_page]:
            new_subtask_graph[last_explored_page].append((page_index, last_explored_subtask))

    # Update state back_edges when a back action was performed
    new_back_edges = state.get("back_edges", {})
    last_back_from = state.get("last_back_from_page")
    if last_action_was_back and last_back_from is not None:
        new_back_edges = new_back_edges.copy()
        if last_back_from not in new_back_edges:
            new_back_edges[last_back_from] = []
        if page_index not in new_back_edges[last_back_from]:
            new_back_edges[last_back_from].append(page_index)
            log(f":::DISCOVER::: Added back_edge: {last_back_from} -> {page_index}", "cyan")

    # Initialize page manager
    memory.init_page_manager(page_index)

    # Check if this is a new page
    is_new = page_index not in visited_pages

    # Clear last explored info after processing
    clear_last_explored = {
        "last_explored_page_index": None,
        "last_explored_subtask_name": None,
        "last_explored_ui_index": None,
        "last_back_from_page": None,
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

        # Subtask Graph: Generate page summary for new pages
        try:
            page_summary = summary_agent.generate_summary(
                encoded_xml=encoded_xml,
                available_subtasks=available_subtasks,
                screenshot_path=screenshot_path
            )
            memory.update_page_summary(page_index, page_summary)
            log(f":::DISCOVER::: Generated summary for page {page_index}: {page_summary[:50]}...", "green")
        except Exception as e:
            log(f":::DISCOVER::: Error generating page summary: {e}", "red")

        return {
            "page_index": page_index,
            "is_new_screen": False,  # We've now processed it
            "visited_pages": new_visited,
            "unexplored_subtasks": new_unexplored,
            "subtask_graph": new_subtask_graph,
            "back_edges": new_back_edges,
            "status": "page_discovered",
            "next_agent": "explore_action",
            "action_history": [],  # Subtask Graph: Reset after processing
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
        "subtask_graph": new_subtask_graph,
        "back_edges": new_back_edges,
        "status": "page_found",
        "next_agent": "explore_action",
        "action_history": [],  # Subtask Graph: Reset after processing
        **clear_last_explored,
    }


def _process_action_history(
    action_history: List[dict],
    after_xml: str,
    after_screenshot_path: Optional[str],
    memory: Any,
    page_index: int,
    subtask_name: str,
    trigger_ui_index: int
) -> None:
    """Process action history to generate descriptions.

    Guideline is already generated at exploration time (explore_action_node).
    This function only generates descriptions using before/after XML comparison.

    For each action in history:
    1. Generate description using HistoryAgent (what changed)
    2. Save to memory via update_action_description (preserving existing guideline)

    Args:
        action_history: List of action entries with before_xml, before_screenshot, action
        after_xml: XML state after the last action (current screen)
        after_screenshot_path: Screenshot path after the last action
        memory: Memory instance for saving descriptions
        page_index: Page where the subtask started
        subtask_name: Name of the completed subtask
        trigger_ui_index: Trigger UI index of the subtask
    """
    if action_history and not action_history[0].get("before_xml"):
        log(":::DISCOVER::: Warning: first action missing before_xml, skipping history generation", "yellow")
        return

    for i, entry in enumerate(action_history):
        before_xml = entry.get("before_xml", "")
        before_screenshot = entry.get("before_screenshot")
        action = entry.get("action", {})
        step = entry.get("step", i)

        # Determine after state for this action
        # If this is the last action, use the final after_xml
        # Otherwise, use the next action's before_xml
        if i < len(action_history) - 1:
            current_after_xml = action_history[i + 1].get("before_xml", "")
            current_after_screenshot = action_history[i + 1].get("before_screenshot")
        else:
            current_after_xml = after_xml
            current_after_screenshot = after_screenshot_path

        try:
            # Generate description (what changed)
            # Generate description (what changed after action)
            description = history_agent.generate_description(
                before_xml=before_xml,
                after_xml=current_after_xml,
                action=action,
                before_screenshot_path=before_screenshot,
                after_screenshot_path=current_after_screenshot
            )
            log(f":::DISCOVER::: Generated description for step {step}: {description[:50]}...", "green")

            # Save description only (guideline is already set at exploration time)
            memory.update_action_description(
                page_index=page_index,
                subtask_name=subtask_name,
                trigger_ui_index=trigger_ui_index,
                step=step,
                description=description,
                guideline=""  # empty string preserves existing guideline
            )

        except Exception as e:
            log(f":::DISCOVER::: Error generating description for step {step}: {e}", "red")
