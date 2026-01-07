"""LangGraph State definition for inference."""

from typing import Any, TypedDict


class InferenceState(TypedDict, total=False):
    """Inference graph state.

    Tracks the state of subtask selection and verification loop.

    Flow:
        1. MemoryAgent: page/state lookup, load available subtasks
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
    state_index: int
    current_xml: str
    hierarchy_xml: str
    encoded_xml: str

    # Subtask selection
    selected_subtask: dict | None
    rejected_subtasks: list[dict]  # Rejected subtasks (for reselection)
    available_subtasks: list[dict]

    # VerifyAgent results
    next_page_index: int | None
    next_state_index: int | None
    next_page_subtasks: list[dict]
    verification_passed: bool | None  # True: go, False: don't go, None: not verified

    # Routing
    next_agent: str

    # Result
    action: dict | None
    status: str
    iteration: int  # Reselection loop count
