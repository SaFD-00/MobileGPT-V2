import json
import os
from copy import deepcopy

from agents import action_summarize_agent, guideline_agent
from agents.prompts import derive_agent_prompt
from memory.memory_manager import Memory
from utils.utils import query, log, parse_completion_rate
from utils import action_utils, parsing_utils


class DeriveAgent:
    """
    서브태스크를 구체적인 액션으로 변환하는 에이전트
    클릭, 입력, 스크롤 등의 상세 액션 생성
    """
    def __init__(self, memory: Memory, instruction: str):
        self.memory = memory
        self.instruction = instruction
        self.subtask = None
        self.subtask_history = []
        self.action_history = []
        self.response_history = []

    def init_subtask(self, subtask: dict, subtask_history: list) -> None:
        """새로운 서브태스크 처리를 위한 초기화"""
        self.subtask = subtask
        self.subtask_history = subtask_history
        self.action_history = []

    def derive(self, screen: str, examples=None) -> (dict, dict):
        """
        현재 화면 상태에서 서브태스크를 수행할 구체적 액션 도출
        Returns:
            action: 실행할 액션 정보
            example: 학습용 예시 데이터
        """
        if examples is None:
            examples = []

        derive_prompt = derive_agent_prompt.get_prompts(self.instruction, self.subtask,
                                                        self.subtask_history + self.action_history, screen, examples)
        response = query(derive_prompt, model=os.getenv("DERIVE_AGENT_GPT_VERSION"))
        response['completion_rate'] = parse_completion_rate(response['completion_rate'])
        self.response_history.append(response)

        # 액션 히스토리에 성공적 실행 기록
        history = "your past response: " + json.dumps(response) + " has been executed successfully."
        self.action_history.append(history)

        example = self.__exemplify(response, screen)
        return response['action'], example

        # 실시간 저장 (현재 비활성화)
        # self.__generalize_and_save_action(response, screen)
        # generalized_action = self.__generalize_action(response, screen)
        # return response['action'], generalized_action

    def add_finish_action(self) -> None:
        """서브태스크 종료 액션 추가"""
        finish_action = {
            "name": "finish",
            "parameters": {},
        }
        self.memory.save_action(self.subtask['name'], finish_action, example=None)

    def summarize_actions(self) -> str:
        """수행한 액션들을 하나의 문장으로 요약"""
        if len(self.response_history) > 0:
            action_summary = action_summarize_agent.summarize_actions(self.response_history)
            self.action_history = []
            self.response_history = []
            return action_summary

    def generate_guideline(self) -> str:
        """서브태스크 수행 과정을 요약하여 guideline 설명 생성

        Returns:
            사람이 읽기 쉬운 guideline 요약 문자열
        """
        if self.subtask is None or len(self.response_history) == 0:
            return ""
        return guideline_agent.summarize_guideline(self.subtask, self.response_history)

    def __exemplify(self, response: dict, screen: str) -> dict:
        """액션을 학습용 예시로 변환"""
        action = response['action']
        example = {}
        if "index" in action['parameters']:
            shrunk_xml = parsing_utils.shrink_screen_xml(screen, int(action['parameters']['index']))
            example = {"instruction": self.instruction, "subtask": json.dumps(self.subtask), "screen": shrunk_xml,
                       "response": json.dumps(response)}
        return example

    def __generalize_and_save_action(self, response: dict, screen) -> None:
        """액션을 일반화하여 재사용 가능하게 만들고 저장"""
        action = response['action']
        example = {}
        if "index" in response['action']['parameters']:
            action = deepcopy(action)
            subtask_arguments = self.subtask['parameters']
            action = action_utils.generalize_action(action, screen, subtask_arguments)

            shrunk_xml = parsing_utils.shrink_screen_xml(screen, int(action['parameters']['index']))
            example = {"instruction": self.instruction, "subtask": json.dumps(self.subtask), "screen": shrunk_xml, "response": json.dumps(response)}


        self.memory.save_action(self.subtask, action, example)

    # ==================== Exploration Mode Methods ====================

    def derive_exploration(self, subtask: dict, screen: str, action_history: list, step: int = 0, max_steps: int = 10) -> dict:
        """
        Exploration 모드에서 서브태스크를 수행할 다음 액션 도출

        Args:
            subtask: 탐색할 서브태스크 정보
            screen: 현재 화면 XML
            action_history: 지금까지 수행한 액션 히스토리
            step: 현재 스텝 번호
            max_steps: 최대 스텝 수

        Returns:
            dict: GPT 응답 (action, reasoning, is_subtask_complete)
        """
        log(":::DERIVE (Exploration):::", "blue")

        # Exploration 전용 프롬프트 사용
        prompts = derive_agent_prompt.get_exploration_prompts(
            subtask, action_history, screen, step, max_steps
        )

        response = query(prompts, model=os.getenv("DERIVE_AGENT_GPT_VERSION"))

        # 응답 로깅
        log(f"Exploration action: {response.get('action', {})}", "cyan")

        return response




