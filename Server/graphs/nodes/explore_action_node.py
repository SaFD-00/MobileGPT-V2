"""Explore action node with 3 exploration algorithms.

Algorithms:
- DFS: Stack-based depth-first exploration with backtracking
- BFS: Queue-based breadth-first exploration
- GREEDY: App-wide shortest path to nearest unexplored (action-based distance)
          Inspired by LLM-Explorer's App-wide Action Selector concept.
"""

import re
import xml.etree.ElementTree as ET
from typing import Any, Dict, List, Optional, Tuple

from agents import history_agent
from graphs.state import ExploreState
from utils.utils import log


def _add_to_action_history(
    state: ExploreState,
    action: dict
) -> List[dict]:
    """Add action entry to history for action description generation.

    Args:
        state: Current explore state (contains before_xml, before_screenshot_path)
        action: The action being executed

    Returns:
        Updated action_history list
    """
    action_history = state.get("action_history", []).copy()
    action_entry = {
        "step": len(action_history),
        "before_xml": state.get("before_xml") or state.get("current_xml", ""),
        "before_screenshot": state.get("before_screenshot_path") or state.get("screenshot_path"),
        "action": action,
    }
    action_history.append(action_entry)
    return action_history


def _generate_and_save_guideline(
    memory: Any,
    page_index: int,
    subtask_name: str,
    trigger_ui_index: int,
    action: dict,
    current_xml: str
) -> None:
    """Generate HOW-to guideline at exploration time and save to actions.csv + subtasks.csv."""
    try:
        guideline = history_agent.generate_guidance(
            action=action,
            screen_xml=current_xml
        )
        if guideline:
            memory.update_action_description(
                page_index=page_index,
                subtask_name=subtask_name,
                trigger_ui_index=trigger_ui_index,
                step=0,
                description="",
                guideline=guideline
            )
            memory.update_guideline(
                page_index=page_index,
                subtask_name=subtask_name,
                trigger_ui_index=trigger_ui_index
            )
            log(f":::EXPLORE::: Generated guideline for '{subtask_name}': {guideline[:50]}...", "green")
    except Exception as e:
        log(f":::EXPLORE::: Error generating guideline for '{subtask_name}': {e}", "red")


def _ensure_unexplored_subtasks(
    unexplored_subtasks: Dict,
    explored_subtasks: Dict,
    page_index: int,
    memory: Any
) -> Dict:
    """Ensure unexplored_subtasks contains entries for the current page.

    This is a defensive fallback for GREEDY algorithms in case
    discover_node didn't initialize unexplored_subtasks properly.

    Args:
        unexplored_subtasks: Current unexplored subtasks dict
        explored_subtasks: Current explored subtasks dict
        page_index: Current page index
        memory: Memory instance

    Returns:
        Dict: Updated unexplored_subtasks with current page initialized
    """
    if page_index in unexplored_subtasks:
        return unexplored_subtasks

    new_unexplored = unexplored_subtasks.copy()
    available = memory.get_available_subtasks(page_index)
    explored_set = set(explored_subtasks.get(page_index, []))
    new_unexplored[page_index] = [
        s for s in available
        if (s.get("name"), s.get("trigger_ui_index", -1)) not in explored_set
    ]
    log(f":::EXPLORE_ACTION::: Defensive init: {len(new_unexplored[page_index])} unexplored subtasks for page {page_index}", "yellow")
    return new_unexplored


def explore_action_node(state: ExploreState) -> dict:
    """Explore action node: determine next exploration action based on algorithm.

    Routes to appropriate algorithm implementation:
    - DFS: Depth-first search with stack-based backtracking
    - BFS: Breadth-first search with queue
    - GREEDY: App-wide shortest path to nearest unexplored (action-based distance)

    Args:
        state: Current explore state

    Returns:
        dict: Updated state with action or exploration_complete status
    """
    algorithm = state.get("algorithm", "DFS")
    page_index = state["page_index"]

    log(f":::EXPLORE_ACTION::: Algorithm={algorithm}, page={page_index}", "blue")

    if algorithm == "DFS":
        return _get_dfs_action(state)
    elif algorithm == "BFS":
        return _get_bfs_action(state)
    elif algorithm == "GREEDY":
        return _get_greedy_action(state)
    else:
        log(f":::EXPLORE_ACTION::: Unknown algorithm: {algorithm}", "red")
        return {
            "action": None,
            "status": "unknown_algorithm",
            "next_agent": "FINISH",
        }


