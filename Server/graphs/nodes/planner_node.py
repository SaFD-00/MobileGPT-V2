"""Planner node for Subtask Path Planning (UICompass integration)."""

from typing import Any

from agents.planner_agent import PlannerAgent, replan_from_current
from graphs.state import TaskState
from utils.utils import log


def planner_node(state: TaskState) -> dict:
    """Planner node: create or update subtask path plan.

    This node implements UICompass's Subtask Path Planning:
    - Initial planning: Analyze instruction and STG to create optimal path
    - Replanning: After unexpected transitions, replan from current position

    Args:
        state: Current task state

    Returns:
        dict: Updated state with planned_path and related fields
    """
    memory = state["memory"]
    instruction = state["instruction"]
    current_page = state.get("page_index", -1)

    # Check if STG has data
    if not memory.subtask_graph.get("edges"):
        log(":::PLANNER::: No STG edges, fallback to Select mode", "yellow")
        return {
            "planned_path": None,
            "path_step_index": 0,
            "status": "no_stg_data",
        }

    # Get all available subtasks for planning
    all_subtasks = memory.get_all_available_subtasks()
    if not all_subtasks:
        log(":::PLANNER::: No subtasks available", "yellow")
        return {
            "planned_path": None,
            "path_step_index": 0,
            "status": "no_subtasks",
        }

    # Case 1: Replanning after unexpected transition
    if state.get("replan_needed"):
        replan_count = state.get("replan_count", 0) + 1
        max_replan = state.get("max_replan", 5)

        log(f":::PLANNER::: Replanning attempt {replan_count}/{max_replan}", "cyan")

        if replan_count > max_replan:
            log(":::PLANNER::: Max replan attempts reached", "red")
            return {
                "planned_path": None,
                "replan_needed": False,
                "replan_count": replan_count,
                "status": "max_replan_reached",
            }

        new_path = replan_from_current(
            instruction=instruction,
            current_page=current_page,
            subtask_graph=memory.subtask_graph,
            all_subtasks=all_subtasks
        )

        if new_path:
            log(f":::PLANNER::: Replanned {len(new_path)} steps from page {current_page}", "green")
            return {
                "planned_path": new_path,
                "path_step_index": 0,
                "replan_needed": False,
                "replan_count": replan_count,
                "selected_subtask": None,  # Clear for new selection
                "verification_passed": None,
            }
        else:
            log(":::PLANNER::: Replan failed, fallback to Select", "yellow")
            return {
                "planned_path": None,
                "path_step_index": 0,
                "replan_needed": False,
                "replan_count": replan_count,
                "status": "replan_failed",
            }

    # Case 2: Initial planning
    log(f":::PLANNER::: Creating initial plan from page {current_page}", "cyan")

    planner = PlannerAgent(instruction)
    planned_path = planner.plan(
        current_page=current_page,
        subtask_graph=memory.subtask_graph,
        all_subtasks=all_subtasks
    )

    if planned_path:
        log(f":::PLANNER::: Planned {len(planned_path)} steps", "green")
        for i, step in enumerate(planned_path):
            log(f"  Step {i+1}: {step['subtask']} @ page {step['page']}", "cyan")

        return {
            "planned_path": planned_path,
            "path_step_index": 0,
            "replan_count": 0,
            "max_replan": 5,
            "status": "path_planned",
        }
    else:
        log(":::PLANNER::: No path found, fallback to Select mode", "yellow")
        return {
            "planned_path": None,
            "path_step_index": 0,
            "replan_count": 0,
            "max_replan": 5,
            "status": "no_path_found",
        }
