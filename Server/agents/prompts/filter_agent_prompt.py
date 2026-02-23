"""Subtask Graph: Filter agent prompts for 4-step workflow.

Generates prompts for filtering subtasks relevant to user instruction.
"""

import json
from typing import List


def get_sys_prompt() -> str:
    """System prompt for subtask filtering."""
    sys_msg = (
        "You are an expert at understanding user intentions and matching them to available actions. "
        "Your task is to select subtasks that are relevant to completing the user's instruction.\n\n"

        "***Output Format***:\n"
        "Return a JSON array of subtask names that are relevant to the instruction.\n"
        "Example: [\"search_emails\", \"view_email_details\", \"compose_email\"]\n\n"

        "***Selection Criteria***:\n"
        "- Select subtasks directly needed to complete the instruction\n"
        "- Include navigation subtasks if needed to reach the target\n"
        "- Consider the page_summary to understand what subtasks are available where\n"
        "- Order subtasks by relevance (most relevant first)\n"
        "- Do NOT include subtasks unrelated to the instruction\n\n"

        "***Guidelines***:\n"
        "- If the instruction is about searching, include search-related subtasks\n"
        "- If the instruction involves multiple steps, include all necessary subtasks\n"
        "- Consider alternative paths if multiple subtasks achieve similar goals\n"
        "- Be conservative - only include clearly relevant subtasks\n"
    )
    return sys_msg


def get_usr_prompt(instruction: str, subtasks: List[dict], max_results: int) -> str:
    """User prompt for subtask filtering.

    Args:
        instruction: User's task instruction
        subtasks: List of all available subtasks
        max_results: Maximum number of subtasks to return

    Returns:
        User prompt string
    """
    # Simplify subtask info for prompt
    subtask_summaries = []
    for subtask in subtasks:
        summary = {
            "name": subtask.get("name", ""),
            "description": subtask.get("description", ""),
            "page_index": subtask.get("page_index", -1),
        }
        if subtask.get("page_summary"):
            summary["page_summary"] = subtask["page_summary"][:100]  # Truncate
        if subtask.get("guideline"):
            summary["guideline"] = subtask["guideline"][:100]  # Truncate
        subtask_summaries.append(summary)

    usr_msg = (
        f"***User Instruction***:\n{instruction}\n\n"

        "***Available Subtasks***:\n"
        f"{json.dumps(subtask_summaries, indent=2)}\n\n"

        f"Select up to {max_results} subtasks most relevant to the instruction.\n"
        "Return ONLY a JSON array of subtask names, no explanation:\n"
    )

    return usr_msg


def get_prompts(instruction: str, subtasks: List[dict], max_results: int = 10) -> list:
    """Generate prompts for subtask filtering.

    Args:
        instruction: User's task instruction
        subtasks: List of all available subtasks
        max_results: Maximum number of subtasks to return

    Returns:
        List of message dicts for LLM API
    """
    sys_msg = get_sys_prompt()
    usr_msg = get_usr_prompt(instruction, subtasks, max_results)
    messages = [
        {"role": "system", "content": sys_msg},
        {"role": "user", "content": usr_msg}
    ]
    return messages
