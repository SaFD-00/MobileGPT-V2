# MobileGPT-V2 아키텍처 (Architecture)

다중 에이전트 모바일 자동화 프레임워크 기술 상세

---

## 1. 시스템 개요 (System Overview)

### 1.1 고수준 아키텍처 (High-Level Architecture)

MobileGPT-V2는 분산 클라이언트-서버 아키텍처를 구현합니다:
- **Python 서버**: 의사결정을 위한 LangGraph 기반 다중 에이전트 파이프라인 호스팅
- **Android 클라이언트**: 접근성 서비스를 통한 UI 상태 캡처 및 액션 실행

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              MobileGPT-V2                                   │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌─────────────────────────────────────────┐     TCP Socket                 │
│  │           Python Server                 │    ┌─────────────────┐         │
│  │  ┌───────────────────────────────────┐  │    │                 │         │
│  │  │        LangGraph Pipeline         │  │    │  Android Client │         │
│  │  │  ┌─────────────────────────────┐  │  │◄──►│  (클라이언트)   │         │
│  │  │  │     Task Graph (6-step)     │  │  │XML │  ┌───────────┐  │         │
│  │  │  │  supervisor → memory →      │  │  │JSON│  │Accessibility│ │         │
│  │  │  │  planner → selector →       │  │  │IMG │  │  Service   │ │         │
│  │  │  │  verifier → deriver         │  │  │    │  │(접근성서비스)│ │         │
│  │  │  └─────────────────────────────┘  │  │    │  └───────────┘  │         │
│  │  │  ┌─────────────────────────────┐  │  │    │  ┌───────────┐  │         │
│  │  │  │     Explore Graph           │  │  │    │  │  Input    │  │         │
│  │  │  │  supervisor → discover →    │  │  │    │  │ Dispatcher│  │         │
│  │  │  │  explore_action             │  │  │    │  │(액션실행) │  │         │
│  │  │  └─────────────────────────────┘  │  │    │  └───────────┘  │         │
│  │  └───────────────────────────────────┘  │    └─────────────────┘         │
│  │                                         │                                │
│  │  ┌───────────────────────────────────┐  │                                │
│  │  │        Memory Manager             │  │  ← 메모리 관리자               │
│  │  │  ┌─────────┐ ┌───────┐ ┌───────┐  │  │                                │
│  │  │  │ Mobile  │ │ Pages │ │Subtask│  │  │                                │
│  │  │  │   Map   │ │+sumry │ │+guide │  │  │                                │
│  │  │  └─────────┘ └───────┘ └───────┘  │  │                                │
│  │  └───────────────────────────────────┘  │                                │
│  └─────────────────────────────────────────┘                                │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 1.2 설계 철학 (Design Philosophy)

MobileGPT-V2는 다음 핵심 원칙을 따릅니다:

1. **모듈형 에이전트 설계**: 각 에이전트가 태스크 실행의 특정 측면을 담당
2. **명시적 상태 관리**: 타입이 지정된 상태 딕셔너리를 가진 LangGraph StateGraph
3. **Mobile Map 지식**: 페이지 요약, 액션 설명, 가이던스를 포함한 풍부한 그래프 구조
4. **4-Step 워크플로우**: Load → Filter → Plan → Execute/Replan
5. **적응형 실행**: 강건한 태스크 완료를 위한 검증 기반 재계획
6. **안전 우선 탐색**: 위험한 액션을 방지하는 내장 가드레일

---

## 2. 다중 에이전트 프레임워크 (Multi-Agent Framework)

### 2.1 에이전트 정의 (Agent Definitions)

| 에이전트 | 입력 | 출력 | 핵심 함수 |
|----------|------|------|-----------|
| **ExploreAgent** | XML, 스크린샷 | 서브태스크, TriggerUI | `explore()` |
| **HistoryAgent** | 이전/이후 XML, 액션 | 설명, 가이던스 | `generate_description()` |
| **SummaryAgent** | XML, 서브태스크 | 페이지 요약 | `generate_summary()` |
| **FilterAgent** | 지시어, 전체 서브태스크 | 필터링된 서브태스크 | `filter_subtasks()` |
| **PlannerAgent** | 지시어, Mobile Map, filtered_names | planned_path (with is_transit) | `plan()` |
| **StepVerifyAgent** | subtasks, path, graph | pass/warn/fail 결정 | `verify_load()`, `verify_filter()`, `verify_plan()` |
| **SelectAgent** | available_subtasks | selected_subtask | `select()` |
| **DeriveAgent** | 서브태스크, XML | 액션 JSON | `derive()` |
| **VerifyAgent** | expected_page, current_page, page_summary | 결정 | `verify_path()`, `verify_planned_path()` |
| **MemoryManager** | XML | page_index, 서브태스크 | `search_node()` |

