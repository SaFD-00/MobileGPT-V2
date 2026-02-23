"""Step verification agent for Subtask Graph 4-Step Workflow.

Provides lightweight verification at each step of the workflow:
- Load verification: Check subtask completeness
- Filter verification: Check filtering reasonableness
- Plan verification: Check plan feasibility
"""

from typing import Any, Dict, List, Optional

from utils.utils import log


class StepVerifyResult:
    """Verification result status."""
    PASS = "pass"
    WARN = "warn"
    FAIL = "fail"


def verify_load(all_subtasks: List[dict], memory: Any) -> dict:
    """Step 1 verification: Check loaded subtask completeness.

    Checks:
    - At least 1 subtask loaded
    - Multiple pages represented (single page = WARN)
    - No empty pages

    Args:
        all_subtasks: All loaded subtasks from all pages
        memory: Memory manager instance

    Returns:
        dict with 'status' (pass/warn/fail), 'reason', 'details'
    """
    if not all_subtasks:
        return {
            "status": StepVerifyResult.FAIL,
            "reason": "No subtasks loaded from any page",
            "details": {"total_subtasks": 0, "total_pages": 0}
        }

    # Count pages represented
    pages = set()
    for s in all_subtasks:
        page_idx = s.get("page_index")
        if page_idx is not None:
            pages.add(page_idx)

    total_pages = len(pages)
    total_subtasks = len(all_subtasks)

    details = {
        "total_subtasks": total_subtasks,
        "total_pages": total_pages,
        "pages": list(pages)
    }

    if total_pages <= 1:
        log(f":::STEP_VERIFY::: Load WARN - only {total_pages} page(s) with {total_subtasks} subtasks", "yellow")
        return {
            "status": StepVerifyResult.WARN,
            "reason": f"Only {total_pages} page(s) loaded, Subtask Graph may be incomplete",
            "details": details
        }

    log(f":::STEP_VERIFY::: Load PASS - {total_subtasks} subtasks from {total_pages} pages", "green")
    return {
        "status": StepVerifyResult.PASS,
        "reason": f"Loaded {total_subtasks} subtasks from {total_pages} pages",
        "details": details
    }


def verify_filter(
    instruction: str,
    filtered: List[dict],
    all_subtasks: List[dict]
) -> dict:
    """Step 2 verification: Check filtering result reasonableness.

    Checks:
    - At least 1 subtask filtered
    - Filter ratio not too extreme (>90% removal = WARN)

    Args:
        instruction: User instruction
        filtered: Filtered subtasks
        all_subtasks: All subtasks before filtering

    Returns:
        dict with 'status', 'reason', 'details'
    """
    total = len(all_subtasks)
    filtered_count = len(filtered)

    details = {
        "total_before": total,
        "filtered_count": filtered_count,
        "removal_ratio": round(1 - filtered_count / total, 2) if total > 0 else 0
    }

    if filtered_count == 0:
        log(":::STEP_VERIFY::: Filter FAIL - no subtasks passed filter", "red")
        return {
            "status": StepVerifyResult.FAIL,
            "reason": "No subtasks passed filter, will fallback to all subtasks",
            "details": details
        }

    removal_ratio = details["removal_ratio"]
    if total > 5 and removal_ratio > 0.9:
        log(f":::STEP_VERIFY::: Filter WARN - {removal_ratio*100:.0f}% removal rate", "yellow")
        return {
            "status": StepVerifyResult.WARN,
            "reason": f"High removal rate ({removal_ratio*100:.0f}%), filter may be too aggressive",
            "details": details
        }

    log(f":::STEP_VERIFY::: Filter PASS - {filtered_count}/{total} subtasks kept", "green")
    return {
        "status": StepVerifyResult.PASS,
        "reason": f"Filtered {filtered_count} from {total} subtasks",
        "details": details
    }


def verify_plan(
    planned_path: Optional[List[dict]],
    subtask_graph: dict,
    current_page: int
) -> dict:
    """Step 3 verification: Check plan feasibility.

    Checks:
    - Path is not empty
    - Consecutive steps are connected in subtask_graph
    - Starting page matches current_page
    - No circular loops

    Args:
        planned_path: Planned subtask path
        subtask_graph: Subtask Graph with nodes and edges
        current_page: Current page index

    Returns:
        dict with 'status', 'reason', 'details'
    """
    if not planned_path:
        log(":::STEP_VERIFY::: Plan FAIL - empty planned path", "red")
        return {
            "status": StepVerifyResult.FAIL,
            "reason": "No planned path generated",
            "details": {"path_length": 0}
        }

    path_length = len(planned_path)

    # Check starting page
    first_step_page = planned_path[0].get("page", -1)
    if first_step_page != current_page:
        log(f":::STEP_VERIFY::: Plan WARN - start page mismatch (expected {current_page}, got {first_step_page})", "yellow")
        return {
            "status": StepVerifyResult.WARN,
            "reason": f"Starting page mismatch: expected {current_page}, path starts at {first_step_page}",
            "details": {"path_length": path_length, "expected_start": current_page, "actual_start": first_step_page}
        }

    # Check for circular loops
    visited_pages = []
    for step in planned_path:
        page = step.get("page", -1)
        if page in visited_pages:
            log(f":::STEP_VERIFY::: Plan WARN - circular loop detected at page {page}", "yellow")
            return {
                "status": StepVerifyResult.WARN,
                "reason": f"Circular loop detected: page {page} visited twice",
                "details": {"path_length": path_length, "loop_page": page}
            }
        visited_pages.append(page)

    # Check edge connectivity
    edges = subtask_graph.get("edges", [])
    edge_set = set()
    for edge in edges:
        edge_set.add((edge["from_page"], edge["to_page"], edge["subtask"]))

    disconnected_steps = []
    for i in range(len(planned_path) - 1):
        from_page = planned_path[i].get("page", -1)
        subtask_name = planned_path[i].get("subtask", "")
        to_page = planned_path[i + 1].get("page", -1)

        if (from_page, to_page, subtask_name) not in edge_set:
            disconnected_steps.append(i)

    if disconnected_steps:
        log(f":::STEP_VERIFY::: Plan WARN - {len(disconnected_steps)} disconnected step(s)", "yellow")
        return {
            "status": StepVerifyResult.WARN,
            "reason": f"{len(disconnected_steps)} step(s) not connected in Subtask Graph",
            "details": {"path_length": path_length, "disconnected_steps": disconnected_steps}
        }

    log(f":::STEP_VERIFY::: Plan PASS - {path_length} steps, all connected", "green")
    return {
        "status": StepVerifyResult.PASS,
        "reason": f"Plan verified: {path_length} connected steps",
        "details": {"path_length": path_length}
    }
