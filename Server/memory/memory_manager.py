import json
import os
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

from memory.page_manager import PageManager
from utils import parsing_utils
from utils.action_utils import generalize_action
from loguru import logger
from utils.utils import get_openai_embedding, safe_literal_eval, cosine_similarity


def init_database(path: str, headers: list):
    """Database initialization function - create or load CSV file"""
    if not os.path.exists(path):
        database = pd.DataFrame([], columns=headers)
        database.to_csv(path, index=False)
    else:
        database = pd.read_csv(path)
    return database


class Memory:
    """Memory class for storing and managing task execution information"""
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
        # Subtask Graph: added 'summary' for page summary
        page_header = ['index', 'available_subtasks', 'trigger_uis', 'extra_uis', "screen", "summary"]
        hierarchy_header = ['index', 'screen', 'embedding']

        self.task_db = init_database(self.task_db_path, task_header)

        self.page_db = init_database(self.page_path, page_header)
        # Subtask Graph: Fill missing 'summary' for backward compatibility
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

        # Subtask Graph
        # Stores app navigation structure: pages (nodes) and subtask transitions (edges)
        self.subtask_graph_path = base_database_path + "subtask_graph.json"
        self.subtask_graph = self._load_subtask_graph()

    # ========================================================================
    # Subtask Graph Methods
    # ========================================================================

    def _load_subtask_graph(self) -> dict:
        """Load Subtask Graph from subtask_graph.json or rebuild from existing data."""
        if os.path.exists(self.subtask_graph_path):
            try:
                with open(self.subtask_graph_path, 'r') as f:
                    return json.load(f)
            except (json.JSONDecodeError, IOError):
                logger.warning("Failed to load subtask_graph.json, rebuilding...")

        return self._build_subtask_graph()

    def _save_subtask_graph(self):
        """Save Subtask Graph to subtask_graph.json."""
        try:
            with open(self.subtask_graph_path, 'w') as f:
                json.dump(self.subtask_graph, f, indent=2, ensure_ascii=False)
            logger.info(f"Saved subtask_graph.json with {len(self.subtask_graph.get('edges', []))} edges")
        except IOError as e:
            logger.error(f"Failed to save subtask_graph.json: {e}")

    def _build_subtask_graph(self) -> dict:
        """Rebuild Subtask Graph from existing subtasks.csv and actions.csv data."""
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
        logger.info(f"Built Subtask Graph with {len(graph['nodes'])} nodes and {len(graph['edges'])} edges")
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
        """Check if an equivalent edge already exists in Subtask Graph."""
        for existing in self.subtask_graph.get("edges", []):
            if (existing["from_page"] == edge["from_page"] and
                existing["to_page"] == edge["to_page"] and
                existing["subtask"] == edge["subtask"] and
                existing["trigger_ui_index"] == edge["trigger_ui_index"]):
                return True
        return False

    def add_transition(self, from_page: int, to_page: int, subtask_name: str,
                       trigger_ui_index: int, action_sequence: List[dict] = None):
        """Add a new transition edge to Subtask Graph.

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
            logger.info(f"Added Subtask Graph edge: {from_page} -> {to_page} via '{subtask_name}'")

    def delete_subtask(self, page_index: int, subtask_name: str,
                       trigger_ui_index: int = -1, reason: str = "unknown") -> bool:
        """Delete a subtask from memory due to external app transition or failure.

        This method performs coordinated deletion across:
        1. PageManager CSV files (available_subtasks, subtasks, actions)
        2. Subtask Graph transitions

        Args:
            page_index: Page index where the subtask exists
            subtask_name: Name of the subtask to delete
            trigger_ui_index: UI index that triggers the subtask (-1 to match all)
            reason: Reason for deletion ("external_app", "failure", etc.)

        Returns:
            bool: True if deletion was successful
        """
        logger.warning(f"Deleting subtask '{subtask_name}' from page {page_index} "
            f"(trigger_ui={trigger_ui_index}, reason={reason})")

        try:
            # 1. Delete/update CSV data through PageManager
            if page_index not in self.page_managers:
                self.init_page_manager(page_index)

            page_manager = self.page_managers.get(page_index)
            if page_manager:
                page_manager.delete_subtask_data(
                    subtask_name=subtask_name,
                    trigger_ui_index=trigger_ui_index,
                    reason=reason
                )

            # 2. Delete related edges from Subtask Graph
            self.remove_transition(
                from_page=page_index,
                subtask_name=subtask_name,
                trigger_ui_index=trigger_ui_index
            )

            logger.info(f"Successfully deleted subtask '{subtask_name}' from page {page_index}")
            return True

        except Exception as e:
            logger.error(f"Failed to delete subtask: {str(e)}")
            return False

    def remove_transition(self, from_page: int, subtask_name: str,
                          trigger_ui_index: int = -1) -> bool:
        """Remove transition edge(s) from Subtask Graph.

        Args:
            from_page: Source page index
            subtask_name: Name of the subtask
            trigger_ui_index: UI index (-1 to remove all edges with matching subtask)

        Returns:
            bool: True if any edges were removed
        """
        edges_before = len(self.subtask_graph.get("edges", []))

        # Filter and remove edges matching the condition
        def should_keep(edge: dict) -> bool:
            if edge["from_page"] != from_page:
                return True
            if edge["subtask"] != subtask_name:
                return True
            if trigger_ui_index >= 0 and edge.get("trigger_ui_index", -1) != trigger_ui_index:
                return True
            return False  # Remove if condition matches

        self.subtask_graph["edges"] = [
            edge for edge in self.subtask_graph.get("edges", [])
            if should_keep(edge)
        ]

        edges_removed = edges_before - len(self.subtask_graph.get("edges", []))

        if edges_removed > 0:
            self._save_subtask_graph()
            logger.info(f"Removed {edges_removed} edge(s) from Subtask Graph for subtask '{subtask_name}' at page {from_page}")

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

    def get_all_explored_subtasks(self) -> Dict[int, List[dict]]:
        """Get explored subtasks from subtasks.csv for all pages.

        Used by the planner pipeline (Load step). Returns only subtasks
        that have been explored and registered in subtasks.csv.

        Returns:
            Dict mapping page_index to list of explored subtasks
        """
        result = {}
        if os.path.exists(self.page_database_path):
            for page_dir in os.listdir(self.page_database_path):
                page_path = os.path.join(self.page_database_path, page_dir)
                if os.path.isdir(page_path):
                    try:
                        page_index = int(page_dir)
                        if page_index not in self.page_managers:
                            self.init_page_manager(page_index)
                        subtasks = self.page_managers[page_index].get_subtasks()
                        if subtasks:
                            result[page_index] = subtasks
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
    # Subtask Graph: Page Summary Methods
    # ========================================================================

    def update_page_summary(self, page_index: int, summary: str) -> bool:
        """Update page summary.

        Args:
            page_index: Page index to update
            summary: Page summary (e.g., "This page displays inbox, allows search...")

        Returns:
            bool: True if update was successful
        """
        if page_index in self.page_db.index:
            self.page_db.loc[page_index, 'summary'] = summary
            self.page_db.to_csv(self.page_path, index=False)
            logger.info(f"Updated page summary for page {page_index}: {summary[:50]}...")
            return True
        return False

    def get_page_summary(self, page_index: int) -> str:
        """Get page summary.

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
    # Subtask Graph: Action History Methods
    # ========================================================================

    def update_action_description(self, page_index: int, subtask_name: str,
                                   trigger_ui_index: int, step: int,
                                   description: str, guideline: str = "") -> bool:
        """Update action description and guideline.

        Args:
            page_index: Page index where action exists
            subtask_name: Subtask name
            trigger_ui_index: Trigger UI index
            step: Action step number
            description: Description of what changed
            guideline: Semantic meaning of the action

        Returns:
            bool: True if update was successful
        """
        if page_index not in self.page_managers:
            self.init_page_manager(page_index)

        return self.page_managers[page_index].update_action_description(
            subtask_name, trigger_ui_index, step, description, guideline
        )

    def save_action_history(self, page_index: int, subtask_name: str,
                            history: List[dict]) -> bool:
        """Save action history for a subtask exploration.

        Updates actions.csv with descriptions and guidelines from history entries.

        Args:
            page_index: Page index where subtask exists
            subtask_name: Subtask name
            history: List of history entries [{step, action, description, guideline?}, ...]

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
            guideline = entry.get('guideline', '')
            action = entry.get('action', {})

            # Find trigger_ui_index from action parameters
            trigger_ui_index = action.get('parameters', {}).get('index', -1)

            # Update action description
            result = page_manager.update_action_description(
                subtask_name, trigger_ui_index, step, description, guideline
            )
            if not result:
                success = False

        # Update guideline after all actions are updated
        page_manager.update_guideline(subtask_name)

        logger.info(f"Saved action history for '{subtask_name}' at page {page_index}: {len(history)} entries")
        return success

    def update_guideline(self, page_index: int, subtask_name: str,
                          trigger_ui_index: int = -1) -> str:
        """Update guideline for a subtask by aggregating action-level guidelines.

        Subtask Graph: Called after all action descriptions/guidelines are updated
        to combine them into a single subtask-level guideline.

        Args:
            page_index: Page index where subtask exists
            subtask_name: Subtask name
            trigger_ui_index: Trigger UI index (optional)

        Returns:
            str: The combined guideline string
        """
        if page_index not in self.page_managers:
            self.init_page_manager(page_index)

        return self.page_managers[page_index].update_guideline(
            subtask_name, trigger_ui_index
        )

    def init_page_manager(self, page_index: int):
        """Initialize page manager

        Args:
            page_index: Page index
        """
        if page_index not in self.page_managers:
            self.page_managers[page_index] = PageManager(self.page_database_path, page_index)
        self.page_manager = self.page_managers[page_index]

    def search_node(self, parsed_xml, hierarchy_xml, encoded_xml) -> tuple:
        """Search for a similar node on the current screen

        Returns:
            Tuple[int, float]: (page_index, similarity)
        """
        most_similar_page, similarity = self.__search_most_similar_hierarchy_node(hierarchy_xml)

        if most_similar_page >= 0:
            self.current_page_index = most_similar_page
            return most_similar_page, similarity

        return -1, 0.0

    def get_available_subtasks(self, page_index):
        """Return the list of available subtasks for a specific page"""
        if page_index not in self.page_managers:
            self.init_page_manager(page_index)
        return self.page_managers[page_index].get_available_subtasks()

    def get_subtask_destination(self, page_index: int, subtask_name: str) -> int:
        """Look up the page navigated to when performing a subtask

        Args:
            page_index: Current page index
            subtask_name: Name of the subtask to look up

        Returns:
            int: end_page_index, -1 if not found
        """
        if page_index not in self.page_managers:
            self.init_page_manager(page_index)
        return self.page_managers[page_index].get_subtask_destination(subtask_name)

    def add_new_action(self, new_action, page_index):
        """Add a new action to the page"""
        if page_index not in self.page_managers:
            self.init_page_manager(page_index)
        self.page_managers[page_index].add_new_action(new_action)

    def search_node_by_hierarchy(self, parsed_xml, hierarchy_xml, encoded_xml) -> tuple:
        """Search for a node based on screen hierarchy structure"""
        most_similar_node_index, _ = self.__search_most_similar_hierarchy_node(hierarchy_xml)

        if most_similar_node_index >= 0:
            page_data = json.loads(self.page_db.loc[most_similar_node_index].to_json())
            available_subtasks = json.loads(page_data['available_subtasks'])
            return most_similar_node_index, available_subtasks
        else:
            return -1, []

    def add_node(self, available_subtasks: list, trigger_uis: dict, extra_uis: list, screen: str, screen_num=None) -> int:
        """Add a new node (page) to the database"""
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

        # Create and add a new PageManager instance
        self.page_managers[new_index] = PageManager(self.page_database_path, new_index)

        return new_index

    def update_node(self, page_index, new_available_subtasks: list, new_trigger_uis: dict, new_extra_uis: list,
                    new_screen: str):
        """Update existing node information"""
        page_data = json.loads(self.page_db.loc[page_index].to_json())
        page_data = {key: json.loads(value) if key in ['available_subtasks', 'trigger_uis', 'extra_uis'] else value for
                     key, value in page_data.items()}

        # Add 'exploration' field with default value 'unexplored' for new subtasks
        for subtask in new_available_subtasks:
            if 'exploration' not in subtask:
                subtask['exploration'] = 'unexplored'

        # Merge existing information with new information
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
        """Save screen hierarchy XML along with its embedding"""
        embedding = get_openai_embedding(screen)
        new_screen_hierarchy = {'index': page_index, 'screen': screen, 'embedding': str(embedding)}
        hierarchy_db = init_database(self.screen_hierarchy_path, ['index', 'screen', 'embedding'])
        hierarchy_db = pd.concat([hierarchy_db, pd.DataFrame([new_screen_hierarchy])], ignore_index=True)
        hierarchy_db.to_csv(self.screen_hierarchy_path, index=False)

        self.hierarchy_db = init_database(self.screen_hierarchy_path, ['index', 'screen', 'embedding'])
        self.hierarchy_db['embedding'] = self.hierarchy_db.embedding.apply(safe_literal_eval)

    def save_subtask(self, subtask_raw: dict, example: dict, guideline: str = "") -> None:
        """Save subtask information

        Args:
            subtask_raw: Subtask information dictionary
            example: Training example
            guideline: Guideline for subtask execution
        """
        self.page_manager.save_subtask(subtask_raw, example, guideline)

    def get_next_action(self, subtask: dict, screen: str) -> dict:
        """Return the next action in the current subtask"""
        next_action = self.page_manager.get_next_action(subtask, screen, self.curr_action_step)
        self.curr_action_step += 1
        logger.info("DERIVE")
        return next_action

    def save_action(self, subtask: dict, action: dict, example=None) -> None:
        """Save executed action information"""
        if action['name'] == 'finish':
            self.curr_action_step += 1
        self.page_manager.save_action(subtask, self.curr_action_step, action, example)

    def save_task(self, task_path: list) -> None:
        """Save the entire task path"""
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
        logger.info(f"Path saved: {new_task_path}")

    def mark_subtask_explored(self, page_index: int, subtask_name: str, ui_info: dict = None,
                              action: dict = None, screen: str = None,
                              trigger_ui_index: int = -1, end_page: int = -1):
        """Mark a subtask as explored on a specific page and save action

        Args:
            page_index: Page index (starting page)
            subtask_name: Name of the explored subtask
            ui_info: Clicked UI information (for usage generation)
            action: Performed action (for saving to actions.csv)
            screen: Screen XML (for action generalization)
            trigger_ui_index: Trigger UI index (for distinguishing different paths of the same subtask)
            end_page: Subtask ending page index
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
        """Mark a subtask as explored and save all actions after multi-step exploration

        Args:
            page_index: Page index
            subtask_name: Subtask name
            subtask_info: Subtask information (name, description, parameters)
            actions: List of performed actions [{step, action, screen, reasoning?}, ...]
            trigger_ui_index: Trigger UI index (for distinguishing different paths of the same subtask)
            start_page: Starting page index
            end_page: Ending page index
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
        """Update the end_page of a subtask and its actions

        Updates end_page with the page index arrived at after action execution.

        Args:
            page_index: Page index where the subtask belongs
            subtask_name: Subtask name
            trigger_ui_index: Trigger UI index
            end_page: Page index arrived at after action execution

        Returns:
            bool: Whether the update was successful
        """
        if page_index not in self.page_managers:
            return False
        return self.page_managers[page_index].update_end_page(
            subtask_name, trigger_ui_index, end_page
        )

    def save_task_path(self, new_task_path: dict):
        """Update task path"""
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
        """Retrieve stored task data"""
        # Search for task
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

            logger.warning(f"Known path for the task: {task_name}")
            logger.warning(task_path)

            return task_path

    def __search_similar_hierarchy_nodes(self, hierarchy) -> list:
        """Search for similar hierarchy nodes (based on embedding similarity)"""
        new_hierarchy_vector = np.array(get_openai_embedding(hierarchy))
        self.hierarchy_db["similarity"] = self.hierarchy_db.embedding.apply(
            lambda x: cosine_similarity(x, new_hierarchy_vector))

        # Get the top apps with the highest similarity
        candidates = self.hierarchy_db.sort_values('similarity', ascending=False).head(5).to_dict(orient='records')
        candidate_node_indexes = []
        for node in candidates:
            candidate_node_indexes.append(node['index'])

        return candidate_node_indexes

    def __search_most_similar_hierarchy_node(self, hierarchy) -> tuple:
        """Search for the most similar hierarchy node (threshold 0.95 or above)

        Returns:
            Tuple[int, float]: (page_index, similarity)
        """
        new_hierarchy_vector = np.array(get_openai_embedding(hierarchy))
        self.hierarchy_db["similarity"] = self.hierarchy_db.embedding.apply(
            lambda x: cosine_similarity(x, new_hierarchy_vector))

        # Get the top apps with the highest similarity
        candidates = self.hierarchy_db.sort_values('similarity', ascending=False).head(5).to_dict(orient='records')
        if candidates:
            highest_similarity = candidates[0]['similarity']
            logger.debug(highest_similarity)
            if highest_similarity > 0.95:
                return candidates[0]['index'], highest_similarity
        return -1, 0.0

