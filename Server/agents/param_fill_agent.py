import os

from agents.prompts import param_fill_agent_prompt
from utils.utils import query, log


def parm_fill_subtask(instruction: str, subtask: dict, qa_history: list, screen: str, example: dict):
    """
    Fill in the empty parameters of a subtask by extracting them from context.

    Args:
        instruction: User command
        subtask: Subtask whose parameters need to be filled
        qa_history: Q&A history
        screen: Current screen XML
        example: Reference example data
    Returns:
        Dictionary of filled parameters
    """
    prompts = param_fill_agent_prompt.get_prompts(instruction, subtask, qa_history, screen, example)
    # Use the trained model if examples exist, otherwise use gpt-5-chat-latest
    if len(example) > 0:
     response = query(prompts, model=os.getenv("PARAMETER_FILLER_AGENT_GPT_VERSION"))
    else:
        response = query(prompts, model="gpt-5.2")
    return response
