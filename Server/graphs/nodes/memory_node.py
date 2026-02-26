"""MemoryAgent node for page lookup and subtask loading."""

from graphs.state import TaskState
from loguru import logger


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

    logger.info("Searching for page...")

    # Search for matching page
    page_index, similarity = memory.search_node(
        current_xml, hierarchy_xml, encoded_xml
    )

    if page_index < 0:
        logger.warning(f"No matching page found (similarity: {similarity})")
        return {
            "page_index": -1,
            "available_subtasks": [],
            "rejected_subtasks": [],
            "iteration": 0,
            "status": "no_matching_page",
            "next_agent": "FINISH",
        }

    logger.info(f"Found page {page_index} (similarity: {similarity:.3f})")

    # Initialize page manager and get available subtasks
    memory.init_page_manager(page_index)
    available_subtasks = memory.get_available_subtasks(page_index)

    logger.info(f"Loaded {len(available_subtasks)} available subtasks")

    if not available_subtasks:
        logger.warning("No available subtasks on this page")
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