### 2.2 에이전트 간 통신 (Inter-Agent Communication)

에이전트들은 LangGraph가 관리하는 공유 **StateGraph**를 통해 통신합니다:

```python
class TaskState(TypedDict, total=False):
    # 세션 (Session)
    session_id: str
    instruction: str

    # 메모리 (Memory)
    memory: Memory
    page_index: int
    current_xml: str

    # 서브태스크 추적 (Subtask tracking)
    selected_subtask: Optional[dict]
    available_subtasks: List[dict]

    # 경로 계획 (Path planning - UICompass)
    planned_path: List[PlannedPathStep]  # is_transit 플래그 포함
    path_step_index: int

    # 적응형 재계획 (Adaptive replanning)
    replan_count: int
    replan_needed: bool
    max_replan: int  # 기본값: 5

    # 라우팅 (Routing)
    next_agent: str

    # 출력 (Output)
    action: Optional[dict]
    status: str
```

### 2.3 상태 관리 (State Management - LangGraph)

**Task Graph 구조**:

```
START
  │
  ▼
┌─────────────┐
│ supervisor  │◄──────────────────────────────────────────┐  ← 라우팅 컨트롤러
└──────┬──────┘                                           │
       │ route_next_agent()  ← 다음 에이전트 결정         │
       ▼                                                  │
  ┌────┴────┬─────────┬──────────┬──────────┐            │
  ▼         ▼         ▼          ▼          ▼            │
memory   planner   selector   verifier   deriver → END   │
  │         │         │          │         ↑ 최종 액션   │
  └─────────┴─────────┴──────────┘         출력          │
                      │                                   │
                      └───────────────────────────────────┘
```

**라우팅 로직** (supervisor_node.py):

```python
def route_next_agent(state: TaskState) -> str:
    if state.get("page_index") is None:
        return "memory"      # Recall 단계

    if state.get("planned_path") is None:
        return "planner"     # Plan 단계

    if state.get("replan_needed"):
        return "planner"     # 재계획

    if state.get("selected_subtask") is None:
        return "selector"    # Select 단계

    if state.get("verification_passed") is None:
        return "verifier"    # Verify 단계

    if state.get("verification_passed"):
        return "deriver"     # Derive 단계

    if state.get("replan_count", 0) < 5:
        return "planner"     # 계획 재시도

    return "FINISH"
```

---

## 3. Auto-Explore 모듈 & Mobile Map 생성

### 3.1 동기 (Motivation)

전통적인 모바일 자동화는 앱 구조의 수동 주석이 필요합니다. MobileGPT-V2의 Auto-Explore 모듈은 다음을 통해 이를 해결합니다:

1. **자율 발견**: 화면과 사용 가능한 서브태스크를 자동으로 식별
2. **체계적 커버리지**: 설정 가능한 알고리즘을 사용하여 도달 가능한 모든 UI 상태 탐색
3. **Mobile Map 구축**: 다음을 포함한 풍부한 네비게이션 그래프 구축:
   - **페이지 요약** (UICompass 스타일): 페이지가 표시하고 허용하는 것
   - **액션 설명** (M3A 스타일): 각 액션 후 변경된 내용
   - **액션 가이던스**: 각 액션의 시맨틱 의미
   - **통합 가이던스**: 집계된 서브태스크 레벨 지침
4. **안전 필터링**: 잠재적으로 위험한 액션 실행 방지

### 3.2 탐색 알고리즘 (Exploration Algorithms)

#### 3.2.1 DFS (Depth-First Search, 깊이 우선 탐색)

```
알고리즘 DFS_Explore(start_page):
    stack ← [(start_page, unexplored_subtasks)]  // 스택 초기화
    visited ← {}

    while stack이 비어있지 않음:
        (page, subtasks) ← stack.top()

        if current_page ≠ page:
            navigate_to(page)  // back 액션
            continue

        if subtasks가 비어있음:
            stack.pop()
            continue

        subtask ← subtasks.pop()
        action ← execute(subtask)
        new_page ← observe_result()

        if new_page가 visited에 없음:
            visited.add(new_page)
            new_subtasks ← discover(new_page)
            stack.push((new_page, new_subtasks))

        update_STG(page, new_page, subtask, action)

    return STG
```

**특징**:
- 스택 기반 탐색
- 백트래킹 전 깊이 탐색
- 깊은 네비게이션 계층 구조를 가진 앱에 적합

#### 3.2.2 BFS (Breadth-First Search, 너비 우선 탐색)

