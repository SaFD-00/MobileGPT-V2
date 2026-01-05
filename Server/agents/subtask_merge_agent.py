import os

from agents.prompts import subtask_merge_prompt
from utils.utils import query, log


def merge_subtasks(subtask_history: list):
    """
    중복되거나 유사한 서브태스크들을 병합하여 효율적으로 정리

    Args:
        subtask_history: 수행된 서브태스크 목록
    Returns:
        병합된 서브태스크 목록
    """
    prompts = subtask_merge_prompt.get_prompts(subtask_history)
    response = query(prompts, model=os.getenv("SUBTASK_MERGE_AGENT_GPT_VERSION"), is_list=True)
    return response
