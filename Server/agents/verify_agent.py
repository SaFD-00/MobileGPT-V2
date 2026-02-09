"""Path verification agent for subtask navigation.

This agent uses LLM to verify whether executing a selected subtask
will help achieve the user's instruction.
"""

import os
from typing import List, Tuple

from pydantic import BaseModel, Field

from utils.utils import log, query


class VerifyDecision(BaseModel):
    """Verification decision from LLM."""
    should_proceed: bool = Field(description="True if should proceed to next screen, False otherwise")
    reasoning: str = Field(description="Reasoning for the decision")


VERIFY_SYSTEM_PROMPT = """You are a mobile app navigation expert. Your task is to verify whether executing a subtask will help achieve the user's instruction.

Given:
1. User's instruction (what they want to achieve)
2. Currently selected subtask
3. Available subtasks on the NEXT screen (after executing the selected subtask)

Decide whether we should proceed with the selected subtask.

Answer "should_proceed": true if:
- The next screen has subtasks that can help achieve the instruction
- The selected subtask is a reasonable step toward the goal
- Going to the next screen brings us closer to completing the instruction

Answer "should_proceed": false if:
- The next screen has no relevant subtasks for the instruction
- The selected subtask leads to a dead end or irrelevant path
- There might be a better subtask on the current screen

Respond in JSON format:
{
    "should_proceed": true/false,
    "reasoning": "Brief explanation of your decision"
}"""


def verify_path(
    instruction: str,
    selected_subtask: dict,
    current_subtasks: List[dict],
    next_subtasks: List[dict],
    current_page_summary: str = "",
    next_page_summary: str = "",
) -> Tuple[bool, str]:
    """Verify if the selected subtask leads to a good path.

    Uses LLM to determine whether proceeding with the selected subtask
    will help achieve the user's instruction.

    Args:
        instruction: User's instruction
        selected_subtask: Currently selected subtask
        current_subtasks: Available subtasks on current screen
        next_subtasks: Available subtasks on next screen (destination)
        current_page_summary: Summary of the current page
        next_page_summary: Summary of the next page

    Returns:
        Tuple[bool, str]: (should_proceed, reasoning)
    """
    verify_prompts = _create_verify_prompt(
        instruction=instruction,
        selected_subtask=selected_subtask,
        current_subtasks=current_subtasks,
        next_subtasks=next_subtasks,
        current_page_summary=current_page_summary,
        next_page_summary=next_page_summary,
    )

    model = os.getenv("VERIFY_AGENT_GPT_VERSION", os.getenv("SELECT_AGENT_GPT_VERSION", "gpt-5.2"))
    response = query(verify_prompts, model=model)

    should_proceed = response.get("should_proceed", True)
    reasoning = response.get("reasoning", "")

    return should_proceed, reasoning


def _create_verify_prompt(instruction: str, selected_subtask: dict,
                          current_subtasks: list, next_subtasks: list,
                          current_page_summary: str = "",
                          next_page_summary: str = "") -> list:
    """Create verification prompt for LLM."""
    page_summary_section = ""
    if current_page_summary:
        page_summary_section += f"\nCurrent Page: {current_page_summary}"
    if next_page_summary:
        page_summary_section += f"\nNext Page: {next_page_summary}"

    user_content = f"""User Instruction: {instruction}

Selected Subtask: {selected_subtask.get('name', 'unknown')}
- Description: {selected_subtask.get('description', 'N/A')}

Current Screen Subtasks:
{_format_subtasks(current_subtasks)}

Next Screen Subtasks (after executing selected subtask):
{_format_subtasks(next_subtasks) if next_subtasks else 'No subtasks available (dead end)'}
{page_summary_section}
Should we proceed with the selected subtask?"""

    return [
        {"role": "system", "content": VERIFY_SYSTEM_PROMPT},
        {"role": "user", "content": user_content}
    ]


def _format_subtasks(subtasks: list) -> str:
    """Format subtask list for prompt."""
    if not subtasks:
        return "None"

    lines = []
    for s in subtasks:
        name = s.get('name', 'unknown')
        desc = s.get('description', 'N/A')
        lines.append(f"- {name}: {desc}")
    return "\n".join(lines)


# ============================================================================
# Adaptive Replanning
# ============================================================================

class PathVerificationResult:
    """Result of path-based verification."""
    PROCEED = "proceed"  # Expected page reached, continue
    SKIP = "skip"       # Ahead in path, skip intermediate steps
    REPLAN = "replan"   # Unexpected page, need to replan


def verify_with_path(
    planned_path: List[dict],
    current_step: int,
    current_page: int
) -> dict:
    """Verify current position against planned path (Adaptive Replanning).

    Compares actual page with expected page from planned_path and decides:
    - PROCEED: On expected page, continue with planned steps
    - SKIP: Jumped ahead in path, skip intermediate steps
    - REPLAN: On unexpected page, need to replan from current position

    Args:
        planned_path: List of planned path steps
        current_step: Current step index in planned_path
        current_page: Actual current page index

    Returns:
        dict: {
            "decision": "proceed" | "skip" | "replan",
            "new_step_index": int (for skip),
            "reason": str
        }
    """
    if not planned_path or current_step >= len(planned_path):
        return {
            "decision": PathVerificationResult.PROCEED,
            "reason": "No path or all steps completed"
        }

    expected_page = planned_path[current_step]["page"]

    # Case 1: On expected page
    if current_page == expected_page:
        return {
            "decision": PathVerificationResult.PROCEED,
            "reason": f"On expected page {expected_page}"
        }

    # Case 2: Check if we jumped ahead in the path
    future_pages = [
        (i, step["page"])
        for i, step in enumerate(planned_path[current_step + 1:], start=current_step + 1)
    ]

    for step_idx, page in future_pages:
        if current_page == page:
            return {
                "decision": PathVerificationResult.SKIP,
                "new_step_index": step_idx,
                "reason": f"Skipped to page {current_page} (was step {step_idx})"
            }

    # Case 3: Completely unexpected page
    return {
        "decision": PathVerificationResult.REPLAN,
        "reason": f"Unexpected page {current_page}, expected {expected_page}"
    }


def _find_step_index_for_page(planned_path: List[dict], target_page: int,
                               start_from: int = 0) -> int:
    """Find the step index for a given page in planned_path."""
    for i, step in enumerate(planned_path[start_from:], start=start_from):
        if step["page"] == target_page:
            return i
    return -1
