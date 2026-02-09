import json

from utils.utils import generate_numbered_list


def get_sys_prompt():
    """Generate system prompt"""
    sys_msg = (
        "You are a technical writer who creates concise guideline descriptions for mobile app subtasks. "
        "Your descriptions help users understand what each subtask does and how to use it.\n\n"

        "***Output Format***:\n"
        "- ALWAYS start with a present-tense verb (Opens, Searches, Navigates, Sends, etc.)\n"
        "- Keep it to 1-2 short sentences maximum\n"
        "- Focus on the user-facing action, not technical implementation\n"
        "- Never include UI indices, coordinates, or technical parameters\n"
        "- Describe the end result, not every intermediate step\n\n"

        "***Good Examples***:\n"
        "- Opens the navigation drawer\n"
        "- Searches for a contact by name and selects from results\n"
        "- Sends a message by typing in the text field and tapping send\n"
        "- Navigates back to the home screen\n"
        "- Opens settings menu via the gear icon\n"
        "- Creates a new note by entering title and content\n\n"

        "***Bad Examples (avoid these)***:\n"
        "- Triggered by clicking 'hub_drawer_label_container' (too technical)\n"
        "- Click index 5, then input text, then click index 12 (lists raw actions)\n"
        "- This subtask is used to... (don't start with 'This subtask')\n"
    )
    return sys_msg


def get_usr_prompt(subtask: dict, action_history: list):
    """Generate user prompt"""
    # Remove unnecessary fields from action_history
    cleaned_history = []
    for action in action_history:
        action_copy = action.copy() if isinstance(action, dict) else {}
        # Remove unnecessary fields
        for key in ['completion_rate', 'plan']:
            if key in action_copy:
                del action_copy[key]
        cleaned_history.append(action_copy)

    numbered_history = generate_numbered_list(cleaned_history)

    # Extract only the necessary parts from subtask info
    subtask_summary = {
        'name': subtask.get('name', ''),
        'description': subtask.get('description', '')
    }

    usr_msg = (
        f"Subtask: {json.dumps(subtask_summary)}\n\n"

        "Actions performed:\n"
        f"{numbered_history}\n\n"

        "Write a concise guideline description (start with a verb):\n"
    )
    return usr_msg


def get_prompts(subtask: dict, action_history: list) -> list:
    """Generate prompts for guideline_agent

    Args:
        subtask: Information about the performed subtask
        action_history: List of performed actions

    Returns:
        List of prompt messages
    """
    sys_msg = get_sys_prompt()
    usr_msg = get_usr_prompt(subtask, action_history)
    messages = [
        {"role": "system", "content": sys_msg},
        {"role": "user", "content": usr_msg}
    ]
    return messages
