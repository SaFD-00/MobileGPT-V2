import json
import os

from agents.prompts import subtask_extraction_prompt
from agents.prompts import trigger_ui_selection_prompt
from memory.memory_manager import Memory
from utils.parsing_utils import get_trigger_ui_attributes, get_extra_ui_attributes
from utils.utils import query, query_with_vision, log

import xml.etree.ElementTree as ET


class ExploreAgent:
    """
    Agent that explores new screens and discovers possible subtasks.
    Two-phase process:
    1. Step 1: Extract possible high-level subtasks from the screen
    2. Step 2: Select the representative triggerUI for each subtask
    """
    def __init__(self, memory: Memory):
        self.memory = memory

    def explore(self, parsed_xml, hierarchy_xml, html_xml,
                screen_num=None, screenshot_path=None) -> int:
        """
        Analyze the given screen XML and create a new node.
        Args:
            parsed_xml: Parsed XML screen structure
            hierarchy_xml: Hierarchy XML
            html_xml: HTML format XML
            screen_num: Screen number
            screenshot_path: Screenshot file path (for Vision API)
        Returns:
            Index of the created node
        """

        log(f":::EXPLORE:::", "blue")
        model = os.getenv("EXPLORE_AGENT_GPT_VERSION", "gpt-5.2")
        has_screenshot = screenshot_path is not None

        # ============================================
        # Step 1: Subtask extraction (using Vision API)
        # ============================================
        log(f":::EXPLORE STEP 1::: Extracting high-level subtasks", "cyan")
        subtask_prompts = subtask_extraction_prompt.get_prompts(
            html_xml, has_screenshot=has_screenshot
        )
        subtasks = query_with_vision(
            subtask_prompts, model=model,
            screenshot_path=screenshot_path, is_list=True
        )

        # Type validation - initialize as empty list if not a list
        if not isinstance(subtasks, list):
            log(f":::EXPLORE WARNING::: subtasks is not a list (type: {type(subtasks).__name__}), using empty list", "yellow")
            subtasks = []

        # Set default values for required fields + handle safe field
        safe_subtasks = []
        unsafe_subtasks = []

        for subtask in subtasks:
            if "parameters" not in subtask:
                subtask['parameters'] = {}
            if "expected_steps" not in subtask:
                subtask['expected_steps'] = 2
            if "safe" not in subtask:
                subtask['safe'] = True  # Default: safe
            if "risk_category" not in subtask:
                subtask['risk_category'] = None

            # Classify as safe/unsafe
            if subtask.get('safe', True):
                safe_subtasks.append(subtask)
            else:
                unsafe_subtasks.append(subtask)

        # Log all subtasks (showing both safe/unsafe)
        log(f":::EXPLORE STEP 1::: Extracted {len(subtasks)} subtasks "
            f"(safe: {len(safe_subtasks)}, unsafe: {len(unsafe_subtasks)})", "cyan")
        log(f"All Subtasks: {json.dumps(subtasks, indent=2)}", "blue")

        # Log warnings for unsafe subtasks
        for unsafe in unsafe_subtasks:
            log(f":::GUARDRAIL::: Blocked unsafe subtask '{unsafe.get('name')}' "
                f"(category: {unsafe.get('risk_category')})", "red")

        # Proceed to the next step with only safe subtasks
        subtasks = safe_subtasks

        if not subtasks:
            log(f":::EXPLORE::: No subtasks found, creating empty node", "yellow")
            # Create an empty node
            new_node_index = self.memory.add_node([], {}, {}, parsed_xml, screen_num)
            self.memory.add_hierarchy_xml(hierarchy_xml, new_node_index)
            return new_node_index

        # ============================================
        # Step 2: TriggerUI selection (using Vision API)
        # ============================================
        log(f":::EXPLORE STEP 2::: Selecting trigger UIs for {len(subtasks)} subtasks", "cyan")
        trigger_prompts = trigger_ui_selection_prompt.get_prompts(
            html_xml, subtasks, has_screenshot=has_screenshot
        )
        trigger_ui_mapping = query_with_vision(
            trigger_prompts, model=model,
            screenshot_path=screenshot_path, is_list=False
        )

        # Validate trigger_ui_mapping
        if not isinstance(trigger_ui_mapping, dict):
            log(f":::EXPLORE WARNING::: trigger_ui_mapping is not a dict (type: {type(trigger_ui_mapping).__name__}), using empty dict", "yellow")
            trigger_ui_mapping = {}

        log(f":::EXPLORE STEP 2::: Trigger UI mapping: {json.dumps(trigger_ui_mapping, indent=2)}", "cyan")

        # ============================================
        # Combine Subtask + TriggerUI
        # ============================================
        available_subtasks = []
        subtasks_trigger_uis = {}  # {subtask_name: [trigger_ui_index]}

        for subtask in subtasks:
            subtask_name = subtask.get('name', '')
            trigger_ui = trigger_ui_mapping.get(subtask_name, -1)

            # Only add if trigger_ui is valid (integer validation)
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

        # Extract trigger UI attributes
        subtasks_trigger_ui_attributes = get_trigger_ui_attributes(subtasks_trigger_uis, parsed_xml)

        # List of trigger UI indices
        trigger_ui_indexes = [ui for uis in subtasks_trigger_uis.values() for ui in uis]
        # Extract additional UI attributes beyond trigger UIs
        extra_ui_attributes = get_extra_ui_attributes(trigger_ui_indexes, parsed_xml)

        # Add new node to memory
        new_node_index = self.memory.add_node(
            available_subtasks,
            subtasks_trigger_ui_attributes,
            extra_ui_attributes,
            parsed_xml,
            screen_num
        )

        # Save hierarchy XML and embeddings
        self.memory.add_hierarchy_xml(hierarchy_xml, new_node_index)

        return new_node_index
