import os
from typing import List

from agents.prompts import guideline_agent_prompt
from utils.utils import query, log


def summarize_guideline(subtask: dict, action_history: list) -> str:
    """
    서브태스크 수행 과정을 요약하여 guideline 설명 생성

    Args:
        subtask: 수행된 서브태스크 정보 (name, description, parameters 등)
        action_history: 수행된 액션들의 목록

    Returns:
        사람이 읽기 쉬운 guideline 요약 문자열
    """
    log(":::GUIDELINE SUMMARIZE:::", "blue")

    if not action_history or len(action_history) == 0:
        return ""

    prompts = guideline_agent_prompt.get_prompts(subtask, action_history)
    response = query(prompts, model=os.getenv("GUIDELINE_AGENT_GPT_VERSION", "gpt-5.2"))

    # response가 문자열인지 확인하고 반환
    if isinstance(response, str):
        return response.strip()
    elif isinstance(response, dict) and 'guideline' in response:
        return response['guideline'].strip()
    else:
        return str(response).strip()


def combine_action_guidances(action_guidances: List[str]) -> str:
    """Combine action-level guidances into subtask-level combined guidance.

    Mobile Map: Aggregates individual action guidances into a coherent
    step-by-step guide for the entire subtask.

    Args:
        action_guidances: List of guidance strings for each action step

    Returns:
        Combined guidance string describing the full subtask flow
        Example: "1. Click search icon to open search dialog.
                  2. Enter query in search field.
                  3. Tap result to view details."
    """
    if not action_guidances:
        return ""

    # Filter out empty guidances
    valid_guidances = [g.strip() for g in action_guidances if g and g.strip()]

    if not valid_guidances:
        return ""

    # Single action - return as is
    if len(valid_guidances) == 1:
        return valid_guidances[0]

    # Multiple actions - combine with step numbers
    combined_parts = []
    for i, guidance in enumerate(valid_guidances, 1):
        # Remove trailing period if present for consistency
        guidance = guidance.rstrip('.')
        combined_parts.append(f"{i}. {guidance}.")

    return " ".join(combined_parts)
