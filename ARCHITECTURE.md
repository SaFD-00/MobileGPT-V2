# MobileGPT-V2 아키텍처

## 1. 시스템 개요

### 1.1 고수준 아키텍처 다이어그램

```
┌─────────────────────────────────────────────────────────────────────────┐
│                            MobileGPT-V2                                 │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  ┌───────────────────────────────────────┐                              │
│  │           Python Server               │                              │
│  │  ┌─────────────────────────────────┐  │         TCP Socket           │
│  │  │      LangGraph Pipeline         │  │       ┌─────────────┐        │
│  │  │  ┌───────────────────────────┐  │  │       │             │        │
│  │  │  │  Task Graph (6-step)      │  │  │◄─────►│   Android   │        │
│  │  │  │  supervisor → memory →    │  │  │ XML   │   Client    │        │
│  │  │  │  planner → selector →     │  │  │ JSON  │             │        │
│  │  │  │  verifier → deriver       │  │  │ Image │             │        │
│  │  │  └───────────────────────────┘  │  │       │             │        │
│  │  │  ┌───────────────────────────┐  │  │       │  ┌───────┐  │        │
│  │  │  │  Explore Graph            │  │  │       │  │Access-│  │        │
│  │  │  │  supervisor → discover →  │  │  │       │  │ibility│  │        │
│  │  │  │  explore_action           │  │  │       │  │Service│  │        │
│  │  │  └───────────────────────────┘  │  │       │  └───────┘  │        │
│  │  └─────────────────────────────────┘  │       │             │        │
│  │                                       │       │  ┌───────┐  │        │
│  │  ┌─────────────────────────────────┐  │       │  │ Input │  │        │
│  │  │       Memory Manager            │  │       │  │Dispatch│ │        │
│  │  │  ┌───────┐ ┌───────┐ ┌───────┐  │  │       │  └───────┘  │        │
│  │  │  │ STG   │ │ Pages │ │Subtask│  │  │       │             │        │
│  │  │  │.json  │ │ .csv  │ │ .csv  │  │  │       └─────────────┘        │
│  │  │  └───────┘ └───────┘ └───────┘  │  │                              │
│  │  └─────────────────────────────────┘  │                              │
│  └───────────────────────────────────────┘                              │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

### 1.2 6단계 핵심 프로세스

```
Auto-Explore → Plan → Select → Derive → Verify → Recall
```

| 단계 | 노드 | 에이전트 | 역할 |
|------|------|---------|------|
| **Auto-Explore** | discover_node, explore_action_node | ExploreAgent | UI 자동 탐색 및 학습 |
| **Plan** | planner_node | PlannerAgent | STG 기반 경로 계획 |
| **Select** | selector_node | SelectAgent | Subtask 선택 |
| **Derive** | deriver_node | DeriveAgent | 액션 도출 |
| **Verify** | verifier_node | VerifyAgent | 결과 검증 및 재계획 |
| **Recall** | memory_node | - | 메모리에서 정보 로드 |

---

## 2. 6단계 프로세스 상세

### 2.1 Auto-Explore (탐색 및 학습)

**목적**: UI 자동 탐색으로 페이지/subtask/액션 학습

**구현 파일**:
- `Server/graphs/explore_graph.py` - LangGraph 탐색 파이프라인
- `Server/graphs/nodes/discover_node.py` - 화면 발견 노드
- `Server/graphs/nodes/explore_action_node.py` - 탐색 액션 노드
- `Server/agents/explore_agent.py` - 탐색 에이전트

**탐색 알고리즘**:

| 알고리즘 | 자료구조 | 특징 |
|---------|---------|------|
| **DFS** | 스택 | 깊이 우선, 한 경로를 끝까지 탐색 후 백트래킹 |
| **BFS** | 큐 | 너비 우선, 현재 레벨의 모든 subtask 탐색 후 다음 레벨 |
| **GREEDY_BFS** | 큐 + STG | 전체 앱에서 가장 가까운 미탐색 subtask로 이동 |
| **GREEDY_DFS** | 스택 + STG | 깊이 우선으로 가장 가까운 미탐색 subtask로 이동 |

**출력 데이터**:
- `pages.csv` - 페이지 레지스트리
- `subtasks.csv` - 학습된 subtask
- `actions.csv` - 액션 시퀀스
- `subtask_graph.json` - Subtask Transition Graph (STG)

#### OLD MobileGPT vs NEW MobileGPT-V2 비교

| 항목 | OLD MobileGPT | NEW MobileGPT-V2 |
|------|---------------|------------------|
| **프레임워크** | 순차적 서버 루프 (소켓 기반) | LangGraph 상태 머신 + MemorySaver |
| **탐색 흐름** | 선형: Server → ExploreAgent → Memory | 다중 노드: Supervisor → Discover → ExploreAction |
| **탐색 알고리즘** | 암시적 선형 탐색 | 명시적: DFS, BFS, GREEDY (런타임 선택 가능) |
| **Page Graph** | 없음 (CSV에 암시적) | **subtask_graph.json (STG)** - 명시적 그래프 |
| **End-Page 추적** | 수동 | 자동 (`update_end_page()`) |
| **백트래킹** | 단순 Back 버튼 | 지능형 경로 계획 (BFS) |
| **상태 지속성** | 연결 해제 시 소실 | MemorySaver로 보존 |
| **코드 구조** | 단일 ExploreAgent | 모듈형 노드 (Discover/ExploreAction 분리) |
| **안전 장치** | 없음 | Dangerous subtask 필터링 |

#### 핵심 개선사항

1. **STG (Page Transition Graph)**: 페이지 간 전이를 명시적 그래프로 관리
2. **다중 탐색 알고리즘**: DFS(깊이 우선), BFS(너비 우선), GREEDY(최근접 미탐색)
3. **Subtask 탐색 추적**: `trigger_ui_index`, `start_page`, `end_page`, `exploration` 상태
4. **지능형 내비게이션**: STG 기반 최적 경로 탐색으로 효율적 백트래킹

#### Auto-Explore 가드레일 (Safety Guardrails)

**목적**: 자동 탐색 중 위험한 액션 자동 필터링으로 안전한 탐색 보장

**위험 분류 (danger_reason)**:

| 분류 | 설명 | 예시 |
|------|------|------|
| `financial` | 금전 거래 | 주문, 구매, 결제, 구독, 체크아웃 |
| `account` | 인증/계정 | 로그인, 로그아웃, 회원가입, 계정 삭제, 탈퇴 |
| `system` | 시스템 변경 | 앱 설치/제거, 설정 변경, 권한 부여, 외부 앱 실행 |
| `data` | 비가역적 데이터 | 삭제, 초기화, 포맷, 리셋 |

**동작 방식**:
1. ExploreAgent가 LLM으로 subtask 추출 시 `is_dangerous` 필드 판단
2. `is_dangerous: true`인 subtask는 탐색 대상에서 자동 제외
3. 로그에 `:::GUARDRAIL:::` 태그로 필터링된 subtask 기록

**구현 위치**:
- `Server/agents/explore_agent.py` (필터링 로직)
- `Server/agents/prompts/explore_agent_prompt.py` (LLM 프롬프트)

---

### 2.2 Plan (경로 계획) - UICompass

**목적**: STG 기반 최적 subtask 경로 계획

**구현 파일**:
- `Server/graphs/nodes/planner_node.py`
- `Server/agents/planner_agent.py`
- `Server/agents/prompts/planner_agent_prompt.py`

**알고리즘**: BFS 최단 경로 탐색

```python
def plan_path(current_page, subtask_graph, instruction):
    # 1. LLM으로 목표 subtask 분석
    goal_analysis = analyze_goal(instruction, all_subtasks)

    # 2. 목표 subtask가 있는 페이지 탐색
    target_pages = find_target_pages(goal_analysis.target_subtasks)

    # 3. BFS로 최단 경로 탐색
    best_path = bfs_find_path(current_page, target_pages, subtask_graph)

    # 4. planned_path 생성
    return build_planned_path(best_path, goal_analysis.final_subtask)
