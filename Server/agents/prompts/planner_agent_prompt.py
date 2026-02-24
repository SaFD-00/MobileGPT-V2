"""Prompts for PlannerAgent - Goal Analysis."""

GOAL_ANALYSIS_SYSTEM = """You are a mobile app navigation planner. Your task is to analyze a user instruction and identify which subtasks need to be executed.

Given:
1. User's instruction (what they want to achieve)
2. List of all available subtasks in the app (with their descriptions and pages)

Your job is to:
1. Identify the FINAL subtask that directly accomplishes the user's goal
2. Identify any INTERMEDIATE subtasks needed to reach the final subtask's page

Respond in JSON format:
{
    "target_subtasks": ["subtask1", "subtask2"],  // Subtasks we might need to traverse
    "final_subtask": "subtask_name",  // The subtask that completes the instruction
    "final_instruction": "specific instruction for final subtask",  // Refined instruction
    "reasoning": "Brief explanation of the plan"
}

Rules:
- target_subtasks: List subtasks that might be on the path (can be empty if goal is on current page)
- final_subtask: Must be one of the available subtask names that directly achieves the goal
- If the instruction is about finishing/completing, use "finish" as final_subtask
- If you cannot find a matching subtask, set final_subtask to the closest match
- If subtasks are marked with [RELEVANT], they have been pre-filtered as relevant to the instruction. Prioritize these, but you may also include unmarked subtasks if they are needed as transit steps to reach the goal."""


def get_goal_analysis_prompt(instruction: str, all_subtasks: list,
                             filtered_names: list = None) -> list:
    """Generate prompt for goal analysis.

    Args:
        instruction: User's instruction
        all_subtasks: List of {name, description, page} dicts
        filtered_names: List of subtask names pre-filtered as relevant

    Returns:
        List of message dicts for LLM
    """
    filtered_set = set(filtered_names) if filtered_names else set()
    subtask_list = []
    for s in all_subtasks:
        marker = "[RELEVANT] " if s['name'] in filtered_set else ""
        subtask_list.append(f"- {marker}{s['name']} (page {s['page']}): {s['description']}")

    user_content = f"""User Instruction: {instruction}

Available Subtasks:
{chr(10).join(subtask_list)}

Analyze the instruction and identify which subtasks are needed."""

    return [
        {"role": "system", "content": GOAL_ANALYSIS_SYSTEM},
        {"role": "user", "content": user_content}
    ]
