"""Verifier node for next screen verification."""

import os
from typing import Any

from pydantic import BaseModel, Field

from inference.schemas.state import InferenceState
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


def verifier_node(state: InferenceState) -> dict:
    """Verifier agent node: verify if selected subtask leads to a good path.

    Checks the destination page/state and uses LLM to determine if we should proceed.

    Args:
        state: Current inference state

    Returns:
        dict: Updated state with verification_passed flag
    """
    memory = state["memory"]
    instruction = state["instruction"]
    selected_subtask = state.get("selected_subtask")
    page_index = state["page_index"]
    state_index = state["state_index"]
    available_subtasks = state["available_subtasks"]

    if not selected_subtask:
        log(":::VERIFIER::: No subtask selected, skipping verification", "yellow")
        return {
            "verification_passed": False,
            "status": "no_subtask_to_verify",
            "next_agent": "FINISH",
        }

    subtask_name = selected_subtask.get("name", "")
    log(f":::VERIFIER::: Verifying subtask '{subtask_name}'", "blue")

    # Handle special subtasks that don't need verification
    if subtask_name in ["finish", "scroll_screen", "speak"]:
        log(f":::VERIFIER::: Special subtask '{subtask_name}' - auto approved", "green")
        return {
            "verification_passed": True,
            "next_page_index": page_index,
            "next_state_index": state_index,
            "next_page_subtasks": [],
            "status": "verified_special",
            "next_agent": "deriver",
        }

    # Get destination page/state for this subtask
    end_page, end_state = memory.get_subtask_destination(page_index, state_index, subtask_name)

    log(f":::VERIFIER::: Subtask '{subtask_name}' leads to page {end_page}, state {end_state}", "blue")

    # If destination is unknown, we can't verify - assume it's okay (unexplored path)
    if end_page < 0:
        log(f":::VERIFIER::: Destination unknown for '{subtask_name}' - auto approved (unexplored)", "yellow")
        return {
            "verification_passed": True,
            "next_page_index": end_page,
            "next_state_index": end_state,
            "next_page_subtasks": [],
            "status": "verified_unexplored",
            "next_agent": "deriver",
        }

    # Get subtasks available on the next screen
    memory.init_page_manager(end_page, end_state)
    next_subtasks = memory.get_available_subtasks(end_page)

    log(f":::VERIFIER::: Next screen has {len(next_subtasks)} subtasks", "blue")

    # Use LLM to verify if this is a good path
    verify_prompts = _create_verify_prompt(
        instruction=instruction,
        selected_subtask=selected_subtask,
        current_subtasks=available_subtasks,
        next_subtasks=next_subtasks
    )

    model = os.getenv("VERIFY_AGENT_GPT_VERSION", os.getenv("SELECT_AGENT_GPT_VERSION", "gpt-5.2-chat-latest"))
    response = query(verify_prompts, model=model)

    should_proceed = response.get("should_proceed", True)
    reasoning = response.get("reasoning", "")

    if should_proceed:
        log(f":::VERIFIER::: APPROVED - {reasoning}", "green")
        return {
            "verification_passed": True,
            "next_page_index": end_page,
            "next_state_index": end_state,
            "next_page_subtasks": next_subtasks,
            "status": "verified_approved",
            "next_agent": "deriver",
        }
    else:
        log(f":::VERIFIER::: REJECTED - {reasoning}", "red")
        return {
            "verification_passed": False,
            "next_page_index": end_page,
            "next_state_index": end_state,
            "next_page_subtasks": next_subtasks,
            "status": "verified_rejected",
            "next_agent": "supervisor",  # Go back to supervisor for reselection
        }
