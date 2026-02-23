"""Subtask Graph: Page summary generation prompts.

Generates prompts for describing what a page displays and what users can do.
"""

import json
from typing import List


def get_sys_prompt() -> str:
    """System prompt for page summary generation."""
    sys_msg = (
        "You are an expert at summarizing mobile app screens. "
        "Your task is to describe what the page displays and what actions users can perform.\n\n"

        "***Output Format***:\n"
        "- Write 2-3 sentences (max 100 words)\n"
        "- First sentence: Describe what the page shows/displays\n"
        "- Second sentence: Describe main actions users can take\n"
        "- Use user-friendly language, avoid technical terms\n"
        "- Focus on functionality, not visual appearance\n\n"

        "***Good Examples***:\n"
        "- This page displays the email inbox with a list of received messages. "
        "Users can search for emails, compose new messages, access settings, "
        "and navigate to different folders like sent or drafts.\n\n"

        "- This is the settings menu showing various configuration options. "
        "Users can adjust notifications, manage account settings, change display preferences, "
        "and access help documentation.\n\n"

        "- This page shows the search results for the user's query. "
        "Users can filter results, view item details, add items to cart, "
        "and navigate back to search.\n\n"

        "***Bad Examples (avoid these)***:\n"
        "- This page has a RecyclerView with LinearLayout (too technical)\n"
        "- The screen is blue with white text (describes appearance, not function)\n"
        "- Users can click on many buttons (too vague about what buttons do)\n"
    )
    return sys_msg


def get_usr_prompt(encoded_xml: str, available_subtasks: List[dict]) -> str:
    """User prompt for page summary generation.

    Args:
        encoded_xml: XML representation of the screen
        available_subtasks: List of subtasks available on this page

    Returns:
        User prompt string
    """
    # Extract subtask names and descriptions for context
    subtask_summaries = []
    for subtask in available_subtasks:
        name = subtask.get('name', '')
        description = subtask.get('description', '')
        if name:
            subtask_summaries.append({
                'name': name,
                'description': description
            })

    # Truncate XML if too long
    max_xml_length = 4000
    if len(encoded_xml) > max_xml_length:
        half = max_xml_length // 2
        encoded_xml = encoded_xml[:half] + "\n... [truncated] ...\n" + encoded_xml[-half:]

    usr_msg = (
        "***Screen XML***:\n"
        f"{encoded_xml}\n\n"
    )

    if subtask_summaries:
        usr_msg += (
            "***Available Actions on this Page***:\n"
            f"{json.dumps(subtask_summaries, indent=2)}\n\n"
        )

    usr_msg += (
        "If a screenshot is provided, use it as the primary source for understanding the page.\n\n"
        "Write a brief summary of this page (2-3 sentences, max 100 words):\n"
    )

    return usr_msg


def get_prompts(encoded_xml: str, available_subtasks: List[dict]) -> list:
    """Generate prompts for page summary.

    Args:
        encoded_xml: XML representation of the screen
        available_subtasks: List of subtasks available on this page

    Returns:
        List of message dicts for LLM API
    """
    sys_msg = get_sys_prompt()
    usr_msg = get_usr_prompt(encoded_xml, available_subtasks)
    messages = [
        {"role": "system", "content": sys_msg},
        {"role": "user", "content": usr_msg}
    ]
    return messages
