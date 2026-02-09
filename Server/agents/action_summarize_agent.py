import os

from agents.prompts import action_summarize_prompt
from utils.utils import query


def summarize_actions(action_history: list):
    """
    Summarize the performed action history and return it as a concise sentence.
    Args:
        action_history: List of performed actions
    Returns:
        Summarized string
    """
    prompts = action_summarize_prompt.get_prompts(action_history)
    response = query(prompts, model=os.getenv("ACTION_SUMMARIZE_AGENT_GPT_VERSION"))
    return response