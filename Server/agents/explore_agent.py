import json
import os

from agents.prompts import subtask_extraction_prompt
from agents.prompts import trigger_ui_selection_prompt
from memory.memory_manager import Memory
from utils.parsing_utils import get_trigger_ui_attributes, get_extra_ui_attributes
from utils.utils import query, log

import xml.etree.ElementTree as ET


class ExploreAgent:
    """
    새로운 화면을 탐색하고 가능한 서브태스크를 발견하는 에이전트
    2단계 프로세스:
    1. Step 1: 화면에서 가능한 high-level subtask 추출
    2. Step 2: 각 subtask의 대표 triggerUI 선택
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
        model = os.getenv("EXPLORE_AGENT_GPT_VERSION", "gpt-5.2-chat-latest")

        # ============================================
        # Step 1: Subtask 추출 (triggerUI 없이)
        # ============================================
        log(f":::EXPLORE STEP 1::: Extracting high-level subtasks", "cyan")
        subtask_prompts = subtask_extraction_prompt.get_prompts(html_xml)
        subtasks_raw = query(subtask_prompts, model=model, is_list=True)

        # 타입 검증 - 리스트가 아닌 경우 빈 리스트로 초기화
        if not isinstance(subtasks_raw, list):
            log(f":::EXPLORE WARNING::: subtasks_raw is not a list (type: {type(subtasks_raw).__name__}), using empty list", "yellow")
            subtasks_raw = []

        # 필수 필드 기본값 설정
        for subtask in subtasks_raw:
            if "parameters" not in subtask:
                subtask['parameters'] = {}
            if "expected_steps" not in subtask:
                subtask['expected_steps'] = 2
            if "is_dangerous" not in subtask:
                subtask['is_dangerous'] = False
            if "danger_reason" not in subtask:
                subtask['danger_reason'] = None

        log(f":::EXPLORE STEP 1::: Extracted {len(subtasks_raw)} subtasks", "cyan")
        log(f"Raw Subtasks: {json.dumps(subtasks_raw, indent=2)}", "blue")

        # 위험 subtask 필터링 (auto-explore 가드레일)
        safe_subtasks = self._filter_dangerous_subtasks(subtasks_raw)

        if not safe_subtasks:
            log(f":::EXPLORE::: No safe subtasks found, creating empty node", "yellow")
            # 빈 노드 생성
            new_node_index = self.memory.add_node([], {}, {}, parsed_xml, screen_num)
            self.memory.add_hierarchy_xml(hierarchy_xml, new_node_index)
            return new_node_index

        # ============================================
        # Step 2: TriggerUI 선택 (각 subtask당 1개)
        # ============================================
        log(f":::EXPLORE STEP 2::: Selecting trigger UIs for {len(safe_subtasks)} subtasks", "cyan")
        trigger_prompts = trigger_ui_selection_prompt.get_prompts(html_xml, safe_subtasks)
        trigger_ui_mapping = query(trigger_prompts, model=model, is_list=False)

        # trigger_ui_mapping 검증
        if not isinstance(trigger_ui_mapping, dict):
            log(f":::EXPLORE WARNING::: trigger_ui_mapping is not a dict (type: {type(trigger_ui_mapping).__name__}), using empty dict", "yellow")
            trigger_ui_mapping = {}

        log(f":::EXPLORE STEP 2::: Trigger UI mapping: {json.dumps(trigger_ui_mapping, indent=2)}", "cyan")

        # ============================================
        # Subtask + TriggerUI 결합
        # ============================================
        available_subtasks = []
        subtasks_trigger_uis = {}  # {subtask_name: [trigger_ui_index]}

        for subtask in safe_subtasks:
            subtask_name = subtask.get('name', '')
            trigger_ui = trigger_ui_mapping.get(subtask_name, -1)

            # trigger_ui가 유효한 경우만 추가 (정수 검증)
            if isinstance(trigger_ui, int) and trigger_ui >= 0:
                subtask_entry = {
                    'name': subtask_name,
                    'description': subtask.get('description', ''),
                    'parameters': subtask.get('parameters', {}),
                    'expected_steps': subtask.get('expected_steps', 2),
                    'trigger_ui_index': trigger_ui,
                    'exploration': 'unexplored'
                }
                available_subtasks.append(subtask_entry)
                subtasks_trigger_uis[subtask_name] = [trigger_ui]
                log(f":::EXPLORE::: Added subtask '{subtask_name}' with trigger_ui={trigger_ui}", "green")
            else:
                log(f":::EXPLORE::: Skipping subtask '{subtask_name}' (no valid trigger_ui)", "yellow")

        log(f":::EXPLORE::: Final available subtasks: {len(available_subtasks)}", "blue")

        # 트리거 UI 속성 추출
        subtasks_trigger_ui_attributes = get_trigger_ui_attributes(subtasks_trigger_uis, parsed_xml)

        # 트리거 UI 인덱스 리스트
        trigger_ui_indexes = [ui for uis in subtasks_trigger_uis.values() for ui in uis]
        # 트리거 UI 외의 추가 UI 속성 추출
        extra_ui_attributes = get_extra_ui_attributes(trigger_ui_indexes, parsed_xml)

        # 메모리에 새 노드 추가
        new_node_index = self.memory.add_node(
            available_subtasks,
            subtasks_trigger_ui_attributes,
            extra_ui_attributes,
            parsed_xml,
            screen_num
        )

        # 계층 구조 XML과 임베딩 저장
        self.memory.add_hierarchy_xml(hierarchy_xml, new_node_index)

        return new_node_index

    def _filter_dangerous_subtasks(self, subtasks: list) -> list:
        """
        위험한 subtask를 필터링합니다.
        Args:
            subtasks: 원본 subtask 리스트
        Returns:
            안전한 subtask 리스트
        """
        safe_subtasks = []
        for subtask in subtasks:
            if subtask.get("is_dangerous", False):
                log(f":::GUARDRAIL::: Skipping dangerous subtask: {subtask.get('name', 'unknown')} "
                    f"(reason: {subtask.get('danger_reason', 'unknown')})", "yellow")
            else:
                safe_subtasks.append(subtask)

        if len(subtasks) != len(safe_subtasks):
            log(f":::GUARDRAIL::: Filtered {len(subtasks) - len(safe_subtasks)} dangerous subtasks, "
                f"keeping {len(safe_subtasks)} safe subtasks", "green")

        return safe_subtasks