def _get_dfs_action(state: ExploreState) -> dict:
    """DFS: Stack-based depth-first exploration.

    Args:
        state: Current explore state

    Returns:
        dict: Updated state with action
    """
    exploration_stack = state.get("exploration_stack", [])
    explored_subtasks = state.get("explored_subtasks", {})
    traversal_path = state.get("traversal_path", [])
    page_index = state["page_index"]
    memory = state["memory"]
    current_xml = state["current_xml"]
    encoded_xml = state.get("encoded_xml", "")

    # Get available subtasks for current page
    available_subtasks = memory.get_available_subtasks(page_index)

    # Add unexplored subtasks to stack
    for subtask in available_subtasks:
        subtask_name = subtask.get("name", "")
        trigger_ui = subtask.get("trigger_ui_index", -1)

        if (subtask_name, trigger_ui) not in explored_subtasks.get(page_index, []):
            # Check if not already in stack
            if not any(
                p == page_index and st.get("name") == subtask_name
                for p, st in exploration_stack
            ):
                exploration_stack.append((page_index, subtask))

    while exploration_stack:
        target_page, subtask_info = exploration_stack[-1]

        # Need to navigate back to target page
        if target_page != page_index:
            # Can't go back from page 0
            if page_index == 0:
                log(f":::DFS::: Cannot go back from page 0, skipping", "yellow")
                exploration_stack.pop()
                continue

            # Navigate back
            new_traversal = traversal_path.copy()
            if new_traversal and new_traversal[-1] == page_index:
                new_traversal.pop()

            log(f":::DFS::: Going back from page {page_index} to reach {target_page}", "yellow")
            return {
                "action": {"name": "back", "parameters": {}},
                "exploration_stack": exploration_stack,
                "traversal_path": new_traversal,
                "last_action_was_back": True,
                "status": "navigating_back",
                "next_agent": "END",
            }

        exploration_stack.pop()

        subtask_name = subtask_info.get("name", "")
        trigger_ui = subtask_info.get("trigger_ui_index", -1)

        # Skip already explored
        if (subtask_name, trigger_ui) in explored_subtasks.get(page_index, []):
            continue

        # Start exploring this subtask
        log(f":::DFS::: Exploring subtask '{subtask_name}' (trigger_ui={trigger_ui})", "cyan")

        # Mark as explored (in-memory)
        new_explored = explored_subtasks.copy()
        if page_index not in new_explored:
            new_explored[page_index] = []
        new_explored[page_index] = new_explored[page_index] + [(subtask_name, trigger_ui)]

        # Create action
        action = _create_subtask_action(subtask_info, current_xml, encoded_xml, memory, page_index)

        if action:
            # Mark as explored in CSV file (persistent storage)
            memory.mark_subtask_explored(
                page_index=page_index,
                subtask_name=subtask_name,
                trigger_ui_index=trigger_ui,
                action=action,
                screen=current_xml
            )
            _generate_and_save_guideline(memory, page_index, subtask_name, trigger_ui, action, current_xml)

            new_traversal = traversal_path.copy()
            new_traversal.append(page_index)

            # Subtask Graph: Track action for action history generation
            new_action_history = _add_to_action_history(state, action)

            return {
                "action": action,
                "exploration_stack": exploration_stack,
                "explored_subtasks": new_explored,
                "traversal_path": new_traversal,
                "last_action_was_back": False,
                "status": "subtask_started",
                "next_agent": "END",
                # Track for end_page update after action execution
                "last_explored_page_index": page_index,
                "last_explored_subtask_name": subtask_name,
                "last_explored_ui_index": trigger_ui,
                # Subtask Graph: action history tracking
                "action_history": new_action_history,
                "before_xml": current_xml,
                "before_screenshot_path": state.get("screenshot_path"),
            }

    # Stack empty but not at start - go back
    if traversal_path:
        if page_index == 0:
            log(":::DFS::: Stack empty at page 0, exploration complete", "green")
            return {
                "action": None,
                "status": "exploration_complete",
                "next_agent": "FINISH",
            }

        new_traversal = traversal_path.copy()
        new_traversal.pop()
        log(f":::DFS::: Stack empty, going back from page {page_index}", "yellow")
        return {
            "action": {"name": "back", "parameters": {}},
            "traversal_path": new_traversal,
            "last_action_was_back": True,
            "status": "navigating_back",
            "next_agent": "END",
        }

    log(":::DFS::: Exploration complete", "green")
    return {
        "action": None,
        "status": "exploration_complete",
        "next_agent": "FINISH",
    }


