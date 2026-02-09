import json
import os
from collections import defaultdict
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

from agents import param_fill_agent, subtask_merge_agent
from memory.page_manager import PageManager
from memory.node_manager import NodeManager
from utils import parsing_utils
from utils.action_utils import generalize_action
from utils.utils import get_openai_embedding, log, safe_literal_eval, cosine_similarity


def init_database(path: str, headers: list):
    """데이터베이스 초기화 함수 - CSV 파일 생성 또는 로드"""
    if not os.path.exists(path):
        database = pd.DataFrame([], columns=headers)
        database.to_csv(path, index=False)
    else:
        database = pd.read_csv(path)
    return database


class Memory:
    """작업 실행 정보를 저장하고 관리하는 메모리 클래스"""
    def __init__(self, app: str, instruction: str, task_name: str):
        self.app = app
        self.instruction = instruction
        self.task_name = task_name
        self.curr_action_step = 0

        base_database_path = f"./memory/{app}/"
        if not os.path.exists(base_database_path):
            os.makedirs(base_database_path)

        self.task_db_path = base_database_path + "tasks.csv"
        self.page_path = base_database_path + "pages.csv"
        self.screen_hierarchy_path = base_database_path + "hierarchy.csv"

        self.page_database_path = base_database_path + "pages/"
        if not os.path.exists(self.page_database_path):
            os.makedirs(self.page_database_path)

        task_header = ['name', 'path']
        # Mobile Map: added 'summary' for UICompass-style page summary
        page_header = ['index', 'available_subtasks', 'trigger_uis', 'extra_uis', "screen", "summary"]
        hierarchy_header = ['index', 'screen', 'embedding']

        self.task_db = init_database(self.task_db_path, task_header)

        self.page_db = init_database(self.page_path, page_header)
        # Mobile Map: Fill missing 'summary' for backward compatibility
        if 'summary' not in self.page_db.columns:
            self.page_db['summary'] = ''
        else:
            self.page_db['summary'] = self.page_db['summary'].fillna('')
        self.page_db.set_index('index', drop=False, inplace=True)

        self.hierarchy_db = init_database(self.screen_hierarchy_path, hierarchy_header)
        self.hierarchy_db['embedding'] = self.hierarchy_db.embedding.apply(safe_literal_eval)
        self.task_path = self.__get_task_data(self.task_name)
        self.page_managers: Dict[int, PageManager] = {}
        self.page_manager = None
        self.current_page_index = -1

        # Mobile Map (formerly STG - Subtask Transition Graph)
        # Stores app navigation structure: pages (nodes) and subtask transitions (edges)
        self.subtask_graph_path = base_database_path + "subtask_graph.json"
        self.subtask_graph = self._load_subtask_graph()

    # ========================================================================
    # Mobile Map Methods (Subtask Transition Graph)
    # ========================================================================

    def _load_subtask_graph(self) -> dict:
        """Load Mobile Map from subtask_graph.json or rebuild from existing data."""
        if os.path.exists(self.subtask_graph_path):
            try:
                with open(self.subtask_graph_path, 'r') as f:
                    return json.load(f)
            except (json.JSONDecodeError, IOError):
                log("Failed to load subtask_graph.json, rebuilding...", "yellow")

        return self._build_subtask_graph()

    def _save_subtask_graph(self):
        """Save Mobile Map to subtask_graph.json."""
        try:
            with open(self.subtask_graph_path, 'w') as f:
                json.dump(self.subtask_graph, f, indent=2, ensure_ascii=False)
            log(f"Saved subtask_graph.json with {len(self.subtask_graph.get('edges', []))} edges")
        except IOError as e:
            log(f"Failed to save subtask_graph.json: {e}", "red")

    def _build_subtask_graph(self) -> dict:
        """Rebuild Mobile Map from existing subtasks.csv and actions.csv data."""
        graph = {"nodes": [], "edges": []}

        # Collect all page indices
        if os.path.exists(self.page_database_path):
            for page_dir in os.listdir(self.page_database_path):
                page_path = os.path.join(self.page_database_path, page_dir)
                if os.path.isdir(page_path):
                    try:
                        page_index = int(page_dir)
                        if page_index not in graph["nodes"]:
                            graph["nodes"].append(page_index)

                        # Read subtasks.csv for transition info
                        subtasks_path = os.path.join(page_path, "subtasks.csv")
                        if os.path.exists(subtasks_path):
                            subtasks_df = pd.read_csv(subtasks_path)
                            for _, row in subtasks_df.iterrows():
                                start_page = int(row.get('start_page', page_index))
                                end_page = int(row.get('end_page', -1))
                                if end_page >= 0 and start_page != end_page:
                                    edge = {
                                        "from_page": start_page,
                                        "to_page": end_page,
                                        "subtask": row.get('name', ''),
                                        "trigger_ui_index": int(row.get('trigger_ui_index', -1)),
                                        "action_sequence": self._get_action_sequence(
                                            page_path, row.get('name'), int(row.get('trigger_ui_index', -1))
                                        ),
                                        "explored": True
                                    }
                                    if not self._edge_exists(edge):
                                        graph["edges"].append(edge)
                                        if end_page not in graph["nodes"]:
                                            graph["nodes"].append(end_page)
                    except ValueError:
                        continue

        graph["nodes"].sort()
        log(f"Built Mobile Map with {len(graph['nodes'])} nodes and {len(graph['edges'])} edges")
        return graph

    def _get_action_sequence(self, page_path: str, subtask_name: str,
                              trigger_ui_index: int) -> List[dict]:
        """Get action sequence for a subtask from actions.csv."""
        actions_path = os.path.join(page_path, "actions.csv")
        if not os.path.exists(actions_path):
            return []

        try:
            actions_df = pd.read_csv(actions_path)
            condition = (actions_df['subtask_name'] == subtask_name)
            if trigger_ui_index >= 0:
                condition = condition & (actions_df['trigger_ui_index'] == trigger_ui_index)

            subtask_actions = actions_df[condition].sort_values('step')
            action_sequence = []
            for _, row in subtask_actions.iterrows():
                try:
                    action = json.loads(row['action'])
                    if action.get('name') != 'finish':
                        action_sequence.append(action)
                except (json.JSONDecodeError, TypeError):
                    continue
            return action_sequence
        except Exception:
            return []

    def _edge_exists(self, edge: dict) -> bool:
        """Check if an equivalent edge already exists in Mobile Map."""
        for existing in self.subtask_graph.get("edges", []):
            if (existing["from_page"] == edge["from_page"] and
                existing["to_page"] == edge["to_page"] and
                existing["subtask"] == edge["subtask"] and
                existing["trigger_ui_index"] == edge["trigger_ui_index"]):
                return True
        return False

    def add_transition(self, from_page: int, to_page: int, subtask_name: str,
                       trigger_ui_index: int, action_sequence: List[dict] = None):
        """Add a new transition edge to Mobile Map.

        Args:
            from_page: Source page index
            to_page: Destination page index
            subtask_name: Name of the subtask causing transition
            trigger_ui_index: UI index that triggers the subtask
            action_sequence: List of actions to execute
        """
        if from_page == to_page:
            return  # Same page, no transition

        edge = {
            "from_page": from_page,
            "to_page": to_page,
            "subtask": subtask_name,
            "trigger_ui_index": trigger_ui_index,
            "action_sequence": action_sequence or [],
            "explored": True
        }

        if not self._edge_exists(edge):
            # Ensure nodes exist
            if from_page not in self.subtask_graph["nodes"]:
                self.subtask_graph["nodes"].append(from_page)
                self.subtask_graph["nodes"].sort()
            if to_page not in self.subtask_graph["nodes"]:
                self.subtask_graph["nodes"].append(to_page)
                self.subtask_graph["nodes"].sort()

            self.subtask_graph["edges"].append(edge)
            self._save_subtask_graph()
            log(f"Added Mobile Map edge: {from_page} -> {to_page} via '{subtask_name}'")

    def delete_subtask(self, page_index: int, subtask_name: str,
                       trigger_ui_index: int = -1, reason: str = "unknown") -> bool:
        """Delete a subtask from memory due to external app transition or failure.

        This method performs coordinated deletion across:
        1. PageManager CSV files (available_subtasks, subtasks, actions)
        2. Mobile Map transitions

        Args:
            page_index: Page index where the subtask exists
            subtask_name: Name of the subtask to delete
            trigger_ui_index: UI index that triggers the subtask (-1 to match all)
            reason: Reason for deletion ("external_app", "failure", etc.)

        Returns:
            bool: True if deletion was successful
        """
        log(f":::DELETE::: Deleting subtask '{subtask_name}' from page {page_index} "
            f"(trigger_ui={trigger_ui_index}, reason={reason})", "yellow")

        try:
            # 1. PageManager를 통해 CSV 데이터 삭제/업데이트
            if page_index not in self.page_managers:
                self.init_page_manager(page_index)

            page_manager = self.page_managers.get(page_index)
            if page_manager:
                page_manager.delete_subtask_data(
                    subtask_name=subtask_name,
                    trigger_ui_index=trigger_ui_index,
                    reason=reason
                )

            # 2. Mobile Map에서 관련 엣지 삭제
            self.remove_transition(
                from_page=page_index,
                subtask_name=subtask_name,
                trigger_ui_index=trigger_ui_index
            )

            log(f":::DELETE::: Successfully deleted subtask '{subtask_name}' from page {page_index}", "green")
            return True

        except Exception as e:
            log(f":::DELETE::: Failed to delete subtask: {str(e)}", "red")
            return False

    def remove_transition(self, from_page: int, subtask_name: str,
                          trigger_ui_index: int = -1) -> bool:
        """Remove transition edge(s) from Mobile Map.

        Args:
            from_page: Source page index
            subtask_name: Name of the subtask
            trigger_ui_index: UI index (-1 to remove all edges with matching subtask)

        Returns:
            bool: True if any edges were removed
        """
        edges_before = len(self.subtask_graph.get("edges", []))

        # 조건에 맞는 엣지 필터링하여 제거
        def should_keep(edge: dict) -> bool:
            if edge["from_page"] != from_page:
                return True
            if edge["subtask"] != subtask_name:
                return True
            if trigger_ui_index >= 0 and edge.get("trigger_ui_index", -1) != trigger_ui_index:
                return True
            return False  # 조건에 맞으면 제거

        self.subtask_graph["edges"] = [
            edge for edge in self.subtask_graph.get("edges", [])
            if should_keep(edge)
        ]

        edges_removed = edges_before - len(self.subtask_graph.get("edges", []))

        if edges_removed > 0:
            self._save_subtask_graph()
            log(f":::DELETE::: Removed {edges_removed} edge(s) from Mobile Map for subtask '{subtask_name}' at page {from_page}")

        return edges_removed > 0

    def get_path_to_page(self, from_page: int, to_page: int) -> Optional[List[dict]]:
        """Find shortest path between pages using BFS.

        Args:
            from_page: Starting page index
            to_page: Target page index

        Returns:
            List of edges forming the path, or None if no path exists
        """
        if from_page == to_page:
            return []

        # BFS for shortest path
        queue = [(from_page, [])]
        visited = {from_page}

        while queue:
            current, path = queue.pop(0)

            for edge in self.subtask_graph.get("edges", []):
                if edge["from_page"] == current and edge["to_page"] not in visited:
                    new_path = path + [edge]
                    if edge["to_page"] == to_page:
                        return new_path
                    visited.add(edge["to_page"])
                    queue.append((edge["to_page"], new_path))

        return None  # No path found

    def get_all_available_subtasks(self) -> Dict[int, List[dict]]:
        """Get all available subtasks for all pages.

        Returns:
            Dict mapping page_index to list of available subtasks
        """
        result = {}
        if os.path.exists(self.page_database_path):
            for page_dir in os.listdir(self.page_database_path):
                page_path = os.path.join(self.page_database_path, page_dir)
                if os.path.isdir(page_path):
                    try:
                        page_index = int(page_dir)
                        result[page_index] = self.get_available_subtasks(page_index)
                    except ValueError:
                        continue
        return result

    def get_outgoing_edges(self, page_index: int) -> List[dict]:
        """Get all outgoing edges from a page.

        Args:
            page_index: Source page index

        Returns:
            List of edges originating from the page
        """
        return [
            edge for edge in self.subtask_graph.get("edges", [])
            if edge["from_page"] == page_index
        ]

    # ========================================================================
    # Mobile Map: Page Summary Methods (UICompass Integration)
    # ========================================================================

    def update_page_summary(self, page_index: int, summary: str) -> bool:
        """Update UICompass-style page summary.

        Args:
            page_index: Page index to update
            summary: Page summary (e.g., "This page displays inbox, allows search...")

        Returns:
            bool: True if update was successful
        """
        if page_index in self.page_db.index:
            self.page_db.loc[page_index, 'summary'] = summary
            self.page_db.to_csv(self.page_path, index=False)
            log(f"Updated page summary for page {page_index}: {summary[:50]}...")
            return True
        return False

    def get_page_summary(self, page_index: int) -> str:
        """Get UICompass-style page summary.

        Args:
            page_index: Page index

        Returns:
            str: Page summary or empty string if not found
        """
        if page_index in self.page_db.index:
            summary = self.page_db.loc[page_index, 'summary']
            return summary if pd.notna(summary) else ''
        return ''

    # ========================================================================
    # Mobile Map: Action History Methods (M3A Integration)
    # ========================================================================

    def update_action_description(self, page_index: int, subtask_name: str,
                                   trigger_ui_index: int, step: int,
                                   description: str, guidance: str = "") -> bool:
        """Update M3A-style action description and guidance.

        Args:
            page_index: Page index where action exists
            subtask_name: Subtask name
            trigger_ui_index: Trigger UI index
            step: Action step number
            description: M3A-style description of what changed
            guidance: Semantic meaning of the action

        Returns:
            bool: True if update was successful
        """
        if page_index not in self.page_managers:
            self.init_page_manager(page_index)

        return self.page_managers[page_index].update_action_description(
            subtask_name, trigger_ui_index, step, description, guidance
        )

    def save_action_history(self, page_index: int, subtask_name: str,
                            history: List[dict]) -> bool:
        """Save M3A-style action history for a subtask exploration.

        Updates actions.csv with descriptions and guidances from history entries.

        Args:
            page_index: Page index where subtask exists
            subtask_name: Subtask name
            history: List of history entries [{step, action, description, guidance?}, ...]

        Returns:
            bool: True if save was successful
        """
        if page_index not in self.page_managers:
            self.init_page_manager(page_index)

        page_manager = self.page_managers[page_index]
        success = True

        for entry in history:
            step = entry.get('step', 0)
            description = entry.get('description', '')
            guidance = entry.get('guidance', '')
            action = entry.get('action', {})

            # Find trigger_ui_index from action parameters
            trigger_ui_index = action.get('parameters', {}).get('index', -1)

            # Update action description
            result = page_manager.update_action_description(
                subtask_name, trigger_ui_index, step, description, guidance
            )
            if not result:
                success = False

        # Update combined guidance after all actions are updated
        page_manager.update_combined_guidance(subtask_name)

        log(f"Saved action history for '{subtask_name}' at page {page_index}: {len(history)} entries")
        return success

    def update_combined_guidance(self, page_index: int, subtask_name: str,
                                  trigger_ui_index: int = -1) -> str:
        """Update combined guidance for a subtask by aggregating action guidances.

        Mobile Map: Called after all action descriptions/guidances are updated
        to combine them into a single subtask-level guidance.

        Args:
            page_index: Page index where subtask exists
            subtask_name: Subtask name
            trigger_ui_index: Trigger UI index (optional)

        Returns:
            str: The combined guidance string
        """
        if page_index not in self.page_managers:
            self.init_page_manager(page_index)

        return self.page_managers[page_index].update_combined_guidance(
            subtask_name, trigger_ui_index
        )

    def init_page_manager(self, page_index: int):
        """페이지 관리자 초기화

        Args:
            page_index: 페이지 인덱스
        """
        if page_index not in self.page_managers:
            self.page_managers[page_index] = PageManager(self.page_database_path, page_index)
        self.page_manager = self.page_managers[page_index]

    def search_node(self, parsed_xml, hierarchy_xml, encoded_xml) -> tuple:
        """현재 화면에서 유사한 노드 검색

        Returns:
            Tuple[int, float]: (page_index, similarity)
        """
        most_similar_page, similarity = self.__search_most_similar_hierarchy_node(hierarchy_xml)

        if most_similar_page >= 0:
            self.current_page_index = most_similar_page
            return most_similar_page, similarity

        return -1, 0.0

    def get_available_subtasks(self, page_index):
        """특정 페이지에서 사용 가능한 서브태스크 목록 반환"""
        if page_index not in self.page_managers:
            self.init_page_manager(page_index)
        return self.page_managers[page_index].get_available_subtasks()

    def get_subtask_destination(self, page_index: int, subtask_name: str) -> int:
        """subtask 수행 시 이동하는 page 조회

        Args:
            page_index: 현재 페이지 인덱스
            subtask_name: 조회할 서브태스크 이름

        Returns:
            int: end_page_index, -1 if not found
        """
        if page_index not in self.page_managers:
            self.init_page_manager(page_index)
        return self.page_managers[page_index].get_subtask_destination(subtask_name)

    def add_new_action(self, new_action, page_index):
        """새로운 액션을 페이지에 추가"""
        if page_index not in self.page_managers:
            self.init_page_manager(page_index)
        self.page_managers[page_index].add_new_action(new_action)

    def search_node_by_hierarchy(self, parsed_xml, hierarchy_xml, encoded_xml) -> tuple:
        """화면 계층 구조를 기반으로 노드 검색"""
        most_similar_node_index, _ = self.__search_most_similar_hierarchy_node(hierarchy_xml)

        if most_similar_node_index >= 0:
            page_data = json.loads(self.page_db.loc[most_similar_node_index].to_json())
            available_subtasks = json.loads(page_data['available_subtasks'])
            return most_similar_node_index, available_subtasks
        else:
            return -1, []

    def add_node(self, available_subtasks: list, trigger_uis: dict, extra_uis: list, screen: str, screen_num=None) -> int:
        """새로운 노드(페이지)를 데이터베이스에 추가"""
        new_index = len(self.page_db)
        new_row = {'index': new_index, 'available_subtasks': json.dumps(available_subtasks),
                   'trigger_uis': json.dumps(trigger_uis),
                   'extra_uis': json.dumps(extra_uis), "screen": screen}
        self.page_db = pd.concat([self.page_db, pd.DataFrame([new_row])], ignore_index=True)
        self.page_db.to_csv(self.page_path, index=False)

        page_path = self.page_database_path + f"{new_index}/"
        page_screen_path = os.path.join(page_path, "screen")
        if not os.path.exists(page_path):
            os.makedirs(page_path)
            # Add 'exploration' field with default value 'unexplored'
            for subtask in available_subtasks:
                if 'exploration' not in subtask:
                    subtask['exploration'] = 'unexplored'
            available_subtasks_df = pd.DataFrame(available_subtasks)
            available_subtasks_df.to_csv(os.path.join(page_path, "available_subtasks.csv"), index=False)
            os.makedirs(page_screen_path)
        parsing_utils.save_screen_info(self.app, self.task_name, page_screen_path, screen_num)

        # 새로운 PageManager 인스턴스 생성 및 추가
        self.page_managers[new_index] = PageManager(self.page_database_path, new_index)

        return new_index

    def update_node(self, page_index, new_available_subtasks: list, new_trigger_uis: dict, new_extra_uis: list,
                    new_screen: str):
        """기존 노드 정보 업데이트"""
        page_data = json.loads(self.page_db.loc[page_index].to_json())
        page_data = {key: json.loads(value) if key in ['available_subtasks', 'trigger_uis', 'extra_uis'] else value for
                     key, value in page_data.items()}

        # Add 'exploration' field with default value 'unexplored' for new subtasks
        for subtask in new_available_subtasks:
            if 'exploration' not in subtask:
                subtask['exploration'] = 'unexplored'

        # 기존 정보와 새 정보 병합
        merged_available_subtasks = page_data['available_subtasks'] + new_available_subtasks
        merged_trigger_uis = {}
        merged_trigger_uis.update(page_data['trigger_uis'])
        merged_trigger_uis.update(new_trigger_uis)
        merged_extra_uis = page_data['extra_uis'] + new_extra_uis

        updated_row = {'index': page_index, 'available_subtasks': json.dumps(merged_available_subtasks),
                       'trigger_uis': json.dumps(merged_trigger_uis),
                       'extra_uis': json.dumps(merged_extra_uis), "screen": new_screen}

        self.page_db.loc[page_index] = updated_row
        self.page_db.to_csv(self.page_path, index=False)

        page_path = self.page_database_path + f"{page_index}/"
        available_subtasks_df = pd.DataFrame(merged_available_subtasks)
        available_subtasks_df.to_csv(os.path.join(page_path, "available_subtasks.csv"), index=False)

    def add_hierarchy_xml(self, screen, page_index):
        """화면 계층 구조 XML을 임베딩과 함께 저장"""
        embedding = get_openai_embedding(screen)
        new_screen_hierarchy = {'index': page_index, 'screen': screen, 'embedding': str(embedding)}
        hierarchy_db = init_database(self.screen_hierarchy_path, ['index', 'screen', 'embedding'])
        hierarchy_db = pd.concat([hierarchy_db, pd.DataFrame([new_screen_hierarchy])], ignore_index=True)
        hierarchy_db.to_csv(self.screen_hierarchy_path, index=False)

        self.hierarchy_db = init_database(self.screen_hierarchy_path, ['index', 'screen', 'embedding'])
        self.hierarchy_db['embedding'] = self.hierarchy_db.embedding.apply(safe_literal_eval)

    def get_next_subtask(self, page_index, qa_history, screen):
        """다음에 실행할 서브태스크 반환"""
        # 액션 단계 초기화
        self.curr_action_step = 0

        candidate_subtasks = self.task_path.get(page_index, [])
        next_subtask_name = None
        for subtask in candidate_subtasks:
            if not subtask.get("traversed", False):
                next_subtask_name = subtask.get("name")
                subtask['traversed'] = True
                break
        if next_subtask_name == 'finish':
            finish_subtask = {"name": "finish",
                              "description": "Use this to signal that the task has been completed",
                              "parameters": {}
                              }
            return finish_subtask
        elif next_subtask_name == "scroll_screen":
            scroll_subtask = {"name": "scroll_screen", "parameters": {"scroll_ui_index": 1, "direction": 'down'}}
            return scroll_subtask

        if next_subtask_name:
            next_subtask_data = self.page_manager.get_next_subtask_data(next_subtask_name)

            next_subtask = {'name': next_subtask_data['name'], 'description': next_subtask_data['description'],
                            'parameters': json.loads(next_subtask_data['parameters']) if next_subtask_data['parameters'] != "\"{}\"" else {}}

            if len(next_subtask['parameters']) > 0:
                params = param_fill_agent.parm_fill_subtask(instruction=self.instruction,
                                                            subtask=next_subtask,
                                                            qa_history=qa_history,
                                                            screen=screen,
                                                            example=json.loads(
                                                                next_subtask_data.get('example', {})))

                next_subtask['parameters'] = params

            return next_subtask

        return None

    def save_subtask(self, subtask_raw: dict, example: dict, guideline: str = "") -> None:
        """서브태스크 정보 저장

        Args:
            subtask_raw: 서브태스크 정보 딕셔너리
            example: 학습용 예시
            guideline: 서브태스크 수행 가이드라인
        """
        self.page_manager.save_subtask(subtask_raw, example, guideline)

    def get_next_action(self, subtask: dict, screen: str) -> dict:
        """현재 서브태스크에서 다음 액션 반환"""
        next_action = self.page_manager.get_next_action(subtask, screen, self.curr_action_step)
        self.curr_action_step += 1
        log(f":::DERIVE:::", "blue")
        return next_action

    def save_action(self, subtask: dict, action: dict, example=None) -> None:
        """실행한 액션 정보 저장"""
        if action['name'] == 'finish':
            self.curr_action_step += 1
        self.page_manager.save_action(subtask, self.curr_action_step, action, example)

    def merge_subtasks(self, task_path: list) -> list:
        """중복 서브태스크 병합"""
        # 마지막 finish 서브태스크 제거
        finish_subtask = task_path.pop()

        # 수행된 서브태스크 목록 초기화
        raw_subtask_list = []
        for subtask_data in task_path:
            page_index = subtask_data['page_index']
            subtask_name = subtask_data['subtask_name']
            page_data = json.loads(self.page_db.loc[page_index].to_json())
            available_subtasks = json.loads(page_data['available_subtasks'])
            for subtask_available in available_subtasks:
                if subtask_available['name'] == subtask_name:
                    raw_subtask_list.append(subtask_available)

        merged_subtask_list = subtask_merge_agent.merge_subtasks(raw_subtask_list)

        merged_task_path = self.__merge_subtasks_data(task_path, merged_subtask_list)
        # 마지막에 Finish 서브태스크 다시 추가
        merged_task_path.append(finish_subtask)

        return merged_task_path

    def save_task(self, task_path: list) -> None:
        """전체 작업 경로 저장"""
        for subtask in task_path:
            subtask_name = subtask['subtask_name']
            subtask_dict = subtask['subtask']
            actions = subtask['actions']
            step = 0
            for action_data in actions:
                page_index = action_data['page_index']
                action = action_data['action']
                screen = action_data['screen']
                example = action_data['example']

                if action['name'] == 'finish' or example:
                    generalized_action = generalize_action(action, subtask_dict, screen)
                    if page_index not in self.page_managers:
                        self.init_page_manager(page_index)
                    page_manager = self.page_managers[page_index]
                    page_manager.save_action(subtask_name, -1, step, generalized_action, example)
                step += 1

        known_task_path = {
            key: [item["name"] for item in value]
            for key, value in self.task_path.items()
        }

        for subtask in task_path:
            page_index = subtask['page_index']
            subtask_name = subtask['subtask_name']
            if page_index in known_task_path:
                if subtask_name not in known_task_path[page_index]:
                    known_task_path[page_index].append(subtask_name)
            else:
                known_task_path[page_index] = [subtask_name]

        new_task_path = {
            'name': self.task_name,
            'path': json.dumps(known_task_path)
        }


        condition = (self.task_db['name'] == new_task_path['name'])
        if condition.any():
            self.task_db.loc[condition] = pd.DataFrame([new_task_path])
        else:
            self.task_db = pd.concat([self.task_db, pd.DataFrame([new_task_path])], ignore_index=True)

        self.task_db.to_csv(self.task_db_path, index=False)
        log(f":::TASK SAVE::: Path saved: {new_task_path}")

    def mark_subtask_explored(self, page_index: int, subtask_name: str, ui_info: dict = None,
                              action: dict = None, screen: str = None,
                              trigger_ui_index: int = -1, end_page: int = -1):
        """Mark a subtask as explored on a specific page and save action

        Args:
            page_index: 페이지 인덱스 (시작 페이지)
            subtask_name: 탐험 완료된 서브태스크 이름
            ui_info: 클릭된 UI 정보 (usage 생성용)
            action: 수행된 액션 (actions.csv 저장용)
            screen: 화면 XML (액션 일반화용)
            trigger_ui_index: 트리거 UI 인덱스 (같은 서브태스크의 다른 경로 구분용)
            end_page: 서브태스크 종료 페이지 인덱스
        """
        if page_index not in self.page_managers:
            self.init_page_manager(page_index)
        self.page_managers[page_index].mark_subtask_explored(
            subtask_name, ui_info, action, screen,
            trigger_ui_index=trigger_ui_index,
            start_page=page_index, end_page=end_page
        )

    def mark_subtask_explored_multistep(self, page_index: int, subtask_name: str,
                                         subtask_info: dict, actions: list,
                                         trigger_ui_index: int = -1,
                                         start_page: int = -1, end_page: int = -1):
        """Multi-step 탐색 완료 후 서브태스크를 explored로 마킹하고 모든 액션 저장

        Args:
            page_index: 페이지 인덱스
            subtask_name: 서브태스크 이름
            subtask_info: 서브태스크 정보 (name, description, parameters)
            actions: 수행된 액션 리스트 [{step, action, screen, reasoning?}, ...]
            trigger_ui_index: 트리거 UI 인덱스 (같은 서브태스크의 다른 경로 구분용)
            start_page: 시작 페이지 인덱스
            end_page: 종료 페이지 인덱스
        """
        if page_index not in self.page_managers:
            self.init_page_manager(page_index)
        self.page_managers[page_index].mark_subtask_explored_multistep(
            page_index, subtask_name, subtask_info, actions,
            trigger_ui_index=trigger_ui_index,
            start_page=start_page, end_page=end_page
        )

    def update_end_page(self, page_index: int, subtask_name: str,
                        trigger_ui_index: int, end_page: int) -> bool:
        """서브태스크와 액션의 end_page 업데이트

        액션 실행 후 도착한 페이지 인덱스로 end_page를 업데이트합니다.

        Args:
            page_index: 서브태스크가 속한 페이지 인덱스
            subtask_name: 서브태스크 이름
            trigger_ui_index: 트리거 UI 인덱스
            end_page: 액션 실행 후 도착한 페이지 인덱스

        Returns:
            bool: 업데이트 성공 여부
        """
        if page_index not in self.page_managers:
            return False
        return self.page_managers[page_index].update_end_page(
            subtask_name, trigger_ui_index, end_page
        )

    def save_task_path(self, new_task_path: dict):
        """작업 경로 업데이트"""
        for page_index, subtasks in new_task_path.items():
            if page_index in self.task_path:
                self.task_path[page_index].extend(subtasks)
            else:
                self.task_path[page_index] = subtasks[:]

        new_task_data = {
            'name': self.task_name,
            'path': json.dumps(self.task_path)
        }

        condition = (self.task_db['name'] == new_task_data['name'])
        if condition.any():
            for column in new_task_path.keys():
                self.task_db.loc[condition, column] = new_task_path[column]
        else:
            self.task_db = pd.concat([self.task_db, pd.DataFrame([new_task_data])], ignore_index=True)

        self.task_db.to_csv(self.task_db_path, index=False)

    def __get_task_data(self, task_name):
        """저장된 작업 데이터 가져오기"""
        # 작업 검색
        matched_tasks = self.task_db[(self.task_db['name'] == task_name)]
        if matched_tasks.empty:
            return {}
        else:
            task_data = matched_tasks.iloc[0].to_dict()
            path = json.loads(task_data['path'])

            task_path = {}
            for page_index, subtasks in path.items():
                subtasks_data = []
                for subtask in subtasks:
                    subtasks_data.append({"name": subtask, "traversed": False})
                task_path[int(page_index)] = subtasks_data

            log(f"Known path for the task: {task_name}", "yellow")
            log(task_path, "yellow")

            return task_path

    def __search_similar_hierarchy_nodes(self, hierarchy) -> list:
        """유사한 계층 구조 노드들 검색 (임베딩 유사도 기반)"""
        new_hierarchy_vector = np.array(get_openai_embedding(hierarchy))
        self.hierarchy_db["similarity"] = self.hierarchy_db.embedding.apply(
            lambda x: cosine_similarity(x, new_hierarchy_vector))

        # 가장 유사도가 높은 상위 앱들 가져오기
        candidates = self.hierarchy_db.sort_values('similarity', ascending=False).head(5).to_dict(orient='records')
        candidate_node_indexes = []
        for node in candidates:
            candidate_node_indexes.append(node['index'])

        return candidate_node_indexes

    def __search_most_similar_hierarchy_node(self, hierarchy) -> tuple:
        """가장 유사한 계층 구조 노드 검색 (임계값 0.95 이상)

        Returns:
            Tuple[int, float]: (page_index, similarity)
        """
        new_hierarchy_vector = np.array(get_openai_embedding(hierarchy))
        self.hierarchy_db["similarity"] = self.hierarchy_db.embedding.apply(
            lambda x: cosine_similarity(x, new_hierarchy_vector))

        # 가장 유사도가 높은 상위 앱들 가져오기
        candidates = self.hierarchy_db.sort_values('similarity', ascending=False).head(5).to_dict(orient='records')
        if candidates:
            highest_similarity = candidates[0]['similarity']
            print(highest_similarity)
            if highest_similarity > 0.95:
                return candidates[0]['index'], highest_similarity
        return -1, 0.0

    def __merge_subtasks_data(self, original_subtasks_data, merged_subtasks) -> list:
        """서브태스크 데이터 병합 - 원본 데이터와 병합된 서브태스크 정보 통합"""
        len_diff = len(original_subtasks_data) - len(merged_subtasks)
        for i in range(0, len_diff):
            merged_subtasks.append({"name": "dummy"})

        original_pointer = 0
        merged_pointer = 0
        while original_pointer < len(original_subtasks_data):
            curr_subtask_data = original_subtasks_data[original_pointer]
            curr_subtask_name = curr_subtask_data['subtask_name']
            curr_subtask_actions = curr_subtask_data['actions']

            merged_subtask_dict = merged_subtasks[merged_pointer]
            if merged_subtask_dict['name'] == curr_subtask_name:
                page_index = curr_subtask_data['page_index']
                page_data = json.loads(self.page_db.loc[page_index].to_json())
                available_subtasks = json.loads(page_data['available_subtasks'])
                # 사용 가능한 서브태스크 목록을 순회하며 새로운 것으로 교체
                for i in range(len(available_subtasks)):
                    if available_subtasks[i]['name'] == curr_subtask_name:
                        available_subtasks[i] = merged_subtask_dict

                page_data['available_subtasks'] = json.dumps(available_subtasks)
                self.page_db.loc[page_index] = page_data
                self.page_db.to_csv(self.page_path, index=False)

                if page_index not in self.page_managers:
                    self.init_page_manager(page_index)
                self.page_managers[page_index].update_subtask_info(merged_subtask_dict)

                merged_subtask_params = merged_subtask_dict['parameters']
                curr_subtask_params = curr_subtask_data['subtask']['parameters']
                for param_name, _ in merged_subtask_params.items():
                    if param_name not in curr_subtask_params:
                        curr_subtask_params[param_name] = None

                original_pointer += 1
                merged_pointer += 1
            else:
                base_subtask_data = original_subtasks_data[original_pointer - 1]
                base_subtask_actions = base_subtask_data['actions']

                base_subtask_params = base_subtask_data['subtask']['parameters']
                curr_subtask_params = curr_subtask_data['subtask']['parameters']
                for param_name, param_value in base_subtask_params.items():
                    if param_value is None and param_name in curr_subtask_params:
                        base_subtask_params[param_name] = curr_subtask_params[param_name]

                base_subtask_actions.pop()

                merged_actions = base_subtask_actions + curr_subtask_actions
                base_subtask_data['actions'] = merged_actions

                original_subtasks_data.pop(original_pointer)

        return original_subtasks_data
