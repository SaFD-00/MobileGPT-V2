# MobileGPT-V2 Architecture

A Technical Deep-Dive into the Multi-Agent Mobile Automation Framework

---

## 1. System Overview

### 1.1 High-Level Architecture

MobileGPT-V2 implements a distributed client-server architecture where:
- **Python Server**: Hosts LangGraph-based multi-agent pipelines for decision-making
- **Android Client**: Captures UI state and executes actions via Accessibility Service

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              MobileGPT-V2                                   │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌─────────────────────────────────────────┐     TCP Socket                 │
│  │           Python Server                 │    ┌─────────────────┐         │
│  │  ┌───────────────────────────────────┐  │    │                 │         │
│  │  │        LangGraph Pipeline         │  │    │  Android Client │         │
│  │  │  ┌─────────────────────────────┐  │  │◄──►│                 │         │
│  │  │  │     Task Graph (6-step)     │  │  │XML │  ┌───────────┐  │         │
│  │  │  │  supervisor → memory →      │  │  │JSON│  │Accessibility│ │         │
│  │  │  │  planner → selector →       │  │  │IMG │  │  Service   │ │         │
│  │  │  │  verifier → deriver         │  │  │    │  └───────────┘  │         │
│  │  │  └─────────────────────────────┘  │  │    │                 │         │
│  │  │  ┌─────────────────────────────┐  │  │    │  ┌───────────┐  │         │
│  │  │  │     Explore Graph           │  │  │    │  │  Input    │  │         │
│  │  │  │  supervisor → discover →    │  │  │    │  │ Dispatcher│  │         │
│  │  │  │  explore_action             │  │  │    │  └───────────┘  │         │
│  │  │  └─────────────────────────────┘  │  │    │                 │         │
│  │  └───────────────────────────────────┘  │    └─────────────────┘         │
│  │                                         │                                │
│  │  ┌───────────────────────────────────┐  │                                │
│  │  │        Memory Manager             │  │                                │
│  │  │  ┌─────────┐ ┌───────┐ ┌───────┐  │  │                                │
│  │  │  │  STG    │ │ Pages │ │Subtask│  │  │                                │
│  │  │  │  .json  │ │ .csv  │ │ .csv  │  │  │                                │
│  │  │  └─────────┘ └───────┘ └───────┘  │  │                                │
│  │  └───────────────────────────────────┘  │                                │
│  └─────────────────────────────────────────┘                                │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 1.2 Design Philosophy

MobileGPT-V2 follows these core principles:

1. **Modular Agent Design**: Each agent handles a specific aspect of task execution
2. **Explicit State Management**: LangGraph StateGraph with typed state dictionaries
3. **Graph-Based Knowledge**: STG enables efficient path planning and reuse
4. **Adaptive Execution**: Verification-driven replanning for robust task completion
5. **Safety-First Exploration**: Built-in guardrails prevent dangerous actions

### 1.3 Comparison with Mobile-Agent-v3

| Component | Mobile-Agent-v3 | MobileGPT-V2 |
|-----------|-----------------|--------------|
| **Core Model** | GUI-Owl (Qwen2.5-VL) | GPT-5.2 + LangGraph |
| **Architecture** | End-to-end multimodal | Multi-agent pipeline |
| **Learning** | Manual/Pre-defined | **Auto-Explore (DFS/BFS/GREEDY)** |
| **Knowledge** | Implicit | **Explicit STG** |
| **Planning** | Single-pass | **UICompass with BFS** |
| **Verification** | Reflection agent | **PROCEED/SKIP/REPLAN decisions** |

---

## 2. Multi-Agent Framework

### 2.1 Agent Definitions

| Agent | Mobile-Agent-v3 Role | Input | Output | Key Function |
|-------|---------------------|-------|--------|--------------|
| **ExploreAgent** | Perception + Grounding | XML, Screenshot | Subtasks, TriggerUIs | `explore()` |
| **PlannerAgent** | Planning | Instruction, STG | planned_path | `plan()` |
| **SelectAgent** | Reasoning | available_subtasks | selected_subtask | `select()` |
| **DeriveAgent** | Action | subtask, XML | Action JSON | `derive()` |
| **VerifyAgent** | Reflection | expected_page, current_page | Decision | `verify()` |
| **MemoryManager** | Memory | XML | page_index, subtasks | `search_node()` |

