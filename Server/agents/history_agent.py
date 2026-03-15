"""Subtask Graph: Action history generation agent.

Generates:
- Description: WHY an action was performed + WHAT changed after it.
  Example: "To open the search feature, clicked the search icon; keyboard appeared and search interface activated"
- Guideline: HOW to perform the action on the screen.
  Example: "Click the magnifying glass icon in the top-right toolbar"
"""

import os
from typing import Optional

from agents.prompts import history_agent_prompt
from loguru import logger
from utils.utils import query, query_with_vision


def generate_description(
    before_xml: str,
    after_xml: str,
    action: dict,
    before_screenshot_path: Optional[str] = None,
    after_screenshot_path: Optional[str] = None
) -> str:
    """Generate action description (WHY + WHAT changed).

    Explains why an action was performed and what changed after it, based on before/after states.

    Args:
        before_xml: XML representation of screen before action
        after_xml: XML representation of screen after action
        action: The action that was performed (e.g., {"name": "click", "parameters": {...}})
        before_screenshot_path: Path to screenshot before action (optional, for Vision API)
        after_screenshot_path: Path to screenshot after action (optional, for Vision API)

    Returns:
        Human-readable description of purpose and result (max 50 words)
        Example: "To open the search feature, clicked the search icon; keyboard appeared and search interface activated"
    """
    logger.info("Generating action description")

    prompts = history_agent_prompt.get_prompts(
        before_xml=before_xml,
        after_xml=after_xml,
        action=action
    )

    # Use Vision API if screenshots are available
    screenshot_paths = []
    if before_screenshot_path and os.path.exists(before_screenshot_path):
        screenshot_paths.append(before_screenshot_path)
    if after_screenshot_path and os.path.exists(after_screenshot_path):
        screenshot_paths.append(after_screenshot_path)

    model = os.getenv("HISTORY_AGENT_GPT_VERSION", "gpt-5.4")

    if screenshot_paths:
        logger.debug(f"Using Vision API with {len(screenshot_paths)} screenshot(s)")
        response = query_with_vision(
            prompts,
            model=model,
            screenshot_paths=screenshot_paths,
            parse_json=False
        )
    else:
        logger.warning("Using text-only mode (no screenshots)")
        response = query(prompts, model=model, parse_json=False)

    return response


def generate_guidance(action: dict, screen_xml: str) -> str:
    """Generate HOW-to guideline for a single action.

    Creates a human-readable instruction for how to perform the action on the screen.

    Args:
        action: The action to describe (e.g., {"name": "click", "parameters": {...}})
        screen_xml: XML representation of the current screen

    Returns:
        HOW-to guideline string describing the UI element and interaction method
        Example: "Click the magnifying glass icon in the top-right toolbar"
    """
    logger.info("Generating action guidance")

    prompts = history_agent_prompt.get_guidance_prompts(
        action=action,
        screen_xml=screen_xml
    )

    model = os.getenv("HISTORY_AGENT_GPT_VERSION", "gpt-5.4")
    response = query(prompts, model=model, parse_json=False)

    return response