```
알고리즘 BFS_Explore(start_page):
    queue ← [(start_page, unexplored_subtasks)]  // 큐 초기화
    visited ← {}

    while queue가 비어있지 않음:
        (page, subtasks) ← queue.dequeue()

        if current_page ≠ page:
            path ← find_path_to(page)
            navigate(path)
            continue

        for subtask in subtasks:
            action ← execute(subtask)
            new_page ← observe_result()

            if new_page가 visited에 없음:
                visited.add(new_page)
                new_subtasks ← discover(new_page)
                queue.enqueue((new_page, new_subtasks))

            update_STG(page, new_page, subtask, action)
            navigate_back()

    return STG
```

**특징**:
- 큐 기반 탐색
- 현재 레벨의 모든 서브태스크를 먼저 탐색
- 균일한 커버리지 보장

#### 3.2.3 GREEDY (Shortest-Path First, 최단 경로 우선)

```
알고리즘 GREEDY_Explore(start_page):
    unexplored ← {start_page: discover(start_page)}  // 미탐색 딕셔너리
    visited ← {}

    while unexplored가 비어있지 않음:
        (target_page, subtask) ← find_nearest_unexplored()  // 가장 가까운 미탐색

        if target_page가 None:
            break  // 모두 탐색됨

        path ← BFS_path(current_page, target_page)
        navigate(path)

        action ← execute(subtask)
        new_page ← observe_result()

        if new_page가 visited에 없음:
            visited.add(new_page)
            unexplored[new_page] ← discover(new_page)

        mark_explored(target_page, subtask)
        update_STG(target_page, new_page, subtask, action)

    return STG
```

**특징**:
- BFS 경로 탐색을 사용한 전역 최적화
- 항상 가장 가까운 미탐색 서브태스크 탐색
- 완전한 앱 커버리지에 가장 효율적 (권장)

### 3.3 Mobile Map (서브태스크 전이 그래프)

Mobile Map은 학습된 앱 네비게이션을 나타내는 핵심 데이터 구조입니다:

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
        {
          "name": "click",
          "parameters": {"index": 5},
          "description": "설정 아이콘 클릭, 설정 메뉴 표시됨",
          "guidance": "설정 아이콘을 클릭하여 설정 메뉴 열기"
        }
      ],
      "explored": true
    },
    {
      "from_page": 1,
      "to_page": 2,
      "subtask": "change_language",
      "trigger_ui_index": 12,
      "action_sequence": [
        {
          "name": "click",
          "parameters": {"index": 12},
          "description": "언어 옵션 클릭, 언어 선택기 표시됨",
          "guidance": "언어 옵션을 클릭하여 언어 선택"
        },
        {
          "name": "click",
          "parameters": {"index": 3},
          "description": "English 선택, 확인 다이얼로그 표시됨",
          "guidance": "목록에서 원하는 언어 선택"
        }
      ],
      "explored": true
    }
  ]
}
```

**주요 연산**:

| 연산 | 설명 | 복잡도 |
|------|------|--------|
| `add_transition()` | Mobile Map에 새 엣지 추가 | O(1) |
| `get_path_to_page()` | BFS 최단 경로 | O(V + E) |
| `get_all_subtasks()` | 모든 서브태스크 조회 | O(E) |
| `mark_explored()` | 탐색 상태 업데이트 | O(1) |
| `update_page_summary()` | 페이지 요약 저장 | O(1) |
| `update_action_description()` | 액션 히스토리 저장 | O(1) |

### 3.4 안전 가드레일 (Safety Guardrails)

Auto-Explore는 잠재적으로 위험한 액션을 자동으로 필터링합니다:

| 카테고리 | 설명 | 예시 |
|----------|------|------|
| `financial` | 금전 거래 | Order, Purchase, Subscribe, Pay |
| `account` | 인증/계정 | Login, Logout, Delete Account |
| `system` | 시스템 수정 | Install, Uninstall, Reset |
| `data` | 비가역적 데이터 작업 | Delete, Format, Clear |

**분류 프로세스**:
1. ExploreAgent가 `safe` 플래그와 함께 서브태스크 추출
2. 안전하지 않은 서브태스크는 로깅되지만 실행되지 않음
3. Mobile Map 엣지는 안전한 서브태스크에 대해서만 생성

### 3.5 M3A-style 히스토리 추적 (Action History Tracking)

탐색 중 수행된 액션의 히스토리를 추적하여 설명과 가이던스를 생성합니다.

**상태 필드**:

```python
# ExploreState에 포함
action_history: List[dict]           # 액션 히스토리 리스트
before_xml: str                       # 액션 실행 전 XML
before_screenshot_path: str           # 액션 실행 전 스크린샷 경로
```

**처리 흐름**:

```
┌─────────────────────────────────────────────────────────────────┐
│                M3A-style 히스토리 처리 흐름                      │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  1. explore_action_node                                          │
│     └── _add_to_action_history()                                 │
│         └── before_xml, action 정보 저장                         │
│                                                                  │
│  2. discover_node                                                │
│     └── _process_action_history()                                │
│         └── HistoryAgent 호출 → 설명/가이던스 생성               │
│                                                                  │
│  3. memory_manager                                               │
│     └── save_action_history()                                    │
│         └── actions.csv에 저장                                   │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