### 2.2 Inter-Agent Communication

Agents communicate through the shared **StateGraph** managed by LangGraph:

```python
class TaskState(TypedDict, total=False):
    # Session
    session_id: str
    instruction: str

    # Memory
    memory: Memory
    page_index: int
    current_xml: str

    # Subtask tracking
    selected_subtask: Optional[dict]
    available_subtasks: List[dict]

    # Path planning (UICompass)
    planned_path: List[PlannedPathStep]
    path_step_index: int

    # Adaptive replanning
    replan_count: int
    replan_needed: bool
    max_replan: int  # default: 5

    # Routing
    next_agent: str

    # Output
    action: Optional[dict]
    status: str
```

### 2.3 State Management (LangGraph)

**Task Graph Structure**:

```
START
  │
  ▼
┌─────────────┐
│ supervisor  │◄──────────────────────────────────────────┐
└──────┬──────┘                                           │
       │ route_next_agent()                               │
       ▼                                                  │
  ┌────┴────┬─────────┬──────────┬──────────┐            │
  ▼         ▼         ▼          ▼          ▼            │
memory   planner   selector   verifier   deriver → END   │
  │         │         │          │                       │
  └─────────┴─────────┴──────────┘                       │
                      │                                   │
                      └───────────────────────────────────┘
```

**Routing Logic** (supervisor_node.py):

```python
def route_next_agent(state: TaskState) -> str:
    if state.get("page_index") is None:
        return "memory"      # Recall step

    if state.get("planned_path") is None:
        return "planner"     # Plan step

    if state.get("replan_needed"):
        return "planner"     # Replan

    if state.get("selected_subtask") is None:
        return "selector"    # Select step

    if state.get("verification_passed") is None:
        return "verifier"    # Verify step

    if state.get("verification_passed"):
        return "deriver"     # Derive step

    if state.get("replan_count", 0) < 5:
        return "planner"     # Retry planning

    return "FINISH"
```

---

## 3. Auto-Explore Module

### 3.1 Motivation

Traditional mobile automation requires manual annotation of app structures. MobileGPT-V2's Auto-Explore module addresses this by:

1. **Autonomous Discovery**: Automatically identifies screens and available subtasks
2. **Systematic Coverage**: Explores all reachable UI states using configurable algorithms
3. **Knowledge Construction**: Builds STG for efficient task execution
4. **Safety Filtering**: Prevents execution of potentially harmful actions

### 3.2 Exploration Algorithms

#### 3.2.1 DFS (Depth-First Search)

```
Algorithm DFS_Explore(start_page):
    stack ← [(start_page, unexplored_subtasks)]
    visited ← {}

    while stack is not empty:
        (page, subtasks) ← stack.top()

        if current_page ≠ page:
            navigate_to(page)  // back action
            continue

        if subtasks is empty:
            stack.pop()
            continue

        subtask ← subtasks.pop()
        action ← execute(subtask)
        new_page ← observe_result()

        if new_page not in visited:
            visited.add(new_page)
            new_subtasks ← discover(new_page)
            stack.push((new_page, new_subtasks))

        update_STG(page, new_page, subtask, action)

    return STG
```

**Characteristics**:
- Stack-based exploration
- Explores deeply before backtracking
- Good for apps with deep navigation hierarchies

#### 3.2.2 BFS (Breadth-First Search)

```
Algorithm BFS_Explore(start_page):
    queue ← [(start_page, unexplored_subtasks)]
    visited ← {}

    while queue is not empty:
        (page, subtasks) ← queue.dequeue()

        if current_page ≠ page:
            path ← find_path_to(page)
            navigate(path)
            continue

        for subtask in subtasks:
            action ← execute(subtask)
            new_page ← observe_result()

            if new_page not in visited:
                visited.add(new_page)
                new_subtasks ← discover(new_page)
                queue.enqueue((new_page, new_subtasks))

            update_STG(page, new_page, subtask, action)
            navigate_back()

    return STG
```

**Characteristics**:
- Queue-based exploration
- Explores all subtasks at current level first
- Ensures uniform coverage