def _get_bfs_action(state: ExploreState) -> dict:
    """BFS: Queue-based breadth-first exploration.

    Args:
        state: Current explore state

    Returns:
        dict: Updated state with action
    """
    exploration_queue = state.get("exploration_queue", [])
    explored_subtasks = state.get("explored_subtasks", {})
    navigation_plan = state.get("navigation_plan", [])
    page_index = state["page_index"]
    memory = state["memory"]
    current_xml = state["current_xml"]
    encoded_xml = state.get("encoded_xml", "")
    subtask_graph = state.get("subtask_graph", {})
    back_edges = state.get("back_edges", {})
    traversal_path = state.get("traversal_path", [])

    # Execute navigation plan if exists
    if navigation_plan:
        return _execute_navigation_step(state)

    # Get available subtasks and add to queue
    available_subtasks = memory.get_available_subtasks(page_index)
    for subtask in available_subtasks:
        subtask_name = subtask.get("name", "")
        trigger_ui = subtask.get("trigger_ui_index", -1)

        if (subtask_name, trigger_ui) not in explored_subtasks.get(page_index, []):
            if not any(
                p == page_index and st.get("name") == subtask_name
                for p, st in exploration_queue
            ):
                exploration_queue.append((page_index, subtask))

    while exploration_queue:
        target_page, subtask_info = exploration_queue[0]

        # Need to navigate to target page
        if target_page != page_index:
            path = _find_path_to_page(subtask_graph, back_edges, page_index, target_page)

            if path:
                log(f":::BFS::: Found path from {page_index} to {target_page}: {path}", "cyan")
                return {
                    "exploration_queue": exploration_queue,
                    "navigation_plan": path,
                    "status": "planning_navigation",
                    "next_agent": "explore_action",  # Re-enter to execute navigation
                }
            else:
                # No path found - try going back first
                if traversal_path:
                    log(f":::BFS::: No path to page {target_page}, going back", "yellow")
                    new_traversal = traversal_path.copy()
                    new_traversal.pop()
                    return {
                        "action": {"name": "back", "parameters": {}},
                        "exploration_queue": exploration_queue,  # Keep queue intact
                        "traversal_path": new_traversal,
                        "last_action_was_back": True,
                        "status": "navigating_back",
                        "next_agent": "END",
                    }
                else:
                    # No traversal path - skip this subtask
                    log(f":::BFS::: No path and no traversal history, skipping", "yellow")
                    exploration_queue.pop(0)
                    continue

        exploration_queue.pop(0)

        subtask_name = subtask_info.get("name", "")
        trigger_ui = subtask_info.get("trigger_ui_index", -1)

        # Skip already explored
        if (subtask_name, trigger_ui) in explored_subtasks.get(target_page, []):
            continue

        # Start exploring
        log(f":::BFS::: Exploring subtask '{subtask_name}' on page {page_index}", "cyan")

        # Mark as explored (in-memory)
        new_explored = explored_subtasks.copy()
        if page_index not in new_explored:
            new_explored[page_index] = []
        new_explored[page_index] = new_explored[page_index] + [(subtask_name, trigger_ui)]

        action = _create_subtask_action(subtask_info, current_xml, encoded_xml, memory, page_index)

        if action:
            # Mark as explored in CSV file (persistent storage)
            memory.mark_subtask_explored(
                page_index=page_index,
                subtask_name=subtask_name,
                trigger_ui_index=trigger_ui,
                action=action,
                screen=current_xml
            )
            _generate_and_save_guideline(memory, page_index, subtask_name, trigger_ui, action, current_xml)

            new_traversal = traversal_path.copy()
            new_traversal.append(page_index)

            # Subtask Graph: Track action for action history generation
            new_action_history = _add_to_action_history(state, action)

            return {
                "action": action,
                "exploration_queue": exploration_queue,
                "explored_subtasks": new_explored,
                "traversal_path": new_traversal,
                "last_action_was_back": False,
                "status": "subtask_started",
                "next_agent": "END",
                # Track for end_page update after action execution
                "last_explored_page_index": page_index,
                "last_explored_subtask_name": subtask_name,
                "last_explored_ui_index": trigger_ui,
                # Subtask Graph: action history tracking
                "action_history": new_action_history,
                "before_xml": current_xml,
                "before_screenshot_path": state.get("screenshot_path"),
            }

    log(":::BFS::: Exploration complete", "green")
    return {
        "action": None,
        "status": "exploration_complete",
        "next_agent": "FINISH",
    }


