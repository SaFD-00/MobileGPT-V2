"""
Step 2: Trigger UI Selection Prompt
Selects the representative trigger UI for each given subtask in the list.
Selects exactly 1 UI per subtask.
"""

import json


def get_sys_prompt():
    sys_msg = (
        "You are a smartphone assistant that maps subtasks to their trigger UI elements.\n\n"

        "***Your Task***:\n"
        "Given a list of subtasks and a screen HTML, identify the SINGLE BEST UI element "
        "that triggers each subtask.\n\n"

        "***Guidelines for selecting trigger UI***:\n"
        "1. Select exactly ONE UI element per subtask - the most representative one.\n"
        "2. The trigger UI should be the ENTRY POINT that initiates the subtask.\n"
        "   - For 'fill_form': select the first input field or the form container\n"
        "   - For 'search_items': select the search icon or search input\n"
        "   - For 'navigate_to_section': select the navigation button/tab\n"
        "3. Prefer interactive elements: <button>, <input>, <checker>, clickable <div>\n"
        "4. Use the 'index' attribute of the HTML element as the trigger_ui_index.\n"
        "5. If no suitable UI exists for a subtask, use -1.\n\n"

        "***Selection Priority***:\n"
        "1. Primary action buttons (e.g., 'Submit', 'Save', 'Add')\n"
        "2. Input fields that start the flow\n"
        "3. Navigation elements (tabs, menu items)\n"
        "4. Icons that trigger actions\n\n"

        "***Response Format***:\n"
        "Return a JSON object mapping subtask names to their trigger_ui_index:\n"
        '{"subtask_name": <index>, "subtask_name2": <index2>, ...}\n\n'

        "Example:\n"
        '{"add_new_contact": 15, "search_contacts": 3, "call_contact": 8}\n\n'

        "If a subtask cannot be triggered from this screen, use -1:\n"
        '{"add_new_contact": 15, "unavailable_feature": -1}\n\n'

        "Begin!!"
    )
    return sys_msg


def get_usr_prompt(screen: str, subtasks: list, has_screenshot: bool = False):
    # Extract and pass only subtask names and descriptions
    subtask_info = []
    for st in subtasks:
        info = {
            "name": st.get("name", ""),
            "description": st.get("description", ""),
            "expected_steps": st.get("expected_steps", 2)
        }
        subtask_info.append(info)

    screenshot_hint = ""
    if has_screenshot:
        screenshot_hint = (
            "\n[A screenshot of the current screen is also provided for visual reference. "
            "Use the visual layout to better identify which UI element best triggers each subtask.]\n"
        )

    usr_msg = (
        "HTML code of the current app screen:\n"
        f"<screen>{screen}</screen>\n"
        f"{screenshot_hint}\n"
        "Subtasks to map:\n"
        f"<subtasks>{json.dumps(subtask_info, indent=2)}</subtasks>\n\n"
        "For each subtask, select the SINGLE BEST trigger UI element (by index attribute).\n"
        "If no suitable UI exists, use -1.\n\n"
        "Response (JSON object mapping subtask name to trigger_ui_index):\n"
    )
    return usr_msg


def get_prompts(screen: str, subtasks: list, has_screenshot: bool = False):
    sys_msg = get_sys_prompt()
    usr_msg = get_usr_prompt(screen, subtasks, has_screenshot)
    messages = [
        {"role": "system", "content": sys_msg},
        {"role": "user", "content": usr_msg}
    ]
    return messages