#### 3.2.3 GREEDY (Shortest-Path First)

```
Algorithm GREEDY_Explore(start_page):
    unexplored ← {start_page: discover(start_page)}
    visited ← {}

    while unexplored is not empty:
        (target_page, subtask) ← find_nearest_unexplored()

        if target_page is None:
            break  // All explored

        path ← BFS_path(current_page, target_page)
        navigate(path)

        action ← execute(subtask)
        new_page ← observe_result()

        if new_page not in visited:
            visited.add(new_page)
            unexplored[new_page] ← discover(new_page)

        mark_explored(target_page, subtask)
        update_STG(target_page, new_page, subtask, action)

    return STG
```

**Characteristics**:
- Global optimization using BFS path finding
- Always explores nearest unexplored subtask
- Most efficient for complete app coverage (recommended)

### 3.3 Subtask Transition Graph (STG)

The STG is the core data structure representing learned app navigation:

```json
{
  "nodes": [0, 1, 2, 3],
  "edges": [
    {
      "from_page": 0,
      "to_page": 1,
      "subtask": "open_settings",
      "trigger_ui_index": 5,
      "action_sequence": [
        {"name": "click", "parameters": {"index": 5}}
      ],
      "explored": true
    },
    {
      "from_page": 1,
      "to_page": 2,
      "subtask": "change_language",
      "trigger_ui_index": 12,
      "action_sequence": [
        {"name": "click", "parameters": {"index": 12}},
        {"name": "click", "parameters": {"index": 3}}
      ],
      "explored": true
    }
  ]
}
```

**Key Operations**:

| Operation | Description | Complexity |
|-----------|-------------|------------|
| `add_transition()` | Add new edge to STG | O(1) |
| `get_path_to_page()` | BFS shortest path | O(V + E) |
| `get_all_subtasks()` | Retrieve all subtasks | O(E) |
| `mark_explored()` | Update exploration status | O(1) |

### 3.4 Safety Guardrails

Auto-Explore automatically filters potentially dangerous actions:

| Category | Description | Examples |
|----------|-------------|----------|
| `financial` | Monetary transactions | Order, Purchase, Subscribe, Pay |
| `account` | Authentication/Account | Login, Logout, Delete Account |
| `system` | System modifications | Install, Uninstall, Reset |
| `data` | Irreversible data ops | Delete, Format, Clear |

**Classification Process**:
1. ExploreAgent extracts subtasks with `safe` flag
2. Unsafe subtasks are logged but not executed
3. STG edges only created for safe subtasks

---

## 4. Task Execution Pipeline

### 4.1 6-Step Process

```
┌─────────────────────────────────────────────────────────────────┐
│                    6-Step Task Pipeline                          │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌──────────┐   ┌──────────┐   ┌──────────┐                     │
│  │1. RECALL │──►│2. PLAN   │──►│3. SELECT │                     │
│  │          │   │(UICompass)│   │          │                     │
│  │ Memory   │   │ BFS Path │   │ Subtask  │                     │
│  │ Lookup   │   │ Planning │   │ Choice   │                     │
│  └──────────┘   └──────────┘   └────┬─────┘                     │
│                                      │                           │
│                                      ▼                           │
│  ┌──────────┐   ┌──────────┐   ┌──────────┐                     │
│  │6. RECALL │◄──│5. VERIFY │◄──│4. DERIVE │                     │
│  │  (next)  │   │          │   │          │                     │
│  │          │   │ PROCEED  │   │ Action   │                     │
│  │          │   │ SKIP     │   │ Generate │                     │
│  │          │   │ REPLAN   │   │          │                     │
│  └──────────┘   └──────────┘   └──────────┘                     │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

| Step | Agent | Input | Output |
|------|-------|-------|--------|
| **Recall** | MemoryNode | current_xml | page_index, available_subtasks |
| **Plan** | PlannerAgent | instruction, STG | planned_path |
| **Select** | SelectAgent | planned_path / available_subtasks | selected_subtask |
| **Derive** | DeriveAgent | selected_subtask, xml | action JSON |
| **Verify** | VerifyAgent | expected_page, current_page | decision |
| **Recall** | MemoryNode | new_xml | updated state |

### 4.2 Adaptive Replanning

The Verify step implements adaptive replanning logic:

```python
def verify_with_path(planned_path, step_index, current_page):
    expected_page = planned_path[step_index]["page"]

    if current_page == expected_page:
        return "PROCEED"  # Continue to next step

    # Check if jumped ahead in path
    future_pages = [s["page"] for s in planned_path[step_index + 1:]]
    if current_page in future_pages:
        new_index = find_index(future_pages, current_page)
        return "SKIP", new_index  # Jump to matching step

    return "REPLAN"  # Unexpected page, replan needed