def _get_greedy_action(state: ExploreState) -> dict:
    """GREEDY: Find and explore nearest unexplored subtask (App-wide Action Selector).

    Uses BFS to find the closest unexplored subtask across all pages.
    Distance is calculated based on action count (forward/back).

    Inspired by LLM-Explorer's App-wide Action Selector concept.

    Args:
        state: Current explore state

    Returns:
        dict: Updated state with action
    """
    unexplored_subtasks = state.get("unexplored_subtasks", {})
    explored_subtasks = state.get("explored_subtasks", {})
    navigation_plan = state.get("navigation_plan", [])
    page_index = state["page_index"]
    memory = state["memory"]
    current_xml = state["current_xml"]
    encoded_xml = state.get("encoded_xml", "")
    subtask_graph = state.get("subtask_graph", {})
    back_edges = state.get("back_edges", {})
    traversal_path = state.get("traversal_path", [])

    # Defensive: ensure unexplored_subtasks is initialized for current page
    unexplored_subtasks = _ensure_unexplored_subtasks(
        unexplored_subtasks, explored_subtasks, page_index, memory
    )

    # Execute navigation plan if exists
    if navigation_plan:
        return _execute_navigation_step(state)

    # Find nearest unexplored subtask using BFS (action-based distance)
    target_page, target_subtask, path = _find_nearest_unexplored(
        page_index, unexplored_subtasks, subtask_graph, back_edges
    )

    if target_page is None:
        # No unexplored found - try going back to discover more
        if traversal_path:
            log(":::GREEDY::: No unexplored found, going back to explore more", "yellow")
            new_traversal = traversal_path.copy()
            new_traversal.pop()
            return {
                "action": {"name": "back", "parameters": {}},
                "unexplored_subtasks": unexplored_subtasks,
                "traversal_path": new_traversal,
                "last_action_was_back": True,
                "status": "navigating_back",
                "next_agent": "END",
            }
        log(":::GREEDY::: All subtasks explored", "green")
        return {
            "action": None,
            "status": "exploration_complete",
            "next_agent": "FINISH",
        }

    subtask_name = target_subtask.get("name", "")
    log(f":::GREEDY::: Nearest unexplored is '{subtask_name}' on page {target_page} (distance: {len(path)} actions)", "cyan")

    # Need to navigate to target page
    if path:
        log(f":::GREEDY::: Navigating via path: {path}", "cyan")
        return {
            "navigation_plan": path,
            "unexplored_subtasks": unexplored_subtasks,
            "status": "planning_navigation",
            "next_agent": "explore_action",
        }

    # Target is on current page - explore directly
    new_unexplored = unexplored_subtasks.copy()
    if page_index in new_unexplored:
        new_unexplored[page_index] = [
            s for s in new_unexplored[page_index]
            if s.get("name") != subtask_name
        ]

    # Mark as explored (in-memory)
    new_explored = explored_subtasks.copy()
    if page_index not in new_explored:
        new_explored[page_index] = []
    trigger_ui = target_subtask.get("trigger_ui_index", -1)
    new_explored[page_index] = new_explored[page_index] + [(subtask_name, trigger_ui)]

    action = _create_subtask_action(target_subtask, current_xml, encoded_xml, memory, page_index)

    if action:
        # Mark as explored in CSV file (persistent storage)
        memory.mark_subtask_explored(
            page_index=page_index,
            subtask_name=subtask_name,
            trigger_ui_index=trigger_ui,
            action=action,
            screen=current_xml
        )
        _generate_and_save_guideline(memory, page_index, subtask_name, trigger_ui, action, current_xml)

        new_traversal = traversal_path.copy()
        new_traversal.append(page_index)

        # Subtask Graph: Track action for action history generation
        new_action_history = _add_to_action_history(state, action)

        return {
            "action": action,
            "unexplored_subtasks": new_unexplored,
            "explored_subtasks": new_explored,
            "traversal_path": new_traversal,
            "last_action_was_back": False,
            "status": "subtask_started",
            "next_agent": "END",
            # Track for end_page update after action execution
            "last_explored_page_index": page_index,
            "last_explored_subtask_name": subtask_name,
            "last_explored_ui_index": trigger_ui,
            # Subtask Graph: action history tracking
            "action_history": new_action_history,
            "before_xml": current_xml,
            "before_screenshot_path": state.get("screenshot_path"),
        }

    # Action creation failed - continue exploration
    return {
        "unexplored_subtasks": new_unexplored,
        "status": "action_failed",
        "next_agent": "explore_action",
    }


