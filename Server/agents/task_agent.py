import os

import pandas as pd

from agents.prompts import task_agent_prompt
from loguru import logger
from utils.utils import query


class TaskAgent:
    """
    Agent that analyzes user commands and converts them into structured tasks.
    Extracts task name, description, parameters, and target app.
    """
    def __init__(self):
        self.database_path = f"./memory/tasks.csv"
        if not os.path.exists(self.database_path):
            self.database = pd.DataFrame([], columns=['name', 'description', 'parameters', 'app'])
            self.database.to_csv(self.database_path, index=False)
        else:
            self.database = pd.read_csv(self.database_path, header=0)

    def get_task(self, instruction) -> (dict, bool):
        """
        Analyze the command and create a task object.
        Returns:
            task: Task information dictionary
            is_new: Whether it is a new task
        """
        # Get the list of previously known tasks
        known_tasks = self.database.to_dict(orient='records')
        response = query(messages=task_agent_prompt.get_prompts(instruction, known_tasks),
                         model=os.getenv("TASK_AGENT_GPT_VERSION"))

        task = response["api"]
        is_new = True
        # If it matches an existing task, update it; otherwise, classify as a new task
        if str(response["found_match"]).lower() == "true":
            self.update_task(task)
            is_new = False

        return task, is_new

    def update_task(self, task):
        """Update the description and parameters of an existing task"""
        condition = (self.database['name'] == task['name']) & (self.database['app'] == task['app'])
        index_to_update = self.database.index[condition]

        if not index_to_update.empty:
            # Update 'description' and 'parameters' of the matching row
            self.database.loc[index_to_update, 'description'] = task['description']
            self.database.loc[index_to_update, 'parameters'] = task['parameters']
        else:
            # Handle the case when no matching task is found
            logger.error("No matching task found to update")