**액션 히스토리 구조**:

```python
action_history_entry = {
    "subtask_name": "open_settings",
    "trigger_ui_index": 5,
    "action": {"name": "click", "parameters": {"index": 5}},
    "before_xml": "<hierarchy>...</hierarchy>",
    "before_screenshot_path": "/path/to/screenshot.jpg",
    "start_page": 0
}
```

---

## 4. Task 실행 파이프라인 (Task Execution Pipeline)

### 4.1 Mobile Map 4-Step 워크플로우

```
┌─────────────────────────────────────────────────────────────────┐
│              Mobile Map 4-Step Workflow                          │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌──────────┐   ┌──────────┐   ┌──────────┐   ┌──────────┐     │
│  │1. LOAD   │──►│2. FILTER │──►│3. PLAN   │──►│4. EXECUTE│     │
│  │ (로드)   │   │ (필터)   │   │ (계획)   │   │ (실행)   │     │
│  │ Get all  │   │ Select   │   │ BFS Path │   │ Run &    │     │
│  │ subtasks │   │ relevant │   │ Planning │   │ Replan   │     │
│  └──────────┘   └──────────┘   └──────────┘   └──────────┘     │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

| 단계 | 에이전트 | 설명 |
|------|----------|------|
| **Load** | MemoryManager → StepVerifyAgent | 모든 페이지에서 요약과 함께 모든 서브태스크 가져오기 → `verify_load()` |
| **Filter** | FilterAgent → StepVerifyAgent | 지시어에 관련된 서브태스크 선택 → `verify_filter()` |
| **Plan** | PlannerAgent → StepVerifyAgent | 전체 subtask에 `[RELEVANT]` 마커 부여 후 Mobile Map BFS로 최적 경로 생성. 경유(transit) subtask 자동 포함 (`is_transit` 플래그) → `verify_plan()` |
| **Execute** | Selector/Verifier | 액션 실행, `verify_planned_path()` → 불일치 시 재계획 |

### 4.2 6-Step 프로세스

```
┌─────────────────────────────────────────────────────────────────┐
│                    6-Step Task Pipeline                          │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌──────────┐   ┌──────────┐   ┌──────────┐                     │
│  │1. RECALL │──►│2. PLAN   │──►│3. SELECT │                     │
│  │ (조회)   │   │(UICompass)│   │ (선택)   │                     │
│  │ Memory   │   │ BFS Path │   │ Subtask  │                     │
│  │ Lookup   │   │ Planning │   │ Choice   │                     │
│  └──────────┘   └──────────┘   └────┬─────┘                     │
│                                      │                           │
│                                      ▼                           │
│  ┌──────────┐   ┌──────────┐   ┌──────────┐                     │
│  │6. RECALL │◄──│5. VERIFY │◄──│4. DERIVE │                     │
│  │  (다음)  │   │ (검증)   │   │ (도출)   │                     │
│  │          │   │ PROCEED  │   │ Action   │                     │
│  │          │   │ SKIP     │   │ Generate │                     │
│  │          │   │ REPLAN   │   │          │                     │
│  └──────────┘   └──────────┘   └──────────┘                     │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

| 단계 | 에이전트 | 입력 | 출력 |
|------|----------|------|------|
| **Recall** | MemoryNode | current_xml | page_index, available_subtasks → planner로 라우팅 |
| **Plan** | PlannerAgent + StepVerifyAgent | instruction, Mobile Map | planned_path (각 Step별 검증 포함) |
| **Select** | SelectAgent | planned_path / available_subtasks + filtered_subtasks | selected_subtask |
| **Derive** | DeriveAgent | selected_subtask, xml | 액션 JSON |
| **Verify** | VerifyAgent | expected_page, current_page, page_summary | 결정 (PROCEED/SKIP/REPLAN) |
| **Recall** | MemoryNode | new_xml | 업데이트된 상태 |

### 4.3 Step Verification Layer

4-Step 워크플로우의 각 단계에 경량 검증 레이어가 추가됩니다 (`StepVerifyAgent`):

