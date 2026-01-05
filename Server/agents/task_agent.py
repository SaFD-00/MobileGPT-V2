import json
import os

import pandas as pd

from agents.prompts import task_agent_prompt
from utils.utils import query, log


class TaskAgent:
    """
    사용자 명령어를 분석하여 구조화된 작업으로 변환하는 에이전트
    작업 이름, 설명, 파라미터, 대상 앱 추출
    """
    def __init__(self):
        self.database_path = f"./memory/tasks.csv"
        if not os.path.exists(self.database_path):
            self.database = pd.DataFrame([], columns=['name', 'description', 'parameters', 'app'])
            self.database.to_csv(self.database_path, index=False)
        else:
            self.database = pd.read_csv(self.database_path, header=0)

    def get_task(self, instruction) -> (dict, bool):
        """
        명령어를 분석하여 작업 객체 생성
        Returns:
            task: 작업 정보 딕셔너리
            is_new: 새 작업 여부
        """
        # 기존에 알려진 작업 목록 가져오기
        known_tasks = self.database.to_dict(orient='records')
        response = query(messages=task_agent_prompt.get_prompts(instruction, known_tasks),
                         model=os.getenv("TASK_AGENT_GPT_VERSION"))

        task = response["api"]
        is_new = True
        # 기존 작업과 일치하면 업데이트, 아니면 새 작업으로 분류
        if str(response["found_match"]).lower() == "true":
            self.update_task(task)
            is_new = False

        return task, is_new

    # 하드코딩 테스트용 코드
    # def get_task(self, instruction) -> (dict, bool):
    #     sample_response = """{"name":"sendGenericMessageToTelegram", "description": "send a generic message to Telegram without specifying a recipient or message content", "parameters":{}, "app": "Telegram"}"""
    #
    #     return json.loads(sample_response), True

    def update_task(self, task):
        """기존 작업의 설명과 파라미터 업데이트"""
        condition = (self.database['name'] == task['name']) & (self.database['app'] == task['app'])
        index_to_update = self.database.index[condition]

        if not index_to_update.empty:
            # 일치하는 행의 'description'과 'parameters' 업데이트
            self.database.loc[index_to_update, 'description'] = task['description']
            self.database.loc[index_to_update, 'parameters'] = task['parameters']
        else:
            # 일치하는 작업을 찾지 못한 경우 처리
            log("No matching task found to update", "red")
