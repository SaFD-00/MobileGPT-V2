import json
import os

from agents.prompts import explore_agent_prompt
from memory.memory_manager import Memory
from utils.parsing_utils import get_trigger_ui_attributes, get_extra_ui_attributes
from utils.utils import query, log

import xml.etree.ElementTree as ET


class ExploreAgent:
    """
    새로운 화면을 탐색하고 가능한 서브태스크를 발견하는 에이전트
    UI 요소를 분석하여 상호작용 가능한 동작들을 파악
    """
    def __init__(self, memory: Memory):
        self.memory = memory

    def explore(self, parsed_xml, hierarchy_xml, html_xml, screen_num=None) -> int:
        """
        주어진 화면 XML을 분석하여 새로운 노드 생성
        Args:
            parsed_xml: 파싱된 XML 화면 구조
            hierarchy_xml: 계층 구조 XML
            html_xml: HTML 형식 XML
            screen_num: 화면 번호
        Returns:
            생성된 노드의 인덱스
        """
        
        log(f":::EXPLORE:::", "blue")

        # GPT를 통해 화면에서 가능한 서브태스크들 추출
        prompts = explore_agent_prompt.get_prompts(html_xml)
        subtasks_raw = query(prompts, model=os.getenv("EXPLORE_AGENT_GPT_VERSION"), is_list=True)
        # 필수 필드가 없는 경우 기본값 설정
        for subtask in subtasks_raw:
            if "parameters" not in subtask:
                subtask['parameters'] = {}
            if "trigger_UIs" not in subtask:
                subtask['trigger_UIs'] = []

        # 트리거 UI가 있는 서브태스크만 필터링 (go_back은 예외, 단 페이지 0에서는 go_back도 필터링)
        log(f"Raw Available Subtasks: {json.dumps(subtasks_raw, indent=2)}", "blue")
        is_first_page = (self.memory is None or self.memory.page_db is None
                         or len(self.memory.page_db) == 0)
        subtasks_raw = list(filter(lambda x: len(x["trigger_UIs"]) > 0, subtasks_raw))

        # 각 서브태스크의 트리거 UI 속성 추출
        subtasks_trigger_uis = {subtask['name']: subtask['trigger_UIs'] for subtask in subtasks_raw}
        subtasks_trigger_ui_attributes = get_trigger_ui_attributes(subtasks_trigger_uis, parsed_xml)

        # 트리거 UI 인덱스 리스트 평탄화
        trigger_ui_indexes = [index for ui_indexes in subtasks_trigger_uis.values() for index in ui_indexes]
        # 트리거 UI 외의 추가 UI 속성 추출
        extra_ui_attributes = get_extra_ui_attributes(trigger_ui_indexes, parsed_xml)

        # trigger_UIs의 각 인덱스를 개별 subtask entry로 분리 (trigger_ui_index 포함)
        available_subtasks = []
        for subtask in subtasks_raw:
            trigger_uis = subtask.get('trigger_UIs', [])
            base_subtask = {key: value for key, value in subtask.items() if key != 'trigger_UIs'}
            base_subtask['exploration'] = 'unexplored'

            if trigger_uis:
                # 각 trigger UI에 대해 개별 entry 생성
                for trigger_ui_index in trigger_uis:
                    subtask_entry = {**base_subtask, 'trigger_ui_index': trigger_ui_index}
                    available_subtasks.append(subtask_entry)
            else:
                # trigger UI가 없는 경우 -1로 설정
                base_subtask['trigger_ui_index'] = -1
                available_subtasks.append(base_subtask)
        # 메모리에 새 노드 추가
        new_node_index = self.memory.add_node(available_subtasks, subtasks_trigger_ui_attributes, extra_ui_attributes, parsed_xml, screen_num)

        # 계층 구조 XML과 임베딩 저장
        self.memory.add_hierarchy_xml(hierarchy_xml, new_node_index)

        return new_node_index