| 검증 함수 | 단계 | 검증 내용 | 실패 시 |
|------------|------|-----------|---------|
| `verify_load()` | Load | subtask 최소 1개 로딩, 다중 page 커버리지 | 파이프라인 중단 |
| `verify_filter()` | Filter | 필터 결과 비어있지 않음, 제거율 90% 이하 | all_subtasks로 fallback |
| `verify_plan()` | Plan | path 비어있지 않음, 엣지 연결성, 순환 없음 | Select 모드로 fallback |

추가로, Verifier 노드에서 `verify_planned_path()`가 실행 중 위치를 검증합니다:

| 결정 | 조건 | 라우팅 |
|------|------|--------|
| **PROCEED** | 예상 페이지 도착 | 기존 LLM 검증 계속 |
| **SKIP** | 미래 페이지로 점프 | supervisor → selector |
| **REPLAN** | 예상치 못한 페이지 | planner로 재계획 |

### 4.4 적응형 재계획 (Adaptive Replanning)

Verify 단계는 적응형 재계획 로직을 구현합니다:

```python
def verify_with_path(planned_path, step_index, current_page):
    expected_page = planned_path[step_index]["page"]

    if current_page == expected_page:
        return "PROCEED"  # 다음 단계로 계속

    # 경로에서 앞으로 점프했는지 확인
    future_pages = [s["page"] for s in planned_path[step_index + 1:]]
    if current_page in future_pages:
        new_index = find_index(future_pages, current_page)
        return "SKIP", new_index  # 일치하는 단계로 점프

    return "REPLAN"  # 예상치 못한 페이지, 재계획 필요
```

**결정 유형**:

| 결정 | 조건 | 액션 |
|------|------|------|
| **PROCEED** | current_page == expected_page | 다음 단계로 계속 |
| **SKIP** | current_page가 future path에 있음 | 일치하는 단계로 점프 |
| **REPLAN** | 예상치 못한 페이지 | Plan 단계로 돌아감 |

**최대 재계획 횟수**: 5회 (`max_replan`으로 설정 가능)

### 4.4 UICompass 경로 계획

PlannerAgent는 최적 경로 계획을 위해 Mobile Map에서 BFS를 사용합니다.

**Transit Subtask 자동 포함**: Plan 단계에서 전체 subtask에 Filter 결과를 `[RELEVANT]` 마커로 표시하여 LLM에 전달합니다. BFS 경로 탐색 시 필터링되지 않았지만 경로상 필요한 경유(transit) subtask가 자동으로 포함되며, `is_transit: True` 플래그로 구분됩니다. (UICompass Focusing Strategy Step 5 영감)

```python
def plan_path(current_page, subtask_graph, instruction, filtered_names):
    # 1. LLM을 사용하여 목표 분석 (전체 subtask + [RELEVANT] 마커)
    goal_analysis = analyze_goal(instruction, all_subtasks, filtered_names)

    # 2. 목표 서브태스크를 포함하는 타겟 페이지 찾기
    target_pages = find_target_pages(goal_analysis.target_subtasks)

    # 3. 가장 가까운 타겟으로 BFS 최단 경로
    best_path = bfs_find_path(current_page, target_pages, subtask_graph)

    # 4. 단계 세부사항 + transit 감지와 함께 planned_path 구축
    return build_planned_path(best_path, goal_analysis.final_subtask, filtered_names)
```

**planned_path 구조**:

```python
planned_path = [
    {
        "page": 0,
        "subtask": "open_settings",
        "instruction": "설정 메뉴 열기",
        "trigger_ui_index": 5,
        "status": "pending",  # pending | in_progress | completed | skipped
        "is_transit": True    # 경유 subtask (필터에 없지만 경로상 필요)
    },
    {
        "page": 1,
        "subtask": "change_language",
        "instruction": "언어 옵션 선택",
        "trigger_ui_index": 12,
        "status": "pending",
        "is_transit": False   # 직접 관련 subtask (필터에 포함)
    }
]
```

---

## 5. Vision 통합 (Vision Integration)

### 5.1 스크린샷 분석 (Screenshot Analysis)

MobileGPT-V2는 Vision API 통합을 통해 UI 인식을 향상시킵니다:

| 에이전트 | Vision 사용 | 향상 효과 |
|----------|-------------|----------|
| **ExploreAgent** | 서브태스크 추출 | 시각적 UI 요소 인식 |
| **SelectAgent** | 서브태스크 선택 | 시각적 컨텍스트 인식 |
| **DeriveAgent** | 액션 도출 | 요소 위치 힌트 |

### 5.2 API 형식 (API Format)

Vision API 메시지는 Chat Completions 형식을 따릅니다:

