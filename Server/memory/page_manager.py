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
    def __init__(self, page_path, page_index, state_index: int = 0):
        self.page_index = page_index
        self.state_index = state_index  # [NEW] State 지원

        subtask_header = ['name', 'description', 'guideline', 'parameters', 'example']
        # [MODIFIED] 컬럼명 변경: start -> start_page, end -> end_page
        action_header = ['subtask_name', 'trigger_ui_index', 'step',
                        'start_page', 'start_state', 'end_page', 'end_state',
                        'action', 'example']
        available_subtask_header = ['name', 'description', 'parameters', 'exploration']

        # [MODIFIED] state별 경로 계산
        state_path = os.path.join(page_path, str(page_index), str(state_index))
        if not os.path.exists(state_path):
            os.makedirs(state_path)

        self.subtask_db_path = os.path.join(state_path, "subtasks.csv")
        self.subtask_db = init_database(self.subtask_db_path, subtask_header)

        # Fill missing 'guideline' values with empty string for backward compatibility
        if 'guideline' not in self.subtask_db.columns:
            self.subtask_db['guideline'] = ''
        else:
            self.subtask_db['guideline'] = self.subtask_db['guideline'].fillna('')

        self.available_subtask_db_path = os.path.join(state_path, "available_subtasks.csv")
        self.available_subtask_db = init_database(self.available_subtask_db_path, available_subtask_header)

        # Fill missing 'exploration' values with 'unexplored' for backward compatibility
        if 'exploration' in self.available_subtask_db.columns:
            self.available_subtask_db['exploration'] = self.available_subtask_db['exploration'].fillna('unexplored')

        self.action_db_path = os.path.join(state_path, "actions.csv")
        self.action_db = init_database(self.action_db_path, action_header)

        # Fill missing 'trigger_ui_index' with -1 for backward compatibility
        if 'trigger_ui_index' not in self.action_db.columns:
            self.action_db['trigger_ui_index'] = -1
        else:
            self.action_db['trigger_ui_index'] = self.action_db['trigger_ui_index'].fillna(-1).astype(int)

        # [MODIFIED] Backward compatibility: start/end -> start_page/end_page
        # Handle old 'start'/'end' column names
        if 'start' in self.action_db.columns and 'start_page' not in self.action_db.columns:
            self.action_db = self.action_db.rename(columns={'start': 'start_page'})
        if 'end' in self.action_db.columns and 'end_page' not in self.action_db.columns:
            self.action_db = self.action_db.rename(columns={'end': 'end_page'})

        # Fill missing 'start_page' and 'end_page' values with -1 for backward compatibility
        if 'start_page' not in self.action_db.columns:
            self.action_db['start_page'] = -1
        else:
            self.action_db['start_page'] = self.action_db['start_page'].fillna(-1).astype(int)
        if 'end_page' not in self.action_db.columns:
            self.action_db['end_page'] = -1
        else:
            self.action_db['end_page'] = self.action_db['end_page'].fillna(-1).astype(int)

        # [NEW] Fill missing 'start_state' and 'end_state' with 0 for backward compatibility
        if 'start_state' not in self.action_db.columns:
            self.action_db['start_state'] = 0
        else:
            self.action_db['start_state'] = self.action_db['start_state'].fillna(0).astype(int)

        if 'end_state' not in self.action_db.columns:
            self.action_db['end_state'] = 0
        else:
            self.action_db['end_state'] = self.action_db['end_state'].fillna(0).astype(int)

        self.action_data = self.action_db.to_dict(orient='records')

        for action in self.action_data:
            action['traversed'] = False

    def get_available_subtasks(self):
        """사용 가능한 서브태스크 목록 반환 (subtasks.csv에서 guideline 정보 병합)"""
        available_subtasks = self.available_subtask_db.to_dict(orient='records')

        # subtasks.csv에서 guideline 정보 가져와서 병합
        for subtask in available_subtasks:
            subtask_name = subtask.get('name')
            if subtask_name:
                learned_subtask = self.subtask_db[self.subtask_db['name'] == subtask_name]
                if not learned_subtask.empty:
                    guideline = learned_subtask.iloc[0].get('guideline', '')
                    if guideline and pd.notna(guideline):
                        subtask['guideline'] = guideline

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
                              start_page: int = -1, end_page: int = -1,
                              start_state: int = 0, end_state: int = 0):
        """Mark a subtask as explored and register it in subtasks.csv + actions.csv

        Args:
            subtask_name: 탐험 완료된 서브태스크 이름
            ui_info: 클릭된 UI 정보 (guideline 생성용)
            action: 수행된 액션 (actions.csv 저장용)
            screen: 화면 XML (액션 일반화용)
            trigger_ui_index: 트리거 UI 인덱스
            start_page: 서브태스크 시작 페이지 인덱스
            end_page: 서브태스크 종료 페이지 인덱스
            start_state: 시작 state 인덱스 [NEW]
            end_state: 종료 state 인덱스 [NEW]
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

            # Generate guideline from UI info
            guideline = self._generate_guideline_from_ui(ui_info)

            self.save_subtask(subtask_data, {}, guideline)
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

                # actions.csv에 저장 (step=0: 첫 번째 액션, state 포함)
                self.save_action(subtask_name, trigger_ui_index, 0, generalized_action, {},
                                start_page=start_page, end_page=end_page,
                                start_state=start_state, end_state=end_state)

                # finish 액션도 저장 (서브태스크 완료 표시)
                finish_action = {"name": "finish", "parameters": {}}
                self.save_action(subtask_name, trigger_ui_index, 1, finish_action, {},
                                start_page=end_page, end_page=end_page,
                                start_state=end_state, end_state=end_state)

                log(f"Action saved for subtask '{subtask_name}' (trigger_ui={trigger_ui_index}) in actions.csv")

    def _generate_guideline_from_ui(self, ui_info: dict) -> str:
        """UI 정보로부터 guideline 문자열 생성

        Args:
            ui_info: UI 정보 딕셔너리

        Returns:
            str: guideline 설명 문자열
        """
        if not ui_info:
            return ""

        # ui_info structure: {"self": {...}, "parent": {...}, "children": [...], "index": N}
        ui_self = ui_info.get('self', {})
        ui_description = ui_self.get('description', '')
        ui_id = ui_self.get('id', '')
        ui_tag = ui_self.get('tag', '')
        ui_class = ui_self.get('class', '')

        # Build guideline description based on available UI info
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
                                         start_page: int = -1, end_page: int = -1,
                                         start_state: int = 0, end_state: int = 0):
        """Multi-step 탐색 완료 후 특정 trigger UI 경로의 액션 저장

        Args:
            page_index: 페이지 인덱스
            subtask_name: 서브태스크 이름
            subtask_info: 서브태스크 정보 (name, description, parameters)
            actions: 수행된 액션 리스트 [{step, action, screen, reasoning?, start_page?, end_page?, start_state?, end_state?}, ...]
            trigger_ui_index: 트리거 UI 인덱스 (같은 서브태스크의 다른 경로 구분용)
            start_page: 시작 페이지 인덱스 (deprecated, use action-level)
            end_page: 종료 페이지 인덱스 (deprecated, use action-level)
            start_state: 시작 state 인덱스 (deprecated, use action-level)
            end_state: 종료 state 인덱스 (deprecated, use action-level)
        """
        from agents import guideline_agent
        from utils.action_utils import generalize_action

        # 1. GPT 기반 guideline 생성
        guideline = ""
        if actions and len(actions) > 0:
            # action_history 형식으로 변환 (guideline_agent가 기대하는 형식)
            action_history = []
            for action_data in actions:
                action = action_data.get('action', {})
                reasoning = action_data.get('reasoning', '')
                action_history.append({
                    'action': action,
                    'reasoning': reasoning
                })
            guideline = guideline_agent.summarize_guideline(subtask_info, action_history)
            log(f"Generated guideline for '{subtask_name}' (trigger_ui={trigger_ui_index}): {guideline}")

        # 2. subtasks.csv에 저장 (서브태스크 정보는 한 번만 저장)
        subtask_data = {
            'name': subtask_name,
            'description': subtask_info.get('description', ''),
            'parameters': subtask_info.get('parameters', {})
        }
        self.save_subtask(subtask_data, {}, guideline)

        # 3. 기존 액션 삭제 - (subtask_name, trigger_ui_index) 조합으로 중복 방지
        self.action_db = self.action_db[
            ~((self.action_db['subtask_name'] == subtask_name) &
              (self.action_db['trigger_ui_index'] == trigger_ui_index))
        ]
        self.action_db.to_csv(self.action_db_path, index=False)

        # 4. actions.csv에 모든 액션 저장 (각 액션의 page/state 포함)
        last_end_page = start_page
        last_end_state = start_state
        for action_data in actions:
            step = action_data.get('step', 0)
            action = action_data.get('action', {})
            screen = action_data.get('screen', '')
            action_start_page = action_data.get('start_page', action_data.get('start', last_end_page))
            action_end_page = action_data.get('end_page', action_data.get('end', action_start_page))
            action_start_state = action_data.get('start_state', last_end_state)
            action_end_state = action_data.get('end_state', action_start_state)
            last_end_page = action_end_page
            last_end_state = action_end_state

            # 액션 일반화
            if 'index' in action.get('parameters', {}):
                generalized_action = generalize_action(action, subtask_info, screen)
            else:
                generalized_action = action

            self.save_action(subtask_name, trigger_ui_index, step, generalized_action, {},
                            start_page=action_start_page, end_page=action_end_page,
                            start_state=action_start_state, end_state=action_end_state)

        # 5. finish 액션 추가
        finish_step = len(actions)
        finish_action = {"name": "finish", "parameters": {}}
        self.save_action(subtask_name, trigger_ui_index, finish_step, finish_action, {},
                        start_page=last_end_page, end_page=last_end_page,
                        start_state=last_end_state, end_state=last_end_state)

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

    def save_subtask(self, subtask_raw: dict, example: dict, guideline: str = ""):
        """서브태스크 정보를 데이터베이스에 저장

        Args:
            subtask_raw: 서브태스크 정보 딕셔너리 (name, description, parameters)
            example: 학습용 예시 정보
            guideline: 서브태스크 수행 가이드라인 설명
        """
        filtered_subtask = self.subtask_db[(self.subtask_db['name'] == subtask_raw['name'])]
        if len(filtered_subtask) == 0:
            # 새로운 서브태스크 삽입
            subtask_data = {
                "name": subtask_raw['name'],
                "description": subtask_raw['description'],
                "guideline": guideline,
                "parameters": json.dumps(subtask_raw['parameters']),
                "example": json.dumps(example)
            }

            self.subtask_db = pd.concat([self.subtask_db, pd.DataFrame([subtask_data])], ignore_index=True)
            self.subtask_db.to_csv(self.subtask_db_path, index=False)
            log("added new subtask to the database")

    def get_next_subtask_data(self, subtask_name: str) -> dict:
        """특정 서브태스크 데이터 반환"""
        # 특정 'name'에 해당하는 행 필터링
        filtered_subtask = self.subtask_db[(self.subtask_db['name'] == subtask_name)]
        next_subtask_data = filtered_subtask.iloc[0].to_dict()

        return next_subtask_data

    def save_action(self, subtask_name, trigger_ui_index: int, step: int, action: dict,
                    example=None, start_page: int = -1, end_page: int = -1,
                    start_state: int = 0, end_state: int = 0) -> None:
        """액션 정보를 데이터베이스에 저장

        Args:
            subtask_name: 서브태스크 이름
            trigger_ui_index: 트리거 UI 인덱스 (같은 서브태스크의 다른 경로 구분용)
            step: 액션 스텝 번호
            action: 액션 정보 딕셔너리
            example: 학습용 예시 데이터
            start_page: 액션 수행 전 페이지 인덱스
            end_page: 액션 수행 후 페이지 인덱스
            start_state: 액션 수행 전 state 인덱스
            end_state: 액션 수행 후 state 인덱스
        """
        if example is None:
            example = {}
        new_action_db = {
            "subtask_name": subtask_name,
            "trigger_ui_index": trigger_ui_index,
            'step': step,
            "start_page": start_page,
            "start_state": start_state,
            "end_page": end_page,
            "end_state": end_state,
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
            "start_page": start_page,
            "start_state": start_state,
            "end_page": end_page,
            "end_state": end_state,
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

    def get_subtask_destination(self, subtask_name: str) -> tuple:
        """Get the destination page/state for a subtask.

        Looks up the actions.csv to find where executing this subtask leads to.
        Uses the end_page and end_state from the last action (typically 'finish').

        Args:
            subtask_name: Name of the subtask to look up

        Returns:
            tuple: (end_page_index, end_state_index), (-1, -1) if not found
        """
        # Filter actions for this subtask
        subtask_actions = self.action_db[self.action_db['subtask_name'] == subtask_name]

        if subtask_actions.empty:
            return (-1, -1)

        # Get the last action (usually 'finish') which has the final destination
        last_action = subtask_actions.iloc[-1]
        end_page = int(last_action.get('end_page', -1))
        end_state = int(last_action.get('end_state', 0))

        return (end_page, end_state)
