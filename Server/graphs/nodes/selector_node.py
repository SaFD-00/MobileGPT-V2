"""Selector node for subtask selection (wraps SelectAgent)."""

from typing import Any, Optional

from agents.select_agent import SelectAgent
from graphs.state import TaskState
from utils.utils import log


def selector_node(state: TaskState) -> dict:
    """Selector agent node: select best subtask from available options.

    If planned_path exists, selects the subtask from current step.
    Otherwise, uses SelectAgent to choose the best one.

    Args:
        state: Current task state

    Returns:
        dict: Updated state with selected_subtask
    """
    memory = state["memory"]
    instruction = state["instruction"]
    available_subtasks = state["available_subtasks"]
    rejected_subtasks = state.get("rejected_subtasks", [])
    current_xml = state["current_xml"]
    planned_path = state.get("planned_path")
    path_step_index = state.get("path_step_index", 0)

    log(f":::SELECTOR::: Available: {len(available_subtasks)}, Rejected: {len(rejected_subtasks)}", "blue")

    # Check if we have a planned path and should follow it
    if planned_path and path_step_index < len(planned_path):
        result = _select_from_planned_path(
            planned_path, path_step_index, available_subtasks, rejected_subtasks
        )
        if result:
            return result
        # Fall through to standard selection if planned subtask not found

    # Filter out rejected subtasks
    rejected_names = {s.get("name") for s in rejected_subtasks}
    filtered_subtasks = [
        s for s in available_subtasks
        if s.get("name") not in rejected_names
    ]

    # Mobile Map: Prioritize planner's filtered subtasks if available
    filtered_from_planner = state.get("filtered_subtasks", [])
    if filtered_from_planner:
        filtered_names = {s.get("name") for s in filtered_from_planner}
        priority_subtasks = [s for s in filtered_subtasks if s.get("name") in filtered_names]
        if priority_subtasks:
            filtered_subtasks = priority_subtasks
            log(f":::SELECTOR::: Using {len(priority_subtasks)} planner-filtered subtasks", "cyan")

    if not filtered_subtasks:
        log(":::SELECTOR::: All subtasks rejected, no options left", "red")
        return {
            "selected_subtask": None,
            "verification_passed": None,
            "status": "no_available_subtask",
            "next_agent": "FINISH",
        }

    log(f":::SELECTOR::: Selecting from {len(filtered_subtasks)} subtasks", "blue")

    # Use SelectAgent to choose the best subtask
    select_agent = SelectAgent(memory, instruction)
    response, new_action = select_agent.select(
        available_subtasks=filtered_subtasks,
        subtask_history=[],
        qa_history=[],
        screen=current_xml
    )

    selected_subtask = response.get("action")

    if selected_subtask:
        log(f":::SELECTOR::: Selected subtask: {selected_subtask.get('name')}", "green")
    else:
        log(":::SELECTOR::: No subtask selected", "yellow")

    # Add new action if created
    if new_action:
        log(f":::SELECTOR::: New action created: {new_action.get('name')}", "cyan")

    return {
        "selected_subtask": selected_subtask,
        "verification_passed": None,  # Pending verification
        "status": "subtask_selected",
        "next_agent": "verifier",
    }


def _select_from_planned_path(
    planned_path: list,
    path_step_index: int,
    available_subtasks: list,
    rejected_subtasks: list
) -> Optional[dict]:
    """Select subtask from planned path if available.

    Args:
        planned_path: Planned subtask sequence
        path_step_index: Current step index
        available_subtasks: Subtasks available on current page
        rejected_subtasks: Previously rejected subtasks

    Returns:
        dict with selected_subtask if found, None otherwise
    """
    if path_step_index >= len(planned_path):
        return None

    current_step = planned_path[path_step_index]
    planned_subtask_name = current_step.get("subtask", "")

    log(f":::SELECTOR::: Following planned path step {path_step_index}: '{planned_subtask_name}'", "cyan")

    # Check if planned subtask is rejected
    rejected_names = {s.get("name") for s in rejected_subtasks}
    if planned_subtask_name in rejected_names:
        log(f":::SELECTOR::: Planned subtask '{planned_subtask_name}' was rejected, falling back", "yellow")
        return None

    # Find the planned subtask in available subtasks
    for subtask in available_subtasks:
        if subtask.get("name") == planned_subtask_name:
            log(f":::SELECTOR::: Selected planned subtask: {planned_subtask_name}", "green")

            # Update path step status
            updated_path = planned_path.copy()
            updated_path[path_step_index]["status"] = "in_progress"

            return {
                "selected_subtask": subtask,
                "planned_path": updated_path,
                "path_step_index": path_step_index,
                "verification_passed": None,
                "status": "planned_subtask_selected",
                "next_agent": "verifier",
            }

    log(f":::SELECTOR::: Planned subtask '{planned_subtask_name}' not found on this page, falling back", "yellow")
    return None
