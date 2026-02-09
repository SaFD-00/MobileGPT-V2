"""Mobile Map: M3A-style action history generation agent.

Generates human-readable descriptions of what changed after an action,
following the Mobile-Agent-v3 (M3A) approach.

Example output: "Clicked search icon, keyboard appeared and search interface activated"
"""

import os
from typing import Optional

from agents.prompts import history_agent_prompt
from utils.utils import query, query_with_vision, log


def generate_description(
    before_xml: str,
    after_xml: str,
    action: dict,
    before_screenshot_path: Optional[str] = None,
    after_screenshot_path: Optional[str] = None
) -> str:
    """Generate M3A-style action history description.

    Describes what changed after performing an action, based on before/after states.

    Args:
        before_xml: XML representation of screen before action
        after_xml: XML representation of screen after action
        action: The action that was performed (e.g., {"name": "click", "parameters": {...}})
        before_screenshot_path: Path to screenshot before action (optional, for Vision API)
        after_screenshot_path: Path to screenshot after action (optional, for Vision API)

    Returns:
        Human-readable description of what changed (max 50 words)
        Example: "Clicked search icon, keyboard appeared and search interface activated"
    """
    log(":::HISTORY AGENT::: Generating action description", "blue")

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

    model = os.getenv("HISTORY_AGENT_GPT_VERSION", "gpt-4o-mini")

    if screenshot_paths:
        log(f":::HISTORY AGENT::: Using Vision API with {len(screenshot_paths)} screenshot(s)", "cyan")
        response = query_with_vision(
            prompts,
            model=model,
            screenshot_paths=screenshot_paths
        )
    else:
        log(":::HISTORY AGENT::: Using text-only mode (no screenshots)", "yellow")
        response = query(prompts, model=model)

    # Extract description from response
    if isinstance(response, str):
        return response.strip()
    elif isinstance(response, dict) and 'description' in response:
        return response['description'].strip()
    else:
        return str(response).strip()


def generate_guidance(action: dict, screen_xml: str) -> str:
    """Generate semantic guidance for a single action.

    Creates a human-readable explanation of what an action does semantically.

    Args:
        action: The action to describe (e.g., {"name": "click", "parameters": {...}})
        screen_xml: XML representation of the current screen

    Returns:
        Semantic guidance string
        Example: "Click the search icon to open the search dialog"
    """
    log(":::HISTORY AGENT::: Generating action guidance", "blue")

    prompts = history_agent_prompt.get_guidance_prompts(
        action=action,
        screen_xml=screen_xml
    )

    model = os.getenv("HISTORY_AGENT_GPT_VERSION", "gpt-4o-mini")
    response = query(prompts, model=model)

    if isinstance(response, str):
        return response.strip()
    elif isinstance(response, dict) and 'guidance' in response:
        return response['guidance'].strip()
    else:
        return str(response).strip()
