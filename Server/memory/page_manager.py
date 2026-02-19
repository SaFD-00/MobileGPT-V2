import json
import os

import pandas as pd

from agents import param_fill_agent
from utils.action_utils import adapt_action
from utils.utils import log


def init_database(path: str, headers: list):
    """Database initialization - create or load CSV file"""
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
    """Class for managing subtasks and actions for each page (screen state)"""
    def __init__(self, page_path, page_index):
        self.page_index = page_index

        subtask_header = ['name', 'description', 'guideline', 'trigger_ui_index', 'start_page', 'end_page', 'parameters', 'example']
        # Mobile Map: added 'description' (action history) and 'guideline' (semantic action meaning)
        action_header = ['subtask_name', 'trigger_ui_index', 'step', 'start_page', 'end_page', 'action', 'description', 'guideline', 'example']
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

        # Backward compatibility: migrate 'combined_guidance' data into 'guideline'
        if 'combined_guidance' in self.subtask_db.columns:
            # Copy combined_guidance values into guideline where guideline is empty
            mask = (self.subtask_db['guideline'] == '') & (self.subtask_db['combined_guidance'] != '')
            self.subtask_db.loc[mask, 'guideline'] = self.subtask_db.loc[mask, 'combined_guidance']
            self.subtask_db = self.subtask_db.drop(columns=['combined_guidance'])

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

        # Mobile Map: Fill missing 'description' and 'guideline' for backward compatibility
        if 'description' not in self.action_db.columns:
            self.action_db['description'] = ''
        else:
            self.action_db['description'] = self.action_db['description'].fillna('')

        # Backward compatibility: rename old 'guidance' column to 'guideline'
        if 'guidance' in self.action_db.columns and 'guideline' not in self.action_db.columns:
            self.action_db = self.action_db.rename(columns={'guidance': 'guideline'})

        if 'guideline' not in self.action_db.columns:
            self.action_db['guideline'] = ''
        else:
            self.action_db['guideline'] = self.action_db['guideline'].fillna('')

        self.action_data = self.action_db.to_dict(orient='records')

        for action in self.action_data:
            action['traversed'] = False

    def get_available_subtasks(self):
        """Return the list of available subtasks (merging guideline information from subtasks.csv)"""
        available_subtasks = self.available_subtask_db.to_dict(orient='records')

        # Fetch guideline information from subtasks.csv and merge
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
        """Add a new action"""
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
            subtask_name: Name of the explored subtask
            ui_info: Clicked UI information (for guideline generation)
            action: Performed action (for saving to actions.csv)
            screen: Screen XML (for action generalization)
            trigger_ui_index: Trigger UI index
            start_page: Subtask starting page index
            end_page: Subtask ending page index
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

            # === Save action to actions.csv ===
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

                # Generalize the action
                generalized_action = generalize_action(action, subtask_dict, screen)

                # Save to actions.csv
                self.save_action(subtask_name, trigger_ui_index, 0, generalized_action, {},
                                start_page=start_page, end_page=end_page)

                # Also save the finish action
                finish_action = {"name": "finish", "parameters": {}}
                self.save_action(subtask_name, trigger_ui_index, 1, finish_action, {},
                                start_page=end_page, end_page=end_page)

                log(f"Action saved for subtask '{subtask_name}' (trigger_ui={trigger_ui_index}) in actions.csv")

    def _generate_guideline_from_ui(self, ui_info: dict) -> str:
        """Generate a guideline string from UI information"""
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
        """Generate a guideline string from action information

        Extracts description from action parameters to generate a guideline.
        Converts "Click to explore 'X'" to "Triggered by clicking 'X'".
        """
        if not action:
            return ""

        params = action.get('parameters', {})
        description = params.get('description', '')

        if description:
            # "Click to explore 'subtask_name'" → "Triggered by clicking to explore 'subtask_name'"
            if "Click to explore" in description:
                return description.replace("Click to explore", "Triggered by clicking to explore")
            # Use general descriptions as-is
            return f"Triggered by: {description}"

        # Fallback based on action name
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
        """Save actions for a specific trigger UI path after multi-step exploration

        Args:
            page_index: Page index
            subtask_name: Subtask name
            subtask_info: Subtask information (name, description, parameters)
            actions: List of performed actions [{step, action, screen, reasoning?, start_page?, end_page?}, ...]
            trigger_ui_index: Trigger UI index
            start_page: Starting page index
            end_page: Ending page index
        """
        from utils.action_utils import generalize_action

        # 1. Save to subtasks.csv (guideline will be populated by update_guideline() later)
        subtask_data = {
            'name': subtask_name,
            'description': subtask_info.get('description', ''),
            'parameters': subtask_info.get('parameters', {})
        }
        self.save_subtask(subtask_data, {})

        # 3. Delete existing actions - prevent duplicates by (subtask_name, trigger_ui_index) combination
        self.action_db = self.action_db[
            ~((self.action_db['subtask_name'] == subtask_name) &
              (self.action_db['trigger_ui_index'] == trigger_ui_index))
        ]
        self.action_db.to_csv(self.action_db_path, index=False)

        # 4. Save all actions to actions.csv
        last_end_page = start_page
        for action_data in actions:
            step = action_data.get('step', 0)
            action = action_data.get('action', {})
            screen = action_data.get('screen', '')
            action_start_page = action_data.get('start_page', action_data.get('start', last_end_page))
            action_end_page = action_data.get('end_page', action_data.get('end', action_start_page))
            last_end_page = action_end_page

            # Generalize the action
            if 'index' in action.get('parameters', {}):
                generalized_action = generalize_action(action, subtask_info, screen)
            else:
                generalized_action = action

            self.save_action(subtask_name, trigger_ui_index, step, generalized_action, {},
                            start_page=action_start_page, end_page=action_end_page)

        # 5. Add finish action
        finish_step = len(actions)
        finish_action = {"name": "finish", "parameters": {}}
        self.save_action(subtask_name, trigger_ui_index, finish_step, finish_action, {},
                        start_page=last_end_page, end_page=last_end_page)

        log(f"Saved {len(actions) + 1} actions for subtask '{subtask_name}' (trigger_ui={trigger_ui_index}) in actions.csv")

    def mark_subtask_fully_explored(self, subtask_name: str):
        """Mark as explored after all trigger UIs of a subtask have been explored"""
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
        """Save subtask information to the database

        Args:
            subtask_raw: Subtask information dictionary (name, description, parameters)
            example: Training example data
            guideline: Guideline for subtask execution
            trigger_ui_index: Trigger UI index (same name can start from different UIs)
            start_page: Subtask starting page index
            end_page: Subtask ending page index

        Duplicate check: based on name + trigger_ui_index
        """
        # Duplicate check: based on name + trigger_ui_index
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
        """Return data for a specific subtask"""
        filtered_subtask = self.subtask_db[(self.subtask_db['name'] == subtask_name)]
        next_subtask_data = filtered_subtask.iloc[0].to_dict()
        return next_subtask_data

    def save_action(self, subtask_name, trigger_ui_index: int, step: int, action: dict,
                    example=None, start_page: int = -1, end_page: int = -1,
                    description: str = "", guideline: str = "") -> None:
        """Save action information to the database

        Args:
            subtask_name: Subtask name
            trigger_ui_index: Trigger UI index
            step: Action step number
            action: Action information dictionary
            example: Training example data
            start_page: Page index before action execution
            end_page: Page index after action execution
            description: History description (what changed after action)
            guideline: Semantic meaning of the action
        """
        if example is None:
            example = {}

        # Check if the same (subtask_name, trigger_ui_index, step) already exists
        existing_mask = (
            (self.action_db['subtask_name'] == subtask_name) &
            (self.action_db['trigger_ui_index'] == trigger_ui_index) &
            (self.action_db['step'] == step)
        )

        action_json = json.dumps(action)
        example_json = json.dumps(example)

        if existing_mask.any():
            # Update existing row (overwrite with more detailed information)
            self.action_db.loc[existing_mask, 'action'] = action_json
            self.action_db.loc[existing_mask, 'example'] = example_json
            if start_page != -1:
                self.action_db.loc[existing_mask, 'start_page'] = start_page
            if end_page != -1:
                self.action_db.loc[existing_mask, 'end_page'] = end_page
            # Mobile Map: update description and guideline
            if description:
                self.action_db.loc[existing_mask, 'description'] = description
            if guideline:
                self.action_db.loc[existing_mask, 'guideline'] = guideline
            self.action_db.to_csv(self.action_db_path, index=False)
        else:
            # Add new row
            new_action_db = {
                "subtask_name": subtask_name,
                "trigger_ui_index": trigger_ui_index,
                'step': step,
                "start_page": start_page,
                "end_page": end_page,
                "action": action_json,
                "description": description,  # Mobile Map: action history
                "guideline": guideline,      # Mobile Map: semantic meaning
                "example": example_json
            }
            self.action_db = pd.concat([self.action_db, pd.DataFrame([new_action_db])], ignore_index=True)
            self.action_db.to_csv(self.action_db_path, index=False)

        # Add/update in action data
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
            "guideline": guideline if guideline else (self.action_data[existing_idx].get('guideline', '') if existing_idx is not None else ''),
            "example": example_json,
            "traversed": True
        }

        if existing_idx is not None:
            self.action_data[existing_idx] = new_action_data
        else:
            self.action_data.append(new_action_data)

    def update_end_page(self, subtask_name: str, trigger_ui_index: int, end_page: int) -> bool:
        """Update the end_page of a subtask and its last action

        Updates end_page with the page index arrived at after action execution.
        Also updates the start_page of the finish action.

        Args:
            subtask_name: Subtask name
            trigger_ui_index: Trigger UI index
            end_page: Page index arrived at after action execution

        Returns:
            bool: Whether the update was successful
        """
        updated = False

        # 1. Update subtasks.csv
        subtask_condition = (self.subtask_db['name'] == subtask_name)
        if trigger_ui_index >= 0:
            subtask_condition = subtask_condition & (self.subtask_db['trigger_ui_index'] == trigger_ui_index)

        if subtask_condition.any():
            self.subtask_db.loc[subtask_condition, 'end_page'] = end_page
            self.subtask_db.to_csv(self.subtask_db_path, index=False)
            updated = True

        # 2. Update actions with end_page=-1 for this subtask in actions.csv
        action_condition = (
            (self.action_db['subtask_name'] == subtask_name) &
            (self.action_db['trigger_ui_index'] == trigger_ui_index) &
            (self.action_db['end_page'] == -1)
        )

        if action_condition.any():
            self.action_db.loc[action_condition, 'end_page'] = end_page

            # Also update the start_page of the finish action
            # The finish action starts from the page where the last regular action arrived
            for idx in self.action_db[action_condition].index:
                action_str = str(self.action_db.loc[idx, 'action'])
                if '"name": "finish"' in action_str or "'name': 'finish'" in action_str:
                    self.action_db.loc[idx, 'start_page'] = end_page

            self.action_db.to_csv(self.action_db_path, index=False)

            # Also update in-memory action_data
            for action_data in self.action_data:
                if (action_data.get('subtask_name') == subtask_name and
                    action_data.get('trigger_ui_index') == trigger_ui_index and
                    action_data.get('end_page') == -1):
                    action_data['end_page'] = end_page
                    # Also update the start_page of the finish action
                    action_str = str(action_data.get('action', ''))
                    if '"name": "finish"' in action_str or "'name': 'finish'" in action_str:
                        action_data['start_page'] = end_page

            updated = True
            log(f"Updated end_page={end_page} for subtask '{subtask_name}' (trigger_ui={trigger_ui_index})")

        return updated

    def get_next_action(self, subtask: dict, screen: str, step: int):
        """Return the next action in the current subtask"""
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
        """Update subtask information"""
        condition = (self.subtask_db['name'] == subtask['name'])
        if condition.any():
            self.subtask_db.loc[condition, 'name'] = subtask['name']
            self.subtask_db.loc[condition, 'description'] = subtask['description']
            self.subtask_db.loc[condition, 'parameters'] = json.dumps(subtask['parameters'])

            self.subtask_db.to_csv(self.subtask_db_path, index=False)

    def merge_subtask_into(self, base_subtask_name, prev_subtask_name, target_subtask_name):
        """Merge two subtasks into one"""
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
                                   step: int, description: str, guideline: str = "") -> bool:
        """Update description and guideline for an existing action.

        Mobile Map: Action history description update.

        Args:
            subtask_name: Subtask name
            trigger_ui_index: Trigger UI index
            step: Action step number
            description: Description of what changed
            guideline: Semantic meaning of the action

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
            if guideline:
                self.action_db.loc[condition, 'guideline'] = guideline
            self.action_db.to_csv(self.action_db_path, index=False)

            # Update in-memory action_data
            for action_data in self.action_data:
                if (action_data.get('subtask_name') == subtask_name and
                    action_data.get('trigger_ui_index') == trigger_ui_index and
                    action_data.get('step') == step):
                    if description:
                        action_data['description'] = description
                    if guideline:
                        action_data['guideline'] = guideline
                    break

            log(f"Updated action description for '{subtask_name}' step {step}")
            return True

        return False

    def update_guideline(self, subtask_name: str, trigger_ui_index: int = -1) -> str:
        """Aggregate action-level guidelines into subtask guideline.

        Mobile Map: Combines all action-level guidelines into a single subtask guideline.

        Args:
            subtask_name: Subtask name
            trigger_ui_index: Trigger UI index (-1 to match any)

        Returns:
            str: Combined guideline string
        """
        # Get all actions for this subtask
        action_condition = (self.action_db['subtask_name'] == subtask_name)
        if trigger_ui_index >= 0:
            action_condition = action_condition & (self.action_db['trigger_ui_index'] == trigger_ui_index)

        actions = self.action_db[action_condition].sort_values('step')

        # Combine guideline entries
        guidances = []
        for _, row in actions.iterrows():
            gl = row.get('guideline', '')
            if gl and gl.strip():
                step = int(row.get('step', 0)) + 1
                guidances.append(f"{step}. {gl}")

        combined = " → ".join(guidances) if guidances else ""

        # Update subtasks.csv guideline column
        subtask_condition = (self.subtask_db['name'] == subtask_name)
        if trigger_ui_index >= 0:
            subtask_condition = subtask_condition & (self.subtask_db['trigger_ui_index'] == trigger_ui_index)

        if subtask_condition.any():
            # Skip overwrite if existing guideline is a special marker (e.g., EXTERNAL_APP:)
            existing = str(self.subtask_db.loc[subtask_condition, 'guideline'].iloc[0])
            if not existing.startswith('EXTERNAL_APP:'):
                self.subtask_db.loc[subtask_condition, 'guideline'] = combined
                self.subtask_db.to_csv(self.subtask_db_path, index=False)
                log(f"Updated guideline for '{subtask_name}': {combined[:50]}...")

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

        # === 1. Process available_subtasks.csv ===
        # Update the exploration field to reason (preserve row, prevent re-exploration)
        condition = (self.available_subtask_db['name'] == subtask_name)
        if trigger_ui_index >= 0:
            condition = condition & (self.available_subtask_db['trigger_ui_index'] == trigger_ui_index)

        if condition.any():
            self.available_subtask_db.loc[condition, 'exploration'] = reason
            self.available_subtask_db.to_csv(self.available_subtask_db_path, index=False)
            deleted_any = True
            log(f":::DELETE::: Marked subtask '{subtask_name}' as '{reason}' in available_subtasks.csv")

        # === 2. Process subtasks.csv ===
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

        # === 3. Process actions.csv ===
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

            # Also update in-memory action_data
            self.action_data = [
                action for action in self.action_data
                if not (action.get('subtask_name') == subtask_name and
                       (trigger_ui_index < 0 or action.get('trigger_ui_index') == trigger_ui_index))
            ]

        return deleted_any