def _execute_navigation_step(state: ExploreState) -> dict:
    """Execute next step in navigation plan.

    Args:
        state: Current explore state

    Returns:
        dict: Updated state with navigation action
    """
    navigation_plan = state.get("navigation_plan", [])
    page_index = state["page_index"]
    traversal_path = state.get("traversal_path", [])

    if not navigation_plan:
        return {
            "status": "navigation_complete",
            "next_agent": "explore_action",
        }

    step_page, action_type, subtask_name = navigation_plan[0]
    new_plan = navigation_plan[1:]

    if action_type == "back":
        if page_index == 0:
            log(":::NAVIGATION::: Cannot go back from page 0, aborting", "red")
            return {
                "navigation_plan": [],
                "status": "navigation_aborted",
                "next_agent": "explore_action",
            }

        new_traversal = traversal_path.copy()
        if new_traversal:
            new_traversal.pop()

        log(f":::NAVIGATION::: Executing back from page {page_index}", "cyan")
        return {
            "action": {"name": "back", "parameters": {}},
            "navigation_plan": new_plan,
            "traversal_path": new_traversal,
            "last_action_was_back": True,
            "status": "navigating",
            "next_agent": "END",
        }

    # Forward action - need to find and click the subtask
    log(f":::NAVIGATION::: Forward to page via subtask '{subtask_name}'", "cyan")

    # For now, use back_edges to navigate forward
    # This is simplified - in practice would need to execute the subtask
    return {
        "navigation_plan": new_plan,
        "status": "navigation_forward",
        "next_agent": "explore_action",
    }


