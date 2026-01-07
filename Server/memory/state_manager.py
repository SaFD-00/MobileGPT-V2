"""State Manager Module

페이지 내 state 관리 클래스
"""

import os
import json
import hashlib
from datetime import datetime
from typing import List, Dict, Optional, Tuple
import pandas as pd

from memory.state_classifier import StateClassifier, StateType


def init_database(path: str, headers: list):
    """데이터베이스 초기화 - CSV 파일 생성 또는 로드

    Args:
        path: CSV 파일 경로
        headers: 컬럼 헤더 리스트

    Returns:
        pandas.DataFrame: 초기화된 데이터프레임
    """
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


class StateManager:
    """페이지 내 state 관리 클래스

    동적 UI를 가진 앱에서 같은 페이지 내 다른 상태를 관리합니다.
    각 state는 core subtasks 기준으로 구분되며, state별로 독립적인
    디렉토리 구조를 가집니다.
    """

    STATES_HEADER = ['state_index', 'core_subtasks', 'available_subtasks_hash', 'screen_hash', 'created_at']

    def __init__(self, page_path: str, page_index: int, classifier: StateClassifier = None):
        """초기화

        Args:
            page_path: pages 디렉토리 경로 (예: ./memory/AliExpress/pages/)
            page_index: 페이지 인덱스
            classifier: StateClassifier 인스턴스 (없으면 새로 생성)
        """
        self.page_path = page_path
        self.page_index = page_index
        self.classifier = classifier or StateClassifier()

        # states.csv 경로
        self.states_csv_path = os.path.join(page_path, str(page_index), "states.csv")

        # 디렉토리 생성
        page_dir = os.path.join(page_path, str(page_index))
        if not os.path.exists(page_dir):
            os.makedirs(page_dir)

        # states.csv 초기화
        self.states_db = init_database(self.states_csv_path, self.STATES_HEADER)

        self.current_state_index = -1

    def get_or_create_state(self, available_subtasks: List[Dict], screen_hash: str = "") -> Tuple[int, bool]:
        """현재 subtasks에 해당하는 state 조회 또는 생성

        Args:
            available_subtasks: 현재 화면의 available_subtasks
            screen_hash: 화면 embedding 해시 (선택적)

        Returns:
            Tuple[int, bool]: (state_index, is_new_state)
                - state_index: state 인덱스
                - is_new_state: 새로 생성되었으면 True

        Logic:
            1. available_subtasks에서 core_subtasks 추출
            2. states.csv에서 같은 core_subtasks를 가진 state 검색
            3. 있으면 기존 state_index 반환
            4. 없으면 새 state 생성:
                - state_index = len(states_db)
                - states.csv에 추가
                - state 디렉토리 생성

        Examples:
            >>> manager = StateManager("./memory/app/pages/", 0)
            >>> subtasks = [{'name': 'navigate_to_home', 'description': '...'}]
            >>> state_index, is_new = manager.get_or_create_state(subtasks)
            >>> print(state_index, is_new)
            0 True
        """
        core_subtasks = list(self.classifier.extract_core_subtasks(available_subtasks))
        subtasks_hash = self._hash_subtasks(available_subtasks)

        # 기존 state 검색
        for idx, row in self.states_db.iterrows():
            existing_core = json.loads(row['core_subtasks'])
            if set(existing_core) == set(core_subtasks):
                # 같은 core subtasks를 가진 state 발견
                self.current_state_index = int(row['state_index'])
                return self.current_state_index, False

        # 새 state 생성
        new_state_index = len(self.states_db)
        new_state = {
            'state_index': new_state_index,
            'core_subtasks': json.dumps(core_subtasks),
            'available_subtasks_hash': subtasks_hash,
            'screen_hash': screen_hash,
            'created_at': datetime.now().isoformat()
        }

        self.states_db = pd.concat([self.states_db, pd.DataFrame([new_state])], ignore_index=True)
        self.states_db.to_csv(self.states_csv_path, index=False)

        # state 디렉토리 생성
        state_dir = os.path.join(self.page_path, str(self.page_index), str(new_state_index))
        if not os.path.exists(state_dir):
            os.makedirs(state_dir)

        self.current_state_index = new_state_index
        return new_state_index, True

    def get_state_path(self, state_index: int) -> str:
        """state 디렉토리 경로 반환

        Args:
            state_index: state 인덱스

        Returns:
            str: state 디렉토리 절대 경로

        Examples:
            >>> manager = StateManager("./memory/AliExpress/pages/", 5)
            >>> path = manager.get_state_path(0)
            >>> print(path)
            ./memory/AliExpress/pages/5/0
        """
        return os.path.join(self.page_path, str(self.page_index), str(state_index))

    def get_all_states(self) -> List[Dict]:
        """모든 state 목록 반환

        Returns:
            List[Dict]: state 정보 리스트

        Examples:
            >>> manager = StateManager("./memory/app/pages/", 0)
            >>> states = manager.get_all_states()
            >>> print(states)
            [
                {
                    'state_index': 0,
                    'core_subtasks': '["navigate_to_home"]',
                    'available_subtasks_hash': 'abc12345',
                    'screen_hash': '',
                    'created_at': '2025-01-07T10:00:00'
                },
                ...
            ]
        """
        return self.states_db.to_dict(orient='records')

    def _hash_subtasks(self, subtasks: List[Dict]) -> str:
        """subtasks 목록의 해시값 생성

        Args:
            subtasks: subtask 정보 리스트

        Returns:
            str: MD5 해시값 (8자리)

        Logic:
            1. subtask 이름 목록 추출
            2. 알파벳 순 정렬
            3. JSON 문자열로 변환
            4. MD5 해시 계산
            5. 앞 8자리만 반환

        Examples:
            >>> manager = StateManager("./memory/app/pages/", 0)
            >>> subtasks = [
            ...     {'name': 'navigate_to_home'},
            ...     {'name': 'search_items'},
            ... ]
            >>> hash_value = manager._hash_subtasks(subtasks)
            >>> len(hash_value)
            8
        """
        names = sorted([s.get('name', '') for s in subtasks])
        return hashlib.md5(json.dumps(names).encode()).hexdigest()[:8]
