"""Planner node for Subtask Path Planning (UICompass integration).

Mobile Map 4-Step Workflow Implementation:
1. Load: Get all subtasks from all pages with page summaries
2. Filter: Use FilterAgent to select relevant subtasks for instruction
3. Plan: Create ordered subtask path using Mobile Map
4. Execute: Handled by selector/verifier nodes
"""

from typing import Any, Dict, List

from agents.planner_agent import PlannerAgent, replan_from_current
from agents import filter_agent
from agents import step_verify_agent
from graphs.state import TaskState
from utils.utils import log


def planner_node(state: TaskState) -> dict:
    """Planner node: create or update subtask path plan.

    This node implements the Mobile Map 4-Step Workflow:
    - Step 1 (Load): Get all subtasks from all pages
    - Step 2 (Filter): Filter subtasks relevant to instruction
    - Step 3 (Plan): Create optimal path using Mobile Map
    - Step 4 (Execute): Handled by selector/verifier nodes

    Args:
        state: Current task state

    Returns:
        dict: Updated state with planned_path and related fields
    """
    memory = state["memory"]
    instruction = state["instruction"]
    current_page = state.get("page_index", -1)

    # Check if Mobile Map has data
    if not memory.subtask_graph.get("edges"):
        log(":::PLANNER::: No Mobile Map edges, fallback to Select mode", "yellow")
        return {
            "planned_path": None,
            "path_step_index": 0,
            "status": "no_stg_data",
        }

    # ============================================================
    # STEP 1: Load - Get all subtasks from all pages
    # ============================================================
    log(":::PLANNER::: Step 1 - Loading all subtasks", "cyan")
    all_subtasks = _load_all_subtasks_with_context(memory)

    if not all_subtasks:
        log(":::PLANNER::: No subtasks available", "yellow")
        return {
            "planned_path": None,
            "path_step_index": 0,
            "status": "no_subtasks",
            "all_subtasks_list": [],
            "filtered_subtasks": [],
        }

    log(f":::PLANNER::: Loaded {len(all_subtasks)} subtasks from all pages", "cyan")

    # Step 1 Verification
    load_result = step_verify_agent.verify_load(all_subtasks, memory)
    if load_result["status"] == step_verify_agent.StepVerifyResult.FAIL:
        log(f":::PLANNER::: Load verification FAILED: {load_result['reason']}", "red")
        return {
            "planned_path": None,
            "path_step_index": 0,
            "status": "load_verification_failed",
            "all_subtasks_list": [],
            "filtered_subtasks": [],
        }

    # ============================================================
    # STEP 2: Filter - Select subtasks relevant to instruction
    # ============================================================
    log(":::PLANNER::: Step 2 - Filtering relevant subtasks", "cyan")
    filtered_subtasks = filter_agent.filter_subtasks(
        instruction=instruction,
        all_subtasks=all_subtasks,
        max_results=15  # Keep top 15 most relevant
    )
    log(f":::PLANNER::: Filtered to {len(filtered_subtasks)} relevant subtasks", "cyan")

    # Step 2 Verification
    filter_result = step_verify_agent.verify_filter(instruction, filtered_subtasks, all_subtasks)
    if filter_result["status"] == step_verify_agent.StepVerifyResult.FAIL:
        log(":::PLANNER::: Filter verification FAILED, using all subtasks as fallback", "yellow")
        planning_subtasks = all_subtasks  # Fallback to all subtasks
    else:
        # Use filtered subtasks for planning, fallback to all if filter returns nothing
        planning_subtasks = filtered_subtasks if filtered_subtasks else all_subtasks

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
                "all_subtasks_list": all_subtasks,
                "filtered_subtasks": filtered_subtasks,
            }

        new_path = replan_from_current(
            instruction=instruction,
            current_page=current_page,
            subtask_graph=memory.subtask_graph,
            all_subtasks=planning_subtasks  # Use filtered subtasks
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
                "all_subtasks_list": all_subtasks,
                "filtered_subtasks": filtered_subtasks,
            }
        else:
            log(":::PLANNER::: Replan failed, fallback to Select", "yellow")
            return {
                "planned_path": None,
                "path_step_index": 0,
                "replan_needed": False,
                "replan_count": replan_count,
                "status": "replan_failed",
                "all_subtasks_list": all_subtasks,
                "filtered_subtasks": filtered_subtasks,
            }

    # ============================================================
    # STEP 3: Plan - Create optimal path using Mobile Map
    # ============================================================
    log(f":::PLANNER::: Step 3 - Creating plan from page {current_page}", "cyan")

    planner = PlannerAgent(instruction)
    planned_path = planner.plan(
        current_page=current_page,
        subtask_graph=memory.subtask_graph,
        all_subtasks=planning_subtasks  # Use filtered subtasks
    )

    if planned_path:
        log(f":::PLANNER::: Planned {len(planned_path)} steps", "green")
        for i, step in enumerate(planned_path):
            log(f"  Step {i+1}: {step['subtask']} @ page {step['page']}", "cyan")

        # Step 3 Verification
        plan_result = step_verify_agent.verify_plan(planned_path, memory.subtask_graph, current_page)
        if plan_result["status"] == step_verify_agent.StepVerifyResult.FAIL:
            log(":::PLANNER::: Plan verification FAILED, fallback to Select mode", "yellow")
            planned_path = None  # Will fall through to "no path found" return

    if planned_path:
        return {
            "planned_path": planned_path,
            "path_step_index": 0,
            "replan_count": 0,
            "max_replan": 5,
            "status": "path_planned",
            "all_subtasks_list": all_subtasks,
            "filtered_subtasks": filtered_subtasks,
        }
    else:
        log(":::PLANNER::: No path found, fallback to Select mode", "yellow")
        return {
            "planned_path": None,
            "path_step_index": 0,
            "replan_count": 0,
            "max_replan": 5,
            "status": "no_path_found",
            "all_subtasks_list": all_subtasks,
            "filtered_subtasks": filtered_subtasks,
        }


def _load_all_subtasks_with_context(memory: Any) -> List[dict]:
    """Load all subtasks from all pages with page summary context.

    Mobile Map Step 1: Load
    Enriches subtasks with page_summary for better filtering and planning.

    Args:
        memory: Memory manager instance

    Returns:
        List of subtask dicts with page_index and page_summary
    """
    all_subtasks = []
    raw_subtasks = memory.get_all_available_subtasks()

    for page_idx, subtasks in raw_subtasks.items():
        # Get page summary for context
        page_summary = memory.get_page_summary(page_idx)

        for subtask in subtasks:
            enriched = subtask.copy()
            enriched["page_index"] = page_idx
            enriched["page_summary"] = page_summary if page_summary else ""
            all_subtasks.append(enriched)

    return all_subtasks