```python
# 표준 텍스트 메시지
{"role": "user", "content": "이 UI를 분석하세요"}

# Vision 활성화 메시지
{
    "role": "user",
    "content": [
        {"type": "text", "text": "이 UI를 분석하세요"},
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

**구현** (utils.py):

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

## 6. 메모리 시스템 (Memory System)

### 6.1 데이터 구조 (Data Structures)

```
memory/{app_name}/
│
├── pages.csv                    # 페이지 레지스트리
│   └── index, available_subtasks, trigger_uis, screen, summary
│
├── hierarchy.csv                # 화면 임베딩 (페이지 매칭용)
│   └── index, screen, embedding
│
├── tasks.csv                    # 태스크 경로 캐시
│   └── name, path
│
├── subtask_graph.json           # Mobile Map
│   └── {nodes: [int], edges: [SubtaskTransitionEdge]}
│
└── pages/{page_index}/          # 페이지별 데이터
    ├── available_subtasks.csv
    │   └── name, description, parameters, trigger_ui_index, exploration
    ├── subtasks.csv             # 학습된 서브태스크
    │   └── name, description, guideline, trigger_ui_index,
    │       start_page, end_page, parameters, example
    ├── actions.csv              # 액션 시퀀스
    │   └── subtask_name, trigger_ui_index, step,
    │       start_page, end_page, action, description, guidance, example
    └── screen/                  # 스크린샷
```

### 6.2 페이지 매칭 알고리즘 (Page Matching Algorithm)

페이지 매칭은 임베딩 유사도를 사용합니다:

```python
def search_node(self, parsed_xml, hierarchy_xml, encoded_xml) -> Tuple[int, float]:
    # 1. 현재 화면의 임베딩 계산
    embedding = get_openai_embedding(str(parsed_xml))

    # 2. 저장된 임베딩과 비교
    max_similarity = 0
    matched_page = -1

    for stored in self.hierarchy_db:
        similarity = cosine_similarity(embedding, stored.embedding)
        if similarity > max_similarity:
            max_similarity = similarity
            matched_page = stored.index

    # 3. 임계값(0.95) 이상이면 매칭 반환
    if max_similarity > 0.95:
        return matched_page, max_similarity

    return -1, 0.0  # 새 페이지
```

### 6.3 Mobile Map 연산 (Mobile Map Operations)

| 메서드 | 설명 | 용도 |
|--------|------|------|
| `_load_subtask_graph()` | JSON에서 Mobile Map 로드 | 초기화 |
| `_save_subtask_graph()` | Mobile Map을 JSON으로 저장 | 업데이트 후 |
| `add_transition()` | 새 엣지 추가 | 탐색 |
| `get_path_to_page()` | BFS 최단 경로 | 네비게이션 |
| `get_all_available_subtasks()` | 모든 서브태스크 가져오기 | 계획 수립 |
| `update_end_page()` | 엣지 목적지 업데이트 | 발견 |

### 6.4 세션 상태 관리 (Session State Management)

각 세션의 상태를 서버 메모리에서 관리합니다.

**구조**:

```python
# server_auto_explore.py
_sessions = {
    session_id: {
        "state": ExploreState,      # LangGraph 상태
        "memory": Memory,            # 메모리 매니저 인스턴스
        "handler": MessageHandler    # 메시지 핸들러
    }
}
```

**참고**: LangGraph 체크포인터는 Memory/ExploreAgent 객체의 직렬화 불가로 비활성화됨

**세션 라이프사이클**:

```
┌─────────────────────────────────────────────────────────────────┐
│                    세션 라이프사이클                             │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  1. 연결 수립 → 세션 ID 생성                                     │
│  2. 초기 상태 생성 → _sessions에 저장                            │
│  3. 그래프 실행 중 상태 업데이트                                  │
│  4. 연결 종료 또는 'F' 메시지 → 세션 정리                        │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

---

## 7. 통신 프로토콜 (Communication Protocol)

### 7.1 메시지 타입 (Message Types)

| 타입 | 바이트 | 방향 | 내용 |
|------|--------|------|------|
| `A` | Package | Client → Server | 앱 패키지 이름 |
| `S` | Screenshot | Client → Server | JPEG 이미지 바이트 |
| `X` | XML | Client → Server | UI 계층 구조 XML |
| `I` | Instruction | Client → Server | 사용자 태스크 설명 |
| `L` | App List | Client → Server | 설치된 앱 목록 |
| `E` | External | Client → Server | 외부 앱 전환 감지 |
| `F` | Finish | Client → Server | 세션 종료 |
| `-` | Action | Server → Client | 액션 JSON 명령 |

