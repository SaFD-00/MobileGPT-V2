import json
import os

from agents.prompts import select_agent_prompt
from memory.memory_manager import Memory
from utils.utils import query, query_with_vision, log


class SelectAgent:
    """
    Agent that selects the optimal subtask from the available options.
    Determines the next action considering the current situation and goal.
    """
    def __init__(self, memory: Memory, instruction: str):
        self.memory = memory
        self.instruction = instruction

    def select(self, available_subtasks: list, subtask_history: list, qa_history: list,
               screen: str, screenshot_path: str = None) -> (dict, dict):
        """
        Select the optimal subtask from the given options.
        Args:
            available_subtasks: List of available subtasks
            subtask_history: Subtask execution history
            qa_history: Q&A history
            screen: Current screen XML
            screenshot_path: Screenshot file path (for Vision API)
        Returns:
            response: Selection result response
            new_action: Newly created action (if any)
        """
        log(f":::SELECT:::", "blue")
        has_screenshot = screenshot_path is not None
        select_prompts = select_agent_prompt.get_prompts(
            self.instruction, available_subtasks, subtask_history,
            qa_history, screen, has_screenshot=has_screenshot
        )
        response = query_with_vision(
            select_prompts, model=os.getenv("SELECT_AGENT_GPT_VERSION"),
            screenshot_path=screenshot_path
        )
        # Retry until a valid response is obtained
        while not self.__check_response_validity(response, available_subtasks):
            assistant_msg = {"role": "assistant", "content": json.dumps(response)}
            select_prompts.append(assistant_msg)

            # Add error message and request again
            error_msg = {"role": "user", "content": "Error: The selected action is not in the available actions list."}
            select_prompts.append(error_msg)
            response = query(select_prompts, model=os.getenv("SELECT_AGENT_GPT_VERSION"))

        next_subtask_filled = response['action']
        for subtask in available_subtasks:
            if subtask['name'] == next_subtask_filled['name']:
                next_subtask_raw = subtask
                self.__save_as_example(next_subtask_raw, screen, response)
        if "new_action" in response:
            return response, response['new_action']
        else:
            return response, None

    def __check_response_validity(self, response, available_subtasks):
        """Check if the selected action is in the available list"""
        action = response['action']

        # Check if the selected action exists in the available subtasks
        subtask_match = False
        # Default actions are always allowed
        if action['name'] in ['scroll_screen', 'finish', 'speak']:
            subtask_match = True
            return True

        for subtask in available_subtasks:
            if subtask['name'] == action['name']:
                subtask_match = True
                return True

        if not subtask_match:
            # If it is a new action, add it to the available subtasks
            if "new_action" in response:
                new_action = response['new_action']
                available_subtasks.append(new_action)
                return True

            # Error if the selected action is not in the list and no new action is provided
            else:
                return False

    def __save_as_example(self, subtask_raw, screen, response):
        """Save the selection result as a training example"""
        del response['completion_rate']
        example = {"instruction": self.instruction, "screen": screen, "response": response}
        self.memory.save_subtask(subtask_raw, example)
