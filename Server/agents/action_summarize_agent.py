import os

from agents.prompts import action_summarize_prompt
from utils.utils import query


def summarize_actions(action_history: list):
    """
    수행한 액션 기록을 요약하여 간단한 문장으로 반환
    Args:
        action_history: 수행한 액션들의 목록
    Returns:
        요약된 문자열
    """
    prompts = action_summarize_prompt.get_prompts(action_history)
    response = query(prompts, model=os.getenv("ACTION_SUMMARIZE_AGENT_GPT_VERSION"))
    return response