```

**출력**: `planned_path` (subtask 시퀀스)

```python
planned_path = [
    {
        "page": 0,
        "subtask": "open_settings",
        "instruction": "설정 메뉴 열기",
        "trigger_ui_index": 5,
        "status": "pending"  # pending | in_progress | completed | skipped
    },
    ...
]
```

**Fallback**: STG에 경로가 없으면 Select 단계로 직접 이동 (LLM 기반 선택)

---

### 2.3 Select (Subtask 선택)

**목적**: 다음 실행할 subtask 결정

**구현 파일**:
- `Server/graphs/nodes/selector_node.py`
- `Server/agents/select_agent.py`

**로직**:
```
planned_path 존재?
├── YES → planned_path[path_step_index] 선택
└── NO → SelectAgent(LLM)로 최적 subtask 선택
```

**출력**: `selected_subtask`

---

### 2.4 Derive (액션 도출)

**목적**: subtask를 구체적 UI 액션으로 변환

**구현 파일**:
- `Server/graphs/nodes/deriver_node.py`
- `Server/agents/derive_agent.py`

**출력**: Action JSON

```json
{
    "name": "click",
    "parameters": {
        "index": 5,
        "description": "Settings 버튼 클릭"
    }
}
```

**지원 액션**:
| 액션 | 설명 |
|------|------|
| `click` | 단일 탭 |
| `long-click` | 길게 누르기 (2000ms) |
| `input` | 텍스트 입력 |
| `scroll` | 스크롤 (up/down) |
| `back` | 시스템 뒤로가기 |
| `home` | 시스템 홈 |
| `finish` | 세션 종료 |

---

### 2.5 Verify (결과 검증) - Adaptive Replanning

**목적**: 액션 결과 검증 및 경로 조정

**구현 파일**:
- `Server/graphs/nodes/verifier_node.py`
- `Server/agents/verify_agent.py`

**검증 로직**:

```python
def verify_with_path(planned_path, step_index, current_page):
    expected_page = planned_path[step_index]["page"]

    if current_page == expected_page:
        return "PROCEED"  # 정상 진행

    # 경로상 앞선 페이지로 점프했는지 확인
    future_pages = [s["page"] for s in planned_path[step_index + 1:]]
    if current_page in future_pages:
        return "SKIP", new_step_index  # 건너뛰기

    return "REPLAN"  # 예상과 다른 페이지, 재계획 필요
