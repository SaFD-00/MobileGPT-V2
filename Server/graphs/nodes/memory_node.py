"""MemoryAgent node for page lookup and subtask loading."""

from typing import Any

from graphs.state import TaskState
from utils.utils import log


def memory_node(state: TaskState) -> dict:
    """Memory agent node: search page and load available subtasks.

    Args:
        state: Current task state

    Returns:
        dict: Updated state with page_index, available_subtasks
    """
    memory = state["memory"]
    current_xml = state["current_xml"]
    hierarchy_xml = state.get("hierarchy_xml", "")
    encoded_xml = state.get("encoded_xml", "")

    log(":::MEMORY_AGENT::: Searching for page...", "blue")

    # Search for matching page
    page_index, similarity = memory.search_node(
        current_xml, hierarchy_xml, encoded_xml
    )

    if page_index < 0:
        log(f":::MEMORY_AGENT::: No matching page found (similarity: {similarity})", "yellow")
        return {
            "page_index": -1,
            "available_subtasks": [],
            "rejected_subtasks": [],
            "iteration": 0,
            "status": "no_matching_page",
            "next_agent": "FINISH",
        }

    log(f":::MEMORY_AGENT::: Found page {page_index} (similarity: {similarity:.3f})", "green")

    # Initialize page manager and get available subtasks
    memory.init_page_manager(page_index)
    available_subtasks = memory.get_available_subtasks(page_index)

    log(f":::MEMORY_AGENT::: Loaded {len(available_subtasks)} available subtasks", "blue")

    if not available_subtasks:
        log(":::MEMORY_AGENT::: No available subtasks on this page", "yellow")
        return {
            "page_index": page_index,
            "available_subtasks": [],
            "rejected_subtasks": [],
            "iteration": 0,
            "status": "no_subtasks",
            "next_agent": "FINISH",
        }

    return {
        "page_index": page_index,
        "available_subtasks": available_subtasks,
        "rejected_subtasks": [],
        "iteration": 0,
        "status": "subtasks_loaded",
        "next_agent": "planner",
    }
