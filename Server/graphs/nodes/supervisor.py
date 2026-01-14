"""Supervisor node for routing decisions in the task graph."""

from typing import Any

from graphs.state import TaskState
from utils.utils import log

MAX_ITERATIONS = 5  # Maximum reselection attempts


def supervisor_node(state: TaskState) -> dict:
    """Supervisor agent node: decide which agent to call next.

    Implements the routing logic for the task graph:
    1. Initial state -> MemoryAgent (load page/state and subtasks)
    2. Subtasks loaded -> SelectAgent (select best subtask)
    3. Subtask selected -> VerifyAgent (verify next screen)
    4. Verification passed -> DeriveAgent (derive action)
    5. Verification failed -> SelectAgent (reselect with rejection)

    Args:
        state: Current task state

    Returns:
        dict: Updated state with next_agent routing decision
    """
    iteration = state.get("iteration", 0)
    verification_passed = state.get("verification_passed")
    selected_subtask = state.get("selected_subtask")
    available_subtasks = state.get("available_subtasks", [])
    status = state.get("status", "")

    log(f":::SUPERVISOR::: iteration={iteration}, status={status}, verified={verification_passed}", "magenta")

    # Check max iterations (prevent infinite loops)
    if iteration >= MAX_ITERATIONS:
        log(f":::SUPERVISOR::: Max iterations ({MAX_ITERATIONS}) reached, stopping", "red")
        return {
            "status": "max_iterations_reached",
            "next_agent": "FINISH",
        }

    # Check for terminal states
    if status in ["no_matching_page", "no_subtasks", "no_available_subtask",
                  "action_derived", "no_subtask_to_verify", "no_subtask_for_derive"]:
        log(f":::SUPERVISOR::: Terminal status '{status}', finishing", "yellow")
        return {
            "next_agent": "FINISH",
        }

    # Verification completed
    if verification_passed is True:
        # "간다" (should go) -> proceed to DeriveAgent
        log(":::SUPERVISOR::: Verification PASSED -> DeriveAgent", "green")
        return {
            "next_agent": "deriver",
        }

    if verification_passed is False:
        # "가면 안된다" (shouldn't go) -> reselect with rejection
        log(":::SUPERVISOR::: Verification FAILED -> Reselect", "yellow")

        rejected_subtasks = state.get("rejected_subtasks", [])
        if selected_subtask:
            rejected_subtasks = rejected_subtasks + [selected_subtask]

        return {
            "rejected_subtasks": rejected_subtasks,
            "selected_subtask": None,
            "verification_passed": None,
            "iteration": iteration + 1,
            "next_agent": "selector",
        }

    # Subtask selected but not verified yet
    if selected_subtask and verification_passed is None:
        log(":::SUPERVISOR::: Subtask selected, needs verification -> VerifyAgent", "blue")
        return {
            "next_agent": "verifier",
        }

    # Subtasks available but none selected
    if available_subtasks and not selected_subtask:
        log(":::SUPERVISOR::: Subtasks available, need selection -> SelectAgent", "blue")
        return {
            "next_agent": "selector",
        }

    # Initial state - need to load page/state
    log(":::SUPERVISOR::: Initial state -> MemoryAgent", "blue")
    return {
        "next_agent": "memory",
    }
