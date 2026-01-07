import os

from agents.prompts import param_fill_agent_prompt
from utils.utils import query, log


def parm_fill_subtask(instruction: str, subtask: dict, qa_history: list, screen: str, example: dict):
    """
    서브태스크의 비어있는 파라미터를 컨텍스트에서 추출하여 채우기

    Args:
        instruction: 사용자 명령어
        subtask: 파라미터를 채울 서브태스크
        qa_history: Q&A 히스토리
        screen: 현재 화면 XML
        example: 참고할 예시 데이터
    Returns:
        채워진 파라미터 딕셔너리
    """
    prompts = param_fill_agent_prompt.get_prompts(instruction, subtask, qa_history, screen, example)
    # 예시가 있으면 학습된 모델 사용, 없으면 gpt-5-chat-latest 사용
    if len(example) > 0:
     response = query(prompts, model=os.getenv("PARAMETER_FILLER_AGENT_GPT_VERSION"))
    else:
        response = query(prompts, model="gpt-5.2-chat-latest")
    return response