```

**Decision Types**:

| Decision | Condition | Action |
|----------|-----------|--------|
| **PROCEED** | current_page == expected_page | Continue to next step |
| **SKIP** | current_page in future path | Jump to matching step |
| **REPLAN** | Unexpected page | Return to Plan step |

**Maximum Replanning**: 5 attempts (configurable via `max_replan`)

### 4.3 UICompass Path Planning

PlannerAgent uses BFS on STG for optimal path planning:

```python
def plan_path(current_page, subtask_graph, instruction):
    # 1. Analyze goal using LLM
    goal_analysis = analyze_goal(instruction, all_subtasks)

    # 2. Find target pages containing goal subtasks
    target_pages = find_target_pages(goal_analysis.target_subtasks)

    # 3. BFS shortest path to nearest target
    best_path = bfs_find_path(current_page, target_pages, subtask_graph)

    # 4. Build planned_path with step details
    return build_planned_path(best_path, goal_analysis.final_subtask)
```

**planned_path Structure**:

```python
planned_path = [
    {
        "page": 0,
        "subtask": "open_settings",
        "instruction": "Open settings menu",
        "trigger_ui_index": 5,
        "status": "pending"  # pending | in_progress | completed | skipped
    },
    {
        "page": 1,
        "subtask": "change_language",
        "instruction": "Select language option",
        "trigger_ui_index": 12,
        "status": "pending"
    }
]
```

---

## 5. Vision Integration

### 5.1 Screenshot Analysis

MobileGPT-V2 enhances UI recognition through Vision API integration:

| Agent | Vision Usage | Enhancement |
|-------|--------------|-------------|
| **ExploreAgent** | Subtask extraction | Visual UI element recognition |
| **SelectAgent** | Subtask selection | Visual context awareness |
| **DeriveAgent** | Action derivation | Element location hints |

### 5.2 API Format

Vision API messages follow Chat Completions format:

```python
# Standard text message
{"role": "user", "content": "Analyze this UI"}

# Vision-enabled message
{
    "role": "user",
    "content": [
        {"type": "text", "text": "Analyze this UI"},
        {
            "type": "image_url",
            "image_url": {
                "url": "data:image/jpeg;base64,{base64_data}",
                "detail": "high"  # low | high | auto
            }
        }
    ]
}
```

**Implementation** (utils.py):

```python
def query_with_vision(messages, model="gpt-5.2",
                      screenshot_path=None,
                      is_list=False,
                      image_detail="high"):
    if screenshot_path and os.path.exists(screenshot_path):
        messages = _add_image_to_messages(messages, screenshot_path, image_detail)

    return query(messages, model=model, is_list=is_list)
```

---

## 6. Memory System

### 6.1 Data Structures

```
memory/{app_name}/
│
├── pages.csv                    # Page registry
│   └── index, available_subtasks, trigger_uis, screen
│
├── hierarchy.csv                # Screen embeddings (page matching)
│   └── index, screen, embedding
│
├── tasks.csv                    # Task path cache
│   └── name, path
│
├── subtask_graph.json           # STG
│   └── {nodes: [int], edges: [SubtaskTransitionEdge]}
│
└── pages/{page_index}/          # Per-page data
    ├── available_subtasks.csv
    │   └── name, description, parameters, trigger_ui_index, exploration
    ├── subtasks.csv             # Learned subtasks
    │   └── name, description, guideline, trigger_ui_index,
    │       start_page, end_page, parameters, example
    ├── actions.csv              # Action sequences
    │   └── subtask_name, trigger_ui_index, step,
    │       start_page, end_page, action, example
    └── screen/                  # Screenshots
