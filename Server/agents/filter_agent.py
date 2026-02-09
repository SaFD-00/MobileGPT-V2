"""Mobile Map: Filter agent for 4-step workflow.

Filters subtasks relevant to user instruction, implementing Step 2 of the
4-step workflow (Load → Filter → Plan → Execute/Replan).

Inspired by UICompass's selective subtask loading approach.
"""

import json
import os
from typing import Any, List, Optional

from agents.prompts import filter_agent_prompt
from utils.utils import query, log


def filter_subtasks(
    instruction: str,
    all_subtasks: List[dict],
    max_results: int = 10
) -> List[dict]:
    """Filter subtasks relevant to instruction.

    Mobile Map 4-Step Workflow - Step 2: Filter
    Takes all available subtasks across pages and returns those most relevant
    to completing the given instruction.

    Args:
        instruction: User's task instruction
        all_subtasks: List of all subtasks from all pages, each containing:
            - name: Subtask name
            - description: What the subtask does
            - page_index: Page where subtask is located
            - page_summary: Summary of the page (optional)
            - combined_guidance: How to perform the subtask (optional)
        max_results: Maximum number of subtasks to return

    Returns:
        List of filtered subtasks relevant to the instruction
    """
    log(f":::FILTER AGENT::: Filtering {len(all_subtasks)} subtasks for instruction", "blue")

    if not all_subtasks:
        log(":::FILTER AGENT::: No subtasks to filter", "yellow")
        return []

    prompts = filter_agent_prompt.get_prompts(
        instruction=instruction,
        subtasks=all_subtasks,
        max_results=max_results
    )

    model = os.getenv("FILTER_AGENT_GPT_VERSION", "gpt-5.2")
    response = query(prompts, model=model)

    # Parse response
    filtered = _parse_filter_response(response, all_subtasks)
    log(f":::FILTER AGENT::: Filtered to {len(filtered)} relevant subtasks", "green")

    return filtered[:max_results]


def _parse_filter_response(response: Any, all_subtasks: List[dict]) -> List[dict]:
    """Parse filter agent response to extract relevant subtasks.

    Args:
        response: LLM response (can be string, dict, or list)
        all_subtasks: Original list of all subtasks

    Returns:
        List of filtered subtask dicts
    """
    # Create lookup by subtask name for quick matching
    subtask_lookup = {}
    for subtask in all_subtasks:
        name = subtask.get("name", "")
        if name:
            if name not in subtask_lookup:
                subtask_lookup[name] = []
            subtask_lookup[name].append(subtask)

    filtered = []

    # Handle different response formats
    if isinstance(response, list):
        # Response is already a list of names or dicts
        for item in response:
            if isinstance(item, str):
                name = item
            elif isinstance(item, dict):
                name = item.get("name", item.get("subtask_name", ""))
            else:
                continue

            if name in subtask_lookup:
                # Add all matching subtasks (could be on multiple pages)
                filtered.extend(subtask_lookup[name])

    elif isinstance(response, dict):
        # Response is a dict with 'subtasks' or 'filtered' key
        items = response.get("subtasks", response.get("filtered", response.get("relevant", [])))
        return _parse_filter_response(items, all_subtasks)

    elif isinstance(response, str):
        # Try to parse as JSON first
        try:
            parsed = json.loads(response)
            return _parse_filter_response(parsed, all_subtasks)
        except json.JSONDecodeError:
            # Parse as newline-separated list of names
            for line in response.strip().split("\n"):
                line = line.strip().strip("-").strip("*").strip()
                if line:
                    # Handle numbered lists like "1. search_emails"
                    parts = line.split(".", 1)
                    if len(parts) > 1 and parts[0].isdigit():
                        line = parts[1].strip()

                    if line in subtask_lookup:
                        filtered.extend(subtask_lookup[line])

    return filtered