def _create_subtask_action(
    subtask_info: dict,
    current_xml: str,
    encoded_xml: str,
    memory: Any,
    page_index: int
) -> Optional[dict]:
    """Create action for exploring a subtask.

    Args:
        subtask_info: Subtask information
        current_xml: Current screen XML (parsed XML with index/bounds attributes)
        encoded_xml: Encoded XML (unused, kept for compatibility)
        memory: Memory instance
        page_index: Current page index

    Returns:
        dict: Action to execute, or None if failed
    """
    trigger_ui_index = subtask_info.get("trigger_ui_index", -1)
    subtask_name = subtask_info.get("name", "")

    if trigger_ui_index < 0:
        log(f":::ACTION::: No trigger UI for subtask '{subtask_name}'", "yellow")
        return None

    try:
        tree = ET.fromstring(current_xml)
        element = tree.find(f".//*[@index='{trigger_ui_index}']")

        if element is None:
            log(f":::ACTION::: Element with index {trigger_ui_index} not found", "yellow")
            return None

        bounds = element.get("bounds", "")
        if bounds:
            matches = re.findall(r'\d+', bounds)
            if len(matches) >= 4:
                x1, y1, x2, y2 = map(int, matches[:4])
                center_x, center_y = (x1 + x2) // 2, (y1 + y2) // 2

                log(f":::ACTION::: Created click action at ({center_x}, {center_y})", "green")
                return {
                    "name": "click",
                    "parameters": {
                        "index": trigger_ui_index,
                        "x": center_x,
                        "y": center_y,
                        "description": f"Click to explore '{subtask_name}'"
                    }
                }

        # Fallback: return click with index only (no coordinates)
        return {
            "name": "click",
            "parameters": {
                "index": trigger_ui_index,
                "description": f"Click to explore '{subtask_name}'"
            }
        }

    except Exception as e:
        log(f":::ACTION::: Error creating action: {e}", "red")
        return None


def _find_path_to_page(
    subtask_graph: Dict,
    back_edges: Dict,
    from_page: int,
    to_page: int
) -> List[Tuple[int, str, Optional[str]]]:
    """Find path from one page to another using BFS.

    Args:
        subtask_graph: Forward edges {from: [(to, subtask_name), ...]}
        back_edges: Backward edges {from: [to, ...]}
        from_page: Starting page
        to_page: Target page

    Returns:
        List of (page, action_type, subtask_name) tuples
    """
    if from_page == to_page:
        return []

    # BFS to find shortest path
    from collections import deque

    queue = deque([(from_page, [])])
    visited = {from_page}

    while queue:
        current, path = queue.popleft()

        # Check forward edges
        for next_page, subtask_name in subtask_graph.get(current, []):
            if next_page == to_page:
                return path + [(next_page, "forward", subtask_name)]
            if next_page not in visited:
                visited.add(next_page)
                queue.append((next_page, path + [(next_page, "forward", subtask_name)]))

        # Check back edges
        for next_page in back_edges.get(current, []):
            if next_page == to_page:
                return path + [(next_page, "back", None)]
            if next_page not in visited:
                visited.add(next_page)
                queue.append((next_page, path + [(next_page, "back", None)]))

    return []


def _find_nearest_unexplored(
    current_page: int,
    unexplored_subtasks: Dict,
    subtask_graph: Dict,
    back_edges: Dict
) -> Tuple[Optional[int], Optional[dict], List]:
    """Find nearest unexplored subtask using BFS.

    Returns:
        Tuple of (page_index, subtask_info, path)
    """
    # Check current page first
    if current_page in unexplored_subtasks and unexplored_subtasks[current_page]:
        return current_page, unexplored_subtasks[current_page][0], []

    # BFS from current page
    from collections import deque

    queue = deque([(current_page, [])])
    visited = {current_page}

    while queue:
        page, path = queue.popleft()

        # Check this page
        if page in unexplored_subtasks and unexplored_subtasks[page]:
            return page, unexplored_subtasks[page][0], path

        # Add neighbors
        for next_page, subtask_name in subtask_graph.get(page, []):
            if next_page not in visited:
                visited.add(next_page)
                queue.append((next_page, path + [(next_page, "forward", subtask_name)]))

        for next_page in back_edges.get(page, []):
            if next_page not in visited:
                visited.add(next_page)
                queue.append((next_page, path + [(next_page, "back", None)]))

    return None, None, []
