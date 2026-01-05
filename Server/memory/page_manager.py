import json
import os

import pandas as pd

from agents import param_fill_agent
from utils.action_utils import adapt_action
from utils.utils import log


def init_database(path: str, headers: list):
    """데이터베이스 초기화 - CSV 파일 생성 또는 로드"""
    if not os.path.exists(path) or os.path.getsize(path) == 0:
        # 파일이 없거나 빈 파일인 경우 새로 생성
        database = pd.DataFrame([], columns=headers)
        database.to_csv(path, index=False)
    else:
        try:
            database = pd.read_csv(path)
        except pd.errors.EmptyDataError:
            # 파일은 있지만 파싱할 데이터가 없는 경우
            database = pd.DataFrame([], columns=headers)
            database.to_csv(path, index=False)
    return database


class PageManager:
    """각 페이지(화면 상태)에서의 서브태스크와 액션을 관리하는 클래스"""
    def __init__(self, page_path, page_index):
        self.page_index = page_index

        subtask_header = ['name', 'start', 'end', 'description', 'usage', 'parameters', 'example']
        action_header = ['subtask_name', 'trigger_ui_index', 'step', 'action', 'example']
        available_subtask_header = ['name', 'description', 'parameters', 'exploration']

        if not os.path.exists(page_path + f"/{page_index}/"):
            os.makedirs(page_path + f"/{page_index}/")

        self.subtask_db_path = page_path + f"{page_index}/subtasks.csv"
        self.subtask_db = init_database(self.subtask_db_path, subtask_header)

        # Fill missing 'usage' values with empty string for backward compatibility
        if 'usage' not in self.subtask_db.columns:
            self.subtask_db['usage'] = ''
        else:
            self.subtask_db['usage'] = self.subtask_db['usage'].fillna('')

        # Fill missing 'start' and 'end' values with -1 for backward compatibility
        if 'start' not in self.subtask_db.columns:
            self.subtask_db['start'] = -1
        else:
            self.subtask_db['start'] = self.subtask_db['start'].fillna(-1).astype(int)
        if 'end' not in self.subtask_db.columns:
            self.subtask_db['end'] = -1
        else:
            self.subtask_db['end'] = self.subtask_db['end'].fillna(-1).astype(int)

        self.available_subtask_db_path = page_path + f"{page_index}/available_subtasks.csv"
        self.available_subtask_db = init_database(self.available_subtask_db_path, available_subtask_header)

        # Fill missing 'exploration' values with 'unexplored' for backward compatibility
        if 'exploration' in self.available_subtask_db.columns:
            self.available_subtask_db['exploration'] = self.available_subtask_db['exploration'].fillna('unexplored')

        self.action_db_path = page_path + f"{page_index}/actions.csv"
        self.action_db = init_database(self.action_db_path, action_header)

        # Fill missing 'trigger_ui_index' with -1 for backward compatibility
        if 'trigger_ui_index' not in self.action_db.columns:
            self.action_db['trigger_ui_index'] = -1
        else:
            self.action_db['trigger_ui_index'] = self.action_db['trigger_ui_index'].fillna(-1).astype(int)

        self.action_data = self.action_db.to_dict(orient='records')

        for action in self.action_data:
            action['traversed'] = False

    def get_available_subtasks(self):
        """사용 가능한 서브태스크 목록 반환 (subtasks.csv에서 usage 정보 병합)"""
        available_subtasks = self.available_subtask_db.to_dict(orient='records')

        # subtasks.csv에서 usage 정보 가져와서 병합
        for subtask in available_subtasks:
            subtask_name = subtask.get('name')
            if subtask_name:
                learned_subtask = self.subtask_db[self.subtask_db['name'] == subtask_name]
                if not learned_subtask.empty:
                    usage = learned_subtask.iloc[0].get('usage', '')
                    if usage and pd.notna(usage):
                        subtask['usage'] = usage

        return available_subtasks

    def add_new_action(self, new_action):
        """새로운 액션 추가"""
        if 'exploration' not in new_action:
            new_action['exploration'] = 'unexplored'
        self.available_subtask_db = pd.concat([self.available_subtask_db, pd.DataFrame([new_action])], ignore_index=True)
        self.available_subtask_db.to_csv(self.available_subtask_db_path, index=False)

    def mark_subtask_explored(self, subtask_name: str, ui_info: dict = None,
                              action: dict = None, screen: str = None,
                              trigger_ui_index: int = -1,
                              start_page: int = -1, end_page: int = -1):
        """Mark a subtask as explored and register it in subtasks.csv + actions.csv

        Args:
            subtask_name: 탐험 완료된 서브태스크 이름
            ui_info: 클릭된 UI 정보 (usage 생성용)
            action: 수행된 액션 (actions.csv 저장용)
            screen: 화면 XML (액션 일반화용)
            trigger_ui_index: 트리거 UI 인덱스
            start_page: 서브태스크 시작 페이지 인덱스
            end_page: 서브태스크 종료 페이지 인덱스
        """
        condition = (self.available_subtask_db['name'] == subtask_name)
        if condition.any():
            # Update exploration status in available_subtasks
            self.available_subtask_db.loc[condition, 'exploration'] = 'explored'
            self.available_subtask_db.to_csv(self.available_subtask_db_path, index=False)

            # Get subtask data and register in subtasks.csv
            subtask_row = self.available_subtask_db[condition].iloc[0]
            subtask_data = {
                'name': subtask_row['name'],
                'description': subtask_row['description'],
                'parameters': subtask_row['parameters'] if isinstance(subtask_row['parameters'], dict) else {}
            }

            # Generate usage from UI info
            usage = self._generate_usage_from_ui(ui_info)

            self.save_subtask(subtask_data, {}, usage, start_page, end_page)
            log(f"Subtask '{subtask_name}' marked as explored and registered in subtasks.csv")

            # === actions.csv에 액션 저장 ===
            if action is not None and screen is not None:
                from utils.action_utils import generalize_action

                # 서브태스크 정보 구성
                params = subtask_row['parameters']
                if isinstance(params, str):
                    try:
                        params = json.loads(params)
                    except (json.JSONDecodeError, TypeError):
                        params = {}
                elif not isinstance(params, dict):
                    params = {}

                subtask_dict = {
                    'name': subtask_name,
                    'description': subtask_row['description'],
                    'parameters': params
                }

                # 액션 일반화 (LEARN 모드와 동일)
                generalized_action = generalize_action(action, subtask_dict, screen)

                # actions.csv에 저장 (step=0: 첫 번째 액션)
                self.save_action(subtask_name, trigger_ui_index, 0, generalized_action, {})

                # finish 액션도 저장 (서브태스크 완료 표시)
                finish_action = {"name": "finish", "parameters": {}}
                self.save_action(subtask_name, trigger_ui_index, 1, finish_action, {})

                log(f"Action saved for subtask '{subtask_name}' (trigger_ui={trigger_ui_index}) in actions.csv")

    def _generate_usage_from_ui(self, ui_info: dict) -> str:
        """UI 정보로부터 usage 문자열 생성

        Args:
            ui_info: UI 정보 딕셔너리

        Returns:
            str: usage 설명 문자열
        """
        if not ui_info:
            return ""

        # ui_info structure: {"self": {...}, "parent": {...}, "children": [...], "index": N}
        ui_self = ui_info.get('self', {})
        ui_description = ui_self.get('description', '')
        ui_id = ui_self.get('id', '')
        ui_tag = ui_self.get('tag', '')
        ui_class = ui_self.get('class', '')

        # Build usage description based on available UI info
        if ui_description and ui_description != 'NONE':
            return f"Triggered by clicking '{ui_description}'"
        elif ui_id and ui_id != 'NONE':
            return f"Triggered by clicking '{ui_id}'"
        elif ui_tag:
            return f"Triggered by clicking {ui_tag} element"
        elif ui_class:
            return f"Triggered by clicking {ui_class} element"
        return ""

    def mark_subtask_explored_multistep(self, page_index: int, subtask_name: str,
                                         subtask_info: dict, actions: list,
                                         trigger_ui_index: int = -1,
                                         start_page: int = -1, end_page: int = -1):
        """Multi-step 탐색 완료 후 특정 trigger UI 경로의 액션 저장

        Args:
            page_index: 페이지 인덱스
            subtask_name: 서브태스크 이름
            subtask_info: 서브태스크 정보 (name, description, parameters)
            actions: 수행된 액션 리스트 [{step, action, screen, reasoning?}, ...]
            trigger_ui_index: 트리거 UI 인덱스 (같은 서브태스크의 다른 경로 구분용)
            start_page: 시작 페이지 인덱스
            end_page: 종료 페이지 인덱스
        """
        from agents import usage_agent
        from utils.action_utils import generalize_action

        # 1. GPT 기반 usage 생성
        usage = ""
        if actions and len(actions) > 0:
            # action_history 형식으로 변환 (usage_agent가 기대하는 형식)
            action_history = []
            for action_data in actions:
                action = action_data.get('action', {})
                reasoning = action_data.get('reasoning', '')
                action_history.append({
                    'action': action,
                    'reasoning': reasoning
                })
            usage = usage_agent.summarize_usage(subtask_info, action_history)
            log(f"Generated usage for '{subtask_name}' (trigger_ui={trigger_ui_index}): {usage}")

        # 2. subtasks.csv에 저장 (서브태스크 정보는 한 번만 저장)
        subtask_data = {
            'name': subtask_name,
            'description': subtask_info.get('description', ''),
            'parameters': subtask_info.get('parameters', {})
        }
        self.save_subtask(subtask_data, {}, usage, start_page, end_page)

        # 3. 기존 액션 삭제 - (subtask_name, trigger_ui_index) 조합으로 중복 방지
        self.action_db = self.action_db[
            ~((self.action_db['subtask_name'] == subtask_name) &
              (self.action_db['trigger_ui_index'] == trigger_ui_index))
        ]
        self.action_db.to_csv(self.action_db_path, index=False)

        # 4. actions.csv에 모든 액션 저장
        for action_data in actions:
            step = action_data.get('step', 0)
            action = action_data.get('action', {})
            screen = action_data.get('screen', '')

            # 액션 일반화
            if 'index' in action.get('parameters', {}):
                generalized_action = generalize_action(action, subtask_info, screen)
            else:
                generalized_action = action

            self.save_action(subtask_name, trigger_ui_index, step, generalized_action, {})

        # 5. finish 액션 추가
        finish_step = len(actions)
        finish_action = {"name": "finish", "parameters": {}}
        self.save_action(subtask_name, trigger_ui_index, finish_step, finish_action, {})

        log(f"Saved {len(actions) + 1} actions for subtask '{subtask_name}' (trigger_ui={trigger_ui_index}) in actions.csv")

    def mark_subtask_fully_explored(self, subtask_name: str):
        """서브태스크의 모든 trigger UI 탐색 완료 후 explored로 마킹

        Args:
            subtask_name: 서브태스크 이름
        """
        condition = (self.available_subtask_db['name'] == subtask_name)
        if condition.any():
            self.available_subtask_db.loc[condition, 'exploration'] = 'explored'
            self.available_subtask_db.to_csv(self.available_subtask_db_path, index=False)
            log(f"Marked subtask '{subtask_name}' as fully explored in available_subtasks.csv")

    def get_subtask_by_name(self, subtask_name: str) -> dict:
        """Get subtask data by name from available_subtasks

        Args:
            subtask_name: 조회할 서브태스크 이름

        Returns:
            dict: 서브태스크 정보 딕셔너리, 없으면 None
        """
        condition = (self.available_subtask_db['name'] == subtask_name)
        if condition.any():
            row = self.available_subtask_db[condition].iloc[0]
            return row.to_dict()
        return None

    def save_subtask(self, subtask_raw: dict, example: dict, usage: str = "",
                     start_page: int = -1, end_page: int = -1):
        """서브태스크 정보를 데이터베이스에 저장

        Args:
            subtask_raw: 서브태스크 정보 딕셔너리 (name, description, parameters)
            example: 학습용 예시 정보
            usage: 서브태스크 사용 방법 요약 설명
            start_page: 서브태스크 시작 페이지 인덱스
            end_page: 서브태스크 종료 페이지 인덱스
        """
        filtered_subtask = self.subtask_db[(self.subtask_db['name'] == subtask_raw['name'])]
        if len(filtered_subtask) == 0:
            # 새로운 서브태스크 삽입
            subtask_data = {
                "name": subtask_raw['name'],
                "start": start_page,
                "end": end_page,
                "description": subtask_raw['description'],
                "usage": usage,
                "parameters": json.dumps(subtask_raw['parameters']),
                "example": json.dumps(example)
            }

            self.subtask_db = pd.concat([self.subtask_db, pd.DataFrame([subtask_data])], ignore_index=True)
            self.subtask_db.to_csv(self.subtask_db_path, index=False)
            log("added new subtask to the database")
        else:
            # 이미 존재하는 서브태스크: start/end가 -1이고 새 값이 있으면 업데이트
            condition = (self.subtask_db['name'] == subtask_raw['name'])
            existing_start = self.subtask_db.loc[condition, 'start'].iloc[0]
            existing_end = self.subtask_db.loc[condition, 'end'].iloc[0]

            if (existing_start == -1 and start_page != -1) or (existing_end == -1 and end_page != -1):
                if start_page != -1:
                    self.subtask_db.loc[condition, 'start'] = start_page
                if end_page != -1:
                    self.subtask_db.loc[condition, 'end'] = end_page
                self.subtask_db.to_csv(self.subtask_db_path, index=False)
                log("updated subtask start/end in the database")

    def get_next_subtask_data(self, subtask_name: str) -> dict:
        """특정 서브태스크 데이터 반환"""
        # 특정 'name'에 해당하는 행 필터링
        filtered_subtask = self.subtask_db[(self.subtask_db['name'] == subtask_name)]
        next_subtask_data = filtered_subtask.iloc[0].to_dict()

        return next_subtask_data

    def save_action(self, subtask_name, trigger_ui_index: int, step: int, action: dict, example=None) -> None:
        """액션 정보를 데이터베이스에 저장

        Args:
            subtask_name: 서브태스크 이름
            trigger_ui_index: 트리거 UI 인덱스 (같은 서브태스크의 다른 경로 구분용)
            step: 액션 스텝 번호
            action: 액션 정보 딕셔너리
            example: 학습용 예시 데이터
        """
        if example is None:
            example = {}
        new_action_db = {
            "subtask_name": subtask_name,
            "trigger_ui_index": trigger_ui_index,
            'step': step,
            "action": json.dumps(action),
            "example": json.dumps(example)
        }

        # CSV 파일에 기록
        self.action_db = pd.concat([self.action_db, pd.DataFrame([new_action_db])], ignore_index=True)
        self.action_db.to_csv(self.action_db_path, index=False)

        # 액션 데이터에 추가
        new_action_data = {
            "subtask_name": subtask_name,
            "trigger_ui_index": trigger_ui_index,
            'step': step,
            "action": json.dumps(action),
            "example": json.dumps(example),
            "traversed": True
        }
        self.action_data.append(new_action_data)

    def get_next_action(self, subtask: dict, screen: str, step: int):
        """현재 서브태스크에서 다음 액션 반환"""
        curr_subtask_name = subtask['name']
        examples = []
        for action_data in self.action_data:
            if action_data.get("subtask_name", "") == curr_subtask_name and action_data.get("step") == step:
                if not action_data.get("traversed", False):
                    action_data['traversed'] = True
                    next_base_action = json.loads(action_data.get("action"))
                    examples.append(json.loads(action_data.get("example")))

                    subtask_arguments = subtask['parameters']
                    adapted_action = adapt_action(next_base_action, screen, subtask_arguments)
                    if adapted_action:
                        return adapted_action

        if len(examples) > 0:
            return {"examples": examples}

        return None

    def update_subtask_info(self, subtask) -> None:
        """서브태스크 정보 업데이트"""
        condition = (self.subtask_db['name'] == subtask['name'])
        if condition.any():
            self.subtask_db.loc[condition, 'name'] = subtask['name']
            self.subtask_db.loc[condition, 'description'] = subtask['description']
            self.subtask_db.loc[condition, 'parameters'] = json.dumps(subtask['parameters'])

            self.subtask_db.to_csv(self.subtask_db_path, index=False)

    def merge_subtask_into(self, base_subtask_name, prev_subtask_name, target_subtask_name):
        """두 서브태스크를 하나로 병합"""
        actions = self.action_db.to_dict(orient="records")
        starting_step = 0

        for action in actions[:]:  # 리스트 복사본으로 순회
            subtask_name = action['subtask_name']
            action_data = json.loads(action['action'])
            if subtask_name == prev_subtask_name and action_data['name'] == 'finish':
                starting_Step = action['step']
                actions.remove(action)

        for action in actions[:]:
            subtask_name = action['subtask_name']
            if subtask_name == target_subtask_name:
                action['subtask_name'] = base_subtask_name
                action['step'] = starting_step + action['step']

        self.action_db = pd.DataFrame(actions)
        self.action_db.to_csv(self.action_db_path, index=False)
