"""Subtask Graph: Action history generation prompts.

Generates prompts for:
- Description: WHY an action was performed + WHAT changed after it.
- Guideline: HOW to perform the action on the screen.
"""

import json


def get_description_sys_prompt() -> str:
    """System prompt for action description generation."""
    sys_msg = (
        "You are an expert at explaining UI actions and their results in mobile applications. "
        "Your task is to explain WHY an action was performed and WHAT changed on the screen after it.\n\n"

        "***Output Format***:\n"
        "- Write a single, concise sentence (max 50 words)\n"
        "- Start with the PURPOSE of the action (To search, To compose, To navigate, etc.)\n"
        "- Then describe the resulting UI changes after a semicolon\n"
        "- Include both intent and observable changes\n"
        "- Do NOT mention technical details like indices, coordinates, or XML elements\n\n"

        "***Good Examples***:\n"
        "- To open the search feature, clicked the search icon; keyboard appeared and search interface activated\n"
        "- To compose a message, typed 'hello' in the message field; text now visible in input area\n"
        "- To find more options, scrolled down; new list items appeared including 'Settings' option\n"
        "- To return to the inbox, tapped back button; returned to previous inbox screen\n"
        "- To select emails for bulk action, long pressed on email item; selection mode activated with checkbox visible\n"
        "- To dismiss the notification, swiped left; delete button revealed\n\n"

        "***Bad Examples (avoid these)***:\n"
        "- The user clicked on element with index 5 (too technical)\n"
        "- Action was performed successfully (no description of change or purpose)\n"
        "- The screen changed (too vague, no purpose)\n"
        "- Clicked search icon, keyboard appeared (missing WHY/purpose)\n"
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

        "Explain WHY this action was performed and WHAT changed (single sentence, max 50 words):\n"
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
        "You are an expert at describing HOW to perform UI actions in mobile applications. "
        "Your task is to explain HOW to perform a specific action on the screen - which UI element to interact with and how.\n\n"

        "***Output Format***:\n"
        "- Write a single, concise sentence (max 30 words)\n"
        "- Start with a verb describing the interaction method (Click, Tap, Type, Scroll, etc.)\n"
        "- Describe the specific UI element: its visual appearance, label, or position on screen\n"
        "- Focus on identifiable visual cues, not technical details like indices or class names\n\n"

        "***Good Examples***:\n"
        "- Click the magnifying glass icon in the top-right toolbar\n"
        "- Type the email address into the 'To' text input field at the top of the compose screen\n"
        "- Tap the blue arrow-shaped send button at the bottom-right corner\n"
        "- Scroll down on the settings list below the 'General' section\n"
        "- Tap the paperclip icon next to the message input field\n"
        "- Long press the first email item in the inbox list\n\n"

        "***Bad Examples (avoid these)***:\n"
        "- Click element at index 5 (too technical, uses index)\n"
        "- Click the search icon to open the search dialog (describes purpose, not how)\n"
        "- Perform a click action (no specific UI element described)\n"
        "- Tap android.widget.ImageButton (uses technical class name)\n"
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

        "Describe HOW to perform this action on the screen (single sentence, max 30 words):\n"
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