```

### 6.2 Page Matching Algorithm

Page matching uses embedding similarity:

```python
def search_node(self, parsed_xml, hierarchy_xml, encoded_xml) -> Tuple[int, float]:
    # 1. Compute embedding for current screen
    embedding = get_openai_embedding(str(parsed_xml))

    # 2. Compare with stored embeddings
    max_similarity = 0
    matched_page = -1

    for stored in self.hierarchy_db:
        similarity = cosine_similarity(embedding, stored.embedding)
        if similarity > max_similarity:
            max_similarity = similarity
            matched_page = stored.index

    # 3. Return match if above threshold (0.95)
    if max_similarity > 0.95:
        return matched_page, max_similarity

    return -1, 0.0  # New page
```

### 6.3 STG Operations

| Method | Description | Usage |
|--------|-------------|-------|
| `_load_subtask_graph()` | Load STG from JSON | Initialization |
| `_save_subtask_graph()` | Persist STG to JSON | After updates |
| `add_transition()` | Add new edge | Exploration |
| `get_path_to_page()` | BFS shortest path | Navigation |
| `get_all_available_subtasks()` | Get all subtasks | Planning |
| `update_end_page()` | Update edge destination | Discovery |

---

## 7. Communication Protocol

### 7.1 Message Types

| Type | Byte | Direction | Content |
|------|------|-----------|---------|
| `A` | Package | Client → Server | App package name |
| `S` | Screenshot | Client → Server | JPEG image bytes |
| `X` | XML | Client → Server | UI hierarchy XML |
| `I` | Instruction | Client → Server | User task description |
| `L` | App List | Client → Server | Installed app list |
| `E` | External | Client → Server | External app switch detected |
| `F` | Finish | Client → Server | Session termination |
| - | Action | Server → Client | Action JSON command |

### 7.2 Action JSON Format

```json
{
    "name": "click",
    "parameters": {
        "index": 5,
        "description": "Settings button click"
    }
}
```

**Supported Actions**:

| Action | Parameters | Description |
|--------|------------|-------------|
| `click` | `index` | Single tap on UI element |
| `long-click` | `index` | Long press (2000ms) |
| `input` | `index`, `text` | Text input to field |
| `scroll` | `direction` | Scroll (`up`/`down`) |
| `back` | - | System back button |
| `home` | - | System home button |
| `finish` | - | End session |

---

## 8. Android Client

### 8.1 Accessibility Service

**MobileGPTAccessibilityService** is the core Android component:

```
┌──────────────────────────────────────────────────────────────────┐
│                 MobileGPTAccessibilityService                    │
├──────────────────────────────────────────────────────────────────┤
│  ┌──────────────────────┐      ┌──────────────────────────┐     │
│  │ AccessibilityService │      │ FloatingButtonManager    │     │
│  │ (UI tree capture)    │      │ (User control)           │     │
│  └──────────┬───────────┘      └──────────────────────────┘     │
│             │                                                    │
│  ┌──────────▼───────────┐      ┌──────────────────────────┐     │
│  │AccessibilityNode     │      │ InputDispatcher          │     │
│  │InfoDumper            │      │ (Action execution)       │     │
│  │(XML serialization)   │      └──────────────────────────┘     │
│  └──────────────────────┘                                        │
│                                                                  │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │               MobileGPTClient (TCP Socket)               │   │
│  │  ┌─────────┐  ┌─────────┐  ┌─────────┐  ┌─────────┐     │   │
│  │  │sendPkg  │  │sendXML  │  │sendImg  │  │recvMsg  │     │   │
│  │  └─────────┘  └─────────┘  └─────────┘  └─────────┘     │   │
│  └──────────────────────────────────────────────────────────┘   │
└──────────────────────────────────────────────────────────────────┘
```

**UI Hierarchy Serialization**:

```xml
<hierarchy>
  <node
    index="0"
    resource-id="com.app:id/button_login"
    text="Login"
    class="android.widget.Button"
    content-desc="Login button"
    clickable="true"
    long-clickable="false"
    scrollable="false"
    enabled="true"
    bounds="[100,200][300,400]"
    important="true"
    NAF="false" />
  <node index="1" ... />
