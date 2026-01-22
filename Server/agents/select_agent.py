import json
import os

from agents.prompts import select_agent_prompt
from memory.memory_manager import Memory
from utils.utils import query, query_with_vision, log, parse_completion_rate


class SelectAgent:
    """
    사용 가능한 서브태스크 중 최적의 것을 선택하는 에이전트
    현재 상황과 목표를 고려하여 다음 동작 결정
    """
    def __init__(self, memory: Memory, instruction: str):
        self.memory = memory
        self.instruction = instruction

    def select(self, available_subtasks: list, subtask_history: list, qa_history: list,
               screen: str, screenshot_path: str = None) -> (dict, dict):
        """
        주어진 옵션 중 최적의 서브태스크 선택
        Args:
            available_subtasks: 사용 가능한 서브태스크 목록
            subtask_history: 서브태스크 실행 히스토리
            qa_history: Q&A 히스토리
            screen: 현재 화면 XML
            screenshot_path: 스크린샷 파일 경로 (Vision API용)
        Returns:
            response: 선택 결과 응답
            new_action: 새로 생성된 액션 (있을 경우)
        """
        log(f":::SELECT:::", "blue")
        has_screenshot = screenshot_path is not None
        select_prompts = select_agent_prompt.get_prompts(
            self.instruction, available_subtasks, subtask_history,
            qa_history, screen, has_screenshot=has_screenshot
        )
        response = query_with_vision(
            select_prompts, model=os.getenv("SELECT_AGENT_GPT_VERSION"),
            screenshot_path=screenshot_path
        )
        # 유효한 응답이 나올 때까지 재시도
        while not self.__check_response_validity(response, available_subtasks):
            assistant_msg = {"role": "assistant", "content": json.dumps(response)}
            select_prompts.append(assistant_msg)

            # 오류 메시지 추가하여 다시 요청
            error_msg = {"role": "user", "content": "Error: The selected action is not in the available actions list."}
            select_prompts.append(error_msg)
            response = query(select_prompts, model=os.getenv("SELECT_AGENT_GPT_VERSION"))

        next_subtask_filled = response['action']
        for subtask in available_subtasks:
            if subtask['name'] == next_subtask_filled['name']:
                next_subtask_raw = subtask
                self.__save_as_example(next_subtask_raw, screen, response)
        if "new_action" in response:
            return response, response['new_action']
        else:
            return response, None

    def __check_response_validity(self, response, available_subtasks):
        """선택된 액션이 사용 가능한 목록에 있는지 확인"""
        action = response['action']

        # 선택된 액션이 사용 가능한 서브태스크에 있는지 확인
        subtask_match = False
        # 기본 액션들은 항상 허용
        if action['name'] in ['scroll_screen', 'finish', 'speak']:
            subtask_match = True
            return True

        for subtask in available_subtasks:
            if subtask['name'] == action['name']:
                subtask_match = True
                return True

        if not subtask_match:
            # 새로운 액션인 경우 사용 가능한 서브태스크에 추가
            if "new_action" in response:
                new_action = response['new_action']
                available_subtasks.append(new_action)
                return True

            # 선택된 액션이 목록에 없고 새 액션도 제공되지 않으면 오류
            else:
                return False

    def __save_as_example(self, subtask_raw, screen, response):
        """선택 결과를 학습용 예시로 저장"""
        del response['completion_rate']
        example = {"instruction": self.instruction, "screen": screen, "response": response}
        self.memory.save_subtask(subtask_raw, example)
