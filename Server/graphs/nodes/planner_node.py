"""Planner node for Subtask Path Planning.

Subtask Graph 4-Step Workflow Implementation:
1. Load: Get all subtasks from all pages with page summaries
2. Filter: Use FilterAgent to select relevant subtasks for instruction
3. Plan: Create ordered subtask path using Subtask Graph
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

    This node implements the Subtask Graph 4-Step Workflow:
    - Step 1 (Load): Get all subtasks from all pages
    - Step 2 (Filter): Filter subtasks relevant to instruction
    - Step 3 (Plan): Create optimal path using Subtask Graph
    - Step 4 (Execute): Handled by selector/verifier nodes

    Args:
        state: Current task state

    Returns:
        dict: Updated state with planned_path and related fields
    """
    memory = state["memory"]
    instruction = state["instruction"]
    current_page = state.get("page_index", -1)

    # Check if Subtask Graph has data
    if not memory.subtask_graph.get("edges"):
        log(":::PLANNER::: No Subtask Graph edges, fallback to Select mode", "yellow")
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

    # Extract filtered subtask names for [RELEVANT] markers in planning
    filtered_names = [s.get("name", "") for s in filtered_subtasks] if filtered_subtasks else []

    # Step 2 Verification
    filter_result = step_verify_agent.verify_filter(instruction, filtered_subtasks, all_subtasks)
    if filter_result["status"] == step_verify_agent.StepVerifyResult.FAIL:
        log(":::PLANNER::: Filter verification FAILED, using all subtasks without markers", "yellow")
        filtered_names = []  # No markers when filter fails

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
            all_subtasks=_list_to_page_dict(all_subtasks),
            filtered_names=filtered_names
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
    # STEP 3: Plan - Create optimal path using Subtask Graph
    # ============================================================
    log(f":::PLANNER::: Step 3 - Creating plan from page {current_page}", "cyan")

    planner = PlannerAgent(instruction)
    planned_path = planner.plan(
        current_page=current_page,
        subtask_graph=memory.subtask_graph,
        all_subtasks=_list_to_page_dict(all_subtasks),
        filtered_names=filtered_names
    )

    if planned_path:
        log(f":::PLANNER::: Planned {len(planned_path)} steps", "green")
        for i, step in enumerate(planned_path):
            transit_tag = " [TRANSIT]" if step.get("is_transit") else ""
            log(f"  Step {i+1}: {step['subtask']} @ page {step['page']}{transit_tag}", "cyan")

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


def _list_to_page_dict(subtasks_list: List[dict]) -> Dict[int, List[dict]]:
    """Convert flat subtask list to page-indexed dict.

    Args:
        subtasks_list: Flat list of subtask dicts with 'page_index' field
            (set by _load_all_subtasks_with_context)

    Returns:
        Dict mapping page_index to list of subtasks on that page
    """
    page_dict: Dict[int, List[dict]] = {}
    for s in subtasks_list:
        page_idx = s.get("page_index")
        if page_idx is None:
            log(f":::PLANNER::: WARNING - subtask missing page_index: {s.get('name', 'unknown')}", "yellow")
            continue
        if page_idx not in page_dict:
            page_dict[page_idx] = []
        page_dict[page_idx].append(s)
    return page_dict


def _load_all_subtasks_with_context(memory: Any) -> List[dict]:
    """Load explored subtasks from all pages with page summary context.

    Subtask Graph Step 1: Load
    Reads directly from subtasks.csv (explored subtasks only).
    Enriches subtasks with page_summary for better filtering and planning.

    Args:
        memory: Memory manager instance

    Returns:
        List of subtask dicts with page_index and page_summary
    """
    all_subtasks = []
    raw_subtasks = memory.get_all_explored_subtasks()

    for page_idx, subtasks in raw_subtasks.items():
        # Get page summary for context
        page_summary = memory.get_page_summary(page_idx)

        for subtask in subtasks:
            enriched = subtask.copy()
            enriched["page_index"] = page_idx
            enriched["page_summary"] = page_summary if page_summary else ""
            all_subtasks.append(enriched)

    return all_subtasks
