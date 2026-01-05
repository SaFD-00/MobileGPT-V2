import os

from agents.prompts import usage_agent_prompt
from utils.utils import query, log


def summarize_usage(subtask: dict, action_history: list) -> str:
    """
    서브태스크 수행 과정을 요약하여 usage 설명 생성

    Args:
        subtask: 수행된 서브태스크 정보 (name, description, parameters 등)
        action_history: 수행된 액션들의 목록

    Returns:
        사람이 읽기 쉬운 usage 요약 문자열
    """
    log(":::USAGE SUMMARIZE:::", "blue")

    if not action_history or len(action_history) == 0:
        return ""

    prompts = usage_agent_prompt.get_prompts(subtask, action_history)
    response = query(prompts, model=os.getenv("USAGE_AGENT_GPT_VERSION", "gpt-5-chat-latest"))

    # response가 문자열인지 확인하고 반환
    if isinstance(response, str):
        return response.strip()
    elif isinstance(response, dict) and 'usage' in response:
        return response['usage'].strip()
    else:
        return str(response).strip()
