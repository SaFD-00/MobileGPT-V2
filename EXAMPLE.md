# EXAMPLE.md — MobileGPT-V2 동작 예시

MobileGPT-V2의 **Auto-Explore 과정**(Subtask Graph 생성)과 **Task 실행 과정**(사용자 지시 수행)을 프롬프트 기반으로 상세히 설명합니다. 각 단계에서 LLM에 전달되는 실제 프롬프트 내용과 입출력 예시를 포함합니다.

---

## 목차

- [Part 1: Auto-Explore (Subtask Graph 생성)](#part-1-auto-explore-subtask-graph-생성)
  - [1.1 개요 다이어그램](#11-개요-다이어그램)
  - [1.2 Step 1: Subtask Extraction](#12-step-1-subtask-extraction)
  - [1.3 Step 2: Trigger UI Selection](#13-step-2-trigger-ui-selection)
  - [1.4 Page Summary Generation](#14-page-summary-generation)
  - [1.5 Action Description & Guidance](#15-action-description--guidance)
  - [1.6 Explore Action 결정](#16-explore-action-결정)
  - [1.7 생성된 Subtask Graph 예시](#17-생성된-subtask-graph-예시)
- [Part 2: Task Execution (사용자 지시 수행)](#part-2-task-execution-사용자-지시-수행)
  - [2.1 개요 다이어그램](#21-개요-다이어그램)
  - [2.2 Memory Node: 페이지 매칭](#22-memory-node-페이지-매칭)
  - [2.3 Planner Node: 4-Step Workflow](#23-planner-node-4-step-workflow)
  - [2.4 Selector Node: Subtask 선택](#24-selector-node-subtask-선택)
  - [2.5 Verifier Node: 경로 검증](#25-verifier-node-경로-검증)
  - [2.6 Deriver Node: 액션 도출](#26-deriver-node-액션-도출)
  - [2.7 전체 실행 시퀀스 (End-to-End)](#27-전체-실행-시퀀스-end-to-end)
- [Part 3: 부록](#part-3-부록)
  - [3.1 데이터 스키마](#31-데이터-스키마)
  - [3.2 에이전트-프롬프트 매핑 테이블](#32-에이전트-프롬프트-매핑-테이블)
  - [3.3 환경 변수](#33-환경-변수)

---

# Part 1: Auto-Explore (Subtask Graph 생성)

**시나리오**: Google Calendar 앱을 DFS 알고리즘으로 자동 탐색

## 1.1 개요 다이어그램

```
Phone (Android)                              Python Server
──────────────                               ─────────────
                                             server_auto_explore.py
    ┌──────┐    XML + Screenshot
    │ 화면 │ ──────────────────────►  ExploreGraph:
    └──────┘                            ┌──────────────────────────────────────┐
                                        │ supervisor                          │
        ◄─── Action JSON ────────────   │   │                                 │
                                        │   ├── discover_node                 │
    ┌──────┐                            │   │     ├── ExploreAgent.explore()  │
    │ 실행 │                            │   │     │     ├── Step 1: Subtask Extraction
    └──────┘                            │   │     │     └── Step 2: Trigger UI Selection
        │                               │   │     ├── SummaryAgent (페이지 요약)
        │    XML + Screenshot           │   │     └── HistoryAgent (액션 설명/가이던스)
        └──────────────────────►        │   │                                 │
                                        │   └── explore_action_node           │
             ... 반복 ...               │         └── DFS/BFS/GREEDY 알고리즘 │
                                        └──────────────────────────────────────┘
```

**전체 흐름 요약**:

1. Android 클라이언트가 현재 화면의 XML + 스크린샷을 서버로 전송
2. `discover_node`에서 페이지 매칭 → 새 화면이면 `ExploreAgent.explore()` 호출
3. **Step 1**: LLM이 화면에서 수행 가능한 subtask 목록을 추출
4. **Step 2**: LLM이 각 subtask의 trigger UI 요소를 선택
5. `SummaryAgent`가 페이지 요약 생성
6. `explore_action_node`에서 DFS/BFS/GREEDY 알고리즘으로 다음 탐색 액션 결정
7. 액션 실행 후 `HistoryAgent`가 액션 설명/가이던스 생성
8. 결과를 Subtask Graph (subtask_graph.json, CSV 파일)에 저장
9. 탐색이 완료될 때까지 1-8 반복

---

## 1.2 Step 1: Subtask Extraction

> **프롬프트 출처**: `Server/agents/prompts/subtask_extraction_prompt.py`
>
> **호출 위치**: `discover_node.py` → `ExploreAgent.explore()` → `subtask_extraction_prompt.get_prompts()`
>
> **LLM 모델**: `EXPLORE_AGENT_GPT_VERSION` (기본값: `gpt-5.2`)
>
> **Vision**: 스크린샷 제공 시 활용

### System Prompt

<details>
<summary>System Prompt 전문 (클릭하여 펼치기)</summary>

```
You are a smartphone assistant to help users understand the mobile app screen. Given a HTML code of a mobile app screen delimited by <screen></screen>, your job is to list out high-level SUBTASKS that can be performed on this screen.

***IMPORTANT: Subtask Definition***
A subtask is a USER GOAL that typically requires MULTIPLE actions to complete. It is NOT a simple UI click or tap.

***Subtask Complexity Guidelines***:
1. A subtask should represent a USER GOAL, not a UI interaction.
   - BAD: 'click_send_button' (this is just a UI action)
   - GOOD: 'send_message_to_contact' (this is a user goal)

2. A subtask should typically require 2 or more actions to complete.
   - Single-click operations are NOT subtasks unless they trigger a multi-step flow.

3. Group related UI elements into a single higher-level subtask.
   - If you see 'Name input', 'Email input', 'Phone input', 'Save button'
   - Create ONE subtask: 'fill_and_save_contact_information'
   - NOT four separate subtasks for each field

4. Think about what the USER wants to achieve, not what buttons exist.
   - Screen has: [Search icon, Filter button, Sort dropdown, Results list]
   - Create: 'search_and_filter_items' with parameters for search query and filter options

5. Avoid subtasks that are just 'click X' or 'tap Y' - these are too granular.

***Good vs Bad Subtask Examples***:
| BAD (too simple)        | GOOD (user goal)                    |
| click_settings_icon     | configure_app_settings              |
| tap_search_button       | search_and_filter_results           |
| press_add_button        | add_new_contact_with_details        |
| click_menu              | navigate_to_specific_section        |
| tap_checkbox            | select_multiple_items_and_perform   |

***Information to include for each subtask***:
1. Subtask name: A descriptive name representing the user goal
2. Description: Detailed explanation of what this subtask accomplishes
3. Parameters: Information required from the user to execute this subtask
4. Expected steps: Estimated number of actions needed to complete

***Guidelines for generating subtasks***:
1. First, read through the screen HTML code to grasp the overall intent of the app screen.
2. Identify the USER GOALS that can be achieved on this screen.
3. For each goal, create a subtask with clear parameters.
4. Merge related simple actions into higher-level subtasks.
5. Estimate the number of steps (actions) required to complete each subtask.

***SAFETY CLASSIFICATION - REQUIRED FOR EACH SUBTASK***:
For EACH subtask, you MUST determine if it is SAFE or UNSAFE for automatic execution.
Set 'safe': false for subtasks in these SENSITIVE categories:

1. **communication** (irreversible interpersonal impact):
   - Message/email sending: Send, Reply, Reply All, 보내기, 전송
   - SNS posting: Post, Share, Tweet, 게시, 공유
   - Calls/video: Call, Dial, Start meeting
   - Contact management: Delete contact, Block, 삭제, 차단

2. **data** (irreversible data loss):
   - Permanent deletion: Delete, Remove, 삭제, 휴지통 비우기, Clear all
   - File overwrite: Overwrite, Replace, Save (same filename)
   - Bulk operations: Bulk delete, Select all + delete, 일괄 삭제

3. **financial** (monetary loss):
   - Payment: Pay, Purchase, Buy, 결제, 구매, 원클릭 주문
   - Subscription: Subscribe, Start trial, 구독, 무료 체험
   - Transfer: Transfer, Send money, 이체, 송금

4. **system** (system security threat):
   - App install/uninstall: Install, Uninstall, 설치, 삭제
   - Permissions: Permission, Allow, Grant access, 권한 허용
   - System settings: Settings > Security, 시스템 설정

5. **privacy** (personal info/auth risk):
   - Logout: Logout, Sign out, 로그아웃
   - Password: Show password, Copy password, 비밀번호 보기
   - Authentication: OTP, 2FA, Verify, 인증번호

For SAFE subtasks: set 'safe': true, 'risk_category': null
For UNSAFE subtasks: set 'safe': false, 'risk_category': '<category>'

***Constraints***:
1. Make subtask names general, not specific to this screen.
   - Instead of 'call_Bob', use 'call_contact'
2. Make parameters human-friendly.
   - Instead of 'contact_index', use 'contact_name'
3. If a parameter has FEW and IMMUTABLE valid values, provide options.
   - 'which tab? ["Contacts", "Dial pad", "Messages"]'
4. Do NOT include trigger_UIs - that will be determined in a separate step.

Respond using the JSON format described below. Ensure the response can be parsed by Python json.loads.
Response Format:
[{"name": "<subtask name representing user goal>", "description": "<detailed description of multi-step process>", "parameters": {"<parameter name>": "<question to ask>", ...}, "expected_steps": <number of expected actions to complete (integer, minimum 2)>, "safe": <true if safe to auto-execute, false if sensitive>, "risk_category": "<category if unsafe: communication/data/financial/system/privacy, null if safe>"}]

Begin!!
```

</details>

### User Prompt 예시

```
HTML code of the current app screen delimited by <screen></screen>:
<screen>
<hierarchy>
  <node index="0" resource-id="com.google.android.calendar:id/toolbar"
        class="android.widget.Toolbar" text="" bounds="[0,50][1080,200]">
    <node index="1" resource-id="com.google.android.calendar:id/menu_button"
          class="android.widget.ImageButton" text="" content-desc="메뉴 열기"
          clickable="true" bounds="[0,50][150,200]" />
    <node index="2" class="android.widget.TextView" text="2026년 2월"
          bounds="[150,80][500,170]" />
    <node index="3" resource-id="com.google.android.calendar:id/search_button"
          class="android.widget.ImageButton" content-desc="검색"
          clickable="true" bounds="[800,50][950,200]" />
    <node index="4" resource-id="com.google.android.calendar:id/view_switcher"
          class="android.widget.Spinner" text="월" clickable="true"
          bounds="[950,50][1080,200]" />
  </node>
  <node index="5" resource-id="com.google.android.calendar:id/calendar_view"
        class="android.widget.RecyclerView" scrollable="true"
        bounds="[0,200][1080,1800]">
    <node index="6" class="android.widget.TextView" text="9" bounds="[0,300][154,400]" />
    <node index="7" class="android.widget.TextView" text="10" bounds="[154,300][308,400]" />
    <node index="8" class="android.widget.TextView" text="팀 미팅"
          clickable="true" bounds="[154,420][462,470]" />
    <node index="9" class="android.widget.TextView" text="점심 약속"
          clickable="true" bounds="[308,420][616,470]" />
  </node>
  <node index="10" resource-id="com.google.android.calendar:id/fab"
        class="android.widget.FloatingActionButton" content-desc="새 일정 만들기"
        clickable="true" bounds="[900,1700][1050,1850]" />
</hierarchy>
</screen>

[A screenshot of the current screen is also provided for visual reference. Use both the HTML structure and the visual context to identify subtasks more accurately.]

List the high-level subtasks (user goals) that can be performed on this screen.
Remember: Do NOT include simple click/tap actions. Focus on meaningful user goals.

Response:
```

### LLM 응답 예시

```json
[
  {
    "name": "create_new_event",
    "description": "Create a new calendar event by tapping the FAB button, then filling in event details such as title, date, time, location, and guests",
    "parameters": {
      "event_title": "What is the title of the event?",
      "event_date": "What date should the event be on?",
      "event_time": "What time should the event start?",
      "event_location": "Where will the event take place? (optional)",
      "guests": "Who should be invited? (optional)"
    },
    "expected_steps": 6,
    "safe": true,
    "risk_category": null
  },
  {
    "name": "search_events",
    "description": "Search for specific events by keyword using the search functionality",
    "parameters": {
      "search_query": "What event are you looking for?"
    },
    "expected_steps": 3,
    "safe": true,
    "risk_category": null
  },
  {
    "name": "view_event_details",
    "description": "View detailed information about an existing event by tapping on it in the calendar view",
    "parameters": {
      "event_name": "Which event do you want to view?"
    },
    "expected_steps": 2,
    "safe": true,
    "risk_category": null
  },
  {
    "name": "switch_calendar_view",
    "description": "Change the calendar display mode between day, week, month views using the view switcher",
    "parameters": {
      "view_type": "Which view? [\"일\", \"주\", \"월\"]"
    },
    "expected_steps": 2,
    "safe": true,
    "risk_category": null
  },
  {
    "name": "navigate_calendar_menu",
    "description": "Open the side menu to access calendar settings, other calendars, or navigation options",
    "parameters": {},
    "expected_steps": 2,
    "safe": true,
    "risk_category": null
  },
  {
    "name": "delete_event",
    "description": "Delete an existing calendar event after viewing its details",
    "parameters": {
      "event_name": "Which event do you want to delete?"
    },
    "expected_steps": 4,
    "safe": false,
    "risk_category": "data"
  }
]
```

---

## 1.3 Step 2: Trigger UI Selection

> **프롬프트 출처**: `Server/agents/prompts/trigger_ui_selection_prompt.py`
>
> **호출 위치**: `discover_node.py` → `ExploreAgent.explore()` → `trigger_ui_selection_prompt.get_prompts()`
>
> **LLM 모델**: `EXPLORE_AGENT_GPT_VERSION`
>
> **Vision**: 스크린샷 제공 시 활용

### System Prompt

<details>
<summary>System Prompt 전문 (클릭하여 펼치기)</summary>

```
You are a smartphone assistant that maps subtasks to their trigger UI elements.

***Your Task***:
Given a list of subtasks and a screen HTML, identify the SINGLE BEST UI element that triggers each subtask.

***Guidelines for selecting trigger UI***:
1. Select exactly ONE UI element per subtask - the most representative one.
2. The trigger UI should be the ENTRY POINT that initiates the subtask.
   - For 'fill_form': select the first input field or the form container
   - For 'search_items': select the search icon or search input
   - For 'navigate_to_section': select the navigation button/tab
3. Prefer interactive elements: <button>, <input>, <checker>, clickable <div>
4. Use the 'index' attribute of the HTML element as the trigger_ui_index.
5. If no suitable UI exists for a subtask, use -1.

***Selection Priority***:
1. Primary action buttons (e.g., 'Submit', 'Save', 'Add')
2. Input fields that start the flow
3. Navigation elements (tabs, menu items)
4. Icons that trigger actions

***Response Format***:
Return a JSON object mapping subtask names to their trigger_ui_index:
{"subtask_name": <index>, "subtask_name2": <index2>, ...}

Example:
{"add_new_contact": 15, "search_contacts": 3, "call_contact": 8}

If a subtask cannot be triggered from this screen, use -1:
{"add_new_contact": 15, "unavailable_feature": -1}

Begin!!
```

</details>

### User Prompt 예시

```
HTML code of the current app screen:
<screen>
<hierarchy>
  <node index="0" resource-id="com.google.android.calendar:id/toolbar" ...>
    <node index="1" ... content-desc="메뉴 열기" clickable="true" />
    <node index="2" ... text="2026년 2월" />
    <node index="3" ... content-desc="검색" clickable="true" />
    <node index="4" ... text="월" clickable="true" />
  </node>
  <node index="5" ... scrollable="true">
    <node index="8" ... text="팀 미팅" clickable="true" />
    <node index="9" ... text="점심 약속" clickable="true" />
  </node>
  <node index="10" ... content-desc="새 일정 만들기" clickable="true" />
</hierarchy>
</screen>

[A screenshot of the current screen is also provided for visual reference. Use the visual layout to better identify which UI element best triggers each subtask.]

Subtasks to map:
<subtasks>[
  {"name": "create_new_event", "description": "Create a new calendar event...", "expected_steps": 6},
  {"name": "search_events", "description": "Search for specific events...", "expected_steps": 3},
  {"name": "view_event_details", "description": "View detailed information...", "expected_steps": 2},
  {"name": "switch_calendar_view", "description": "Change the calendar display mode...", "expected_steps": 2},
  {"name": "navigate_calendar_menu", "description": "Open the side menu...", "expected_steps": 2},
  {"name": "delete_event", "description": "Delete an existing calendar event...", "expected_steps": 4}
]</subtasks>

For each subtask, select the SINGLE BEST trigger UI element (by index attribute).
If no suitable UI exists, use -1.

Response (JSON object mapping subtask name to trigger_ui_index):
```

### LLM 응답 예시

```json
{
  "create_new_event": 10,
  "search_events": 3,
  "view_event_details": 8,
  "switch_calendar_view": 4,
  "navigate_calendar_menu": 1,
  "delete_event": 8
}
```

---

## 1.4 Page Summary Generation

> **프롬프트 출처**: `Server/agents/prompts/summary_agent_prompt.py`
>
> **호출 위치**: `discover_node.py` → `summary_agent.generate_summary()` (모듈 함수)
>
> **LLM 모델**: `SUMMARY_AGENT_GPT_VERSION`
>
> **Vision**: 스크린샷 제공 시 활용
>
> **생성 시점**: 새로운 페이지가 발견될 때 (`is_new = True`)

### System Prompt

<details>
<summary>System Prompt 전문 (클릭하여 펼치기)</summary>

```
You are an expert at summarizing mobile app screens. Your task is to describe what the page displays and what actions users can perform.

***Output Format***:
- Write 2-3 sentences (max 100 words)
- First sentence: Describe what the page shows/displays
- Second sentence: Describe main actions users can take
- Use user-friendly language, avoid technical terms
- Focus on functionality, not visual appearance

***Good Examples***:
- This page displays the email inbox with a list of received messages. Users can search for emails, compose new messages, access settings, and navigate to different folders like sent or drafts.

- This is the settings menu showing various configuration options. Users can adjust notifications, manage account settings, change display preferences, and access help documentation.

- This page shows the search results for the user's query. Users can filter results, view item details, add items to cart, and navigate back to search.

***Bad Examples (avoid these)***:
- This page has a RecyclerView with LinearLayout (too technical)
- The screen is blue with white text (describes appearance, not function)
- Users can click on many buttons (too vague about what buttons do)
```

</details>

### User Prompt 예시

```
***Screen XML***:
<hierarchy>
  <node index="0" resource-id="com.google.android.calendar:id/toolbar" ...>
    <node index="1" ... content-desc="메뉴 열기" clickable="true" />
    <node index="2" ... text="2026년 2월" />
    <node index="3" ... content-desc="검색" clickable="true" />
    <node index="4" ... text="월" clickable="true" />
  </node>
  <node index="5" ... scrollable="true">
    <node index="8" ... text="팀 미팅" clickable="true" />
    <node index="9" ... text="점심 약속" clickable="true" />
  </node>
  <node index="10" ... content-desc="새 일정 만들기" clickable="true" />
</hierarchy>

***Available Actions on this Page***:
[
  {"name": "create_new_event", "description": "Create a new calendar event..."},
  {"name": "search_events", "description": "Search for specific events..."},
  {"name": "view_event_details", "description": "View detailed information..."},
  {"name": "switch_calendar_view", "description": "Change the calendar display mode..."},
  {"name": "navigate_calendar_menu", "description": "Open the side menu..."}
]

If a screenshot is provided, use it as the primary source for understanding the page.

Write a brief summary of this page (2-3 sentences, max 100 words):
```

### LLM 응답 예시

```
This page displays the Google Calendar monthly view for February 2026, showing scheduled events like "팀 미팅" and "점심 약속" on the calendar grid. Users can create new events, search for existing events, switch between day/week/month views, and access the navigation menu for additional calendar settings.
```

---

## 1.5 Action Description & Guidance

> **프롬프트 출처**: `Server/agents/prompts/history_agent_prompt.py`
>
> **호출 위치**: `discover_node.py` → `_process_action_history()` → `history_agent.generate_description()` / `history_agent.generate_guidance()` (모듈 함수)
>
> **LLM 모델**: `HISTORY_AGENT_GPT_VERSION`
>
> **Vision**: before/after 스크린샷 제공 시 활용 (`before_screenshot_path`, `after_screenshot_path` 모두 지원)
>
> **생성 시점**: subtask 탐색 완료 후, 다음 페이지 discover 시

### Description: 무엇이 변했는가

#### Description System Prompt

<details>
<summary>System Prompt 전문 (클릭하여 펼치기)</summary>

```
You are an expert at describing UI state changes in mobile applications. Your task is to describe what changed on the screen after an action was performed.

***Output Format***:
- Write a single, concise sentence (max 50 words)
- Start with past-tense verb describing the action (Clicked, Typed, Scrolled, etc.)
- Then describe the result/change that occurred
- Focus on visible UI changes: what appeared, disappeared, or changed state
- Do NOT mention technical details like indices, coordinates, or XML elements

***Good Examples***:
- Clicked search icon, keyboard appeared and search interface activated
- Typed 'hello' in message field, text now visible in input area
- Scrolled down, new list items appeared including 'Settings' option
- Tapped back button, returned to previous inbox screen
- Long pressed on email item, selection mode activated with checkbox visible
- Swiped left on notification, delete button revealed

***Bad Examples (avoid these)***:
- The user clicked on element with index 5 (too technical)
- Action was performed successfully (no description of change)
- The screen changed (too vague)
- Clicked on android.widget.ImageButton (uses technical element names)
```

</details>

#### Description User Prompt 예시

```
***Action Performed***:
{
  "name": "click",
  "parameters": {"index": 10}
}

***Screen BEFORE Action***:
<hierarchy>
  <node index="0" ... text="2026년 2월" />
  ...
  <node index="10" content-desc="새 일정 만들기" clickable="true" />
</hierarchy>

***Screen AFTER Action***:
<hierarchy>
  <node index="0" resource-id="com.google.android.calendar:id/title_input"
        class="android.widget.EditText" text="" hint="제목 추가"
        clickable="true" bounds="[0,100][1080,200]" />
  <node index="1" class="android.widget.TextView" text="2026년 2월 10일 (화)"
        bounds="[0,250][540,330]" />
  <node index="2" class="android.widget.TextView" text="오전 9:00"
        clickable="true" bounds="[0,330][540,410]" />
  ...
</hierarchy>

If screenshots are provided, use them as the primary source for understanding changes.

Describe what changed (single sentence, max 50 words):
```

#### Description LLM 응답 예시

```
Clicked the new event button, navigated to the event creation screen with empty title field, date set to February 10, and time fields ready for input.
```

### Guidance: 왜 이 액션을 수행하는가

#### Guidance System Prompt

<details>
<summary>System Prompt 전문 (클릭하여 펼치기)</summary>

```
You are an expert at explaining the semantic meaning of UI actions in mobile applications. Your task is to explain WHY an action is performed and what it accomplishes.

***Output Format***:
- Write a single, concise sentence (max 30 words)
- Start with a verb describing the purpose (Click, Tap, Enter, Select, etc.)
- Explain the goal or intent of the action
- Focus on user-facing purpose, not technical implementation

***Good Examples***:
- Click the search icon to open the search dialog
- Enter the recipient's email address in the To field
- Tap the send button to deliver the message
- Scroll down to reveal more options in the settings list
- Select the attachment to preview its contents
- Long press the item to enter selection mode

***Bad Examples (avoid these)***:
- Click element at index 5 (too technical)
- Perform a click action (no semantic meaning)
- This action clicks on ImageButton (describes implementation, not purpose)
```

</details>

#### Guidance User Prompt 예시

```
***Action***:
{
  "name": "click",
  "parameters": {"index": 10}
}

***Current Screen***:
<hierarchy>
  <node index="0" ... text="2026년 2월" />
  ...
  <node index="10" content-desc="새 일정 만들기" clickable="true" />
</hierarchy>

Explain the semantic purpose of this action (single sentence, max 30 words):
```

#### Guidance LLM 응답 예시

```
Click the floating action button to open the new event creation form.
```

---

## 1.6 Explore Action 결정

> **LLM 사용**: 없음 (순수 알고리즘 기반)
>
> **구현 위치**: `Server/graphs/nodes/explore_action_node.py`

탐색 알고리즘은 LLM을 사용하지 않고, 그래프 자료구조 기반으로 다음 액션을 결정합니다.

### DFS 알고리즘 동작 예시

**초기 상태** (Page 0: Calendar 홈):

```
exploration_stack: []
visited_pages: {0}
explored_subtasks: {}
traversal_path: []
```

**Step 1**: Page 0의 subtask를 스택에 추가

```
exploration_stack: [
  (0, {name: "create_new_event", trigger_ui: 10}),
  (0, {name: "search_events", trigger_ui: 3}),
  (0, {name: "view_event_details", trigger_ui: 8}),
  (0, {name: "switch_calendar_view", trigger_ui: 4}),
  (0, {name: "navigate_calendar_menu", trigger_ui: 1})
]
```

**Step 2**: 스택 top에서 `navigate_calendar_menu` 팝 → 탐색 시작

```
Action: {"name": "click", "parameters": {"index": 1}}
explored_subtasks: {0: [("navigate_calendar_menu", 1)]}
traversal_path: [0]
```

→ 액션 실행 후 새 화면(Page 1: 사이드 메뉴)으로 이동

**Step 3**: Page 1 발견 → discover_node에서 새 subtask 추출

```
visited_pages: {0, 1}
exploration_stack: [
  (0, {name: "create_new_event", trigger_ui: 10}),
  (0, {name: "search_events", trigger_ui: 3}),
  (0, {name: "view_event_details", trigger_ui: 8}),
  (0, {name: "switch_calendar_view", trigger_ui: 4}),
  (1, {name: "open_settings", trigger_ui: 15}),   ← Page 1의 새 subtask
  (1, {name: "switch_account", trigger_ui: 12})    ← Page 1의 새 subtask
]
```

**Step 4**: `switch_account` 팝 → 탐색... (반복)

**Backtracking**: 스택의 target_page ≠ current_page일 때 `back` 액션 수행

```
# current_page = 1, 스택 top의 target_page = 0
Action: {"name": "back", "parameters": {}}
traversal_path: [0] → []  (pop)
```

### BFS / GREEDY 알고리즘 비교

| 특성 | DFS | BFS | GREEDY |
|------|-----|-----|--------|
| 자료구조 | Stack | Queue | BFS 최단경로 |
| 탐색 순서 | 깊이 우선 | 너비 우선 | 최근접 우선 |
| 네비게이션 | backtrack | path planning | path planning |
| 효율성 | 중간 | 중간 | 높음 (권장) |

---

## 1.7 생성된 Subtask Graph 예시

탐색이 완료되면 다음 파일들이 생성됩니다:

### pages.csv

| index | available_subtasks | trigger_uis | screen | summary |
|-------|--------------------|-------------|--------|---------|
| 0 | `["create_new_event","search_events","view_event_details","switch_calendar_view","navigate_calendar_menu"]` | `[10,3,8,4,1]` | `<hierarchy>...` | This page displays the Google Calendar monthly view... |
| 1 | `["open_settings","switch_account","view_trash"]` | `[15,12,18]` | `<hierarchy>...` | This is the navigation drawer showing calendar settings... |
| 2 | `["edit_event_title","set_event_time","set_event_date","add_guests","save_event"]` | `[0,2,1,5,8]` | `<hierarchy>...` | This page shows the event creation form... |

### subtasks.csv (Page 0)

| name | description | parameters | trigger_ui_index | start_page | end_page | guideline |
|------|-------------|------------|------------------|------------|----------|-----------|
| create_new_event | Create a new calendar event... | `{"event_title":"...","event_time":"..."}` | 10 | 0 | 2 | Click the floating action button to open the new event creation form. |
| search_events | Search for specific events... | `{"search_query":"..."}` | 3 | 0 | 3 | Click the search icon to open the search interface. |
| navigate_calendar_menu | Open the side menu... | `{}` | 1 | 0 | 1 | Click the menu button to open the navigation drawer. |

### actions.csv (Page 0)

| subtask_name | trigger_ui_index | step | action | description | guideline |
|--------------|------------------|------|--------|-------------|-----------|
| create_new_event | 10 | 0 | `{"name":"click","parameters":{"index":10}}` | Clicked the new event button, navigated to the event creation screen... | Click the floating action button to open the new event creation form. |
| navigate_calendar_menu | 1 | 0 | `{"name":"click","parameters":{"index":1}}` | Clicked the menu icon, side navigation drawer appeared... | Click the menu button to open the navigation drawer. |

### subtask_graph.json

```json
{
  "nodes": [0, 1, 2, 3],
  "edges": [
    {
      "from_page": 0,
      "to_page": 2,
      "subtask": "create_new_event",
      "trigger_ui_index": 10,
      "action_sequence": [
        {
          "name": "click",
          "parameters": {"index": 10},
          "description": "Clicked the new event button, navigated to the event creation screen...",
          "guideline": "Click the floating action button to open the new event creation form."
        }
      ],
      "explored": true
    },
    {
      "from_page": 0,
      "to_page": 3,
      "subtask": "search_events",
      "trigger_ui_index": 3,
      "action_sequence": [
        {
          "name": "click",
          "parameters": {"index": 3},
          "description": "Clicked search icon, search bar appeared with keyboard...",
          "guideline": "Click the search icon to open the search interface."
        }
      ],
      "explored": true
    },
    {
      "from_page": 0,
      "to_page": 1,
      "subtask": "navigate_calendar_menu",
      "trigger_ui_index": 1,
      "action_sequence": [
        {
          "name": "click",
          "parameters": {"index": 1},
          "description": "Clicked menu icon, navigation drawer appeared...",
          "guideline": "Click the menu button to open the navigation drawer."
        }
      ],
      "explored": true
    },
    {
      "from_page": 1,
      "to_page": 4,
      "subtask": "open_settings",
      "trigger_ui_index": 15,
      "action_sequence": [
        {
          "name": "click",
          "parameters": {"index": 15},
          "description": "Clicked settings option, settings page appeared...",
          "guideline": "Click the settings option to open calendar settings."
        }
      ],
      "explored": true
    }
  ]
}
```

---

# Part 2: Task Execution (사용자 지시 수행)

**시나리오**: "내일 오후 3시에 팀 미팅 일정 추가해줘" 지시

## 2.1 개요 다이어그램

```
Phone (Android)                              Python Server
──────────────                               ─────────────
                                             server.py
    ┌──────┐    Instruction + XML
    │ 화면 │ ──────────────────────►  TaskGraph (LangGraph):
    └──────┘                            ┌──────────────────────────────────────┐
                                        │ supervisor (라우팅 결정)             │
        ◄─── Action JSON ────────────   │   │                                 │
                                        │   ├── memory (페이지 매칭)          │
    ┌──────┐                            │   │                                 │
    │ 실행 │                            │   ├── planner (4-Step Workflow)     │
    └──────┘                            │   │     ├── Step 1: Load            │
        │                               │   │     ├── Step 2: Filter          │
        │    XML                        │   │     └── Step 3: Plan            │
        └──────────────────────►        │   │                                 │
                                        │   ├── selector (subtask 선택)      │
             ... 반복 ...               │   │                                 │
                                        │   ├── verifier (경로 검증)         │
                                        │   │     └── PROCEED/SKIP/REPLAN    │
                                        │   │                                 │
                                        │   └── deriver (액션 도출) → END    │
                                        └──────────────────────────────────────┘
```

**전체 흐름 요약**:

1. Android 클라이언트가 사용자 지시("내일 오후 3시에 팀 미팅 일정 추가해줘")와 현재 화면 XML을 서버로 전송
2. `supervisor`가 `memory` → `planner` → `selector` → `verifier` → `deriver` 순서로 라우팅
3. 매 화면 전환마다 1-2 반복 (새 XML 수신 → 새 그래프 실행)
4. `finish` 액션이 도출되면 태스크 완료

---

## 2.2 Memory Node: 페이지 매칭

> **LLM 사용**: 없음 (임베딩 유사도 기반)
>
> **구현 위치**: `Server/graphs/nodes/memory_node.py`

### 동작 과정

```python
# 1. 현재 화면 XML의 임베딩 계산
embedding = get_openai_embedding(str(parsed_xml))

# 2. 저장된 페이지 임베딩과 코사인 유사도 비교
page_index, similarity = memory.search_node(current_xml, hierarchy_xml, encoded_xml)
# → page_index = 0, similarity = 0.982 (Calendar 홈과 매칭)

# 3. 매칭된 페이지의 subtask 목록 로드
memory.init_page_manager(page_index)
available_subtasks = memory.get_available_subtasks(page_index)
# → [create_new_event, search_events, view_event_details, ...]
```

### 출력 상태

```python
{
    "page_index": 0,
    "available_subtasks": [
        {"name": "create_new_event", "description": "...", "trigger_ui_index": 10, ...},
        {"name": "search_events", "description": "...", "trigger_ui_index": 3, ...},
        {"name": "view_event_details", "description": "...", "trigger_ui_index": 8, ...},
        {"name": "switch_calendar_view", "description": "...", "trigger_ui_index": 4, ...},
        {"name": "navigate_calendar_menu", "description": "...", "trigger_ui_index": 1, ...}
    ],
    "status": "subtasks_loaded",
    "next_agent": "planner"
}
```

---

## 2.3 Planner Node: 4-Step Workflow

> **구현 위치**: `Server/graphs/nodes/planner_node.py`

### Step 1: Load (LLM 없음)

모든 페이지에서 subtask를 수집하고 페이지 요약을 함께 로드합니다.

```python
all_subtasks = _load_all_subtasks_with_context(memory)
# → 전체 4개 페이지에서 15개 subtask 로드

# verify_load() 검증: subtask 1개 이상 존재, 다중 페이지 커버리지 확인
load_result = step_verify_agent.verify_load(all_subtasks, memory)
# → {"status": "pass"}
```

### Step 2: Filter (FilterAgent)

> **프롬프트 출처**: `Server/agents/prompts/filter_agent_prompt.py`
>
> **LLM 모델**: `SELECT_AGENT_GPT_VERSION`

#### System Prompt

<details>
<summary>System Prompt 전문 (클릭하여 펼치기)</summary>

```
You are an expert at understanding user intentions and matching them to available actions. Your task is to select subtasks that are relevant to completing the user's instruction.

***Output Format***:
Return a JSON array of subtask names that are relevant to the instruction.
Example: ["search_emails", "view_email_details", "compose_email"]

***Selection Criteria***:
- Select subtasks directly needed to complete the instruction
- Include navigation subtasks if needed to reach the target
- Consider the page_summary to understand what subtasks are available where
- Order subtasks by relevance (most relevant first)
- Do NOT include subtasks unrelated to the instruction

***Guidelines***:
- If the instruction is about searching, include search-related subtasks
- If the instruction involves multiple steps, include all necessary subtasks
- Consider alternative paths if multiple subtasks achieve similar goals
- Be conservative - only include clearly relevant subtasks
```

</details>

#### User Prompt 예시

```
***User Instruction***:
내일 오후 3시에 팀 미팅 일정 추가해줘

***Available Subtasks***:
[
  {
    "name": "create_new_event",
    "description": "Create a new calendar event by tapping the FAB button...",
    "page_index": 0,
    "page_summary": "This page displays the Google Calendar monthly view..."
  },
  {
    "name": "search_events",
    "description": "Search for specific events by keyword...",
    "page_index": 0,
    "page_summary": "This page displays the Google Calendar monthly view..."
  },
  {
    "name": "edit_event_title",
    "description": "Edit the title field of a calendar event...",
    "page_index": 2,
    "page_summary": "This page shows the event creation form..."
  },
  {
    "name": "set_event_time",
    "description": "Set the start and end time for an event...",
    "page_index": 2,
    "page_summary": "This page shows the event creation form..."
  },
  {
    "name": "set_event_date",
    "description": "Set the date for an event...",
    "page_index": 2,
    "page_summary": "This page shows the event creation form..."
  },
  {
    "name": "save_event",
    "description": "Save the event after filling in details...",
    "page_index": 2,
    "page_summary": "This page shows the event creation form..."
  },
  {
    "name": "open_settings",
    "description": "Open calendar settings...",
    "page_index": 1,
    "page_summary": "This is the navigation drawer..."
  }
]

Select up to 15 subtasks most relevant to the instruction.
Return ONLY a JSON array of subtask names, no explanation:
```

#### LLM 응답 예시

```json
["create_new_event", "edit_event_title", "set_event_time", "set_event_date", "save_event"]
```

#### filtered_names 추출 (Plan 단계 힌트용)

```python
# Filter 결과에서 subtask 이름 추출 → Plan 단계에서 [RELEVANT] 마커로 사용
filtered_names = ["create_new_event", "edit_event_title", "set_event_time", "set_event_date", "save_event"]
```

#### verify_filter() 검증

```python
filter_result = step_verify_agent.verify_filter(instruction, filtered_subtasks, all_subtasks)
# 검증: 필터 결과 비어있지 않음, 제거율 90% 이하
# → {"status": "pass"}
```

### Step 3: Plan (PlannerAgent)

> **프롬프트 출처**: `Server/agents/prompts/planner_agent_prompt.py`
>
> **LLM 모델**: `SELECT_AGENT_GPT_VERSION`

#### Goal Analysis System Prompt

<details>
<summary>System Prompt 전문 (클릭하여 펼치기)</summary>

```
You are a mobile app navigation planner. Your task is to analyze a user instruction and identify which subtasks need to be executed.

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
```

</details>

#### User Prompt 예시

```
User Instruction: 내일 오후 3시에 팀 미팅 일정 추가해줘

Available Subtasks:
- [RELEVANT] create_new_event (page 0): Create a new calendar event by tapping the FAB button...
- search_events (page 0): Search for specific events by keyword...
- view_event_details (page 0): View detailed information about an existing event...
- navigate_calendar_menu (page 0): Open the side menu to access calendar settings...
- [RELEVANT] edit_event_title (page 2): Edit the title field of a calendar event...
- [RELEVANT] set_event_time (page 2): Set the start and end time for an event...
- [RELEVANT] set_event_date (page 2): Set the date for an event...
- [RELEVANT] save_event (page 2): Save the event after filling in details...
- open_settings (page 1): Open calendar settings...

Analyze the instruction and identify which subtasks are needed.
```

> **참고**: `[RELEVANT]` 마커는 Step 2 (Filter)에서 필터링된 subtask에 자동으로 부여됩니다. LLM은 이를 우선 참고하되, 경로상 필요한 미마킹 subtask도 transit으로 포함할 수 있습니다.

#### LLM 응답 예시

```json
{
  "target_subtasks": ["create_new_event", "edit_event_title", "set_event_date", "set_event_time"],
  "final_subtask": "save_event",
  "final_instruction": "Save the newly created event with title '팀 미팅', date set to tomorrow, and time set to 3:00 PM",
  "reasoning": "The user wants to create a new calendar event. We need to: 1) Open the event creation form (create_new_event on page 0 → page 2), 2) Fill in the title, date, and time on page 2, 3) Save the event."
}
```

#### BFS 경로 탐색 (LLM 없음)

```python
# Subtask Graph에서 BFS로 current_page(0) → target_pages를 포함하는 최단 경로 탐색
# Page 0 → (create_new_event) → Page 2 (edit_event_title, set_event_time 등이 있는 페이지)

planned_path = [
    {"page": 0, "subtask": "create_new_event", "trigger_ui_index": 10, "status": "pending", "is_transit": False},
    {"page": 2, "subtask": "edit_event_title", "trigger_ui_index": 0, "status": "pending", "is_transit": False},
    {"page": 2, "subtask": "set_event_date", "trigger_ui_index": 1, "status": "pending", "is_transit": False},
    {"page": 2, "subtask": "set_event_time", "trigger_ui_index": 2, "status": "pending", "is_transit": False},
    {"page": 2, "subtask": "save_event", "trigger_ui_index": 8, "status": "pending", "is_transit": False}
]
# 이 예시에서는 모든 subtask가 필터에 포함되어 transit이 없음.
# 만약 경로상 navigate_calendar_menu 같은 경유 subtask가 필요했다면 is_transit=True로 표시됨.
```

**Transit Subtask 예시** (Settings → Language 변경 시나리오):

```python
# "언어를 영어로 변경해줘" 지시 시:
# - Filter 결과: ["change_language"]
# - BFS 경로: page 0 → (navigate_calendar_menu) → page 1 → (open_settings) → page 4 → change_language
planned_path = [
    {"page": 0, "subtask": "navigate_calendar_menu", ..., "is_transit": True},   # 경유
    {"page": 1, "subtask": "open_settings", ..., "is_transit": True},            # 경유
    {"page": 4, "subtask": "change_language", ..., "is_transit": False}           # 목표
```

#### verify_plan() 검증

```python
plan_result = step_verify_agent.verify_plan(planned_path, memory.subtask_graph, current_page)
# 검증: path 비어있지 않음, 엣지 연결성, 순환 없음
# → {"status": "pass"}
```

---

## 2.4 Selector Node: Subtask 선택

> **프롬프트 출처**: `Server/agents/prompts/select_agent_prompt.py`
>
> **호출 위치**: `Server/graphs/nodes/selector_node.py`
>
> **LLM 모델**: `SELECT_AGENT_GPT_VERSION`
>
> **Vision**: 스크린샷 제공 시 활용

`planned_path`가 존재하면 **경로 기반 선택**을 먼저 시도합니다. 경로의 현재 step에 해당하는 subtask가 available_subtasks에 있으면 그대로 사용합니다.

```python
# planned_path[0] = {"subtask": "create_new_event", ...}
# available_subtasks에 "create_new_event"가 있으므로 바로 선택
selected_subtask = {"name": "create_new_event", "trigger_ui_index": 10, ...}
```

경로에서 찾을 수 없는 경우, LLM 기반 SelectAgent를 사용합니다:

### System Prompt

<details>
<summary>System Prompt 전문 (클릭하여 펼치기)</summary>

```
You are a smartphone assistant to help users use the mobile app. Given a list of actions available on the current mobile screen (delimited by <screen></screen>) and past events that lead to this screen, determine the next action to take in order to complete the user's request.

***Guidelines***:
Follow the below steps step by step:
1. First, read through history of past events (delimited by triple quotes) to grasp the overall flow of the execution.
2. Read through the screen HTML code delimited by <screen></screen> to grasp the overall intent of the current app screen.
3. Select an action that will bring you closer to completing the user's request. If past events indicate that the request has been completed, select 'finish' action. Do not proceed further steps.
4. If you believe the required action is not on the list, you can make a new one.
5. Based on the user's request, screen HTML code, and the QA list, fill in the parameters of the selected action.
6. Self-evaluate how close you are to completing the subtask

***Constraints for selecting an action***:
1. You can perform only a single action at a time.
2. Always select the best matching action. You can make a new one if the required action is not on the list. The new action must be very specific in its purpose, not just 'click' or 'input' something.
3. Always reflect on past events to determine your next action. Avoid repeating the same action.
4. If the action's parameters are not explicitly mentioned anywhere in the prompt, just write 'unknown'. Never assume or guess the parameter's values.

List of available actions:
1. {"name": "create_new_event", "description": "Create a new calendar event...", "parameters": {"event_title": "...", "event_time": "..."}}
2. {"name": "search_events", "description": "Search for specific events...", "parameters": {"search_query": "..."}}
3. {"name": "view_event_details", "description": "View detailed information...", "parameters": {"event_name": "..."}}
4. {"name": "switch_calendar_view", "description": "Change the calendar display mode...", "parameters": {"view_type": "..."}}
5. {"name": "navigate_calendar_menu", "description": "Open the side menu...", "parameters": {}}
6. {"name": "scroll_screen", "description": "Useful when you need to scroll...", "parameters": {"scroll_ui_index": "...", "direction": "...", "target_info": "..."}}
7. {"name": "finish", "description": "Use this to signal that the request has been completed", "parameters": {}}
- If the required action is not on the list, you can make a new one...

Respond using the JSON format described below
Response Format:
{"reasoning": <reasoning based on past events and screen HTML code>, "new_action"(include only when you need to make a new action): {"name": <new action name. This must not be click or input>, "description": <detailed description of the new action>, "parameters": {<parameter_name>: <description of the parameters, including available options>,...}}, "action": {"name":<action_name>, "parameters": {<parameter_name>: <parameter_value, If the parameter values are not explicitly mentioned in the prompt, just write "unknown">,...}}, "completion_rate": <how close you are to completing the task>, "speak": <brief summary of the action in natural language to communicate with the user. Make it short.>}
Begin!
```

</details>

### User Prompt 예시

```
User's Request: 내일 오후 3시에 팀 미팅 일정 추가해줘

QA List:
'''
No QA at this point.
'''

Past Events:
'''
0. No event yet.
'''

HTML code of the current app screen delimited by <screen> </screen>:
<screen>
<hierarchy>
  <node index="0" resource-id="com.google.android.calendar:id/toolbar" ...>
    <node index="1" ... content-desc="메뉴 열기" clickable="true" />
    <node index="2" ... text="2026년 2월" />
    <node index="3" ... content-desc="검색" clickable="true" />
    <node index="4" ... text="월" clickable="true" />
  </node>
  <node index="5" ... scrollable="true">
    <node index="8" ... text="팀 미팅" clickable="true" />
  </node>
  <node index="10" ... content-desc="새 일정 만들기" clickable="true" />
</hierarchy>
</screen>

[A screenshot of the current screen is also provided for visual reference. Use the visual context to better understand the current app state and available options.]

Constructively self-evaluate how close you are to completing the request. If past events indicate that the user's request has been accomplished, You must select the 'finish' action. Do not proceed further steps.

Response:
```

### LLM 응답 예시

```json
{
  "reasoning": "The user wants to add a team meeting event tomorrow at 3 PM. I can see the calendar home screen with a 'new event' button. I should create a new event first.",
  "action": {
    "name": "create_new_event",
    "parameters": {
      "event_title": "팀 미팅",
      "event_date": "내일",
      "event_time": "오후 3시"
    }
  },
  "completion_rate": "10% - Just starting, need to create the event and fill in details",
  "speak": "새 일정 만들기를 시작합니다"
}
```

---

## 2.5 Verifier Node: 경로 검증

> **프롬프트 출처**: `Server/agents/verify_agent.py` (인라인 `VERIFY_SYSTEM_PROMPT`)
>
> **호출 위치**: `Server/graphs/nodes/verifier_node.py`
>
> **LLM 모델**: `VERIFY_AGENT_GPT_VERSION`

### Adaptive Replanning (경로 위치 검증)

`planned_path`가 존재할 때, LLM 검증 전에 먼저 **경로 위치 검증**을 수행합니다:

```python
result = verify_with_path(planned_path, current_step=0, current_page=0)
# planned_path[0]["page"] == 0, current_page == 0
# → decision: "PROCEED" (예상 페이지에 있음)
```

| 결정 | 조건 | 동작 |
|------|------|------|
| **PROCEED** | `current_page == expected_page` | LLM 검증 계속 진행 |
| **SKIP** | `current_page`가 planned_path의 미래 step에 있음 | 해당 step으로 점프 |
| **REPLAN** | `current_page`가 planned_path 어디에도 없음 | `planner_node`로 재계획 |

### LLM 기반 경로 검증

#### System Prompt

<details>
<summary>System Prompt 전문 (클릭하여 펼치기)</summary>

```
You are a mobile app navigation expert. Your task is to verify whether executing a subtask will help achieve the user's instruction.

Given:
1. User's instruction (what they want to achieve)
2. Currently selected subtask
3. Available subtasks on the NEXT screen (after executing the selected subtask)

Decide whether we should proceed with the selected subtask.

Answer "should_proceed": true if:
- The next screen has subtasks that can help achieve the instruction
- The selected subtask is a reasonable step toward the goal
- Going to the next screen brings us closer to completing the instruction

Answer "should_proceed": false if:
- The next screen has no relevant subtasks for the instruction
- The selected subtask leads to a dead end or irrelevant path
- There might be a better subtask on the current screen

Respond in JSON format:
{
    "should_proceed": true/false,
    "reasoning": "Brief explanation of your decision"
}
```

</details>

### User Prompt 예시

```
User Instruction: 내일 오후 3시에 팀 미팅 일정 추가해줘

Selected Subtask: create_new_event
- Description: Create a new calendar event by tapping the FAB button, then filling in event details

Current Screen Subtasks:
- create_new_event: Create a new calendar event...
- search_events: Search for specific events...
- view_event_details: View detailed information...
- switch_calendar_view: Change the calendar display mode...
- navigate_calendar_menu: Open the side menu...

Next Screen Subtasks (after executing selected subtask):
- edit_event_title: Edit the title field of a calendar event
- set_event_time: Set the start and end time for an event
- set_event_date: Set the date for an event
- add_guests: Add guests to the event
- save_event: Save the event after filling in details

Current Page: This page displays the Google Calendar monthly view for February 2026...
Next Page: This page shows the event creation form with fields for title, date, time, and guests...
Should we proceed with the selected subtask?
```

### LLM 응답 예시

```json
{
  "should_proceed": true,
  "reasoning": "The next screen has all the subtasks needed to complete the user's request: edit_event_title for the meeting name, set_event_date for tomorrow, set_event_time for 3 PM, and save_event to confirm. This is the correct path."
}
```

---

## 2.6 Deriver Node: 구체적 액션 도출

> **프롬프트 출처**: `Server/agents/prompts/derive_agent_prompt.py`
>
> **호출 위치**: `Server/graphs/nodes/deriver_node.py` → `DeriveAgent.derive()`
>
> **LLM 모델**: `DERIVE_AGENT_GPT_VERSION`
>
> **Vision**: 스크린샷 제공 시 활용

### System Prompt

<details>
<summary>System Prompt 전문 (클릭하여 펼치기)</summary>

```
You are a smartphone assistant agent that can interact with a mobile app. Your job is to help users use the mobile app by guiding users how to perform specific subtask within their final goal. Given a list of actions available on the current mobile screen (delimited by <screen></screen>) and past events that lead to this screen, determine the next action to take in order to complete the given subtask.

***Guidelines***:
Follow the below steps step by step:
1. First, read through history of past events (delimited by triple quotes) to grasp the overall flow of the task execution.
2. Read through the screen HTML code delimited by <screen></screen> to grasp the overall intent of the current app screen.
3. Select an action that will bring you closer to completing the given subtask. If past events indicate that the task has been completed, select 'finish' action.
4. Self-evaluate how close you are to completing the subtask
5. Plan your next moves

***Hints for understanding the screen HTML code***:
1. Each HTML element represents an UI element on the screen.
2. multiple UI elements can collectively serve a single purpose. Thus, when understanding the purpose of an UI element, looking at its parent or children element will be helpful.

***Hints for selecting the next action***:
1. Always reflect on past events to determine your next action. Avoid repeating the same action.
2. If you need more information to complete the task, use "ask" command to get more information from the user. But be very careful not to ask unnecessarily or repeatedly. If human don't know the answer, do your best to find it out yourself.

***Constraints for selecting an action***:
1. You can perform only single action at a time.
2. Exclusively use the actions listed below.
3. Make sure to select the 'finish' action when past events indicate that the subtask has been completed.
4. Only complete the subtask given to you. The rest is up to the user. Do not proceed further steps.

List of available actions:
1. {"name": "ask", "description": "Ask the user more information to complete the task. Avoid asking unnecessary information or confirmation from the user", "parameters": {"info_name": {"type": "string", "description": "name of the information you need to get from the user (Info Name)"}, "question": {"type": "string", "description": "question to ask the user to get the information"}}}
2. {"name": "click", "description": "Click a specific button on the screen", "parameters": {"index": {"type": "integer", "description": "index of the UI element to be clicked"}}}
3. {"name": "long-click", "description": "Long-click a UI. You can use this only for UIs with long-clickable attribute", "parameters": {"index": {"type": "integer", "description": "index of the UI element to be clicked"}}}
4. {"name": "input", "description": "Input text on the screen.", "parameters": {"index": {"type": "integer", "description": "index of the UI element that takes text input"}, "input_text": {"type": "string", "description": "text or value to input"}}}
5. {"name": "scroll", "description": "Scroll up or down to view more UIs", "parameters": {"index": {"type": "integer", "description": "index of the UI element to scroll."}, "direction": {"type": "string", "description": "direction to scroll, default='down'", "enum": ["up", "down"]}}}
6. {"name": "repeat-click", "description": "Repeat click action multiple times", "parameters": {"index": {"type": "integer", "description": "index of the UI element to clicked."}, "number": {"type": "integer", "description": "number of times you want to click."}}}
7. {"name": "finish", "description": "Use this to signal that you have finished the given subtask.", "parameters": {}}

Make sure to select the 'finish' action when past events indicate that the given subtask has been completed.

Respond using the JSON format described below
Response Format:
{"reasoning": <reasoning based on past events and screen HTML code>, "action": {"name":<action_name>, "parameters": {<parameter_name>: <parameter_value>,...}}, "completion_rate": <indicate how close you are to completing the task>, "plan": <plan for your next moves>}
Begin!
```

</details>

### User Prompt 예시

```
User's final goal (instruction): 내일 오후 3시에 팀 미팅 일정 추가해줘
(Only complete the below subtask given to you. You can ignore parameters with unknown values. But Do not proceed further steps)
Subtask given to you: {"name": "create_new_event", "description": "Create a new calendar event by tapping the FAB button...", "parameters": {"event_title": "팀 미팅", "event_time": "오후 3시"}}
Guideline: Click the floating action button to open the new event creation form.

Past Events:
'''
0. No event yet.

'''

HTML code of the current app screen delimited by <screen> </screen>:
<screen>
<hierarchy>
  <node index="0" resource-id="com.google.android.calendar:id/toolbar" ...>
    <node index="1" ... content-desc="메뉴 열기" clickable="true" />
    <node index="2" ... text="2026년 2월" />
    <node index="3" ... content-desc="검색" clickable="true" />
  </node>
  <node index="5" ... scrollable="true">
    <node index="8" ... text="팀 미팅" clickable="true" />
  </node>
  <node index="10" ... content-desc="새 일정 만들기" clickable="true" />
</hierarchy>
</screen>

[A screenshot of the current screen is also provided for visual reference.]

Response:
```

### LLM 응답 예시

```json
{
  "reasoning": "I need to create a new event. The guideline says to click the floating action button. I can see the FAB with content-desc '새 일정 만들기' at index 10. I should click it to open the event creation form.",
  "action": {
    "name": "click",
    "parameters": {
      "index": 10
    }
  },
  "completion_rate": "20% - About to open the event creation form. Still need to fill in title, date, time, and save.",
  "plan": "1. Click FAB to open event form (current step). 2. Input '팀 미팅' as title. 3. Set date to tomorrow. 4. Set time to 3 PM. 5. Save the event."
}
```

→ 서버가 `{"name": "click", "parameters": {"index": 10}}`을 Android 클라이언트에 전송
→ 클라이언트가 액션 실행 → 새 화면 XML을 서버로 전송 → 다시 TaskGraph 실행...

---

## 2.7 전체 실행 시퀀스 (End-to-End)

"내일 오후 3시에 팀 미팅 일정 추가해줘" 시나리오의 전체 노드 순회 예시:

### Iteration 1: Calendar 홈 (Page 0)

```
┌─ supervisor ─────────────────────────────────────────────────────┐
│ status: initial → next_agent: "memory"                          │
└──────────────────────────────────────────────────────────────────┘
         │
         ▼
┌─ memory ─────────────────────────────────────────────────────────┐
│ search_node() → page_index: 0, similarity: 0.982               │
│ available_subtasks: 5개 로드                                     │
│ → next_agent: "planner"                                         │
└──────────────────────────────────────────────────────────────────┘
         │
         ▼
┌─ planner ────────────────────────────────────────────────────────┐
│ Step 1 (Load): 4개 페이지에서 15개 subtask 로드                  │
│ Step 2 (Filter): 5개로 필터링 → filtered_names 추출              │
│   → [create_new_event, edit_event_title, set_event_date,        │
│      set_event_time, save_event]                                │
│ Step 3 (Plan): 전체 subtask + [RELEVANT] 마커 → BFS 경로        │
│   → 5 steps planned (transit 0개, all relevant)                 │
│ → next_agent: "selector" (via supervisor)                       │
└──────────────────────────────────────────────────────────────────┘
         │
         ▼
┌─ selector ───────────────────────────────────────────────────────┐
│ planned_path[0] = "create_new_event" → available에 존재         │
│ selected_subtask: create_new_event                              │
│ → next_agent: "verifier"                                        │
└──────────────────────────────────────────────────────────────────┘
         │
         ▼
┌─ verifier ───────────────────────────────────────────────────────┐
│ verify_with_path(): PROCEED (page 0 == expected page 0)         │
│ verify_path() LLM: should_proceed = true                       │
│   "Next screen has edit_event_title, set_event_time, etc."      │
│ → next_agent: "deriver"                                         │
└──────────────────────────────────────────────────────────────────┘
         │
         ▼
┌─ deriver ────────────────────────────────────────────────────────┐
│ DeriveAgent.derive() → action: click index 10 (FAB 버튼)       │
│ → action 반환 → END                                            │
└──────────────────────────────────────────────────────────────────┘

→ 서버 → 클라이언트: {"name": "click", "parameters": {"index": 10}}
→ 화면 전환: 일정 생성 폼 (Page 2)
```

### Iteration 2: 일정 생성 폼 (Page 2)

```
┌─ memory ─────────────────────────────────────────────────────────┐
│ search_node() → page_index: 2 (일정 생성 폼)                   │
│ available_subtasks: [edit_event_title, set_event_date,          │
│                      set_event_time, add_guests, save_event]    │
└──────────────────────────────────────────────────────────────────┘
         │
         ▼
┌─ planner ────────────────────────────────────────────────────────┐
│ planned_path 이미 존재 → path_step_index = 1                   │
│ (create_new_event은 completed로 마킹됨)                         │
└──────────────────────────────────────────────────────────────────┘
         │
         ▼
┌─ selector ───────────────────────────────────────────────────────┐
│ planned_path[1] = "edit_event_title" → selected                │
└──────────────────────────────────────────────────────────────────┘
         │
         ▼
┌─ verifier → deriver ─────────────────────────────────────────────┐
│ PROCEED → DeriveAgent:                                          │
│ action: {"name": "input", "parameters":                         │
│   {"index": 0, "input_text": "팀 미팅"}}                        │
└──────────────────────────────────────────────────────────────────┘

→ 서버 → 클라이언트: {"name": "input", "parameters": {"index": 0, "input_text": "팀 미팅"}}
```

### Iteration 3-5: 날짜/시간 설정, 저장

```
Iteration 3: set_event_date
→ action: {"name": "click", "parameters": {"index": 1}}  (날짜 필드)
→ 날짜 피커 열림 → 내일 날짜 선택

Iteration 4: set_event_time
→ action: {"name": "click", "parameters": {"index": 2}}  (시간 필드)
→ 시간 피커 열림 → 오후 3시 설정

Iteration 5: save_event
→ action: {"name": "click", "parameters": {"index": 8}}  (저장 버튼)
→ 일정 저장 완료
```

### Iteration 6: 완료

```
┌─ selector ───────────────────────────────────────────────────────┐
│ planned_path 모든 step 완료                                      │
│ SelectAgent LLM: "Past events show the event was created and    │
│   saved successfully."                                          │
│ selected_subtask: {"name": "finish"}                            │
└──────────────────────────────────────────────────────────────────┘
         │
         ▼
┌─ deriver ────────────────────────────────────────────────────────┐
│ action: {"name": "finish", "parameters": {}}                    │
│ → 태스크 완료                                                    │
└──────────────────────────────────────────────────────────────────┘
```

---

# Part 3: 부록

## 3.1 데이터 스키마

### TaskState 필드 목록

```python
class TaskState(TypedDict, total=False):
    # 세션 정보
    session_id: str                           # 세션 고유 ID
    instruction: str                          # 사용자 지시문

    # 메모리 참조
    memory: Any                               # Memory 인스턴스
    page_index: int                           # 현재 페이지 인덱스
    current_xml: str                          # 현재 화면 XML
    hierarchy_xml: str                        # 계층 구조 XML
    encoded_xml: str                          # 인코딩된 XML

    # Subtask 선택
    selected_subtask: Optional[dict]          # 선택된 subtask
    rejected_subtasks: List[dict]             # 거부된 subtask (재선택용)
    available_subtasks: List[dict]            # 사용 가능한 subtask 목록

    # 검증 결과
    next_page_index: Optional[int]            # 다음 페이지 인덱스
    next_page_subtasks: List[dict]            # 다음 페이지 subtask 목록
    verification_passed: Optional[bool]       # True/False/None

    # 라우팅
    next_agent: str                           # 다음 에이전트

    # 결과
    action: Optional[dict]                    # 도출된 액션
    status: str                               # 상태 문자열
    iteration: int                            # 재선택 루프 카운트

    # 경로 계획
    planned_path: Optional[List[PlannedPathStep]]  # 계획된 경로 (is_transit 포함)
    path_step_index: int                      # 현재 경로 step

    # 적응형 재계획
    expected_page_index: Optional[int]        # 액션 후 예상 페이지
    replan_count: int                         # 재계획 시도 횟수
    replan_needed: bool                       # 재계획 필요 플래그
    max_replan: int                           # 최대 재계획 (기본: 5)

    # Vision 지원
    screenshot_path: Optional[str]            # Vision API용 (None = text-only)

    # 4-Step Workflow
    all_subtasks_list: List[dict]             # Step 1: Load 결과
    filtered_subtasks: List[dict]             # Step 2: Filter 결과
```

### ExploreState 필드 목록

```python
class ExploreState(TypedDict, total=False):
    # 세션 정보
    session_id: str
    app_name: str
    algorithm: Literal["DFS", "BFS", "GREEDY"]

    # 현재 화면
    current_xml: str
    hierarchy_xml: str
    encoded_xml: str
    page_index: int
    screenshot_path: Optional[str]            # Vision API용

    # 탐색 상태
    visited_pages: Set[int]                   # 방문한 페이지
    explored_subtasks: Dict                   # {page: [(name, trigger_ui), ...]}
    exploration_stack: List                    # DFS 스택
    exploration_queue: List                    # BFS 큐
    subtask_graph: Dict                       # Subtask Graph
    back_edges: Dict                          # 뒤로가기 엣지
    unexplored_subtasks: Dict                 # GREEDY용
    traversal_path: List                      # 백트래킹 경로

    # 메모리/에이전트
    memory: Any
    explore_agent: Any

    # 마지막 액션 추적
    last_explored_page_index: Optional[int]
    last_explored_ui_index: Optional[int]
    last_explored_subtask_name: Optional[str]
    last_explored_action: Optional[dict]      # 마지막 탐색 액션
    last_explored_screen: Optional[str]       # 마지막 탐색 화면

    # 액션 히스토리
    action_history: List[dict]                # 서브태스크 탐색 중 누적
    before_xml: Optional[str]                 # 액션 전 XML
    before_screenshot_path: Optional[str]     # 액션 전 스크린샷

    # 라우팅/결과
    next_agent: str
    last_action_was_back: bool                # 마지막 액션이 back이었는지
    action: Optional[dict]
    status: str
    is_new_screen: bool                       # 새 화면 여부
```

### CSV 스키마

**pages.csv**:

| 컬럼 | 타입 | 설명 |
|------|------|------|
| index | int | 페이지 고유 인덱스 |
| available_subtasks | JSON | subtask 이름 배열 |
| trigger_uis | JSON | trigger UI 인덱스 배열 |
| screen | str | XML 시그니처 |
| summary | str | 페이지 요약 |

**subtasks.csv** (페이지별):

| 컬럼 | 타입 | 설명 |
|------|------|------|
| name | str | subtask 이름 |
| description | str | 기능 설명 |
| parameters | JSON | 파라미터 정의 |
| trigger_ui_index | int | 트리거 UI 인덱스 |
| start_page | int | 시작 페이지 |
| end_page | int | 도착 페이지 (-1: 미탐색/외부앱) |
| guideline | str | 수행 지침 (통합 가이던스 포함) |
| example | JSON | 학습된 예시 |

**actions.csv** (페이지별):

| 컬럼 | 타입 | 설명 |
|------|------|------|
| subtask_name | str | 상위 subtask |
| trigger_ui_index | int | 트리거 UI 인덱스 |
| step | int | 시퀀스 번호 |
| action | JSON | 액션 파라미터 |
| description | str | 변경 내용 |
| guideline | str | 시맨틱 의미 |
| start_page | int | 액션 시작 페이지 |
| end_page | int | 액션 후 페이지 |

### subtask_graph.json 구조

```json
{
  "nodes": [0, 1, 2, 3],
  "edges": [
    {
      "from_page": 0,
      "to_page": 2,
      "subtask": "create_new_event",
      "trigger_ui_index": 10,
      "action_sequence": [
        {
          "name": "click",
          "parameters": {"index": 10},
          "description": "Clicked the new event button...",
          "guideline": "Click the FAB to open event form."
        }
      ],
      "explored": true
    }
  ]
}
```

---

## 3.2 에이전트-프롬프트 매핑 테이블

> **구현 형태**: Class = 클래스 인스턴스, Module = 모듈 함수

| 에이전트 | 구현 형태 | 프롬프트 파일 | LLM 모델 환경변수 | Vision | 용도 |
|----------|-----------|-------------|-------------------|--------|------|
| **ExploreAgent** (Step 1) | Class | `prompts/subtask_extraction_prompt.py` | `EXPLORE_AGENT_GPT_VERSION` | O | 화면에서 subtask 추출 |
| **ExploreAgent** (Step 2) | Class | `prompts/trigger_ui_selection_prompt.py` | `EXPLORE_AGENT_GPT_VERSION` | O | 각 subtask의 trigger UI 선택 |
| **summary_agent** | Module | `prompts/summary_agent_prompt.py` | `SUMMARY_AGENT_GPT_VERSION` | O | 페이지 요약 |
| **history_agent** (desc) | Module | `prompts/history_agent_prompt.py` | `HISTORY_AGENT_GPT_VERSION` | O | 액션 설명 (before/after 스크린샷) |
| **history_agent** (guide) | Module | `prompts/history_agent_prompt.py` | `HISTORY_AGENT_GPT_VERSION` | X | 시맨틱 가이던스 |
| **DeriveAgent** (explore) | Class | `prompts/derive_agent_prompt.py` → `get_exploration_prompts()` | `DERIVE_AGENT_GPT_VERSION` | X | Exploration 모드 액션 도출 |
| **filter_agent** | Module | `prompts/filter_agent_prompt.py` | `FILTER_AGENT_GPT_VERSION` | X | 관련 subtask 필터링 |
| **PlannerAgent** | Class | `prompts/planner_agent_prompt.py` | `PLANNER_AGENT_GPT_VERSION` | X | 목표 분석 & 경로 계획 |
| **SelectAgent** | Class | `prompts/select_agent_prompt.py` | `SELECT_AGENT_GPT_VERSION` | O | 다음 subtask 선택 |
| **verify_agent** | Module | `agents/verify_agent.py` (인라인) | `VERIFY_AGENT_GPT_VERSION` | X | 경로 검증 (should_proceed) |
| **DeriveAgent** (task) | Class | `prompts/derive_agent_prompt.py` → `get_prompts()` | `DERIVE_AGENT_GPT_VERSION` | O | 구체적 액션 도출 (7종) |
| **TaskAgent** | Class | `prompts/task_agent_prompt.py` | `TASK_AGENT_GPT_VERSION` | X | 사용자 지시어 분석/태스크 구조화 |
| **app_agent** | Module | `prompts/app_agent_prompt.py` | `APP_AGENT_GPT_VERSION` | X | 앱 패키지 정보 조회/예측 |
| **action_summarize_agent** | Module | `prompts/action_summarize_prompt.py` | `ACTION_SUMMARIZE_AGENT_GPT_VERSION` | X | 액션 히스토리 요약 |
| **param_fill_agent** | Module | `prompts/param_fill_agent_prompt.py` | `PARAMETER_FILLER_AGENT_GPT_VERSION` | X | subtask 파라미터 자동 채우기 |
| **subtask_merge_agent** | Module | `prompts/subtask_merge_prompt.py` | `SUBTASK_MERGE_AGENT_GPT_VERSION` | X | 중복 subtask 병합 |
| **step_verify_agent** | Module | `prompts/step_verify_prompt.py` | *(LLM 미사용, 규칙 기반)* | X | 4-Step 각 단계별 경량 검증 |
| *(node_expand)* | - | `prompts/node_expand_prompt.py` | - | X | 노드 확장 (내부용) |

---

## 3.3 환경 변수

```bash
# ============================================================================
# 핵심 에이전트 모델 (main.py에서 설정)
# ============================================================================
TASK_AGENT_GPT_VERSION=gpt-5.2          # TaskAgent: 지시어 분석/태스크 구조화
EXPLORE_AGENT_GPT_VERSION=gpt-5.2       # ExploreAgent: subtask 추출, trigger UI 선택
SELECT_AGENT_GPT_VERSION=gpt-5.2        # SelectAgent: 다음 subtask 선택
DERIVE_AGENT_GPT_VERSION=gpt-5.2        # DeriveAgent: 구체적 액션 도출
VERIFY_AGENT_GPT_VERSION=gpt-5.2        # verify_agent: 경로 검증 (should_proceed)
APP_AGENT_GPT_VERSION=gpt-5.2           # app_agent: 앱 패키지 정보 조회

# ============================================================================
# 모듈 함수 에이전트 모델
# ============================================================================
FILTER_AGENT_GPT_VERSION=gpt-5.2        # filter_agent: 관련 subtask 필터링
PLANNER_AGENT_GPT_VERSION=gpt-5.2       # PlannerAgent: 목표 분석 & 경로 계획
HISTORY_AGENT_GPT_VERSION=gpt-5.2       # history_agent: 액션 설명/가이던스 생성
SUMMARY_AGENT_GPT_VERSION=gpt-5.2       # summary_agent: 페이지 요약 생성

# ============================================================================
# 레거시/미사용 (main.py에 설정되나 코드에서 직접 참조하지 않음)
# ============================================================================
SELECT_AGENT_HISTORY_GPT_VERSION=gpt-5.2    # (미사용)
GUIDELINE_AGENT_GPT_VERSION=gpt-5.2         # (미사용 - guideline_agent 제거됨)

# ============================================================================
# API 및 서버 설정
# ============================================================================
OPENAI_API_KEY=your-api-key             # 필수
HOST=0.0.0.0                            # 서버 바인드 주소 (기본값)
PORT=12345                              # 서버 포트 (기본값)
```
