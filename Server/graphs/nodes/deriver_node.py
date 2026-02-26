"""Deriver node for action derivation (wraps DeriveAgent)."""

from agents.derive_agent import DeriveAgent
from graphs.state import TaskState
from loguru import logger


def deriver_node(state: TaskState) -> dict:
    """Deriver agent node: derive concrete action from selected subtask.

    Uses DeriveAgent to convert the selected subtask into an executable action.

    Args:
        state: Current task state

    Returns:
        dict: Updated state with action
    """
    memory = state["memory"]
    instruction = state["instruction"]
    selected_subtask = state.get("selected_subtask")
    current_xml = state["current_xml"]

    if not selected_subtask:
        logger.error("No subtask selected, cannot derive action")
        return {
            "action": None,
            "status": "no_subtask_for_derive",
            "next_agent": "FINISH",
        }

    subtask_name = selected_subtask.get("name", "")
    logger.info(f"Deriving action for subtask '{subtask_name}'")

    # Handle special subtasks directly
    if subtask_name == "finish":
        logger.info("Returning finish action")
        return {
            "action": {"name": "finish", "parameters": {}},
            "status": "action_derived",
            "next_agent": "FINISH",
        }

    if subtask_name == "scroll_screen":
        # Use default scroll parameters or from subtask
        params = selected_subtask.get("parameters", {})
        scroll_action = {
            "name": "scroll_screen",
            "parameters": {
                "scroll_ui_index": params.get("scroll_ui_index", 1),
                "direction": params.get("direction", "down")
            }
        }
        logger.info(f"Returning scroll action: {scroll_action}")
        return {
            "action": scroll_action,
            "status": "action_derived",
            "next_agent": "FINISH",
        }

    if subtask_name == "speak":
        params = selected_subtask.get("parameters", {})
        speak_action = {
            "name": "speak",
            "parameters": params
        }
        logger.info(f"Returning speak action: {speak_action}")
        return {
            "action": speak_action,
            "status": "action_derived",
            "next_agent": "FINISH",
        }

    # Use DeriveAgent for regular subtasks
    derive_agent = DeriveAgent(memory, instruction)
    derive_agent.init_subtask(selected_subtask, [])

    # Check if there's a pre-learned action in memory
    page_index = state["page_index"]
    next_action = memory.get_next_action(page_index, [], current_xml)

    if next_action and "examples" not in next_action:
        # Use pre-learned action
        logger.info(f"Using pre-learned action: {next_action}")
        return {
            "action": next_action,
            "status": "action_derived",
            "next_agent": "FINISH",
        }

    # Derive new action using LLM
    examples = next_action.get("examples", []) if next_action else []
    screenshot_path = state.get("screenshot_path")
    action, example = derive_agent.derive(current_xml, examples, screenshot_path=screenshot_path)

    logger.info(f"Derived action: {action}")

    return {
        "action": action,
        "status": "action_derived",
        "next_agent": "FINISH",
    }