```

**결정 유형**:

| 결정 | 조건 | 동작 |
|------|------|------|
| **PROCEED** | 예상 페이지 도착 | 다음 단계 진행 |
| **SKIP** | 경로상 앞선 페이지 | path_step_index 점프 |
| **REPLAN** | 예상과 다른 페이지 | Plan 단계로 돌아가 재계획 |

**최대 재계획**: 5회 (`max_replan`)

---

### 2.6 Recall (메모리 회상)

**목적**: 현재 화면에서 학습된 정보 로드

**구현 파일**:
- `Server/graphs/nodes/memory_node.py`
- `Server/memory/memory_manager.py`

**기능**:
1. **페이지 매칭**: 임베딩 유사도로 현재 화면이 어떤 페이지인지 식별
2. **available_subtasks 로드**: 현재 페이지에서 사용 가능한 subtask 목록
3. **STG 로드**: Page Transition Graph 정보 로드

**페이지 매칭 알고리즘**:

```python
def search_most_similar_hierarchy_node(hierarchy):
    # 1. 현재 화면의 임베딩 계산
    embedding = get_openai_embedding(hierarchy)

    # 2. 저장된 임베딩과 코사인 유사도 비교
    similarity = cosine_similarity(embedding, stored_embeddings)

    # 3. 유사도 0.95 이상이면 매칭
    if similarity > 0.95:
        return page_index, similarity
    return -1, 0.0  # 새 페이지
```

---

## 3. LangGraph 구현

### 3.1 Task Graph (태스크 실행)

**파일**: `Server/graphs/task_graph.py`

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

**라우팅 로직** (`supervisor_node.py`):

```python
def route_next_agent(state: TaskState) -> str:
    if state.get("page_index") is None:
        return "memory"  # Recall 단계

    if state.get("planned_path") is None and state.get("available_subtasks"):
        return "planner"  # Plan 단계

    if state.get("replan_needed"):
        return "planner"  # 재계획

    if state.get("selected_subtask") is None:
        return "selector"  # Select 단계

    if state.get("verification_passed") is None:
        return "verifier"  # Verify 단계

    if state.get("verification_passed"):
        return "deriver"  # Derive 단계

    # REPLAN 처리
    if state.get("replan_count", 0) < 5:
        return "planner"
    return "FINISH"
```

### 3.2 Explore Graph (자동 탐색)

**파일**: `Server/graphs/explore_graph.py`

```
START
  │
  ▼
┌─────────────────┐
│ supervisor      │◄──────────────────────────┐
└────────┬────────┘                           │
         │ route_explore()                    │
    ┌────┴────┐                               │
    ▼         ▼                               │
