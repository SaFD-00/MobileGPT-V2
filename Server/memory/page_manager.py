import json
import os

import pandas as pd

from agents import param_fill_agent
from utils.action_utils import adapt_action
from utils.utils import log


def init_database(path: str, headers: list):
    """데이터베이스 초기화 - CSV 파일 생성 또는 로드"""
    if not os.path.exists(path) or os.path.getsize(path) == 0:
        database = pd.DataFrame([], columns=headers)
        database.to_csv(path, index=False)
    else:
        try:
            database = pd.read_csv(path)
        except pd.errors.EmptyDataError:
            database = pd.DataFrame([], columns=headers)
            database.to_csv(path, index=False)
    return database


class PageManager:
    """각 페이지(화면 상태)에서의 서브태스크와 액션을 관리하는 클래스"""
    def __init__(self, page_path, page_index):
        self.page_index = page_index

        # Mobile Map: added 'combined_guidance' for subtask-level semantic guidance
        subtask_header = ['name', 'description', 'guideline', 'combined_guidance', 'trigger_ui_index', 'start_page', 'end_page', 'parameters', 'example']
        # Mobile Map: added 'description' (M3A-style history) and 'guidance' (semantic action meaning)
        action_header = ['subtask_name', 'trigger_ui_index', 'step', 'start_page', 'end_page', 'action', 'description', 'guidance', 'example']
        available_subtask_header = ['name', 'description', 'parameters', 'trigger_ui_index', 'exploration']

        page_dir = os.path.join(page_path, str(page_index))
        if not os.path.exists(page_dir):
            os.makedirs(page_dir)

        self.subtask_db_path = os.path.join(page_dir, "subtasks.csv")
        self.subtask_db = init_database(self.subtask_db_path, subtask_header)

        # Fill missing 'guideline' values with empty string for backward compatibility
        if 'guideline' not in self.subtask_db.columns:
            self.subtask_db['guideline'] = ''
        else:
            self.subtask_db['guideline'] = self.subtask_db['guideline'].fillna('')

        # Fill missing 'trigger_ui_index', 'start_page', 'end_page' for backward compatibility
        if 'trigger_ui_index' not in self.subtask_db.columns:
            self.subtask_db['trigger_ui_index'] = -1
        else:
            self.subtask_db['trigger_ui_index'] = self.subtask_db['trigger_ui_index'].fillna(-1).astype(int)

        if 'start_page' not in self.subtask_db.columns:
            self.subtask_db['start_page'] = -1
        else:
            self.subtask_db['start_page'] = self.subtask_db['start_page'].fillna(-1).astype(int)

        if 'end_page' not in self.subtask_db.columns:
            self.subtask_db['end_page'] = -1
        else:
            self.subtask_db['end_page'] = self.subtask_db['end_page'].fillna(-1).astype(int)

        # Mobile Map: Fill missing 'combined_guidance' for backward compatibility
        if 'combined_guidance' not in self.subtask_db.columns:
            self.subtask_db['combined_guidance'] = ''
        else:
            self.subtask_db['combined_guidance'] = self.subtask_db['combined_guidance'].fillna('')

        self.available_subtask_db_path = os.path.join(page_dir, "available_subtasks.csv")
        self.available_subtask_db = init_database(self.available_subtask_db_path, available_subtask_header)

        # Fill missing 'exploration' values with 'unexplored' for backward compatibility
        if 'exploration' in self.available_subtask_db.columns:
            self.available_subtask_db['exploration'] = self.available_subtask_db['exploration'].fillna('unexplored')

        # Fill missing 'trigger_ui_index' with -1 for backward compatibility
        if 'trigger_ui_index' not in self.available_subtask_db.columns:
            self.available_subtask_db['trigger_ui_index'] = -1
        else:
            self.available_subtask_db['trigger_ui_index'] = self.available_subtask_db['trigger_ui_index'].fillna(-1).astype(int)

        self.action_db_path = os.path.join(page_dir, "actions.csv")
        self.action_db = init_database(self.action_db_path, action_header)

        # Fill missing 'trigger_ui_index' with -1 for backward compatibility
        if 'trigger_ui_index' not in self.action_db.columns:
            self.action_db['trigger_ui_index'] = -1
        else:
            self.action_db['trigger_ui_index'] = self.action_db['trigger_ui_index'].fillna(-1).astype(int)

        # Backward compatibility: start/end -> start_page/end_page
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

        # Mobile Map: Fill missing 'description' and 'guidance' for backward compatibility
        if 'description' not in self.action_db.columns:
            self.action_db['description'] = ''
        else:
            self.action_db['description'] = self.action_db['description'].fillna('')

        if 'guidance' not in self.action_db.columns:
            self.action_db['guidance'] = ''
        else:
            self.action_db['guidance'] = self.action_db['guidance'].fillna('')

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
                    combined_guidance = learned_subtask.iloc[0].get('combined_guidance', '')
                    if combined_guidance and pd.notna(combined_guidance):
                        subtask['combined_guidance'] = combined_guidance

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
            ui_info: 클릭된 UI 정보 (guideline 생성용)
            action: 수행된 액션 (actions.csv 저장용)
            screen: 화면 XML (액션 일반화용)
            trigger_ui_index: 트리거 UI 인덱스
            start_page: 서브태스크 시작 페이지 인덱스
            end_page: 서브태스크 종료 페이지 인덱스
        """
        # Filter by subtask name
        condition = (self.available_subtask_db['name'] == subtask_name)
        # Also filter by trigger_ui_index if provided
        if trigger_ui_index >= 0:
            condition = condition & (self.available_subtask_db['trigger_ui_index'] == trigger_ui_index)

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

            # Generate guideline from UI info or action
            guideline = self._generate_guideline_from_ui(ui_info)
            if not guideline and action:
                guideline = self._generate_guideline_from_action(action)

            self.save_subtask(subtask_data, {}, guideline,
                             trigger_ui_index=trigger_ui_index,
                             start_page=start_page, end_page=end_page)
            log(f"Subtask '{subtask_name}' marked as explored and registered in subtasks.csv")

            # === actions.csv에 액션 저장 ===
            if action is not None and screen is not None:
                from utils.action_utils import generalize_action

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

                # 액션 일반화
                generalized_action = generalize_action(action, subtask_dict, screen)

                # actions.csv에 저장
                self.save_action(subtask_name, trigger_ui_index, 0, generalized_action, {},
                                start_page=start_page, end_page=end_page)

                # finish 액션도 저장
                finish_action = {"name": "finish", "parameters": {}}
                self.save_action(subtask_name, trigger_ui_index, 1, finish_action, {},
                                start_page=end_page, end_page=end_page)

                log(f"Action saved for subtask '{subtask_name}' (trigger_ui={trigger_ui_index}) in actions.csv")

    def _generate_guideline_from_ui(self, ui_info: dict) -> str:
        """UI 정보로부터 guideline 문자열 생성"""
        if not ui_info:
            return ""

        ui_self = ui_info.get('self', {})
        ui_description = ui_self.get('description', '')
        ui_id = ui_self.get('id', '')
        ui_tag = ui_self.get('tag', '')
        ui_class = ui_self.get('class', '')

        if ui_description and ui_description != 'NONE':
            return f"Triggered by clicking '{ui_description}'"
        elif ui_id and ui_id != 'NONE':
            return f"Triggered by clicking '{ui_id}'"
        elif ui_tag:
            return f"Triggered by clicking {ui_tag} element"
        elif ui_class:
            return f"Triggered by clicking {ui_class} element"
        return ""

    def _generate_guideline_from_action(self, action: dict) -> str:
        """액션 정보로부터 guideline 문자열 생성

        action의 parameters에서 description을 추출하여 guideline 생성.
        "Click to explore 'X'" → "Triggered by clicking 'X'" 변환
        """
        if not action:
            return ""

        params = action.get('parameters', {})
        description = params.get('description', '')

        if description:
            # "Click to explore 'subtask_name'" → "Triggered by clicking to explore 'subtask_name'"
            if "Click to explore" in description:
                return description.replace("Click to explore", "Triggered by clicking to explore")
            # 일반적인 description은 그대로 사용
            return f"Triggered by: {description}"

        # action name 기반 fallback
        action_name = action.get('name', '')
        if action_name == 'click':
            index = params.get('index', -1)
            if index >= 0:
                return f"Triggered by clicking UI element at index {index}"

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
            actions: 수행된 액션 리스트 [{step, action, screen, reasoning?, start_page?, end_page?}, ...]
            trigger_ui_index: 트리거 UI 인덱스
            start_page: 시작 페이지 인덱스
            end_page: 종료 페이지 인덱스
        """
        from agents import guideline_agent
        from utils.action_utils import generalize_action

        # 1. GPT 기반 guideline 생성
        guideline = ""
        if actions and len(actions) > 0:
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

        # 2. subtasks.csv에 저장
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

        # 4. actions.csv에 모든 액션 저장
        last_end_page = start_page
        for action_data in actions:
            step = action_data.get('step', 0)
            action = action_data.get('action', {})
            screen = action_data.get('screen', '')
            action_start_page = action_data.get('start_page', action_data.get('start', last_end_page))
            action_end_page = action_data.get('end_page', action_data.get('end', action_start_page))
            last_end_page = action_end_page

            # 액션 일반화
            if 'index' in action.get('parameters', {}):
                generalized_action = generalize_action(action, subtask_info, screen)
            else:
                generalized_action = action

            self.save_action(subtask_name, trigger_ui_index, step, generalized_action, {},
                            start_page=action_start_page, end_page=action_end_page)

        # 5. finish 액션 추가
        finish_step = len(actions)
        finish_action = {"name": "finish", "parameters": {}}
        self.save_action(subtask_name, trigger_ui_index, finish_step, finish_action, {},
                        start_page=last_end_page, end_page=last_end_page)

        log(f"Saved {len(actions) + 1} actions for subtask '{subtask_name}' (trigger_ui={trigger_ui_index}) in actions.csv")

    def mark_subtask_fully_explored(self, subtask_name: str):
        """서브태스크의 모든 trigger UI 탐색 완료 후 explored로 마킹"""
        condition = (self.available_subtask_db['name'] == subtask_name)
        if condition.any():
            self.available_subtask_db.loc[condition, 'exploration'] = 'explored'
            self.available_subtask_db.to_csv(self.available_subtask_db_path, index=False)
            log(f"Marked subtask '{subtask_name}' as fully explored in available_subtasks.csv")

    def get_subtask_by_name(self, subtask_name: str) -> dict:
        """Get subtask data by name from available_subtasks"""
        condition = (self.available_subtask_db['name'] == subtask_name)
        if condition.any():
            row = self.available_subtask_db[condition].iloc[0]
            return row.to_dict()
        return None

    def save_subtask(self, subtask_raw: dict, example: dict, guideline: str = "",
                     trigger_ui_index: int = -1, start_page: int = -1, end_page: int = -1):
        """서브태스크 정보를 데이터베이스에 저장

        Args:
            subtask_raw: 서브태스크 정보 딕셔너리 (name, description, parameters)
            example: 학습용 예시 데이터
            guideline: 서브태스크 실행 가이드라인
            trigger_ui_index: 트리거 UI 인덱스 (같은 이름이라도 다른 UI에서 시작 가능)
            start_page: 서브태스크 시작 페이지 인덱스
            end_page: 서브태스크 종료 페이지 인덱스

        중복 체크: name + trigger_ui_index 기준
        """
        # 중복 체크: name + trigger_ui_index 기준
        condition = (self.subtask_db['name'] == subtask_raw['name'])
        if trigger_ui_index >= 0:
            condition = condition & (self.subtask_db['trigger_ui_index'] == trigger_ui_index)

        if not condition.any():
            subtask_data = {
                "name": subtask_raw['name'],
                "description": subtask_raw['description'],
                "guideline": guideline,
                "trigger_ui_index": trigger_ui_index,
                "start_page": start_page,
                "end_page": end_page,
                "parameters": json.dumps(subtask_raw['parameters']),
                "example": json.dumps(example)
            }

            self.subtask_db = pd.concat([self.subtask_db, pd.DataFrame([subtask_data])], ignore_index=True)
            self.subtask_db.to_csv(self.subtask_db_path, index=False)
            log(f"added new subtask '{subtask_raw['name']}' (trigger_ui={trigger_ui_index}) to the database")

    def get_next_subtask_data(self, subtask_name: str) -> dict:
        """특정 서브태스크 데이터 반환"""
        filtered_subtask = self.subtask_db[(self.subtask_db['name'] == subtask_name)]
        next_subtask_data = filtered_subtask.iloc[0].to_dict()
        return next_subtask_data

    def save_action(self, subtask_name, trigger_ui_index: int, step: int, action: dict,
                    example=None, start_page: int = -1, end_page: int = -1,
                    description: str = "", guidance: str = "") -> None:
        """액션 정보를 데이터베이스에 저장

        Args:
            subtask_name: 서브태스크 이름
            trigger_ui_index: 트리거 UI 인덱스
            step: 액션 스텝 번호
            action: 액션 정보 딕셔너리
            example: 학습용 예시 데이터
            start_page: 액션 수행 전 페이지 인덱스
            end_page: 액션 수행 후 페이지 인덱스
            description: M3A-style history description (what changed after action)
            guidance: Semantic meaning of the action
        """
        if example is None:
            example = {}

        # 동일한 (subtask_name, trigger_ui_index, step) 존재 여부 확인
        existing_mask = (
            (self.action_db['subtask_name'] == subtask_name) &
            (self.action_db['trigger_ui_index'] == trigger_ui_index) &
            (self.action_db['step'] == step)
        )

        action_json = json.dumps(action)
        example_json = json.dumps(example)

        if existing_mask.any():
            # 기존 행 업데이트 (더 상세한 정보로 덮어쓰기)
            self.action_db.loc[existing_mask, 'action'] = action_json
            self.action_db.loc[existing_mask, 'example'] = example_json
            if start_page != -1:
                self.action_db.loc[existing_mask, 'start_page'] = start_page
            if end_page != -1:
                self.action_db.loc[existing_mask, 'end_page'] = end_page
            # Mobile Map: update description and guidance
            if description:
                self.action_db.loc[existing_mask, 'description'] = description
            if guidance:
                self.action_db.loc[existing_mask, 'guidance'] = guidance
            self.action_db.to_csv(self.action_db_path, index=False)
        else:
            # 새 행 추가
            new_action_db = {
                "subtask_name": subtask_name,
                "trigger_ui_index": trigger_ui_index,
                'step': step,
                "start_page": start_page,
                "end_page": end_page,
                "action": action_json,
                "description": description,  # Mobile Map: M3A-style history
                "guidance": guidance,        # Mobile Map: semantic meaning
                "example": example_json
            }
            self.action_db = pd.concat([self.action_db, pd.DataFrame([new_action_db])], ignore_index=True)
            self.action_db.to_csv(self.action_db_path, index=False)

        # 액션 데이터에 추가/업데이트
        existing_idx = None
        for i, existing_action in enumerate(self.action_data):
            if (existing_action['subtask_name'] == subtask_name and
                existing_action['trigger_ui_index'] == trigger_ui_index and
                existing_action['step'] == step):
                existing_idx = i
                break

        new_action_data = {
            "subtask_name": subtask_name,
            "trigger_ui_index": trigger_ui_index,
            'step': step,
            "start_page": start_page if start_page != -1 else (self.action_data[existing_idx]['start_page'] if existing_idx is not None else start_page),
            "end_page": end_page if end_page != -1 else (self.action_data[existing_idx]['end_page'] if existing_idx is not None else end_page),
            "action": action_json,
            "description": description if description else (self.action_data[existing_idx].get('description', '') if existing_idx is not None else ''),
            "guidance": guidance if guidance else (self.action_data[existing_idx].get('guidance', '') if existing_idx is not None else ''),
            "example": example_json,
            "traversed": True
        }

        if existing_idx is not None:
            self.action_data[existing_idx] = new_action_data
        else:
            self.action_data.append(new_action_data)

    def update_end_page(self, subtask_name: str, trigger_ui_index: int, end_page: int) -> bool:
        """서브태스크와 마지막 액션의 end_page를 업데이트

        액션 실행 후 도착한 페이지 인덱스로 end_page를 업데이트합니다.
        finish 액션의 start_page도 함께 업데이트합니다.

        Args:
            subtask_name: 서브태스크 이름
            trigger_ui_index: 트리거 UI 인덱스
            end_page: 액션 실행 후 도착한 페이지 인덱스

        Returns:
            bool: 업데이트 성공 여부
        """
        updated = False

        # 1. subtasks.csv 업데이트
        subtask_condition = (self.subtask_db['name'] == subtask_name)
        if trigger_ui_index >= 0:
            subtask_condition = subtask_condition & (self.subtask_db['trigger_ui_index'] == trigger_ui_index)

        if subtask_condition.any():
            self.subtask_db.loc[subtask_condition, 'end_page'] = end_page
            self.subtask_db.to_csv(self.subtask_db_path, index=False)
            updated = True

        # 2. actions.csv에서 해당 서브태스크의 end_page=-1인 액션들 업데이트
        action_condition = (
            (self.action_db['subtask_name'] == subtask_name) &
            (self.action_db['trigger_ui_index'] == trigger_ui_index) &
            (self.action_db['end_page'] == -1)
        )

        if action_condition.any():
            self.action_db.loc[action_condition, 'end_page'] = end_page

            # finish 액션의 start_page도 업데이트
            # finish 액션은 마지막 일반 액션이 도착한 페이지에서 시작함
            for idx in self.action_db[action_condition].index:
                action_str = str(self.action_db.loc[idx, 'action'])
                if '"name": "finish"' in action_str or "'name': 'finish'" in action_str:
                    self.action_db.loc[idx, 'start_page'] = end_page

            self.action_db.to_csv(self.action_db_path, index=False)

            # 메모리 내 action_data도 업데이트
            for action_data in self.action_data:
                if (action_data.get('subtask_name') == subtask_name and
                    action_data.get('trigger_ui_index') == trigger_ui_index and
                    action_data.get('end_page') == -1):
                    action_data['end_page'] = end_page
                    # finish 액션의 start_page도 업데이트
                    action_str = str(action_data.get('action', ''))
                    if '"name": "finish"' in action_str or "'name': 'finish'" in action_str:
                        action_data['start_page'] = end_page

            updated = True
            log(f"Updated end_page={end_page} for subtask '{subtask_name}' (trigger_ui={trigger_ui_index})")

        return updated

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

        for action in actions[:]:
            subtask_name = action['subtask_name']
            action_data = json.loads(action['action'])
            if subtask_name == prev_subtask_name and action_data['name'] == 'finish':
                starting_step = action['step']
                actions.remove(action)

        for action in actions[:]:
            subtask_name = action['subtask_name']
            if subtask_name == target_subtask_name:
                action['subtask_name'] = base_subtask_name
                action['step'] = starting_step + action['step']

        self.action_db = pd.DataFrame(actions)
        self.action_db.to_csv(self.action_db_path, index=False)

    def get_subtask_destination(self, subtask_name: str) -> int:
        """Get the destination page for a subtask.

        Args:
            subtask_name: Name of the subtask to look up

        Returns:
            int: end_page_index, -1 if not found
        """
        subtask_actions = self.action_db[self.action_db['subtask_name'] == subtask_name]

        if subtask_actions.empty:
            return -1

        last_action = subtask_actions.iloc[-1]
        end_page = int(last_action.get('end_page', -1))

        return end_page

    def update_action_description(self, subtask_name: str, trigger_ui_index: int,
                                   step: int, description: str, guidance: str = "") -> bool:
        """Update description and guidance for an existing action.

        Mobile Map: M3A-style history description update.

        Args:
            subtask_name: Subtask name
            trigger_ui_index: Trigger UI index
            step: Action step number
            description: M3A-style description of what changed
            guidance: Semantic meaning of the action

        Returns:
            bool: True if update was successful
        """
        condition = (
            (self.action_db['subtask_name'] == subtask_name) &
            (self.action_db['trigger_ui_index'] == trigger_ui_index) &
            (self.action_db['step'] == step)
        )

        if condition.any():
            if description:
                self.action_db.loc[condition, 'description'] = description
            if guidance:
                self.action_db.loc[condition, 'guidance'] = guidance
            self.action_db.to_csv(self.action_db_path, index=False)

            # Update in-memory action_data
            for action_data in self.action_data:
                if (action_data.get('subtask_name') == subtask_name and
                    action_data.get('trigger_ui_index') == trigger_ui_index and
                    action_data.get('step') == step):
                    if description:
                        action_data['description'] = description
                    if guidance:
                        action_data['guidance'] = guidance
                    break

            log(f"Updated action description for '{subtask_name}' step {step}")
            return True

        return False

    def update_combined_guidance(self, subtask_name: str, trigger_ui_index: int = -1) -> str:
        """Aggregate action guidances into subtask combined_guidance.

        Mobile Map: Combines all action-level guidances into a single subtask guidance.

        Args:
            subtask_name: Subtask name
            trigger_ui_index: Trigger UI index (-1 to match any)

        Returns:
            str: Combined guidance string
        """
        # Get all actions for this subtask
        action_condition = (self.action_db['subtask_name'] == subtask_name)
        if trigger_ui_index >= 0:
            action_condition = action_condition & (self.action_db['trigger_ui_index'] == trigger_ui_index)

        actions = self.action_db[action_condition].sort_values('step')

        # Combine guidances
        guidances = []
        for _, row in actions.iterrows():
            guidance = row.get('guidance', '')
            if guidance and guidance.strip():
                step = int(row.get('step', 0)) + 1
                guidances.append(f"{step}. {guidance}")

        combined = " → ".join(guidances) if guidances else ""

        # Update subtasks.csv
        subtask_condition = (self.subtask_db['name'] == subtask_name)
        if trigger_ui_index >= 0:
            subtask_condition = subtask_condition & (self.subtask_db['trigger_ui_index'] == trigger_ui_index)

        if subtask_condition.any():
            self.subtask_db.loc[subtask_condition, 'combined_guidance'] = combined
            self.subtask_db.to_csv(self.subtask_db_path, index=False)
            log(f"Updated combined_guidance for '{subtask_name}': {combined[:50]}...")

        return combined

    def delete_subtask_data(self, subtask_name: str, trigger_ui_index: int = -1,
                            reason: str = "unknown") -> bool:
        """Delete subtask data from this page's CSV files.

        Performs deletion across:
        1. available_subtasks.csv - update exploration status to reason
        2. subtasks.csv - remove the row
        3. actions.csv - remove related actions

        Args:
            subtask_name: Name of the subtask to delete
            trigger_ui_index: UI index that triggers the subtask (-1 to match all)
            reason: Reason for deletion (stored in exploration field)

        Returns:
            bool: True if any data was deleted
        """
        deleted_any = False

        # === 1. available_subtasks.csv 처리 ===
        # exploration 필드를 reason으로 업데이트 (행 보존, 재탐색 방지)
        condition = (self.available_subtask_db['name'] == subtask_name)
        if trigger_ui_index >= 0:
            condition = condition & (self.available_subtask_db['trigger_ui_index'] == trigger_ui_index)

        if condition.any():
            self.available_subtask_db.loc[condition, 'exploration'] = reason
            self.available_subtask_db.to_csv(self.available_subtask_db_path, index=False)
            deleted_any = True
            log(f":::DELETE::: Marked subtask '{subtask_name}' as '{reason}' in available_subtasks.csv")

        # === 2. subtasks.csv 처리 ===
        subtask_condition = (self.subtask_db['name'] == subtask_name)
        if trigger_ui_index >= 0:
            subtask_condition = subtask_condition & (self.subtask_db['trigger_ui_index'] == trigger_ui_index)

        rows_before = len(self.subtask_db)
        self.subtask_db = self.subtask_db[~subtask_condition]
        rows_after = len(self.subtask_db)

        if rows_before > rows_after:
            self.subtask_db.to_csv(self.subtask_db_path, index=False)
            deleted_any = True
            log(f":::DELETE::: Deleted {rows_before - rows_after} row(s) from subtasks.csv for '{subtask_name}'")

        # === 3. actions.csv 처리 ===
        action_condition = (self.action_db['subtask_name'] == subtask_name)
        if trigger_ui_index >= 0:
            action_condition = action_condition & (self.action_db['trigger_ui_index'] == trigger_ui_index)

        actions_before = len(self.action_db)
        self.action_db = self.action_db[~action_condition]
        actions_after = len(self.action_db)

        if actions_before > actions_after:
            self.action_db.to_csv(self.action_db_path, index=False)
            deleted_any = True
            log(f":::DELETE::: Deleted {actions_before - actions_after} action(s) from actions.csv for '{subtask_name}'")

            # 메모리 내 action_data도 업데이트
            self.action_data = [
                action for action in self.action_data
                if not (action.get('subtask_name') == subtask_name and
                       (trigger_ui_index < 0 or action.get('trigger_ui_index') == trigger_ui_index))
            ]

        return deleted_any
