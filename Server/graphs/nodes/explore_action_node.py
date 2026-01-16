"""Explore action node with 4 exploration algorithms.

Contains DFS, BFS, GREEDY_BFS, GREEDY_DFS algorithms unified in a single node.
"""

import re
import xml.etree.ElementTree as ET
from typing import Any, Dict, List, Optional, Set, Tuple

from graphs.state import ExploreState
from utils.utils import log


def explore_action_node(state: ExploreState) -> dict:
    """Explore action node: determine next exploration action based on algorithm.

    Routes to appropriate algorithm implementation:
    - DFS: Depth-first search with stack
    - BFS: Breadth-first search with queue
    - GREEDY_BFS: BFS to find nearest unexplored
    - GREEDY_DFS: DFS to find deepest unexplored

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
    elif algorithm == "GREEDY_BFS":
        return _get_greedy_bfs_action(state)
    elif algorithm == "GREEDY_DFS":
        return _get_greedy_dfs_action(state)
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
            new_traversal = traversal_path.copy()
            new_traversal.append(page_index)

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
    page_graph = state.get("page_graph", {})
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
            path = _find_path_to_page(page_graph, back_edges, page_index, target_page)

            if path:
                log(f":::BFS::: Found path from {page_index} to {target_page}: {path}", "cyan")
                return {
                    "exploration_queue": exploration_queue,
                    "navigation_plan": path,
                    "status": "planning_navigation",
                    "next_agent": "explore_action",  # Re-enter to execute navigation
                }
            else:
                log(f":::BFS::: No path to page {target_page}, skipping", "yellow")
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
            new_traversal = traversal_path.copy()
            new_traversal.append(page_index)

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
            }

    log(":::BFS::: Exploration complete", "green")
    return {
        "action": None,
        "status": "exploration_complete",
        "next_agent": "FINISH",
    }


def _get_greedy_bfs_action(state: ExploreState) -> dict:
    """GREEDY_BFS: Find and explore nearest unexplored subtask.

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
    page_graph = state.get("page_graph", {})
    back_edges = state.get("back_edges", {})
    traversal_path = state.get("traversal_path", [])

    # Execute navigation plan if exists
    if navigation_plan:
        return _execute_navigation_step(state)

    # Find nearest unexplored subtask using BFS
    target_page, target_subtask, path = _find_nearest_unexplored(
        page_index, unexplored_subtasks, page_graph, back_edges
    )

    if target_page is None:
        log(":::GREEDY_BFS::: All subtasks explored", "green")
        return {
            "action": None,
            "status": "exploration_complete",
            "next_agent": "FINISH",
        }

    subtask_name = target_subtask.get("name", "")
    log(f":::GREEDY_BFS::: Nearest unexplored is '{subtask_name}' on page {target_page}", "cyan")

    # Need to navigate
    if path:
        log(f":::GREEDY_BFS::: Navigating via path: {path}", "cyan")
        return {
            "navigation_plan": path,
            "status": "planning_navigation",
            "next_agent": "explore_action",
        }

    # Remove from unexplored and explore
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
            screen=current_xml,
            start_page=page_index  # 현재 페이지 = 시작 페이지
        )
        new_traversal = traversal_path.copy()
        new_traversal.append(page_index)

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
        }

    return {
        "unexplored_subtasks": new_unexplored,
        "status": "action_failed",
        "next_agent": "explore_action",
    }


def _get_greedy_dfs_action(state: ExploreState) -> dict:
    """GREEDY_DFS: Find and explore deepest unexplored subtask.

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
    page_graph = state.get("page_graph", {})
    back_edges = state.get("back_edges", {})
    traversal_path = state.get("traversal_path", [])

    # Execute navigation plan if exists
    if navigation_plan:
        return _execute_navigation_step(state)

    # Find deepest unexplored subtask using DFS
    target_page, target_subtask, path = _find_deepest_unexplored(
        page_index, unexplored_subtasks, page_graph, back_edges
    )

    if target_page is None:
        log(":::GREEDY_DFS::: All subtasks explored", "green")
        return {
            "action": None,
            "status": "exploration_complete",
            "next_agent": "FINISH",
        }

    subtask_name = target_subtask.get("name", "")
    log(f":::GREEDY_DFS::: Deepest unexplored is '{subtask_name}' on page {target_page}", "cyan")

    # Need to navigate
    if path:
        log(f":::GREEDY_DFS::: Navigating via path: {path}", "cyan")
        return {
            "navigation_plan": path,
            "status": "planning_navigation",
            "next_agent": "explore_action",
        }

    # Remove from unexplored and explore
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
            screen=current_xml,
            start_page=page_index  # 현재 페이지 = 시작 페이지
        )
        new_traversal = traversal_path.copy()
        new_traversal.append(page_index)

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
        }

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
    page_graph: Dict,
    back_edges: Dict,
    from_page: int,
    to_page: int
) -> List[Tuple[int, str, Optional[str]]]:
    """Find path from one page to another using BFS.

    Args:
        page_graph: Forward edges {from: [(to, subtask_name), ...]}
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
        for next_page, subtask_name in page_graph.get(current, []):
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
    page_graph: Dict,
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
        for next_page, subtask_name in page_graph.get(page, []):
            if next_page not in visited:
                visited.add(next_page)
                queue.append((next_page, path + [(next_page, "forward", subtask_name)]))

        for next_page in back_edges.get(page, []):
            if next_page not in visited:
                visited.add(next_page)
                queue.append((next_page, path + [(next_page, "back", None)]))

    return None, None, []


def _find_deepest_unexplored(
    current_page: int,
    unexplored_subtasks: Dict,
    page_graph: Dict,
    back_edges: Dict
) -> Tuple[Optional[int], Optional[dict], List]:
    """Find deepest unexplored subtask using DFS.

    Returns:
        Tuple of (page_index, subtask_info, path)
    """
    deepest_result = (None, None, [])
    max_depth = -1

    def dfs(page: int, path: List, depth: int, visited: Set):
        nonlocal deepest_result, max_depth

        # Check this page
        if page in unexplored_subtasks and unexplored_subtasks[page]:
            if depth > max_depth:
                max_depth = depth
                deepest_result = (page, unexplored_subtasks[page][0], path.copy())

        # Continue DFS
        for next_page, subtask_name in page_graph.get(page, []):
            if next_page not in visited:
                visited.add(next_page)
                dfs(next_page, path + [(next_page, "forward", subtask_name)], depth + 1, visited)
                visited.remove(next_page)

    visited = {current_page}
    dfs(current_page, [], 0, visited)

    return deepest_result