discover   explore_action ───────► FINISH     │
    │         │                               │
    └─────────┘                               │
              │                               │
              └───────────────────────────────┘
```

**Discover Node**:
- 현재 화면이 기존 페이지인지 확인
- 새 페이지면 ExploreAgent로 subtask 추출
- `unexplored_subtasks` 초기화

**Explore Action Node**:
- 알고리즘(DFS/BFS/GREEDY)에 따라 다음 탐색 액션 결정
- 탐색 완료된 subtask 마킹
- STG 업데이트

---

## 4. 메모리 관리

### 4.1 데이터 구조 계층

```
memory/{app_name}/
│
├── pages.csv                    # 페이지 레지스트리
│   └── index, available_subtasks, trigger_uis, extra_uis, screen
│
├── hierarchy.csv                # 화면 임베딩 (페이지 매칭용)
│   └── index, screen, embedding
│
├── tasks.csv                    # 태스크 경로 캐시
│   └── name, path
│
├── subtask_graph.json              # Subtask Transition Graph (STG)
│   └── {nodes: [int], edges: [SubtaskTransitionEdge]}
│
└── pages/{page_index}/          # 페이지별 데이터
    ├── available_subtasks.csv
    │   └── name, description, parameters, trigger_ui_index, exploration
    ├── subtasks.csv             # 학습된 subtask
    │   └── name, description, guideline, trigger_ui_index,
    │       start_page, end_page, parameters, example
    ├── actions.csv              # 액션 시퀀스
    │   └── subtask_name, trigger_ui_index, step,
    │       start_page, end_page, action, example
    └── screen/                  # 스크린샷
```

### 4.2 Subtask Transition Graph (STG)

**구조**:

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
    }
  ]
}
```

**주요 메서드** (`memory_manager.py`):

| 메서드 | 설명 |
|--------|------|
| `_load_subtask_graph()` | STG JSON 로드 |
| `_save_subtask_graph()` | STG JSON 저장 |
| `add_transition()` | 새 페이지 전이 추가 |
| `get_path_to_page()` | BFS로 두 페이지 간 최단 경로 |
| `get_all_available_subtasks()` | 모든 페이지의 subtask 반환 |

### 4.3 페이지 매칭 알고리즘

화면 XML을 임베딩으로 변환하여 코사인 유사도로 매칭:

```python
def search_node(self, xml_hierarchy: str) -> Tuple[int, float]:
    # 1. XML에서 핵심 요소 추출
    parsed = parse_xml(xml_hierarchy)

    # 2. OpenAI 임베딩 생성
    embedding = get_embedding(str(parsed))

    # 3. 저장된 임베딩과 비교
    for stored_embedding in self.hierarchy_db:
        similarity = cosine_similarity(embedding, stored_embedding)
        if similarity > 0.95:
            return page_index, similarity

    return -1, 0.0  # 새 페이지
```

---

## 5. 통신 프로토콜

### 5.1 메시지 타입

| 타입 | 바이트 | 방향 | 내용 |
|------|--------|------|------|
| `A` | Package | Client → Server | 앱 패키지명 |
| `S` | Screenshot | Client → Server | JPEG 이미지 |
| `X` | XML | Client → Server | UI 계층 구조 XML |
| `I` | Instruction | Client → Server | 사용자 태스크 |
| `L` | App List | Client → Server | 설치된 앱 목록 |
| `F` | Finish | Client → Server | 세션 종료 |
| - | Action | Server → Client | JSON 액션 명령 |

### 5.2 프로토콜 흐름

```
Client                              Server
  │                                   │
  ├──[L] App List────────────────────►│
  │                                   │
  ├──[I] Instruction─────────────────►│
  │                                   │
  ├──[A] Package Name────────────────►│
  │                                   │
  ├──[S] Screenshot──────────────────►│
  │                                   │
  ├──[X] UI XML──────────────────────►│
  │                                   │
  │◄──────────────────── Action JSON──┤
  │                                   │
  │  (Execute action on device)       │
  │                                   │
  ├──[S] New Screenshot──────────────►│
  ├──[X] New XML─────────────────────►│
  │           ...                     │
  │                                   │
  ├──[F] Finish──────────────────────►│
  │                                   │
```

### 5.3 Action JSON 포맷

