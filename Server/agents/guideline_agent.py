import os

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
