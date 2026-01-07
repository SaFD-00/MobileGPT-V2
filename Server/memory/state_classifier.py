"""State Classifier Module

핵심 subtask 기반으로 page 내 state를 분류하는 모듈
"""

from enum import Enum
from typing import List, Dict, Set


class StateType(Enum):
    """State 분류 타입"""
    SAME_STATE = "same_state"              # 핵심 subtask 완전 일치
    STATE_TRANSITION = "state_transition"  # 핵심 subtask 부분 변경
    NEW_STATE = "new_state"                # 핵심 subtask 완전 변경


class StateClassifier:
    """핵심 subtask 기반 state 분류기

    동적 UI (검색 결과, 광고 등)를 가진 앱에서 같은 페이지 내 다른 상태를
    구분하기 위해 navigation 관련 핵심 subtask를 기준으로 분류합니다.
    """

    # 핵심 subtask 패턴 (navigation 관련)
    CORE_PATTERNS = [
        'navigate_',
        'go_to_',
        'open_',
        'switch_to_',
        'show_',
        'view_'
    ]

    def __init__(self):
        """초기화"""
        pass

    def classify(self, current_subtasks: List[Dict], prev_subtasks: List[Dict]) -> StateType:
        """현재 subtasks와 이전 subtasks를 비교하여 state 분류

        Args:
            current_subtasks: 현재 화면의 subtasks
            prev_subtasks: 이전 화면의 subtasks

        Returns:
            StateType: 분류 결과
                - SAME_STATE: 핵심 subtask 완전 일치
                - STATE_TRANSITION: 핵심 subtask 부분 변경
                - NEW_STATE: 핵심 subtask 완전 변경

        Examples:
            >>> classifier = StateClassifier()
            >>> current = [{'name': 'navigate_to_home'}, {'name': 'search_items'}]
            >>> prev = [{'name': 'navigate_to_home'}, {'name': 'browse_deals'}]
            >>> classifier.classify(current, prev)
            <StateType.SAME_STATE: 'same_state'>
        """
        current_core = self.extract_core_subtasks(current_subtasks)
        prev_core = self.extract_core_subtasks(prev_subtasks)

        if current_core == prev_core:
            return StateType.SAME_STATE
        elif current_core & prev_core:  # 교집합이 있으면
            return StateType.STATE_TRANSITION
        else:
            return StateType.NEW_STATE

    def extract_core_subtasks(self, subtasks: List[Dict]) -> Set[str]:
        """subtask 목록에서 핵심 subtask 이름만 추출

        Args:
            subtasks: subtask 정보 리스트
                [
                    {'name': 'navigate_to_home', 'description': '...'},
                    {'name': 'search_items', 'description': '...'},
                    ...
                ]

        Returns:
            Set[str]: 핵심 subtask 이름 집합

        Examples:
            >>> classifier = StateClassifier()
            >>> subtasks = [
            ...     {'name': 'navigate_to_home', 'description': 'Go home'},
            ...     {'name': 'search_items', 'description': 'Search'},
            ... ]
            >>> classifier.extract_core_subtasks(subtasks)
            {'navigate_to_home'}
        """
        core = set()
        for subtask in subtasks:
            name = subtask.get('name', '')
            if self._is_core_subtask(name):
                core.add(name)
        return core

    def is_same_state(self, current_subtasks: List[Dict], prev_subtasks: List[Dict]) -> bool:
        """같은 state인지 빠른 판단 (헬퍼 메서드)

        Args:
            current_subtasks: 현재 subtasks
            prev_subtasks: 이전 subtasks

        Returns:
            bool: 같은 state면 True

        Examples:
            >>> classifier = StateClassifier()
            >>> current = [{'name': 'navigate_to_home'}]
            >>> prev = [{'name': 'navigate_to_home'}]
            >>> classifier.is_same_state(current, prev)
            True
        """
        return self.classify(current_subtasks, prev_subtasks) == StateType.SAME_STATE

    def _is_core_subtask(self, name: str) -> bool:
        """핵심 subtask인지 판단

        Args:
            name: subtask 이름 (예: "navigate_to_home", "search_items")

        Returns:
            bool: 핵심 subtask이면 True, 아니면 False

        Examples:
            >>> classifier = StateClassifier()
            >>> classifier._is_core_subtask("navigate_to_home")
            True
            >>> classifier._is_core_subtask("search_items")
            False
        """
        return any(name.startswith(pattern) for pattern in self.CORE_PATTERNS)