</hierarchy>
```

### 8.2 Input Dispatcher

**InputDispatcher** executes actions on the device:

```java
public class InputDispatcher {

    public static void performClick(
        AccessibilityService service,
        AccessibilityNodeInfo node,
        boolean isLongClick
    ) {
        if (isLongClick) {
            node.performAction(AccessibilityNodeInfo.ACTION_LONG_CLICK);
        } else {
            node.performAction(AccessibilityNodeInfo.ACTION_CLICK);
        }
    }

    public static void performTextInput(
        AccessibilityService service,
        ClipboardManager clipboard,
        AccessibilityNodeInfo node,
        String text
    ) {
        Bundle args = new Bundle();
        args.putCharSequence(
            AccessibilityNodeInfo.ACTION_ARGUMENT_SET_TEXT_CHARSEQUENCE,
            text
        );
        node.performAction(AccessibilityNodeInfo.ACTION_SET_TEXT, args);
    }

    public static void performScroll(
        AccessibilityNodeInfo node,
        String direction
    ) {
        int action = direction.equals("up")
            ? AccessibilityNodeInfo.ACTION_SCROLL_BACKWARD
            : AccessibilityNodeInfo.ACTION_SCROLL_FORWARD;
        node.performAction(action);
    }

    public static void performBack(AccessibilityService service) {
        service.performGlobalAction(
            AccessibilityService.GLOBAL_ACTION_BACK
        );
    }
}
```

---

## 9. Extension Points

### 9.1 Custom Exploration Algorithm

Add new algorithm in `explore_action_node.py`:

```python
def _get_custom_action(self, state: ExploreState) -> dict:
    # Implement custom exploration logic
    pass
```

### 9.2 New Agent Type

Create in `Server/agents/`:

```python
class CustomAgent:
    def __init__(self, memory):
        self.memory = memory

    def execute(self, state):
        # Agent logic
        pass
```

### 9.3 Additional Action Type

Add in `InputDispatcher.java`:

```java
public static void performCustomAction(
    AccessibilityService service,
    AccessibilityNodeInfo node,
    Map<String, Object> parameters
) {
    // Custom action implementation
}
```

### 9.4 Custom Memory Backend

Replace CSV-based storage in `memory_manager.py` with database backend.

---

## 10. State Definitions

### 10.1 TaskState

```python
class TaskState(TypedDict, total=False):
    # Session
    session_id: str
    instruction: str

    # Memory references
    memory: Any
    page_index: int
    current_xml: str

    # Subtask tracking
    selected_subtask: Optional[dict]
    rejected_subtasks: List[dict]
    available_subtasks: List[dict]

    # Path planning (UICompass)
    planned_path: Optional[List[PlannedPathStep]]
    path_step_index: int

    # Adaptive replanning
    replan_count: int
    replan_needed: bool
    max_replan: int  # default: 5

    # Routing
    next_agent: str

    # Output
    action: Optional[dict]
    status: str
    iteration: int
```

### 10.2 ExploreState

```python
class ExploreState(TypedDict, total=False):
    # Session
    session_id: str
    app_name: str
    algorithm: Literal["DFS", "BFS", "GREEDY"]

    # Current screen
    current_xml: str
    page_index: int

    # Exploration tracking
    visited_pages: Set[int]
    explored_subtasks: Dict
    exploration_stack: List  # DFS
    exploration_queue: List  # BFS
    unexplored_subtasks: Dict  # GREEDY

    # Graph
    subtask_graph: Dict
    back_edges: Dict

    # Path tracking
    traversal_path: List
    navigation_plan: List

    # Last action tracking
    last_explored_page_index: Optional[int]
    last_explored_ui_index: Optional[int]
    last_explored_subtask_name: Optional[str]

    # Routing and output
    next_agent: str
    action: Optional[dict]
    status: str
```

---

## 11. References

- **LangGraph**: https://github.com/langchain-ai/langgraph
- **Mobile-Agent-v3**: GUI-Owl based multi-agent mobile automation
- **MobileGPT**: Original LLM-based mobile automation research
- **Android Accessibility**: https://developer.android.com/guide/topics/ui/accessibility
