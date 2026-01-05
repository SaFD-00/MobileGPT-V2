import copy
import json
import os
import xml.etree.ElementTree as ET

from agents.prompts import node_expand_prompt
from utils.parsing_utils import find_matching_node, get_trigger_ui_attributes, get_extra_ui_attributes
from utils.utils import log, query


class NodeManager:
    """
    화면 노드를 관리하고 매칭하는 클래스
    기존 화면과 현재 화면을 비교하여 유사도 판단
    """
    def __init__(self, page_db, memory, parsed_xml, html_xml):
        self.parsed_xml = parsed_xml
        self.html_xml = html_xml
        self.remaining_ui_indexes = []
        self.page_db = page_db
        self.memory = memory
        self.match_threshold = 0.7  # 노드 매칭 임계값 (70%)
        self.node_expansion_backup = None  # 노드 확장용 백업 데이터

    def search(self, candidate_nodes_indexes: list) -> (int, list):
        """
        후보 노드들 중에서 가장 적합한 노드 검색
        Returns:
            page_index: 매칭된 페이지 인덱스
            new_subtasks: 새로 발견된 서브태스크 목록
        """
        final_page_index = -1
        final_supported_subtasks = []
        final_match_case = ""
        node_expansion_dat = None

        for node_index in candidate_nodes_indexes:
            page_data = json.loads(self.page_db.loc[node_index].to_json())
            page_data = {key: json.loads(value) if key in ['available_subtasks', 'trigger_uis', 'extra_uis'] else value
                         for key, value in page_data.items()}
            supported_subtasks, match_case = self.__match_node(page_data)

            if match_case == "EQSET":
                final_page_index = page_data['index']
                final_supported_subtasks = supported_subtasks
                final_match_case = match_case
                break

            # 가장 많은 서브태스크를 지원하는 노드로 업데이트
            if match_case != "NEW" and len(supported_subtasks) > len(final_supported_subtasks):
                final_page_index = page_data['index']
                final_supported_subtasks = supported_subtasks
                final_match_case = match_case
                if final_match_case == "SUPERSET":
                    node_expansion_data = copy.deepcopy(self.node_expansion_backup)

        log(f":::EXPLORE:::", "blue")

        if final_page_index >= 0:
            new_subtasks = []
            # 평가 모드: 시작
            # if final_match_case == "SUPERSET":
            #     new_subtasks = self.__expand_node(*node_expansion_data)
            # 평가 모드: 끝
            return final_page_index, new_subtasks
        else:
            return -1, []



    def __match_node(self, page_node: dict) -> (list, str):
        """
        현재 화면과 저장된 노드를 비교하여 매칭 타입 결정
        Returns:
            supported_subtasks: 지원 가능한 서브태스크 목록
            match_case: 매칭 타입 (EQSET, SUBSET, SUPERSET, NEW)
        """
        tree = ET.fromstring(self.parsed_xml)

        trigger_uis_for_subtasks: dict = page_node['trigger_uis']  # 각 서브태스크의 트리거 UI
        extra_uis: list = page_node['extra_uis']  # 추가 UI 요소들

        self.remaining_ui_indexes = []  # 아직 처리되지 않은 UI 인덱스
        for tag in ['input', 'button', 'checker']:
            for node in tree.findall(f".//{tag}"):
                index = int(node.attrib['index'])
                self.remaining_ui_indexes.append(index)

        not_supported_subtask_names = []
        supported_subtask_names = []
        new_trigger_uis_for_subtasks = {}
        for subtask_name, trigger_uis in trigger_uis_for_subtasks.items():
            found_trigger_uis = self.__find_required_uis(tree, trigger_uis)
            if len(found_trigger_uis) < len(trigger_uis):
                not_supported_subtask_names.append(subtask_name)
            else:
                supported_subtask_names.append(subtask_name)
                new_trigger_uis_for_subtasks[subtask_name] = found_trigger_uis

        found_extra_uis = self.__find_required_uis(tree, extra_uis)

        num_remaining_uis = len(self.remaining_ui_indexes)  # 현재 화면에서 미처리된 UI 개수
        pct_subtask_supported = 1 - (len(not_supported_subtask_names) / len(
            page_node['available_subtasks']))
        supported_subtasks = [subtask for subtask in page_node['available_subtasks'] if
                              subtask['name'] in supported_subtask_names]
        not_supported_subtasks = [subtask for subtask in page_node['available_subtasks'] if
                                  subtask['name'] in not_supported_subtask_names]

        if num_remaining_uis == 0 and pct_subtask_supported == 1.0:
            print("EQSET")  # 완벽히 동일한 화면
            return supported_subtasks, "EQSET"
        elif num_remaining_uis == 0 and pct_subtask_supported > 0:
            print("SUBSET")  # 현재 화면이 저장된 화면의 부분집합
            return supported_subtasks, "SUBSET"
        elif num_remaining_uis > 0 and pct_subtask_supported >= self.match_threshold:
            print("SUPERSET")  # 현재 화면이 저장된 화면보다 더 많은 UI 포함
            self.node_expansion_backup = copy.deepcopy(
                (self.html_xml, self.parsed_xml, page_node, not_supported_subtasks, new_trigger_uis_for_subtasks,
                 self.remaining_ui_indexes))

            return supported_subtasks, "SUPERSET"
        else:
            supported_subtasks = []
            return supported_subtasks, "NEW"

    def __find_required_uis(self, tree, required_uis) -> list:
        """
        필요한 UI 요소들을 현재 화면에서 찾기
        Returns:
            found_ui_indexes: 찾은 UI들의 인덱스 목록
        """
        # 찾은 UI 목록 반환
        found_ui_indexes = []
        for ui_attributes in required_uis:
            matching_nodes = find_matching_node(tree, ui_attributes)
            found_ui_indexes = found_ui_indexes + [node.attrib.get('index') for node in matching_nodes]
            for node in matching_nodes:
                node_index = int(node.attrib['index'])
                if node_index in self.remaining_ui_indexes:
                    self.remaining_ui_indexes.remove(node_index)

        return found_ui_indexes

    def __expand_node(self, html_xml, parsed_xml, page_node, extra_subtasks, subtasks_with_new_trigger_uis, remaining_ui_indexes):
        """
        노드를 확장하여 새로운 서브태스크 발견
        현재 화면에 있지만 저장된 노드에 없는 UI들을 분석
        """
        old_trigger_ui_indexes = [int(index) for ui_indexes in subtasks_with_new_trigger_uis.values() for index
                                  in ui_indexes]

        new_ui_indexes = [index for index in remaining_ui_indexes if index not in old_trigger_ui_indexes]
        old_subtasks = [subtask for subtask in page_node['available_subtasks'] if
                        subtask['name'] in list(subtasks_with_new_trigger_uis.keys())]
        for subtask in old_subtasks:
            subtask["trigger_UIs"] = subtasks_with_new_trigger_uis[subtask['name']]

        new_subtasks_raw = query(
            node_expand_prompt.get_prompts(html_xml, extra_subtasks, old_trigger_ui_indexes, old_subtasks, new_ui_indexes),
            model=os.getenv("EXPLORE_AGENT_GPT_VERSION"), is_list=True)

        new_subtasks_raw = list(filter(lambda x: len(x["trigger_UIs"]) > 0, new_subtasks_raw))  # 트리거 UI가 있는 서브태스크만 필터링

        # 기존 서브태스크와 중복되지 않는 것만 선택
        new_subtasks_raw = [new_subtask for new_subtask in new_subtasks_raw if
                            not any(new_subtask['name'] == old_subtask['name'] for old_subtask in old_subtasks)]

        new_subtasks_trigger_uis = {subtask['name']: subtask['trigger_UIs'] for subtask in new_subtasks_raw}
        new_subtasks_trigger_ui_attributes = get_trigger_ui_attributes(new_subtasks_trigger_uis, parsed_xml)

        new_trigger_ui_indexes = [index for ui_indexes in new_subtasks_trigger_uis.values() for index in ui_indexes]
        merged_trigger_ui_indexes = old_trigger_ui_indexes + new_trigger_ui_indexes

        new_extra_ui_attributes = get_extra_ui_attributes(merged_trigger_ui_indexes, parsed_xml)

        # trigger_UIs 필드를 제외한 서브태스크 정보만 추출
        new_available_subtasks = [{key: value for key, value in subtask.items() if key != 'trigger_UIs'} for subtask in
                                  new_subtasks_raw]
        # self.memory.update_node(page_node["index"], new_available_subtasks, new_subtasks_trigger_ui_attributes,
        #                         new_extra_ui_attributes, parsed_xml)

        old_supported_subtasks = [subtask for subtask in page_node['available_subtasks'] if
                                  subtask['name'] in list(subtasks_with_new_trigger_uis.keys())]

        return new_available_subtasks
