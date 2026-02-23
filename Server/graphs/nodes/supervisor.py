"""Supervisor node for routing decisions in the task graph."""

from typing import Any

from graphs.state import TaskState
from utils.utils import log

MAX_ITERATIONS = 5  # Maximum reselection attempts


def supervisor_node(state: TaskState) -> dict:
    """Supervisor agent node: decide which agent to call next.

    Implements the routing logic for the extended 6-step task graph:
    1. Initial state -> MemoryAgent (load page/state and subtasks)
    2. Subtasks loaded -> PlannerAgent (plan path) or SelectAgent (fallback)
    3. Path planned -> SelectAgent (select from planned path)
    4. Subtask selected -> VerifyAgent (verify next screen)
    5. Verification passed -> DeriveAgent (derive action)
    6. Verification failed / Replan needed -> PlannerAgent or SelectAgent

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

    # Path Planning state
    planned_path = state.get("planned_path")
    replan_needed = state.get("replan_needed", False)
    path_step_index = state.get("path_step_index", 0)
    replan_count = state.get("replan_count", 0)
    max_replan = state.get("max_replan", 5)

    log(f":::SUPERVISOR::: iteration={iteration}, status={status}, verified={verification_passed}", "magenta")
    if planned_path is not None:
        log(f":::SUPERVISOR::: path_step={path_step_index}/{len(planned_path)}, replan={replan_needed}", "magenta")

    # Check max iterations (prevent infinite loops)
    if iteration >= MAX_ITERATIONS:
        log(f":::SUPERVISOR::: Max iterations ({MAX_ITERATIONS}) reached, stopping", "red")
        return {
            "status": "max_iterations_reached",
            "next_agent": "FINISH",
        }

    # Check for terminal states
    if status in ["no_matching_page", "no_subtasks", "no_available_subtask",
                  "action_derived", "no_subtask_to_verify", "no_subtask_for_derive",
                  "max_replan_reached"]:
        log(f":::SUPERVISOR::: Terminal status '{status}', finishing", "yellow")
        return {
            "next_agent": "FINISH",
        }

    # Subtask Graph: Handle path SKIP (verify_planned_path returned skip)
    if status == "path_verified_skip":
        log(":::SUPERVISOR::: Path SKIP -> SelectAgent for new step", "cyan")
        return {
            "selected_subtask": None,
            "verification_passed": None,
            "next_agent": "selector",
        }

    # =========================================================================
    # Adaptive Replanning
    # =========================================================================
    if replan_needed:
        if replan_count < max_replan:
            log(f":::SUPERVISOR::: Replan needed ({replan_count + 1}/{max_replan}) -> PlannerAgent", "yellow")
            return {
                "next_agent": "planner",
            }
        else:
            log(f":::SUPERVISOR::: Max replan ({max_replan}) reached, finishing", "red")
            return {
                "status": "max_replan_reached",
                "next_agent": "FINISH",
            }

    # =========================================================================
    # Standard Flow
    # =========================================================================

    # Verification completed
    if verification_passed is True:
        # "should go" -> proceed to DeriveAgent
        log(":::SUPERVISOR::: Verification PASSED -> DeriveAgent", "green")

        # Update path step if using planned_path
        updates = {"next_agent": "deriver"}
        if planned_path and path_step_index < len(planned_path):
            # Mark current step as completed and advance
            updated_path = [step.copy() for step in planned_path]
            updated_path[path_step_index]["status"] = "completed"
            updates["planned_path"] = updated_path
            updates["path_step_index"] = path_step_index + 1

        return updates

    if verification_passed is False:
        # "shouldn't go" -> reselect with rejection
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

    # =========================================================================
    # Path Planning
    # =========================================================================
    # Check if we need to plan a path (subtasks available but no path yet)
    if available_subtasks and not selected_subtask:
        # If no planned_path exists yet, try to create one
        if planned_path is None:
            log(":::SUPERVISOR::: No path yet, attempting planning -> PlannerAgent", "cyan")
            return {
                "next_agent": "planner",
            }

        # If planned_path exists (even if empty/failed), go to selector
        log(":::SUPERVISOR::: Subtasks available, need selection -> SelectAgent", "blue")
        return {
            "next_agent": "selector",
        }

    # Initial state - need to load page/state
    log(":::SUPERVISOR::: Initial state -> MemoryAgent", "blue")
    return {
        "next_agent": "memory",
    }