### 7.2 액션 JSON 형식 (Action JSON Format)

```json
{
    "name": "click",
    "parameters": {
        "index": 5,
        "description": "설정 버튼 클릭"
    }
}
```

**지원 액션**:

| 액션 | 파라미터 | 설명 |
|------|----------|------|
| `click` | `index` | UI 요소 단일 탭 |
| `long-click` | `index` | 롱 프레스 (2000ms) |
| `input` | `index`, `text` | 필드에 텍스트 입력 |
| `scroll` | `direction` | 스크롤 (`up`/`down`) |
| `back` | - | 시스템 뒤로 버튼 |
| `home` | - | 시스템 홈 버튼 |
| `finish` | - | 세션 종료 |

### 7.3 External App 처리 (External App Handling)

탐색 중 외부 앱으로 전환될 때의 처리 로직입니다.

**메시지 플로우**:

```
┌─────────────────────────────────────────────────────────────────┐
│                External App 처리 흐름                            │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  1. Android 클라이언트가 외부 앱 전환 감지                       │
│     └── 현재 앱 패키지 ≠ 탐색 중인 앱 패키지                     │
│                                                                  │
│  2. 'E' (External) 메시지 전송                                   │
│     └── 외부 앱 패키지 이름 포함                                 │
│                                                                  │
│  3. 서버에서 _handle_external_app_cleanup() 호출                 │
│     └── 마지막 탐색 서브태스크 정보 확인                         │
│                                                                  │
│  4. 관련 서브태스크 삭제                                         │
│     └── memory.delete_subtask(subtask_name, page_index)          │
│                                                                  │
│  5. 'back' 액션 반환                                             │
│     └── 원래 앱으로 복귀                                         │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

**구현** (server_auto_explore.py):

```python
def _handle_external_app_cleanup(state: ExploreState, memory: Memory) -> dict:
    """외부 앱 전환 시 서브태스크 정리"""
    last_page = state.get("last_explored_page_index")
    last_subtask = state.get("last_explored_subtask_name")

    if last_page is not None and last_subtask:
        # 외부 앱을 여는 서브태스크 삭제
        memory.delete_subtask(last_subtask, last_page)
        log(f"Deleted external app subtask: {last_subtask}")

    return {"name": "back", "parameters": {}}
```

---

## 8. Android 클라이언트 (Android Client)

### 8.1 클라이언트 구조 (Client Structure)

| 디렉토리 | 모드 | 설명 |
|----------|------|------|
| `App/` | Task Mode | 학습된 지식으로 태스크 실행 |
| `App_Auto_Explorer/` | Auto-Explore | 자율 UI 탐색 및 Mobile Map 구축 |

### 8.2 접근성 서비스 (Accessibility Service)

**MobileGPTAccessibilityService**는 핵심 Android 컴포넌트입니다:

```
┌──────────────────────────────────────────────────────────────────┐
│                 MobileGPTAccessibilityService                    │
├──────────────────────────────────────────────────────────────────┤
│  ┌──────────────────────┐      ┌──────────────────────────┐     │
│  │ AccessibilityService │      │ FloatingButtonManager    │     │
│  │ (UI 트리 캡처)       │      │ (사용자 제어)            │     │
│  └──────────┬───────────┘      └──────────────────────────┘     │
│             │                                                    │
│  ┌──────────▼───────────┐      ┌──────────────────────────┐     │
│  │AccessibilityNode     │      │ InputDispatcher          │     │
│  │InfoDumper            │      │ (액션 실행)              │     │
│  │(XML 직렬화)          │      └──────────────────────────┘     │
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

**UI 계층 구조 직렬화**:

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

### 8.3 InputDispatcher

**InputDispatcher**는 기기에서 액션을 실행합니다:

```java
public class InputDispatcher {

    // 클릭 수행
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

    // 텍스트 입력 수행
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

    // 스크롤 수행
    public static void performScroll(
        AccessibilityNodeInfo node,
        String direction
    ) {
        int action = direction.equals("up")
            ? AccessibilityNodeInfo.ACTION_SCROLL_BACKWARD
            : AccessibilityNodeInfo.ACTION_SCROLL_FORWARD;
        node.performAction(action);
    }

    // 뒤로 가기 수행
    public static void performBack(AccessibilityService service) {
        service.performGlobalAction(
            AccessibilityService.GLOBAL_ACTION_BACK
        );
    }
}
```

---

## 9. 확장 포인트 (Extension Points)

### 9.1 커스텀 탐색 알고리즘 (Custom Exploration Algorithm)

`explore_action_node.py`에 새 알고리즘 추가:

```python
def _get_custom_action(self, state: ExploreState) -> dict:
    # 커스텀 탐색 로직 구현
    pass
```

