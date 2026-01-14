"""LangGraph State definitions for task execution and exploration."""

from typing import Any, Dict, List, Literal, Optional, Set, TypedDict


class TaskState(TypedDict, total=False):
    """Task execution graph state.

    Tracks the state of subtask selection and verification loop.

    Flow:
        1. MemoryAgent: page lookup, load available subtasks
        2. SelectAgent: select subtask from available list
        3. VerifyAgent: verify next screen (should we go there?)
           - "가면 안된다" (shouldn't go) -> reselect (loop back to SelectAgent)
           - "간다" (should go) -> confirmed
        4. DeriveAgent: derive action from confirmed subtask
    """

    # Session info
    session_id: str
    instruction: str

    # Memory reference (passed from server)
    memory: Any  # Memory instance

    # Current screen state
    page_index: int
    current_xml: str
    hierarchy_xml: str
    encoded_xml: str

    # Subtask selection
    selected_subtask: Optional[dict]
    rejected_subtasks: List[dict]  # Rejected subtasks (for reselection)
    available_subtasks: List[dict]

    # VerifyAgent results
    next_page_index: Optional[int]
    next_page_subtasks: List[dict]
    verification_passed: Optional[bool]  # True: go, False: don't go, None: not verified

    # Routing
    next_agent: str

    # Result
    action: Optional[dict]
    status: str
    iteration: int  # Reselection loop count


class ExploreState(TypedDict, total=False):
    """Exploration graph state.

    Tracks the state of automatic app exploration using DFS/BFS/GREEDY algorithms.

    Flow:
        1. Supervisor: Route to discover or explore_action
        2. Discover: Search for page, explore new screens
        3. ExploreAction: Decide next action based on algorithm
    """

    # Session info
    session_id: str
    app_name: str
    algorithm: Literal["DFS", "BFS", "GREEDY_BFS", "GREEDY_DFS"]

    # Current screen state
    current_xml: str
    hierarchy_xml: str
    encoded_xml: str
    page_index: int

    # Exploration state (persisted across invocations via MemorySaver)
    visited_pages: Set[int]  # page indices
    explored_subtasks: Dict  # {page: [(subtask_name, trigger_ui), ...]}
    exploration_stack: List  # DFS stack
    exploration_queue: List  # BFS queue
    page_graph: Dict  # Page connection graph {from: [(to, subtask_name), ...]}
    back_edges: Dict  # Back action edges {from: [to, ...]}
    unexplored_subtasks: Dict  # {page: [subtask_info, ...]}
    traversal_path: List  # Current path for backtracking

    # Memory and agents
    memory: Any  # Memory instance
    explore_agent: Any  # ExploreAgent instance

    # Last action tracking (for marking explored)
    last_explored_page_index: Optional[int]
    last_explored_ui_index: Optional[int]
    last_explored_action: Optional[dict]
    last_explored_screen: Optional[str]

    # Routing
    next_agent: str
    last_action_was_back: bool

    # Result
    action: Optional[dict]
    status: str
    is_new_screen: bool
