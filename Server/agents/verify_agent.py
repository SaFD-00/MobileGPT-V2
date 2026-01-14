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
    next_subtasks: List[dict]
) -> Tuple[bool, str]:
    """Verify if the selected subtask leads to a good path.

    Uses LLM to determine whether proceeding with the selected subtask
    will help achieve the user's instruction.

    Args:
        instruction: User's instruction
        selected_subtask: Currently selected subtask
        current_subtasks: Available subtasks on current screen
        next_subtasks: Available subtasks on next screen (destination)

    Returns:
        Tuple[bool, str]: (should_proceed, reasoning)
    """
    verify_prompts = _create_verify_prompt(
        instruction=instruction,
        selected_subtask=selected_subtask,
        current_subtasks=current_subtasks,
        next_subtasks=next_subtasks
    )

    model = os.getenv("VERIFY_AGENT_GPT_VERSION", os.getenv("SELECT_AGENT_GPT_VERSION", "gpt-5.2-chat-latest"))
    response = query(verify_prompts, model=model)

    should_proceed = response.get("should_proceed", True)
    reasoning = response.get("reasoning", "")

    return should_proceed, reasoning


def _create_verify_prompt(instruction: str, selected_subtask: dict,
                          current_subtasks: list, next_subtasks: list) -> list:
    """Create verification prompt for LLM."""
    user_content = f"""User Instruction: {instruction}

Selected Subtask: {selected_subtask.get('name', 'unknown')}
- Description: {selected_subtask.get('description', 'N/A')}

Current Screen Subtasks:
{_format_subtasks(current_subtasks)}

Next Screen Subtasks (after executing selected subtask):
{_format_subtasks(next_subtasks) if next_subtasks else 'No subtasks available (dead end)'}

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