```json
{
    "name": "click",
    "parameters": {
        "index": 5,
        "description": "Settings 버튼 클릭"
    }
}
```

| 액션 | Parameters | 설명 |
|------|------------|------|
| `click` | `index` | UI 요소 인덱스 클릭 |
| `long-click` | `index` | 길게 누르기 (2000ms) |
| `input` | `index`, `text` | 텍스트 입력 |
| `scroll` | `direction` | 스크롤 (`up`/`down`) |
| `back` | - | 시스템 뒤로가기 |
| `home` | - | 시스템 홈 |
| `finish` | - | 세션 종료 |

---

## 6. Android Client 아키텍처

### 6.1 컴포넌트 다이어그램

```
┌──────────────────────────────────────────────────────────────────┐
│                 MobileGPTAccessibilityService                    │
├──────────────────────────────────────────────────────────────────┤
│  ┌──────────────────────┐      ┌──────────────────────────┐     │
│  │ AccessibilityService │      │ FloatingButtonManager    │     │
│  │ (UI 트리 캡처)        │      │ (사용자 컨트롤)           │     │
│  └──────────┬───────────┘      └──────────────────────────┘     │
│             │                                                    │
│  ┌──────────▼───────────┐      ┌──────────────────────────┐     │
│  │AccessibilityNode     │      │ InputDispatcher          │     │
│  │InfoDumper            │      │ (액션 실행)               │     │
│  │(XML 직렬화)           │      └──────────────────────────┘     │
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

### 6.2 UI 계층 구조 직렬화

`AccessibilityNodeInfoDumper`가 접근성 트리를 인덱스가 부여된 XML로 변환:

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

**인덱스 매핑**: 서버는 `index` 값으로 UI 요소를 참조하고, 클라이언트는 해당 노드에 액션 실행

---

## 7. 확장 포인트

### 커스텀 탐색 알고리즘
`Server/graphs/nodes/explore_action_node.py`에 새 알고리즘 추가:

```python
def _get_custom_action(self, state: ExploreState) -> dict:
    # 커스텀 알고리즘 구현
    pass
```

### 새 에이전트 타입
`Server/agents/`에 새 에이전트 파일 추가:

```python
class CustomAgent:
    def __init__(self, memory):
        self.memory = memory

    def execute(self, state):
        # 에이전트 로직
        pass
```

### 추가 액션 타입
`App_Auto_Explorer/.../InputDispatcher.java`에 새 액션 추가:

```java
public static void performCustomAction(
    AccessibilityService service,
    AccessibilityNodeInfo node,
    Map<String, Object> parameters
) {
    // 커스텀 액션 구현
}
```

### 커스텀 메모리 백엔드
`Server/memory/memory_manager.py`의 CSV 기반 저장소를 데이터베이스로 교체 가능

---

## 8. 상태 정의

### TaskState (`Server/graphs/state.py`)

```python
class TaskState(TypedDict, total=False):
    # 세션
    session_id: str
    instruction: str

    # 메모리 참조
    memory: Memory
    page_index: int
    current_xml: str

    # Subtask 추적
    selected_subtask: Optional[dict]
    rejected_subtasks: List[str]
    available_subtasks: List[dict]

    # 경로 계획 (UICompass)
    planned_path: List[dict]
    path_step_index: int
    replan_count: int
    replan_needed: bool
    max_replan: int  # default: 5

    # 라우팅
    next_agent: str

    # 결과
    action: Optional[dict]
    status: str
    iteration: int
```

### ExploreState

```python
class ExploreState(TypedDict, total=False):
    # 세션
    session_id: str
    app_name: str
    algorithm: Literal["DFS", "BFS", "GREEDY_BFS", "GREEDY_DFS"]

    # 현재 화면
    current_xml: str
    page_index: int

    # 탐색 추적
    visited_pages: Set[int]
    explored_subtasks: Dict
    exploration_stack: List  # DFS
    exploration_queue: List  # BFS
    unexplored_subtasks: Dict

    # 그래프
    subtask_graph: Dict
    back_edges: Dict

    # 경로 추적
    traversal_path: List
    navigation_plan: List

    # 마지막 액션 추적
    last_explored_page_index: Optional[int]
    last_explored_ui_index: Optional[int]
    last_explored_subtask_name: Optional[str]

    # 라우팅 및 결과
    next_agent: str
    action: Optional[dict]
    status: str
```
