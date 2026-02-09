"""LangGraph State definitions for task execution and exploration."""

from typing import Any, Dict, List, Literal, Optional, Set, TypedDict


# ============================================================================
# Mobile Map (formerly STG - Subtask Transition Graph)
# ============================================================================
# Mobile Map represents the app's UI navigation structure as a graph.
# - Nodes: Pages (screens) with summaries
# - Edges: Subtask transitions with descriptions, guidance, and action sequences
# ============================================================================

class SubtaskTransitionEdge(TypedDict):
    """Single edge in the Mobile Map.

    Represents a transition from one page to another via a subtask.
    Includes action descriptions and guidance.
    """
    from_page: int
    to_page: int
    subtask: str
    trigger_ui_index: int
    action_sequence: List[dict]  # [{name, parameters, description, guidance}, ...]
    explored: bool


class SubtaskTransitionGraph(TypedDict):
    """Mobile Map (Subtask Transition Graph) for path planning.

    Stores the topology of page transitions discovered during exploration.
    Used for BFS-based optimal path finding and 4-step workflow.

    Note: The variable name `subtask_graph` is kept for backward compatibility.
    This is conceptually referred to as "Mobile Map" in documentation.
    """
    nodes: List[int]  # Page indices (with summaries stored in pages.csv)
    edges: List[SubtaskTransitionEdge]


class PlannedPathStep(TypedDict, total=False):
    """Single step in a planned path."""
    page: int
    subtask: str
    instruction: str
    trigger_ui_index: int
    status: str  # pending | in_progress | completed | skipped
    is_transit: bool  # True if this is a transit subtask (not in filtered set but needed for BFS path)


# ============================================================================
# Task Execution State
# ============================================================================

class TaskState(TypedDict, total=False):
    """Task execution graph state.

    Tracks the state of subtask selection and verification loop.

    Flow:
        1. MemoryAgent: page lookup, load available subtasks
        2. SelectAgent: select subtask from available list
        3. VerifyAgent: verify next screen (should we go there?)
           - "shouldn't go" -> reselect (loop back to SelectAgent)
           - "should go" -> confirmed
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

    # ========================================================================
    # Subtask Path Planning
    # ========================================================================
    planned_path: Optional[List[PlannedPathStep]]  # Planned subtask sequence
    path_step_index: int  # Current step in planned_path

    # ========================================================================
    # Adaptive Replanning
    # ========================================================================
    expected_page_index: Optional[int]  # Expected page after action
    replan_count: int  # Number of replan attempts
    replan_needed: bool  # Flag to trigger replanning
    max_replan: int  # Maximum replan attempts (default: 5)

    # ========================================================================
    # Mobile Map: 4-Step Workflow (Load → Filter → Plan → Execute)
    # ========================================================================
    all_subtasks_list: List[dict]  # All subtasks from all pages (Step 1: Load)
    filtered_subtasks: List[dict]  # Subtasks relevant to instruction (Step 2: Filter)


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
    algorithm: Literal["DFS", "BFS", "GREEDY"]

    # Current screen state
    current_xml: str
    hierarchy_xml: str
    encoded_xml: str
    page_index: int
    screenshot_path: Optional[str]  # Screenshot path for Vision API

    # Exploration state (persisted across invocations via MemorySaver)
    visited_pages: Set[int]  # page indices
    explored_subtasks: Dict  # {page: [(subtask_name, trigger_ui), ...]}
    exploration_stack: List  # DFS stack
    exploration_queue: List  # BFS queue
    subtask_graph: Dict  # Subtask Transition Graph {from: [(to, subtask_name), ...]}
    back_edges: Dict  # Back action edges {from: [to, ...]}
    unexplored_subtasks: Dict  # {page: [subtask_info, ...]}
    traversal_path: List  # Current path for backtracking

    # Memory and agents
    memory: Any  # Memory instance
    explore_agent: Any  # ExploreAgent instance

    # Last action tracking (for marking explored and updating end_page)
    last_explored_page_index: Optional[int]
    last_explored_ui_index: Optional[int]
    last_explored_subtask_name: Optional[str]
    last_explored_action: Optional[dict]
    last_explored_screen: Optional[str]

    # Routing
    next_agent: str
    last_action_was_back: bool

    # Result
    action: Optional[dict]
    status: str
    is_new_screen: bool

    # ========================================================================
    # Mobile Map: Action History Tracking
    # ========================================================================
    # History entries: [{step, before_xml, before_screenshot, action, description?}, ...]
    action_history: List[dict]  # Accumulated during subtask exploration
    before_xml: Optional[str]  # XML state before current action
    before_screenshot_path: Optional[str]  # Screenshot path before current action
