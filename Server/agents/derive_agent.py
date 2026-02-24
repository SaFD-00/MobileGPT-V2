import json
import os

from agents.prompts import derive_agent_prompt
from memory.memory_manager import Memory
from utils.utils import query, query_with_vision, log, parse_completion_rate
from utils import parsing_utils


class DeriveAgent:
    """
    Agent that converts subtasks into concrete actions.
    Generates detailed actions such as click, input, scroll, etc.
    """
    def __init__(self, memory: Memory, instruction: str):
        self.memory = memory
        self.instruction = instruction
        self.subtask = None
        self.subtask_history = []
        self.action_history = []
        self.response_history = []

    def init_subtask(self, subtask: dict, subtask_history: list) -> None:
        """Initialize for processing a new subtask"""
        self.subtask = subtask
        self.subtask_history = subtask_history
        self.action_history = []

    def derive(self, screen: str, examples=None, screenshot_path: str = None) -> (dict, dict):
        """
        Derive a concrete action to perform the subtask from the current screen state.
        Args:
            screen: Current screen XML
            examples: Training example data
            screenshot_path: Screenshot file path (for Vision API)
        Returns:
            action: Action information to execute
            example: Training example data
        """
        if examples is None:
            examples = []

        has_screenshot = screenshot_path is not None
        derive_prompt = derive_agent_prompt.get_prompts(
            self.instruction, self.subtask,
            self.subtask_history + self.action_history, screen, examples,
            has_screenshot=has_screenshot
        )
        response = query_with_vision(
            derive_prompt, model=os.getenv("DERIVE_AGENT_GPT_VERSION"),
            screenshot_path=screenshot_path
        )
        response['completion_rate'] = parse_completion_rate(response['completion_rate'])
        self.response_history.append(response)

        # Record successful execution in action history
        history = "your past response: " + json.dumps(response) + " has been executed successfully."
        self.action_history.append(history)

        example = self.__exemplify(response, screen)
        return response['action'], example

        # Real-time saving (currently disabled)
        # self.__generalize_and_save_action(response, screen)
        # generalized_action = self.__generalize_action(response, screen)
        # return response['action'], generalized_action

    def __exemplify(self, response: dict, screen: str) -> dict:
        """Convert the action into a training example"""
        action = response['action']
        example = {}
        if "index" in action['parameters']:
            shrunk_xml = parsing_utils.shrink_screen_xml(screen, int(action['parameters']['index']))
            example = {"instruction": self.instruction, "subtask": json.dumps(self.subtask), "screen": shrunk_xml,
                       "response": json.dumps(response)}
        return example


