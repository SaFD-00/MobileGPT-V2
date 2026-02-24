"""Subtask Graph: Page summary generation agent.

Generates human-readable summaries of what a page displays and allows users to do.

Example output: "This page displays the inbox with email list. Users can search emails,
compose new messages, access settings, and navigate to different folders."
"""

import os
from typing import List, Optional

from agents.prompts import summary_agent_prompt
from utils.utils import query, query_with_vision, log


def generate_summary(
    encoded_xml: str,
    available_subtasks: List[dict],
    screenshot_path: Optional[str] = None
) -> str:
    """Generate page summary.

    Describes what the page displays and what actions are available to users.

    Args:
        encoded_xml: XML representation of the screen
        available_subtasks: List of subtasks available on this page
        screenshot_path: Path to screenshot (optional, for Vision API)

    Returns:
        Human-readable page summary (max 100 words)
        Example: "This page displays the inbox with email list. Users can search,
                 compose, and access settings."
    """
    log(":::SUMMARY AGENT::: Generating page summary", "blue")

    prompts = summary_agent_prompt.get_prompts(
        encoded_xml=encoded_xml,
        available_subtasks=available_subtasks
    )

    model = os.getenv("SUMMARY_AGENT_GPT_VERSION", "gpt-5.2")

    # Use Vision API if screenshot is available
    if screenshot_path and os.path.exists(screenshot_path):
        log(f":::SUMMARY AGENT::: Using Vision API with screenshot", "cyan")
        response = query_with_vision(
            prompts,
            model=model,
            screenshot_paths=[screenshot_path],
            parse_json=False
        )
    else:
        log(":::SUMMARY AGENT::: Using text-only mode (no screenshot)", "yellow")
        response = query(prompts, model=model, parse_json=False)

    return response
