"""Verifier node for next screen verification.

Mobile Map 4-Step Workflow - Step 4: Execute & Replan

Implements adaptive replanning logic (UICompass-inspired):
- PROCEED: On expected page, continue execution
- SKIP: Jumped ahead in plan, update step index
- REPLAN: Unexpected page, trigger replanning to Planner node
"""

from typing import Any

from agents.verify_agent import verify_path, verify_with_path, PathVerificationResult
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

    # Mobile Map: Planned path position verification (Adaptive Replanning)
    planned_path = state.get("planned_path")
    path_step_index = state.get("path_step_index", 0)

    if planned_path and path_step_index < len(planned_path):
        path_result = verify_planned_path(state)
        if path_result.get("replan_needed"):
            log(":::VERIFIER::: Path verification -> REPLAN needed", "yellow")
            return {**path_result, "next_agent": "planner"}
        if path_result.get("status") == "path_verified_skip":
            log(":::VERIFIER::: Path verification -> SKIP", "yellow")
            return {**path_result, "next_agent": "supervisor"}

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

    # Get page summaries for verification context
    current_page_summary = memory.get_page_summary(page_index)
    next_page_summary = memory.get_page_summary(end_page) if end_page >= 0 else ""

    # Use verify_agent to check if this is a good path
    should_proceed, reasoning = verify_path(
        instruction=instruction,
        selected_subtask=selected_subtask,
        current_subtasks=available_subtasks,
        next_subtasks=next_subtasks,
        current_page_summary=current_page_summary,
        next_page_summary=next_page_summary,
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


def verify_planned_path(state: TaskState) -> dict:
    """Verify current position against planned path (Adaptive Replanning).

    This function is called after action execution to check if we arrived
    at the expected page. Handles three cases:
    - PROCEED: On expected page, continue execution
    - SKIP: Jumped ahead, update step index
    - REPLAN: Unexpected page, trigger replanning

    Args:
        state: Current task state

    Returns:
        dict: Updated state based on verification result
    """
    planned_path = state.get("planned_path")
    path_step_index = state.get("path_step_index", 0)
    current_page = state.get("page_index", -1)
    replan_count = state.get("replan_count", 0)
    max_replan = state.get("max_replan", 5)

    if not planned_path:
        # No planned path, fall back to standard verification
        return verifier_node(state)

    log(f":::VERIFIER::: Path verification at step {path_step_index}, page {current_page}", "blue")

    result = verify_with_path(planned_path, path_step_index, current_page)
    decision = result["decision"]
    reason = result["reason"]

    log(f":::VERIFIER::: Path decision: {decision} - {reason}", "cyan")

    if decision == PathVerificationResult.PROCEED:
        # On expected page, continue with standard verification
        log(":::VERIFIER::: Path PROCEED - continuing execution", "green")
        return {
            "verification_passed": True,
            "status": "path_verified_proceed",
        }

    elif decision == PathVerificationResult.SKIP:
        # Jumped ahead in path, update step index
        new_step_index = result["new_step_index"]
        log(f":::VERIFIER::: Path SKIP - jumping to step {new_step_index}", "yellow")

        # Mark skipped steps
        updated_path = planned_path.copy()
        for i in range(path_step_index, new_step_index):
            if i < len(updated_path):
                updated_path[i]["status"] = "skipped"

        return {
            "planned_path": updated_path,
            "path_step_index": new_step_index,
            "verification_passed": True,
            "status": "path_verified_skip",
        }

    else:  # REPLAN
        # Unexpected page, need to replan
        if replan_count >= max_replan:
            log(f":::VERIFIER::: Max replan ({max_replan}) reached", "red")
            return {
                "replan_needed": False,
                "verification_passed": False,
                "status": "max_replan_reached",
            }

        log(f":::VERIFIER::: Path REPLAN - triggering replanning ({replan_count + 1}/{max_replan})", "yellow")
        return {
            "replan_needed": True,
            "verification_passed": False,
            "status": "path_replan_needed",
        }
