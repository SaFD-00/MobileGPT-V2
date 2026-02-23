"""Step verification prompts for Subtask Graph 4-Step Workflow.

Currently provides prompt templates for optional LLM-based verification.
Used by step_verify_agent for filter verification when enabled.
"""


def get_filter_verify_prompt(instruction: str, filtered_subtasks: list, all_subtasks: list) -> list:
    """Generate prompt for LLM-based filter verification.

    Asks LLM to verify if filtered subtasks adequately cover
    the instruction's requirements.

    Args:
        instruction: User instruction
        filtered_subtasks: Subtasks that passed filtering
        all_subtasks: All available subtasks

    Returns:
        List of message dicts for LLM API
    """
    filtered_names = [s.get("name", "") for s in filtered_subtasks]
    all_names = [s.get("name", "") for s in all_subtasks]

    system_msg = (
        "You are verifying whether a filtered set of subtasks adequately covers "
        "the requirements of a user instruction. "
        "Respond with JSON: {\"adequate\": true/false, \"missing\": [\"subtask_name\", ...]}"
    )

    user_msg = (
        f"Instruction: {instruction}\n\n"
        f"Filtered subtasks: {filtered_names}\n\n"
        f"All available subtasks: {all_names}\n\n"
        "Are the filtered subtasks adequate to complete the instruction? "
        "If not, which subtasks are missing?"
    )

    return [
        {"role": "system", "content": system_msg},
        {"role": "user", "content": user_msg}
    ]
