"""Subtask Graph: Action history generation prompts.

Generates prompts for describing what changed after an action.
"""

import json


def get_description_sys_prompt() -> str:
    """System prompt for action description generation."""
    sys_msg = (
        "You are an expert at describing UI state changes in mobile applications. "
        "Your task is to describe what changed on the screen after an action was performed.\n\n"

        "***Output Format***:\n"
        "- Write a single, concise sentence (max 50 words)\n"
        "- Start with past-tense verb describing the action (Clicked, Typed, Scrolled, etc.)\n"
        "- Then describe the result/change that occurred\n"
        "- Focus on visible UI changes: what appeared, disappeared, or changed state\n"
        "- Do NOT mention technical details like indices, coordinates, or XML elements\n\n"

        "***Good Examples***:\n"
        "- Clicked search icon, keyboard appeared and search interface activated\n"
        "- Typed 'hello' in message field, text now visible in input area\n"
        "- Scrolled down, new list items appeared including 'Settings' option\n"
        "- Tapped back button, returned to previous inbox screen\n"
        "- Long pressed on email item, selection mode activated with checkbox visible\n"
        "- Swiped left on notification, delete button revealed\n\n"

        "***Bad Examples (avoid these)***:\n"
        "- The user clicked on element with index 5 (too technical)\n"
        "- Action was performed successfully (no description of change)\n"
        "- The screen changed (too vague)\n"
        "- Clicked on android.widget.ImageButton (uses technical element names)\n"
    )
    return sys_msg


def get_description_usr_prompt(before_xml: str, after_xml: str, action: dict) -> str:
    """User prompt for action description generation.

    Args:
        before_xml: XML representation of screen before action
        after_xml: XML representation of screen after action
        action: The action that was performed

    Returns:
        User prompt string
    """
    # Clean action dict for display
    action_display = {
        'name': action.get('name', ''),
        'parameters': action.get('parameters', {})
    }

    # Truncate XML if too long (keep first and last parts)
    max_xml_length = 3000

    def truncate_xml(xml: str) -> str:
        if len(xml) <= max_xml_length:
            return xml
        half = max_xml_length // 2
        return xml[:half] + "\n... [truncated] ...\n" + xml[-half:]

    before_display = truncate_xml(before_xml) if before_xml else "[No before state]"
    after_display = truncate_xml(after_xml) if after_xml else "[No after state]"

    usr_msg = (
        "***Action Performed***:\n"
        f"{json.dumps(action_display, indent=2)}\n\n"

        "***Screen BEFORE Action***:\n"
        f"{before_display}\n\n"

        "***Screen AFTER Action***:\n"
        f"{after_display}\n\n"

        "If screenshots are provided, use them as the primary source for understanding changes.\n\n"

        "Describe what changed (single sentence, max 50 words):\n"
    )
    return usr_msg


def get_prompts(before_xml: str, after_xml: str, action: dict) -> list:
    """Generate prompts for action description.

    Args:
        before_xml: XML representation of screen before action
        after_xml: XML representation of screen after action
        action: The action that was performed

    Returns:
        List of message dicts for LLM API
    """
    sys_msg = get_description_sys_prompt()
    usr_msg = get_description_usr_prompt(before_xml, after_xml, action)
    messages = [
        {"role": "system", "content": sys_msg},
        {"role": "user", "content": usr_msg}
    ]
    return messages


# ============================================================
# Guidance Generation Prompts
# ============================================================

def get_guidance_sys_prompt() -> str:
    """System prompt for action guidance generation."""
    sys_msg = (
        "You are an expert at explaining the semantic meaning of UI actions in mobile applications. "
        "Your task is to explain WHY an action is performed and what it accomplishes.\n\n"

        "***Output Format***:\n"
        "- Write a single, concise sentence (max 30 words)\n"
        "- Start with a verb describing the purpose (Click, Tap, Enter, Select, etc.)\n"
        "- Explain the goal or intent of the action\n"
        "- Focus on user-facing purpose, not technical implementation\n\n"

        "***Good Examples***:\n"
        "- Click the search icon to open the search dialog\n"
        "- Enter the recipient's email address in the To field\n"
        "- Tap the send button to deliver the message\n"
        "- Scroll down to reveal more options in the settings list\n"
        "- Select the attachment to preview its contents\n"
        "- Long press the item to enter selection mode\n\n"

        "***Bad Examples (avoid these)***:\n"
        "- Click element at index 5 (too technical)\n"
        "- Perform a click action (no semantic meaning)\n"
        "- This action clicks on ImageButton (describes implementation, not purpose)\n"
    )
    return sys_msg


def get_guidance_usr_prompt(action: dict, screen_xml: str) -> str:
    """User prompt for action guidance generation.

    Args:
        action: The action to describe
        screen_xml: XML representation of the current screen

    Returns:
        User prompt string
    """
    # Clean action dict for display
    action_display = {
        'name': action.get('name', ''),
        'parameters': action.get('parameters', {})
    }

    # Truncate XML if too long
    max_xml_length = 3000
    if len(screen_xml) > max_xml_length:
        half = max_xml_length // 2
        screen_xml = screen_xml[:half] + "\n... [truncated] ...\n" + screen_xml[-half:]

    usr_msg = (
        "***Action***:\n"
        f"{json.dumps(action_display, indent=2)}\n\n"

        "***Current Screen***:\n"
        f"{screen_xml}\n\n"

        "Explain the semantic purpose of this action (single sentence, max 30 words):\n"
    )
    return usr_msg


def get_guidance_prompts(action: dict, screen_xml: str) -> list:
    """Generate prompts for action guidance.

    Args:
        action: The action to describe
        screen_xml: XML representation of the current screen

    Returns:
        List of message dicts for LLM API
    """
    sys_msg = get_guidance_sys_prompt()
    usr_msg = get_guidance_usr_prompt(action, screen_xml)
    messages = [
        {"role": "system", "content": sys_msg},
        {"role": "user", "content": usr_msg}
    ]
    return messages
