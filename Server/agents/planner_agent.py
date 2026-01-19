"""Planner Agent for UICompass-style Subtask Path Planning.

This agent analyzes user instructions and STG (Subtask Transition Graph) to plan
an optimal sequence of subtasks for task completion.
"""

import os
from typing import Dict, List, Optional

from agents.prompts import planner_agent_prompt
from utils.utils import log, query


class PlannerAgent:
    """Plans optimal subtask paths using Subtask Transition Graph.

    Implements UICompass's UI Path Planning concept:
    1. Analyze user instruction to identify goal subtasks
    2. Use BFS on STG to find shortest path to goal
    3. Generate planned_path with step-by-step instructions
    """

    def __init__(self, instruction: str):
        self.instruction = instruction

    def plan(self, current_page: int, subtask_graph: dict,
             all_subtasks: Dict[int, List[dict]]) -> Optional[List[dict]]:
        """Plan the full subtask path to achieve the instruction.

        Args:
            current_page: Current page index
            subtask_graph: Subtask Transition Graph with nodes and edges
            all_subtasks: Dict mapping page_index to available subtasks

        Returns:
            List of planned path steps, or None if no path found
        """
        log(f":::PLANNER::: Planning path from page {current_page}", "cyan")

        # Check if STG has enough data
        if not subtask_graph.get("edges"):
            log(":::PLANNER::: STG empty, falling back to Select", "yellow")
            return None

        # Step 1: Analyze goal to identify target subtasks/pages
        goal_analysis = self._analyze_goal(all_subtasks)
        if not goal_analysis:
            log(":::PLANNER::: Could not analyze goal", "yellow")
            return None

        target_subtasks = goal_analysis.get("target_subtasks", [])
        final_subtask = goal_analysis.get("final_subtask")

        log(f":::PLANNER::: Goal analysis: targets={target_subtasks}, final={final_subtask}", "cyan")

        if not target_subtasks and not final_subtask:
            log(":::PLANNER::: No target subtasks identified", "yellow")
            return None

        # Step 2: Find pages containing target subtasks
        target_pages = self._find_target_pages(target_subtasks, all_subtasks)
        if not target_pages:
            log(":::PLANNER::: Target subtasks not found in any page", "yellow")
            return None

        # Step 3: Find path to nearest target page using BFS
        best_path = None
        best_target = None
        for target_page in target_pages:
            path = self._bfs_find_path(current_page, target_page, subtask_graph)
            if path is not None:
                if best_path is None or len(path) < len(best_path):
                    best_path = path
                    best_target = target_page

        if best_path is None:
            log(f":::PLANNER::: No STG path from {current_page} to targets {target_pages}", "yellow")
            return None

        # Step 4: Convert edges to planned_path steps
        planned_path = self._build_planned_path(best_path, final_subtask, goal_analysis)

        log(f":::PLANNER::: Planned {len(planned_path)} steps to page {best_target}", "green")
        return planned_path

    def _analyze_goal(self, all_subtasks: Dict[int, List[dict]]) -> Optional[dict]:
        """Use LLM to analyze instruction and identify target subtasks.

        Returns:
            Dict with 'target_subtasks' (list of subtask names to traverse)
            and 'final_subtask' (the goal subtask to execute)
        """
        # Collect all unique subtasks across pages
        unique_subtasks = {}
        for page_idx, subtasks in all_subtasks.items():
            for s in subtasks:
                name = s.get('name', '')
                if name and name not in unique_subtasks:
                    unique_subtasks[name] = {
                        'name': name,
                        'description': s.get('description', ''),
                        'page': page_idx
                    }

        if not unique_subtasks:
            return None

        prompts = planner_agent_prompt.get_goal_analysis_prompt(
            self.instruction, list(unique_subtasks.values())
        )

        model = os.getenv("PLANNER_AGENT_GPT_VERSION",
                          os.getenv("SELECT_AGENT_GPT_VERSION", "gpt-4o-mini"))
        response = query(prompts, model=model)

        return response

    def _find_target_pages(self, target_subtasks: List[str],
                           all_subtasks: Dict[int, List[dict]]) -> List[int]:
        """Find pages containing target subtasks."""
        pages = []
        for page_idx, subtasks in all_subtasks.items():
            subtask_names = {s.get('name', '') for s in subtasks}
            if any(t in subtask_names for t in target_subtasks):
                pages.append(page_idx)
        return pages

    def _bfs_find_path(self, from_page: int, to_page: int,
                       subtask_graph: dict) -> Optional[List[dict]]:
        """BFS to find shortest path in STG."""
        if from_page == to_page:
            return []

        queue = [(from_page, [])]
        visited = {from_page}

        while queue:
            current, path = queue.pop(0)

            for edge in subtask_graph.get("edges", []):
                if edge["from_page"] == current and edge["to_page"] not in visited:
                    new_path = path + [edge]
                    if edge["to_page"] == to_page:
                        return new_path
                    visited.add(edge["to_page"])
                    queue.append((edge["to_page"], new_path))

        return None

    def _build_planned_path(self, edges: List[dict], final_subtask: Optional[str],
                            goal_analysis: dict) -> List[dict]:
        """Convert STG edges to planned_path format."""
        planned_path = []

        # Add navigation steps
        for edge in edges:
            step = {
                "page": edge["from_page"],
                "subtask": edge["subtask"],
                "instruction": f"Navigate via '{edge['subtask']}'",
                "trigger_ui_index": edge.get("trigger_ui_index", -1),
                "status": "pending"
            }
            planned_path.append(step)

        # Add final goal subtask
        if final_subtask:
            final_page = edges[-1]["to_page"] if edges else goal_analysis.get("start_page", 0)
            step = {
                "page": final_page,
                "subtask": final_subtask,
                "instruction": goal_analysis.get("final_instruction", self.instruction),
                "trigger_ui_index": -1,
                "status": "pending"
            }
            planned_path.append(step)

        return planned_path


def replan_from_current(instruction: str, current_page: int, subtask_graph: dict,
                        all_subtasks: Dict[int, List[dict]],
                        remaining_goal: str = None) -> Optional[List[dict]]:
    """Replan path from current position after unexpected transition.

    Args:
        instruction: Original user instruction
        current_page: Current page after unexpected transition
        subtask_graph: Subtask Transition Graph
        all_subtasks: All available subtasks by page
        remaining_goal: Optional remaining goal description

    Returns:
        New planned path or None
    """
    planner = PlannerAgent(remaining_goal or instruction)
    return planner.plan(current_page, subtask_graph, all_subtasks)
