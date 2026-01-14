"""Verifier node for next screen verification."""

from typing import Any

from agents.verify_agent import verify_path
from graphs.state import TaskState
from utils.utils import log


def verifier_node(state: TaskState) -> dict:
    """Verifier agent node: verify if selected subtask leads to a good path.

    Checks the destination page and uses LLM to determine if we should proceed.

    Args:
        state: Current task state

    Returns:
        dict: Updated state with verification_passed flag
    """
    memory = state["memory"]
    instruction = state["instruction"]
    selected_subtask = state.get("selected_subtask")
    page_index = state["page_index"]
    available_subtasks = state["available_subtasks"]

    if not selected_subtask:
        log(":::VERIFIER::: No subtask selected, skipping verification", "yellow")
        return {
            "verification_passed": False,
            "status": "no_subtask_to_verify",
            "next_agent": "FINISH",
        }

    subtask_name = selected_subtask.get("name", "")
    log(f":::VERIFIER::: Verifying subtask '{subtask_name}'", "blue")

    # Handle special subtasks that don't need verification
    if subtask_name in ["finish", "scroll_screen", "speak"]:
        log(f":::VERIFIER::: Special subtask '{subtask_name}' - auto approved", "green")
        return {
            "verification_passed": True,
            "next_page_index": page_index,
            "next_page_subtasks": [],
            "status": "verified_special",
            "next_agent": "deriver",
        }

    # Get destination page for this subtask
    end_page = memory.get_subtask_destination(page_index, subtask_name)

    log(f":::VERIFIER::: Subtask '{subtask_name}' leads to page {end_page}", "blue")

    # If destination is unknown, we can't verify - assume it's okay (unexplored path)
    if end_page < 0:
        log(f":::VERIFIER::: Destination unknown for '{subtask_name}' - auto approved (unexplored)", "yellow")
        return {
            "verification_passed": True,
            "next_page_index": end_page,
            "next_page_subtasks": [],
            "status": "verified_unexplored",
            "next_agent": "deriver",
        }

    # Get subtasks available on the next screen
    memory.init_page_manager(end_page)
    next_subtasks = memory.get_available_subtasks(end_page)

    log(f":::VERIFIER::: Next screen has {len(next_subtasks)} subtasks", "blue")

    # Use verify_agent to check if this is a good path
    should_proceed, reasoning = verify_path(
        instruction=instruction,
        selected_subtask=selected_subtask,
        current_subtasks=available_subtasks,
        next_subtasks=next_subtasks
    )

    if should_proceed:
        log(f":::VERIFIER::: APPROVED - {reasoning}", "green")
        return {
            "verification_passed": True,
            "next_page_index": end_page,
            "next_page_subtasks": next_subtasks,
            "status": "verified_approved",
            "next_agent": "deriver",
        }
    else:
        log(f":::VERIFIER::: REJECTED - {reasoning}", "red")
        return {
            "verification_passed": False,
            "next_page_index": end_page,
            "next_page_subtasks": next_subtasks,
            "status": "verified_rejected",
            "next_agent": "supervisor",  # Go back to supervisor for reselection
        }
