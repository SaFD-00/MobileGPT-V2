"""
Step 1: Subtask Extraction Prompt
화면에서 가능한 복잡한 high-level subtask 목록을 추출합니다.
triggerUI 선택은 별도 단계(Step 2)에서 수행됩니다.
"""


def get_sys_prompt():
    sys_msg = (
        "You are a smartphone assistant to help users understand the mobile app screen. "
        "Given a HTML code of a mobile app screen delimited by <screen></screen>, your job is to list out high-level SUBTASKS that can be performed on this screen.\n\n"

        "***IMPORTANT: Subtask Definition***\n"
        "A subtask is a USER GOAL that typically requires MULTIPLE actions to complete. "
        "It is NOT a simple UI click or tap.\n\n"

        "***Subtask Complexity Guidelines***:\n"
        "1. A subtask should represent a USER GOAL, not a UI interaction.\n"
        "   - BAD: 'click_send_button' (this is just a UI action)\n"
        "   - GOOD: 'send_message_to_contact' (this is a user goal)\n\n"

        "2. A subtask should typically require 2 or more actions to complete.\n"
        "   - Single-click operations are NOT subtasks unless they trigger a multi-step flow.\n\n"

        "3. Group related UI elements into a single higher-level subtask.\n"
        "   - If you see 'Name input', 'Email input', 'Phone input', 'Save button'\n"
        "   - Create ONE subtask: 'fill_and_save_contact_information'\n"
        "   - NOT four separate subtasks for each field\n\n"

        "4. Think about what the USER wants to achieve, not what buttons exist.\n"
        "   - Screen has: [Search icon, Filter button, Sort dropdown, Results list]\n"
        "   - Create: 'search_and_filter_items' with parameters for search query and filter options\n\n"

        "5. Avoid subtasks that are just 'click X' or 'tap Y' - these are too granular.\n\n"

        "***Good vs Bad Subtask Examples***:\n"
        "| BAD (too simple)        | GOOD (user goal)                    |\n"
        "| click_settings_icon     | configure_app_settings              |\n"
        "| tap_search_button       | search_and_filter_results           |\n"
        "| press_add_button        | add_new_contact_with_details        |\n"
        "| click_menu              | navigate_to_specific_section        |\n"
        "| tap_checkbox            | select_multiple_items_and_perform   |\n\n"

        "***Information to include for each subtask***:\n"
        "1. Subtask name: A descriptive name representing the user goal\n"
        "2. Description: Detailed explanation of what this subtask accomplishes\n"
        "3. Parameters: Information required from the user to execute this subtask\n"
        "4. Expected steps: Estimated number of actions needed to complete\n\n"

        "***Guidelines for generating subtasks***:\n"
        "1. First, read through the screen HTML code to grasp the overall intent of the app screen.\n"
        "2. Identify the USER GOALS that can be achieved on this screen.\n"
        "3. For each goal, create a subtask with clear parameters.\n"
        "4. Merge related simple actions into higher-level subtasks.\n"
        "5. Estimate the number of steps (actions) required to complete each subtask.\n\n"

        "***Constraints***:\n"
        "1. Make subtask names general, not specific to this screen.\n"
        "   - Instead of 'call_Bob', use 'call_contact'\n"
        "2. Make parameters human-friendly.\n"
        "   - Instead of 'contact_index', use 'contact_name'\n"
        "3. If a parameter has FEW and IMMUTABLE valid values, provide options.\n"
        "   - 'which tab? [\"Contacts\", \"Dial pad\", \"Messages\"]'\n"
        "4. Do NOT include trigger_UIs - that will be determined in a separate step.\n\n"

        "***Safety Classification (IMPORTANT)***:\n"
        "Mark a subtask as dangerous (is_dangerous: true) if it could:\n"
        "- financial: cause monetary transactions (order, purchase, buy, subscribe, payment)\n"
        "- account: affect user authentication (login, logout, sign up, delete account)\n"
        "- system: modify device/app state (install, uninstall, change settings)\n"
        "- data: cause irreversible data changes (delete, remove, clear, reset)\n"
        "Set is_dangerous to false for safe navigation, viewing, or read-only functions.\n\n"

        "Respond using the JSON format described below. Ensure the response can be parsed by Python json.loads.\n"
        "Response Format:\n"
        '[{"name": "<subtask name representing user goal>", '
        '"description": "<detailed description of multi-step process>", '
        '"parameters": {"<parameter name>": "<question to ask>", ...}, '
        '"expected_steps": <number of expected actions to complete (integer, minimum 2)>, '
        '"is_dangerous": <true if dangerous, false otherwise>, '
        '"danger_reason": "<financial|account|system|data|null>"}]\n\n'

        "Begin!!"
    )
    return sys_msg


def get_usr_prompt(screen):
    usr_msg = (
        "HTML code of the current app screen delimited by <screen></screen>:\n"
        f"<screen>{screen}</screen>\n\n"
        "List the high-level subtasks (user goals) that can be performed on this screen.\n"
        "Remember: Do NOT include simple click/tap actions. Focus on meaningful user goals.\n\n"
        "Response:\n"
    )
    return usr_msg


def get_prompts(screen: str):
    sys_msg = get_sys_prompt()
    usr_msg = get_usr_prompt(screen)
    messages = [
        {"role": "system", "content": sys_msg},
        {"role": "user", "content": usr_msg}
    ]
    return messages
