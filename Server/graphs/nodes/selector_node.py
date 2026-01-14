"""Selector node for subtask selection (wraps SelectAgent)."""

from typing import Any

from agents.select_agent import SelectAgent
from graphs.state import TaskState
from utils.utils import log


def selector_node(state: TaskState) -> dict:
    """Selector agent node: select best subtask from available options.

    Filters out rejected subtasks and uses SelectAgent to choose the best one.

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

    log(f":::SELECTOR::: Available: {len(available_subtasks)}, Rejected: {len(rejected_subtasks)}", "blue")

    # Filter out rejected subtasks
    rejected_names = {s.get("name") for s in rejected_subtasks}
    filtered_subtasks = [
        s for s in available_subtasks
        if s.get("name") not in rejected_names
    ]

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