### 9.2 새 에이전트 타입 (New Agent Type)

`Server/agents/`에 생성:

```python
class CustomAgent:
    def __init__(self, memory):
        self.memory = memory

    def execute(self, state):
        # 에이전트 로직
        pass
```

### 9.3 추가 액션 타입 (Additional Action Type)

`InputDispatcher.java`에 추가:

```java
public static void performCustomAction(
    AccessibilityService service,
    AccessibilityNodeInfo node,
    Map<String, Object> parameters
) {
    // 커스텀 액션 구현
}
```

### 9.4 커스텀 메모리 백엔드 (Custom Memory Backend)

`memory_manager.py`의 CSV 기반 저장소를 데이터베이스 백엔드로 교체

---

## 10. 상태 정의 (State Definitions)

### 10.1 TaskState

```python
class TaskState(TypedDict, total=False):
    # 세션 (Session)
    session_id: str
    instruction: str

    # 메모리 참조 (Memory references)
    memory: Any
    page_index: int
    current_xml: str

    # 서브태스크 추적 (Subtask tracking)
    selected_subtask: Optional[dict]
    rejected_subtasks: List[dict]
    available_subtasks: List[dict]

    # 경로 계획 (Path planning - UICompass)
    planned_path: Optional[List[PlannedPathStep]]
    path_step_index: int

    # 적응형 재계획 (Adaptive replanning)
    replan_count: int
    replan_needed: bool
    max_replan: int  # 기본값: 5

    # 라우팅 (Routing)
    next_agent: str

    # 출력 (Output)
    action: Optional[dict]
    status: str
    iteration: int
```

### 10.2 ExploreState

```python
class ExploreState(TypedDict, total=False):
    # 세션 (Session)
    session_id: str
    app_name: str
    algorithm: Literal["DFS", "BFS", "GREEDY"]

    # 현재 화면 (Current screen)
    current_xml: str
    page_index: int

    # 탐색 추적 (Exploration tracking)
    visited_pages: Set[int]
    explored_subtasks: Dict
    exploration_stack: List  # DFS
    exploration_queue: List  # BFS
    unexplored_subtasks: Dict  # GREEDY

    # 그래프 (Graph)
    subtask_graph: Dict
    back_edges: Dict

    # 경로 추적 (Path tracking)
    traversal_path: List
    navigation_plan: List

    # 마지막 액션 추적 (Last action tracking)
    last_explored_page_index: Optional[int]
    last_explored_ui_index: Optional[int]
    last_explored_subtask_name: Optional[str]

    # 라우팅 및 출력 (Routing and output)
    next_agent: str
    action: Optional[dict]
    status: str
```

### 10.3 action_history 구조 (Action History Structure)

```python
action_history = [
    {
        "subtask_name": str,           # 서브태스크 이름
        "trigger_ui_index": int,       # 트리거 UI 인덱스
        "action": dict,                # 실행된 액션
        "before_xml": str,             # 액션 전 XML
        "before_screenshot_path": str, # 액션 전 스크린샷 경로
        "start_page": int              # 시작 페이지
    },
    ...
]
```

---

## 11. 테스트 구조 (Test Structure)

### 11.1 디렉토리 구조

```
Server/tests/
├── unit/           # 단위 테스트
│   ├── agents/     # 에이전트 테스트
│   ├── memory/     # 메모리 시스템 테스트
│   └── utils/      # 유틸리티 테스트
├── integration/    # 통합 테스트
│   ├── graphs/     # 그래프 워크플로우 테스트
│   └── server/     # 서버 통합 테스트
├── mocks/          # Mock 객체
│   ├── mock_llm.py
│   └── mock_memory.py
└── fixtures/       # 테스트 데이터
    ├── xml/        # 샘플 XML
    └── responses/  # 샘플 LLM 응답
```

### 11.2 테스트 실행

```bash
# 전체 테스트
pytest Server/tests/ -v

# 단위 테스트만
pytest Server/tests/unit/ -v

# 통합 테스트만
pytest Server/tests/integration/ -v

# 커버리지 포함
pytest Server/tests/ --cov=Server --cov-report=html
```

---

## 12. 참고 자료 (References)

- **LangGraph**: https://github.com/langchain-ai/langgraph
- **MobileGPT**: LLM 기반 모바일 자동화에 관한 원본 연구
- **Mobile-Agent-v3 (M3A)**: thought-action-summary 트리플을 사용한 액션 히스토리 생성
- **UICompass**: UI Map 구조, 페이지 요약, 적응형 재계획
- **Android Accessibility**: https://developer.android.com/guide/topics/ui/accessibility
