# PRD: MobileGPT-V2

> **Version**: 1.0.0
> **Last Updated**: 2026-03-15
> **Status**: Implemented
> **Upstream**: MobileGPT V1 (연구 논문 구현체)

---

## 1. 개요

### 1.1 프로젝트 요약

**MobileGPT-V2**는 LangGraph 기반 멀티 에이전트 파이프라인으로 Android 기기의 UI를 자율 탐색·학습하고, 자연어 명령을 실행 가능한 액션 시퀀스로 변환하는 모바일 자동화 프레임워크다.

### 1.2 핵심 가치

| 기존 방식 | 문제 | MobileGPT-V2 |
|-----------|------|--------------|
| 수동 스크립트 자동화 (Appium 등) | UI 변경 시 깨짐, 앱별 재작성 필요 | Subtask Graph로 UI 구조를 학습하여 범용 적용 |
| 단일 LLM 에이전트 | 긴 작업에서 맥락 손실, 비효율적 API 호출 | 7개 전문 에이전트 분업 + 메모리 시스템으로 호출 최소화 |
| 정적 실행 계획 | 예상치 못한 화면 전환 시 실패 | 적응형 재계획(Adaptive Replanning)으로 동적 경로 조정 |
| 사전 정의된 태스크만 실행 | 새 앱/기능 지원 불가 | Auto-Explore로 미지의 앱 UI를 자율 학습 |

### 1.3 기술적 차별점

**V1 → V2 주요 변경:**

- **LangGraph 도입**: 선형 파이프라인 → StateGraph 기반 조건부 라우팅, 체크포인터 지원
- **Subtask Graph**: 페이지 간 네비게이션 구조를 그래프로 구축, BFS 경로 탐색
- **4-Step Workflow**: Load → Filter → Plan → Execute/Replan (각 단계 검증 포함)
- **Auto-Explore**: DFS/BFS/GREEDY 3가지 알고리즘으로 앱 UI 자율 학습
- **Vision API 통합**: 스크린샷 기반 UI 인식으로 XML만으로는 판단 어려운 요소 보완
- **2-Layer 검증**: 규칙 기반 경량 검증 + LLM 기반 경로 검증
- **시맨틱 메모리**: 페이지 요약, 액션 설명, 가이드라인을 Subtask Graph에 부착

---

## 2. 시스템 아키텍처

### 2.1 계층 구조

```
┌─────────────────────────────────────────────────────────────────┐
│                        MobileGPT-V2                             │
│                                                                 │
│  ┌─────────────────────┐   TCP Socket   ┌────────────────────┐ │
│  │   Android Client    │◄──────────────►│   Python Server    │ │
│  │   (Java, API 33+)   │  Binary/JSON   │   (LangGraph)      │ │
│  │                     │                │                    │ │
│  │  ┌───────────────┐  │                │  ┌──────────────┐  │ │
│  │  │ Task Mode     │  │                │  │ Task Graph   │  │ │
│  │  │ (App/)        │  │                │  │ (6 nodes)    │  │ │
│  │  ├───────────────┤  │                │  ├──────────────┤  │ │
│  │  │ Explore Mode  │  │                │  │ Explore Graph│  │ │
│  │  │ (App_Auto_    │  │                │  │ (3 nodes)    │  │ │
│  │  │  Explorer/)   │  │                │  ├──────────────┤  │ │
│  │  └───────────────┘  │                │  │ Memory System│  │ │
│  │                     │                │  │ (CSV + JSON) │  │ │
│  └─────────────────────┘                │  └──────────────┘  │ │
│                                         │                    │ │
│                                         │  ┌──────────────┐  │ │
│                                         │  │ OpenAI API   │  │ │
│                                         │  │ (GPT-5.2)    │  │ │
│                                         │  └──────────────┘  │ │
│                                         └────────────────────┘ │
└─────────────────────────────────────────────────────────────────┘
```

### 2.2 데이터 흐름

```
[사용자 명령] "알람을 오전 7시로 설정해줘"
    │
    ▼ TaskAgent: 명령 분석
[Task] {name: "set_alarm", params: {time: "7:00 AM"}}
    │
    ▼ AppAgent: 대상 앱 예측
[App] "com.google.android.deskclock"
    │
    ▼ Android Client: 앱 실행 → XML/Screenshot 전송
[Screen Data] parsed XML + screenshot
    │
    ▼ Task Graph Pipeline (반복)
    ┌──────────────────────────────────────────────────┐
    │ Memory → Planner → Selector → Verifier → Deriver│
    │    ↑         │                    │              │
    │    └─────────┴──── Replan ────────┘              │
    └──────────────────────────────────────────────────┘
    │
    ▼ DeriveAgent: 구체적 액션 도출
[Action] {action: "click", index: 5, description: "7시 선택"}
    │
    ▼ Android Client: 액션 실행 → 다음 화면 전송
[반복] 작업 완료까지
```

### 2.3 핵심 컴포넌트

| 컴포넌트 | 역할 | 기술 스택 |
|----------|------|----------|
| Task Graph | 명령 실행 파이프라인 (6 노드) | LangGraph StateGraph |
| Explore Graph | 앱 UI 자율 탐색 (3 노드) | LangGraph StateGraph |
| Class Agents (7) | ExploreAgent, PlannerAgent, SelectAgent, DeriveAgent, TaskAgent, AppAgent, Memory | OpenAI GPT-5.2 |
| Module Functions (5) | history_agent, summary_agent, filter_agent, step_verify_agent, verify_agent | OpenAI GPT-5.2 |
| Memory System | Subtask Graph, CSV 데이터베이스, 임베딩 검색 | pandas, numpy, JSON |
| Screen Parser | Android XML → HTML-like 시맨틱 변환 | XML ElementTree |
| Message Handler | TCP 바이너리/텍스트 프로토콜 처리 | Python socket |
| Android Client | AccessibilityService 기반 UI 제어 | Java, Android API 33 |

---

## 3. 서버 상세

### 3.1 진입점 — `Server/main.py`

```
함수:
  main():
    1. ArgumentParser로 CLI 인자 파싱
    2. 환경변수에서 에이전트별 GPT 모델 버전 설정 (10개)
    3. --mode에 따라 Server 또는 AutoExplorer 인스턴스 생성
    4. server.open() 호출

설정:
  TASK_AGENT_GPT_VERSION = "gpt-5.2"
  APP_AGENT_GPT_VERSION = "gpt-5.2"
  EXPLORE_AGENT_GPT_VERSION = "gpt-5.2"
  SELECT_AGENT_GPT_VERSION = "gpt-5.2"
  DERIVE_AGENT_GPT_VERSION = "gpt-5.2"
  VERIFY_AGENT_GPT_VERSION = "gpt-5.2"
  FILTER_AGENT_GPT_VERSION = "gpt-5.2"
  HISTORY_AGENT_GPT_VERSION = "gpt-5.2"
  PLANNER_AGENT_GPT_VERSION = "gpt-5.2"
  SUMMARY_AGENT_GPT_VERSION = "gpt-5.2"
```

### 3.2 Task 서버 — `Server/server.py`

```
클래스: Server

  속성:
    host: str = "0.0.0.0"
    port: int = 12345
    buffer_size: int = 4096
    memory_directory: str = "./memory"
    vision_enabled: bool = True

  메서드:
    open() → None
      서버 소켓 열고 클라이언트 연결 대기, 스레드별 처리

    handle_client(client_socket, client_address) → None
      메시지 타입(L/I/S/X/A)에 따라 분기 처리

    _handle_instruction(client_socket, task_agent, app_agent, screen_parser) → tuple
      사용자 명령 수신 → TaskAgent 분석 → AppAgent 앱 예측 → 앱 실행 요청
      반환: (log_directory, memory, instruction, session_id)

    _handle_xml(client_socket, memory, instruction, screen_parser, ...) → int
      XML 수신 → 파싱 → Task Graph 실행 → 액션 응답
      반환: 업데이트된 screen_count
```

### 3.3 Auto-Explore 서버 — `Server/server_auto_explore.py`

```
클래스: AutoExplorer

  속성:
    host: str = "0.0.0.0"
    port: int = 12345
    buffer_size: int = 4096
    memory_directory: str = "./memory"
    algorithm: str = "DFS"
    vision_enabled: bool = True

  메서드:
    open() → None
      탐색 서버 시작

    handle_client(client_socket, client_address) → None
      탐색 클라이언트 처리 (APP_PACKAGE/XML/SCREENSHOT/FINISH)

    _handle_app_init(client_socket, app_agent, screen_parser) → tuple
      앱 패키지 수신 → 탐색 세션 초기화
      반환: (log_directory, memory, explore_agent, app_name, session_id)

    _handle_xml_exploration(client_socket, ..., session_state) → int | None
      XML 수신 → Explore Graph 실행 → 탐색 액션 반환
      세션 상태를 session_state dict에 지속

    _record_external_app_subtask(memory, page_index, ...) → None
      외부 앱 전환 시 subtask 기록

    _handle_external_app_cleanup(memory, session_id, external_info) → None
      외부 앱 감지 시 정리
```

### 3.4 서버 설정

```
ServerConfig:
  host: str = "0.0.0.0"
  port: int = 12345               # CLI --port로 변경 가능
  buffer_size: int = 4096         # TCP 수신 버퍼
  memory_directory: str = "./memory"
  vision_enabled: bool = True     # CLI --vision/--no-vision

환경변수:
  OPENAI_API_KEY: str             # 필수
  GOOGLESEARCH_KEY: str           # 앱 정보 조회용
  *_GPT_VERSION: str              # 에이전트별 모델 버전 (10개)
```

---

## 4. 클라이언트 상세

### 4.1 아키텍처

Android AccessibilityService 기반 클라이언트로, 두 가지 모드를 별도 앱으로 제공한다.

- **App/** (Task Mode): 사용자 명령을 받아 서버와 통신하며 액션 실행
- **App_Auto_Explorer/** (Explore Mode): 서버의 탐색 명령에 따라 앱 UI를 자동 탐색

### 4.2 컴포넌트

**App/ (Task Mode)**

```
app/src/main/java/com/example/mobilegpt/
├── MobileGPTGlobal.java              # 싱글톤 설정 (HOST_IP, PORT, 액션 목록)
├── MobileGPTAccessibilityService.java # 접근성 서비스 메인 (이벤트/액션/화면 수집)
├── MobileGPTClient.java              # TCP 소켓 통신 (메시지 송수신)
├── MainActivity.java                 # UI (instruction 입력, 권한 요청)
├── MobileGPTSpeechRecognizer.java    # 음성 인식/합성 (TTS/STT)
├── InputDispatcher.java              # 터치 입력 실행 (click, long-click, input, scroll, back)
├── AccessibilityNodeInfoDumper.java  # UI 요소 → XML 직렬화 (인덱싱)
├── AccessibilityNodeInfoHelper.java  # UI 요소 정보 추출 유틸리티
├── GPTMessage.java                   # 서버 응답 JSON 파싱
├── AskPopUp.java                     # 사용자 질문 팝업 UI
└── Utils.java                        # 공통 유틸리티
```

**App_Auto_Explorer/ (Explore Mode)**

```
app/src/main/java/com/example/mobilegptexplorer/
├── MobileGPTAccessibilityService.java # 탐색 모드 접근성 서비스 (floating button 제어)
├── MobileGPTClient.java              # TCP 통신 (탐색 프로토콜)
├── MobileGPTGlobal.java              # 설정 관리
├── MainActivity.java                 # 탐색 UI
├── FloatingButtonManager.java        # 부동 제어 버튼 (시작/중지)
├── InputDispatcher.java              # 터치 입력 실행
├── AccessibilityNodeInfoDumper.java  # XML 직렬화
├── AccessibilityNodeInfoHelper.java  # UI 추출
├── GPTMessage.java                   # JSON 파싱
└── Utils.java                        # 공통 유틸리티
```

### 4.3 통신 프로토콜

TCP 바이너리 프로토콜로 첫 바이트가 메시지 타입을 결정한다.

| 타입 코드 | 방향 | 이름 | 페이로드 |
|-----------|------|------|---------|
| `L` | Client → Server | App List | 줄바꿈 구분 패키지 목록 |
| `I` | Client → Server | Instruction | 줄바꿈 종단 텍스트 |
| `S` | Client → Server | Screenshot | 4바이트 크기 + JPEG 바이너리 |
| `X` | Client → Server | XML | 줄바꿈 종단 XML 문자열 |
| `A` | Client → Server | App Package | 줄바꿈 종단 패키지명 |
| `E` | Client → Server | External App | 외부 앱 전환 감지 |
| `F` | Client → Server | Finish | 탐색 완료 신호 |
| JSON | Server → Client | Action | `\r\n` 종단 JSON 응답 |

### 4.4 빌드

```
플랫폼: Android 13+ (API 33)
빌드: Gradle
언어: Java
권한: AccessibilityService, SYSTEM_ALERT_WINDOW (Explore 모드)
설정: MobileGPTGlobal.java
  HOST_IP = "192.168.0.12"
  HOST_PORT = 12345
  AVAILABLE_ACTIONS = ["click", "input", "scroll", "long-click", "go-back"]
```

---

## 5. 파이프라인/오케스트레이터

### 5.1 Task Graph

```
                    ┌──────────┐
                    │  START   │
                    └────┬─────┘
                         │
                    ┌────▼─────┐
              ┌─────┤Supervisor├─────┐
              │     └────┬─────┘     │
              │          │           │
         ┌────▼───┐ ┌───▼────┐ ┌───▼────┐
         │ Memory │ │Planner │ │Selector│
         └────┬───┘ └───┬────┘ └───┬────┘
              │          │          │
              └──────────┴──────────┘
                         │
                    ┌────▼─────┐
                    │Supervisor│
                    └────┬─────┘
                         │
                    ┌────▼─────┐
                    │ Verifier │───── REPLAN ──→ Planner
                    └────┬─────┘
                         │ PASS
                    ┌────▼─────┐
                    │ Deriver  │
                    └────┬─────┘
                         │
                    ┌────▼─────┐
                    │   END    │
                    └──────────┘
```

**6개 노드:**

| 노드 | 역할 |
|------|------|
| supervisor | 상태 기반 조건부 라우팅 (MAX_ITERATIONS = 5) |
| memory | 현재 화면 매칭 → 사용 가능한 subtask 로드 |
| planner | 4-Step Workflow: Load → Filter → Plan → Execute |
| selector | planned_path에서 subtask 선택 또는 LLM 직접 선택 |
| verifier | 선택된 subtask 검증 (PROCEED/SKIP/REPLAN) |
| deriver | 구체적 액션 도출 (click, input, scroll 등) |

### 5.2 Explore Graph

```
              ┌──────────┐
              │  START   │
              └────┬─────┘
                   │
              ┌────▼─────┐
        ┌─────┤Supervisor├─────┐
        │     └──────────┘     │
        │                      │
   ┌────▼────┐          ┌─────▼──────┐
   │Discover │          │ExploreAction│
   └────┬────┘          └─────┬──────┘
        │                     │
        └──────────┬──────────┘
                   │
              ┌────▼─────┐
              │ END/FINISH│
              └──────────┘
```

**3개 노드:**

| 노드 | 역할 |
|------|------|
| supervisor | 화면 상태에 따라 discover/explore_action/END 라우팅 |
| discover | 새 화면 학습: subtask 추출 + trigger UI 매핑 + 페이지 요약 |
| explore_action | DFS/BFS/GREEDY 알고리즘으로 다음 탐색 대상 결정 + 액션 실행 |

### 5.3 4-Step Workflow (Planner)

```
Step 1: LOAD          Step 2: FILTER       Step 3: PLAN          Step 4: EXECUTE
모든 페이지에서   →   instruction에     →  Subtask Graph     →   Selector가
탐색된 subtask        관련된 subtask        위에서 BFS로           planned_path
로드 (+ 요약)         15개 필터링           최단 경로 생성          순서대로 실행
     │                     │                    │                      │
     ▼                     ▼                    ▼                      ▼
verify_load()        verify_filter()      verify_plan()         verify_with_path()
(규칙 기반)          (규칙 + LLM)         (규칙 기반)           (적응형 재계획)
```

---

## 6. 모듈 상세 요구사항

### 6.1 에이전트: `Server/agents/`

#### 6.1.1 목적

사용자 명령을 이해하고, 적절한 앱·화면·subtask를 선택하며, 구체적인 UI 액션을 도출하는 전문 에이전트 집합.

#### 6.1.2 파일 구성

```
Server/agents/
├── task_agent.py          # 사용자 명령 분석 및 Task 매칭
├── app_agent.py           # 대상 앱 예측 (임베딩 유사도)
├── explore_agent.py       # 화면 탐색 (subtask 추출 + trigger UI)
├── planner_agent.py       # Subtask Graph 위 BFS 경로 계획
├── select_agent.py        # 현재 화면에서 subtask 선택
├── derive_agent.py        # 구체적 UI 액션 도출
├── verify_agent.py        # 경로 검증 (PROCEED/SKIP/REPLAN)
├── filter_agent.py        # instruction 관련 subtask 필터링
├── history_agent.py       # 액션 전후 변화 설명 생성
├── summary_agent.py       # 페이지 목적 요약
├── step_verify_agent.py   # 4-Step 각 단계 검증
└── prompts/               # 프롬프트 템플릿 (12개)
```

#### 6.1.3 Class Agents Pseudo-Spec

**`task_agent.py`**

```
클래스: TaskAgent

  속성:
    tasks: DataFrame          # CSV 기반 태스크 데이터베이스 (./memory/tasks.csv)

  메서드:
    get_task(instruction: str) → (dict, bool)
      사용자 명령을 분석하여 기존 Task 매칭 또는 신규 생성
      반환: (task_dict, is_new)

    update_task(task: dict) → None
      기존 Task의 description/parameters 업데이트
```

**`app_agent.py`**

```
클래스: AppAgent

  속성:
    apps: DataFrame           # CSV 기반 앱 데이터베이스 (./memory/apps.csv)

  메서드:
    update_app_list(new_packages: list) → None
      새 패키지를 DB에 추가, Google Play에서 앱 정보 조회

    predict_app(instruction: str) → str
      임베딩 유사도로 후보 5개 선정 → LLM이 최종 앱 결정

    get_package_name(app: str) → str
      앱 이름으로 패키지명 조회

    get_app_name(package_name: str) → str
      패키지명으로 앱 이름 조회

독립 함수:
  get_package_info(package_name: str) → (str, str)
    Google Play Store에서 앱 이름/설명 조회
```

**`explore_agent.py`**

```
클래스: ExploreAgent

  속성:
    memory: Memory            # 메모리 매니저 참조

  메서드:
    explore(parsed_xml, hierarchy_xml, html_xml, screen_num, screenshot_path) → int
      2-Phase 탐색:
      1. Subtask 추출: 화면에서 고수준 subtask 식별 (Vision API)
      2. Trigger UI 선택: 각 subtask의 진입점 UI 요소 매핑
      반환: page_index
```

**`planner_agent.py`**

```
클래스: PlannerAgent

  속성:
    instruction: str          # 사용자 명령

  메서드:
    plan(current_page, subtask_graph, all_subtasks, filtered_names) → Optional[List[dict]]
      Subtask Graph 위 BFS로 최적 경로 생성:
      1. _analyze_goal(): LLM으로 target subtask 식별
      2. _find_target_pages(): 목표 페이지 탐색
      3. _bfs_find_path(): BFS 최단 경로
      4. _build_planned_path(): PlannedPathStep 리스트 생성
      반환: planned_path 또는 None (경로 없음)

독립 함수:
  replan_from_current(state) → dict
    예상치 못한 페이지 전환 시 현재 위치에서 재계획
```

**`select_agent.py`**

```
클래스: SelectAgent

  속성:
    memory: Memory
    instruction: str

  메서드:
    select(available_subtasks, subtask_history, qa_history, screen, screenshot_path) → (dict, dict)
      현재 화면에서 최적 subtask 선택 (retry 로직 포함)
      기본 액션: scroll_screen, finish, speak
      반환: (selected_subtask, example)
```

**`derive_agent.py`**

```
클래스: DeriveAgent

  속성:
    memory: Memory
    instruction: str

  메서드:
    init_subtask(subtask, subtask_history) → None
      새 subtask 실행을 위한 초기화

    derive(screen, examples, screenshot_path) → (dict, dict)
      현재 화면에서 구체적 UI 액션 도출
      액션 유형: click, long-click, input, scroll, repeat-click, ask, finish
      반환: (action_dict, example)
```

**`verify_agent.py`**

```
클래스:
  VerifyDecision(BaseModel)
    should_proceed: bool
    reasoning: str

  PathVerificationResult
    PROCEED = "proceed"
    SKIP = "skip"
    REPLAN = "replan"

독립 함수:
  verify_path(instruction, selected_subtask, current_subtasks,
              next_subtasks, current_summary, next_summary) → (bool, str)
    선택된 subtask의 경로 유효성을 LLM으로 검증
    반환: (should_proceed, reasoning)

  verify_with_path(planned_path, current_step, current_page) → dict
    적응형 재계획: 현재 위치 vs 예상 위치 비교
    반환: {result: PROCEED|SKIP|REPLAN, ...}
```

#### 6.1.4 Module Function Agents Pseudo-Spec

**`filter_agent.py`**

```
독립 함수:
  filter_subtasks(instruction, all_subtasks, max_results=15) → List[dict]
    4-Step Workflow Step 2: instruction에 관련된 subtask만 필터링
    최대 15개 반환
```

**`history_agent.py`**

```
독립 함수:
  generate_description(before_xml, after_xml, action,
                       before_screenshot_path, after_screenshot_path) → str
    액션 전후 화면 비교 → WHY+WHAT 설명 생성 (최대 50단어)

  generate_guidance(action, screen_xml) → str
    액션의 HOW-to 가이드라인 생성 (최대 30단어)
```

**`summary_agent.py`**

```
독립 함수:
  generate_summary(encoded_xml, available_subtasks, screenshot_path) → str
    페이지 목적 요약 (2-3문장, 최대 100단어)
    "이 페이지는 무엇을 보여주며 어떤 작업을 할 수 있는가"
```

**`step_verify_agent.py`**

```
상수:
  StepVerifyResult.PASS = "pass"
  StepVerifyResult.WARN = "warn"
  StepVerifyResult.FAIL = "fail"

독립 함수:
  verify_load(all_subtasks, memory) → dict
    Step 1 검증: 최소 1개 subtask, 2+ 페이지

  verify_filter(instruction, filtered, all_subtasks) → dict
    Step 2 검증: 1+ 필터 통과, 제거율 > 90% 시 WARN

  verify_plan(planned_path, subtask_graph, current_page) → dict
    Step 3 검증: 경로 유효성, 시작 페이지 일치, 순환 없음
```

### 6.2 프롬프트 템플릿: `Server/agents/prompts/`

#### 6.2.1 파일 구성

```
Server/agents/prompts/
├── task_agent_prompt.py            # P-02: 명령 → Task 매칭
├── app_agent_prompt.py             # P-01: 앱 예측
├── filter_agent_prompt.py          # P-03: subtask 필터링
├── planner_agent_prompt.py         # P-04: Goal Analysis
├── select_agent_prompt.py          # P-05: subtask 선택 (Vision)
├── derive_agent_prompt.py          # P-07: 액션 도출 (Vision)
├── subtask_extraction_prompt.py    # P-11: 화면 subtask 추출 (Vision)
├── trigger_ui_selection_prompt.py  # P-12: trigger UI 매핑 (Vision)
├── history_agent_prompt.py         # P-12: 액션 변화 설명
├── summary_agent_prompt.py         # P-13: 페이지 요약
├── step_verify_prompt.py           # (비활성) LLM 필터 검증
└── node_expand_prompt.py           # (레거시) UI 액션 추출
```

#### 6.2.2 안전 가드레일

`subtask_extraction_prompt.py`에 정의된 5가지 위험 카테고리:

| 카테고리 | 설명 | 예시 |
|----------|------|------|
| communication | 메시지/전화 발신 | SMS 전송, 전화 걸기 |
| data | 데이터 삭제/수정 | 파일 삭제, 연락처 수정 |
| financial | 금전 거래 | 결제, 송금 |
| system | 시스템 설정 변경 | 초기화, 권한 변경 |
| privacy | 개인정보 접근 | 위치 공유, 사진 접근 |

unsafe로 분류된 subtask는 탐색 시 자동 필터링된다.

### 6.3 그래프 노드: `Server/graphs/nodes/`

#### 6.3.1 파일 구성

```
Server/graphs/nodes/
├── supervisor.py           # Task Graph 라우팅 (상태 기반 조건부)
├── memory_node.py          # 화면 매칭 + subtask 로드
├── planner_node.py         # 4-Step Workflow 실행
├── selector_node.py        # subtask 선택 (planned_path 우선)
├── verifier_node.py        # 2-Layer 검증
├── deriver_node.py         # 액션 도출 (메모리 우선, LLM fallback)
├── explore_supervisor.py   # Explore Graph 라우팅
├── discover_node.py        # 화면 학습 + Subtask Graph 갱신
└── explore_action_node.py  # 탐색 알고리즘 (DFS/BFS/GREEDY)
```

#### 6.3.2 Supervisor 라우팅 로직

```
supervisor_node(state: TaskState) → dict:

  종료 조건 (→ FINISH):
    - no_matching_page, no_subtasks, no_available_subtask
    - action_derived, no_subtask_to_verify, no_subtask_for_derive
    - max_replan_reached

  재계획 (→ planner):
    - replan_needed = True && replan_count < max_replan (5)

  검증 통과 (→ deriver):
    - verification_passed = True

  검증 실패 (→ selector):
    - verification_passed = False (rejected_subtasks에 추가)

  선택됨 (→ verifier):
    - selected_subtask 존재 && 미검증

  초기 (→ memory):
    - 아직 아무것도 없는 상태
```

### 6.4 메모리 시스템: `Server/memory/`

#### 6.4.1 목적

앱 UI 구조를 Subtask Graph로 지속적으로 학습하고, 학습된 지식을 재활용하여 LLM 호출을 최소화한다.

#### 6.4.2 파일 구성

```
Server/memory/
├── memory_manager.py    # Memory 클래스 (중앙 메모리 관리)
├── page_manager.py      # PageManager 클래스 (페이지별 CSV 관리)
└── node_manager.py      # NodeManager 클래스 (화면 매칭 알고리즘)
```

#### 6.4.3 Pseudo-Spec

**`memory_manager.py`**

```
클래스: Memory

  속성:
    app_name: str
    memory_path: str              # ./memory/{app_name}/
    subtask_graph: dict           # {nodes: [], edges: []}
    pages: DataFrame              # pages.csv
    page_managers: dict           # {page_index: PageManager}

  메서드:
    init_database() → None
      CSV 데이터베이스 생성/로드 (pages.csv)

    _load_subtask_graph() → dict
      subtask_graph.json 로드 또는 기존 CSV에서 재구축

    _build_subtask_graph() → dict
      pages.csv + subtasks.csv에서 Subtask Graph 재구성

    add_transition(from_page, to_page, subtask, trigger_ui_index, action_sequence) → None
      Subtask Graph에 네비게이션 엣지 추가

    get_path_to_page(from_page, to_page) → Optional[List[dict]]
      BFS 최단 경로 탐색

    get_all_explored_subtasks() → List[dict]
      모든 페이지의 탐색 완료된 subtask 수집 (페이지 요약 포함)

    search_node(encoded_xml, hierarchy_xml) → (int, str)
      임베딩 유사도로 기존 페이지 매칭
      반환: (page_index, match_type)

    add_node(screen, trigger_uis, extra_uis, subtask_names) → int
      새 페이지 등록, page_index 반환

    update_node(page_index, trigger_uis, extra_uis, subtask_names) → None
      기존 페이지에 새 subtask 정보 병합

    get_available_subtasks(page_index) → List[dict]
      현재 페이지의 사용 가능한 subtask 로드 (가이드라인 포함)

    get_subtask_destination(page_index, subtask_name) → Optional[int]
      subtask 실행 후 도달하는 page_index 조회

    update_page_summary(page_index, summary) → None
      페이지 시맨틱 요약 저장

    save_action_history(page_index, subtask_name, actions) → None
      액션 히스토리 일괄 저장 (설명/가이드라인 포함)

    mark_subtask_explored(page_index, subtask_name, ...) → None
      단일 스텝 subtask 탐색 완료 등록

    mark_subtask_explored_multistep(page_index, subtask_name, ...) → None
      다단계 subtask 탐색 완료 등록 (액션 시퀀스 포함)
```

**`page_manager.py`**

```
클래스: PageManager

  속성:
    page_path: str                # ./memory/{app}/page_{N}/
    subtasks: DataFrame           # subtasks.csv
    actions: DataFrame            # actions.csv
    available_subtasks: DataFrame # available_subtasks.csv

  메서드:
    get_available_subtasks() → List[dict]
      subtasks와 available_subtasks를 병합하여 가이드라인 포함 반환

    mark_subtask_explored(subtask_name, trigger_ui_index, end_page) → None
      단일 스텝 탐색 완료 등록

    mark_subtask_explored_multistep(subtask_name, ..., action_sequence) → None
      다단계 탐색 완료 등록

    save_subtask(subtask_name, guideline, start_page, end_page) → None
      subtask 등록

    save_action(subtask_name, step, action, description, guideline) → None
      액션 등록

    get_next_action(subtask_name, step, current_xml) → Optional[dict]
      메모리에서 학습된 액션 조회 → 현재 화면에 적응

    delete_subtask_data(subtask_name) → None
      모든 CSV에서 해당 subtask 데이터 삭제
```

**`node_manager.py`**

```
클래스: NodeManager

  매칭 임계값: 70%

  매칭 결과:
    EQSET   = 100% 일치, 추가 UI 없음
    SUBSET  = >70% 일치, 추가 UI 없음 (현재가 저장의 부분집합)
    SUPERSET = >70% 일치, 추가 UI 있음 (현재가 저장의 상위집합)
    NEW     = 매칭 실패

  메서드:
    search(page_candidates, current_trigger_uis, current_extra_uis) → (int, str)
      후보 페이지에서 최적 매칭 탐색
      반환: (page_index, match_type)
```

#### 6.4.4 Subtask Graph 데이터 스키마

**subtask_graph.json**

```json
{
  "nodes": [0, 1, 2],
  "edges": [
    {
      "from_page": 0,
      "to_page": 1,
      "subtask": "open_settings",
      "trigger_ui_index": 5,
      "action_sequence": [
        {"action": "click", "index": 5}
      ],
      "explored": true
    }
  ]
}
```

**pages.csv**

| 컬럼 | 타입 | 설명 |
|------|------|------|
| index | int | 페이지 고유 번호 |
| available_subtasks | str (JSON) | 사용 가능한 subtask 이름 목록 |
| trigger_uis | str (JSON) | 트리거 UI 인덱스 목록 |
| screen | str (JSON) | 화면 XML 메타데이터 |
| summary | str | 페이지 시맨틱 요약 |

**subtasks.csv** (페이지별)

| 컬럼 | 타입 | 설명 |
|------|------|------|
| name | str | subtask 이름 |
| description | str | subtask 설명 |
| guideline | str | 실행 가이드라인 (액션 가이드라인 집합) |
| trigger_ui_index | int | 진입점 UI 인덱스 |
| start_page | int | 시작 페이지 |
| end_page | int | 도착 페이지 |

**actions.csv** (페이지별)

| 컬럼 | 타입 | 설명 |
|------|------|------|
| subtask_name | str | 소속 subtask |
| step | int | 액션 순서 |
| action | str (JSON) | 액션 상세 (type, index, params) |
| description | str | WHY+WHAT 변화 설명 |
| guideline | str | HOW-to 실행 가이드 |
| start_page | int | 액션 시작 페이지 |
| end_page | int | 액션 종료 페이지 |

### 6.5 화면 파서: `Server/screenParser/`

#### 6.5.1 목적

Android AccessibilityService의 원시 XML을 LLM이 이해할 수 있는 시맨틱 HTML-like 형식으로 변환한다.

#### 6.5.2 파일 구성

```
Server/screenParser/
├── Encoder.py     # xmlEncoder 클래스 (파이프라인 오케스트레이션)
└── parseXML.py    # XML 변환 함수 집합
```

#### 6.5.3 Pseudo-Spec

**`Encoder.py`**

```
클래스: xmlEncoder

  메서드:
    init(xml_dir, screenshot_dir) → None
      XML/스크린샷 저장 디렉토리 초기화

    parse(raw_xml) → (parsed_xml, hierarchy_xml)
      reformat → simplify → hierarchy_parse

    encode(raw_xml, screen_num) → (parsed, hierarchy, encoded)
      parse + 파일 저장 (parsed/hierarchy/encoded/pretty)
```

**`parseXML.py`**

```
태그 매핑:
  EditText     → <input>
  Checkable    → <checker>
  Clickable    → <button>
  TextView     → <p>
  ImageView    → <img>
  Layout       → <div> 또는 <scroll>

독립 함수:
  reformat_xml(raw_xml) → Element
    Android 속성을 HTML 태그로 변환, 인덱스 부여

  simplify_structure(element) → Element
    불필요한 중첩 축소

  remove_nodes_with_empty_bounds(element) → Element
    화면 밖/숨겨진 요소 제거

  hierarchy_parse(element) → str
    구조만 남긴 XML (임베딩용)

  remove_redundancies(element) → Element
    스크롤 컨테이너 내 반복 요소 제거
```

### 6.6 메시지 핸들러: `Server/handlers/`

#### 6.6.1 파일 구성

```
Server/handlers/
└── message_handlers.py    # TCP 메시지 송수신 함수
```

#### 6.6.2 Pseudo-Spec

```
독립 함수:
  handle_app_list(client_socket) → list
    'L' 메시지 수신 → 패키지 목록 파싱

  handle_package_name(client_socket) → str
    'A' 메시지 수신 → 현재 앱 패키지명

  handle_xml_message(client_socket, screen_parser, screen_num, ...) → tuple
    'X' 메시지 수신 → XML 파싱 → (parsed, hierarchy, encoded)

  handle_screenshot(client_socket, screenshot_dir, screen_num) → str
    'S' 메시지 수신 → JPEG 저장 → 파일 경로 반환

  handle_external_app(client_socket) → dict
    'E' 메시지 수신 → 외부 앱 전환 정보

  recv_text_line(client_socket) → str
    줄바꿈까지 텍스트 수신

  recv_binary_file(client_socket) → bytes
    4바이트 크기 헤더 + 바이너리 수신

  send_json_response(client_socket, response: dict) → None
    JSON 직렬화 + \r\n 종단 전송
```

### 6.7 유틸리티: `Server/utils/`

#### 6.7.1 파일 구성

```
Server/utils/
├── utils.py           # LLM 호출, 임베딩, 유사도 계산
├── parsing_utils.py   # XML 트리 탐색/추출 유틸리티
├── action_utils.py    # 액션 일반화/적응 파이프라인
├── network.py         # 네트워크 I/O 함수
└── logging.py         # loguru 기반 로깅 설정
```

#### 6.7.2 핵심 함수

**`utils.py`**

```
독립 함수:
  query(prompt, system_prompt, model, ...) → dict
    LLM 채팅 호출 → JSON 파싱 (max_tokens=4096)

  query_with_vision(prompt, system_prompt, image_paths, ...) → dict
    멀티 이미지 Vision API 호출

  get_openai_embedding(text) → list
    텍스트 임베딩 생성 (text-embedding-3-small)

  cosine_similarity(vec_a, vec_b) → float
    코사인 유사도 계산

  encode_image_to_base64(image_path) → str
    이미지 → base64 인코딩
```

**`action_utils.py`**

```
액션 일반화 파이프라인:
  generalize_action(action, subtask_params, screen_xml) → dict
    1. generalize_action_to_arguments(): 파라미터를 플레이스홀더로 치환
       예: "John" → <recipient__-1>
    2. generalize_action_to_screen(): UI 속성을 매칭 키로 추출
    결과: 다른 파라미터/화면에서 재사용 가능한 일반 액션

액션 적응 파이프라인:
  adapt_action(action, subtask_params, current_xml) → dict
    1. adapt_action_to_arguments(): 플레이스홀더를 실제 값으로 치환
    2. adapt_action_to_screen(): 현재 화면에서 UI 인덱스 탐색
    결과: 현재 화면에서 실행 가능한 구체적 액션
```

### 6.8 시각화: `Server/visualization/`

#### 6.8.1 목적

Subtask Graph를 인터랙티브 HTML로 시각화하여 앱 네비게이션 구조를 탐색·디버깅한다.

#### 6.8.2 파일 구성

```
Server/visualization/
├── __init__.py
└── graph_visualizer.py    # PyVis 기반 Subtask Graph 시각화
```

#### 6.8.3 Pseudo-Spec

**`graph_visualizer.py`**

```
독립 모듈 (Memory 클래스 미사용, JSON/CSV 직접 읽기):

독립 함수:
  load_subtask_graph(app_name, memory_dir) → dict
    subtask_graph.json 로드
    없으면 FileNotFoundError + 안내 메시지

  load_page_summaries(app_name, memory_dir) → Dict[int, str]
    pages.csv에서 page_index → summary 매핑 로드

  build_visualization(subtask_graph, page_summaries, title) → Network
    PyVis Network 객체 생성, 노드/엣지 추가, 레이아웃 설정
    반환: pyvis.network.Network

  visualize_app(app_name, memory_dir, output_path, open_browser) → str
    메인 진입점: load → build → save HTML → open browser
    반환: 생성된 HTML 파일 경로
```

#### 6.8.4 시각적 표현

| 요소 | 스타일 | 값 |
|------|--------|-----|
| 노드 | 색상 | `#4FC3F7` (light blue) |
| 노드 | 크기 | `min(20 + outgoing_count * 5, 50)` |
| 노드 | 라벨 | `Page {index}` |
| 노드 | 툴팁 | 페이지 summary + outgoing subtask 수 |
| explored 엣지 | 색상/스타일 | `#66BB6A` (green), 실선, width=2 |
| unexplored 엣지 | 색상/스타일 | `#EF5350` (red), 점선, width=1 |
| 엣지 | 라벨 | subtask 이름 |
| 엣지 | 툴팁 | subtask명, explored 여부, action_sequence 요약 |
| 레이아웃 | ≤15 노드 | force-directed (forceAtlas2Based) |
| 레이아웃 | >15 노드 | hierarchical (UD, directed sort) |

---

## 7. 평가/테스트

### 7.1 테스트 전략

| 테스트 유형 | 도구 | 대상 |
|------------|------|------|
| Unit | pytest | 에이전트, 유틸리티, 파서 |
| Integration | pytest | 그래프 노드 간 상호작용 |
| Mock | unittest.mock | LLM API 호출, TCP 통신 |

### 7.2 테스트 설정

```
Server/tests/
├── unit/              # 단위 테스트
├── integration/       # 통합 테스트
├── mocks/             # Mock 객체
└── fixtures/          # 테스트 데이터

설정: pytest.ini 또는 pyproject.toml
실행: pytest (프로젝트 루트에서)
```

---

## 8. 설정 파일

### 8.1 `Server/.env.example`

```bash
OPENAI_API_KEY = your_openai_api_key_here       # OpenAI API 키 (필수)
GOOGLESEARCH_KEY = your_google_search_api_key_here  # Google Search API 키 (앱 정보 조회)
```

### 8.2 에이전트 모델 설정 (환경변수)

```bash
TASK_AGENT_GPT_VERSION = "gpt-5.2"      # TaskAgent 모델
APP_AGENT_GPT_VERSION = "gpt-5.2"       # AppAgent 모델
EXPLORE_AGENT_GPT_VERSION = "gpt-5.2"   # ExploreAgent 모델
SELECT_AGENT_GPT_VERSION = "gpt-5.2"    # SelectAgent 모델
DERIVE_AGENT_GPT_VERSION = "gpt-5.2"    # DeriveAgent 모델
VERIFY_AGENT_GPT_VERSION = "gpt-5.2"    # VerifyAgent 모델
FILTER_AGENT_GPT_VERSION = "gpt-5.2"    # FilterAgent 모델
HISTORY_AGENT_GPT_VERSION = "gpt-5.2"   # HistoryAgent 모델
PLANNER_AGENT_GPT_VERSION = "gpt-5.2"   # PlannerAgent 모델
SUMMARY_AGENT_GPT_VERSION = "gpt-5.2"   # SummaryAgent 모델
```

### 8.3 Android 클라이언트 설정

```java
// MobileGPTGlobal.java
HOST_IP = "192.168.0.12"                          // 서버 IP
HOST_PORT = 12345                                  // 서버 포트
AVAILABLE_ACTIONS = ["click", "input", "scroll", "long-click", "go-back"]
```

---

## 9. CLI 인터페이스

### 9.1 기본 실행

```bash
# Task 모드 (기본)
python main.py --mode task --port 12345 --vision

# Auto-Explore 모드
python main.py --mode auto_explore --algorithm DFS --port 12345 --vision

# Subtask Graph 시각화
python main.py --mode visualize --app com.google.android.deskclock
```

### 9.2 인자 상세

```bash
python main.py \
  --mode {task|auto_explore|visualize}  # 실행 모드 (필수)
  --algorithm {DFS|BFS|GREEDY}          # 탐색 알고리즘 (auto_explore 모드 전용)
  --port PORT                           # 서버 포트 (기본: 12345)
  --vision | --no-vision                # Vision API 사용 여부 (기본: --vision)
  --app APP_PACKAGE                     # 앱 패키지명 (visualize 모드 전용)
```

| 인자 | 타입 | 기본값 | 설명 |
|------|------|--------|------|
| `--mode` | choice | (필수) | `task`: 명령 실행, `auto_explore`: UI 자율 학습, `visualize`: Subtask Graph 시각화 |
| `--algorithm` | choice | `DFS` | `DFS`: 깊이 우선, `BFS`: 너비 우선, `GREEDY`: 최단 거리 |
| `--port` | int | 12345 | TCP 서버 포트 |
| `--vision` | flag | True | Vision API로 스크린샷 분석 활성화 |
| `--no-vision` | flag | - | 텍스트 전용 모드 (XML만 사용) |
| `--app` | str | - | 시각화 대상 앱 패키지명 (`visualize` 모드 필수) |

---

## 10. 비기능 요구사항

### 10.1 에러 처리

| 상황 | 대응 |
|------|------|
| TCP 연결 끊김 | 클라이언트별 스레드 종료, 리소스 정리 |
| LLM API 에러 | 재시도 로직 (query 함수 내장) |
| XML 파싱 실패 | 빈 요소 제거, graceful fallback |
| 화면 매칭 실패 | `no_matching_page` 상태로 Task 종료 |
| 외부 앱 전환 | 탐색 상태 정리 후 복귀 |
| 재계획 한도 초과 | `max_replan_reached` (5회) 후 Task 종료 |

### 10.2 로깅

```
라이브러리: loguru
포맷: HH:mm:ss | LEVEL | module:function - message
출력: 콘솔 (컬러) + 파일 (선택적)
파일 회전: 10MB, 7일 보관

필수 로그 항목:
  - 서버 시작/종료 (IP, 포트)
  - 클라이언트 연결/해제
  - 에이전트별 LLM 호출 및 응답
  - Subtask 선택/검증/실행 결과
  - 화면 매칭 결과 (page_index, match_type)
  - 탐색 진행 상황 (DFS/BFS/GREEDY)
```

### 10.3 성능 목표

| 메트릭 | 목표 |
|--------|------|
| LLM 호출 최소화 | 메모리에 학습된 액션은 LLM 호출 없이 재사용 |
| 탐색 효율 | Subtask Graph으로 중복 방문 방지 |
| 메모리 재활용 | 한 번 학습한 앱 구조를 영구 저장·재사용 |
| 경로 최적화 | BFS로 최단 경로, 적응형 재계획으로 실패 복구 |

### 10.4 보안

- **Safety Guardrails**: 탐색 시 위험 subtask 자동 분류 (5개 카테고리) 및 차단
- **API 키 보호**: `.env` 파일로 관리, 코드에 하드코딩 금지
- **입력 검증**: LLM 응답 JSON 파싱 시 유효성 검사
- **네트워크**: 로컬 네트워크 TCP 통신 (공용 인터넷 미노출)

---

## 11. 의존성

### 11.1 시스템

```
- Python 3.10+
- Android 13+ (API Level 33)
- OpenAI API 접근 (GPT-5.2, text-embedding-3-small)
- Google Search API (선택, 앱 정보 조회)
```

### 11.2 패키지

| 패키지 | 버전 | 용도 |
|--------|------|------|
| openai | >= 1.50.0 | GPT API 호출 (채팅, 임베딩, Vision) |
| langgraph | >= 0.2.0 | StateGraph 기반 에이전트 파이프라인 |
| langchain | >= 0.3.0 | LLM 체인 기반 구조 |
| langchain-core | >= 0.3.0 | LangChain 핵심 추상화 |
| langchain-openai | >= 0.2.0 | OpenAI LangChain 통합 |
| numpy | >= 1.26.0 | 임베딩 벡터 연산 |
| pandas | >= 2.2.0 | CSV 데이터베이스 관리 |
| loguru | >= 0.7.0 | 구조화된 로깅 |
| python-dotenv | >= 1.0.0 | 환경변수 로드 (.env) |
| pydantic | >= 2.7.0 | 데이터 검증 (VerifyDecision 등) |
| serpapi | >= 0.1.5 | Google Search API 클라이언트 |
| pyvis | >= 0.3.2 | Subtask Graph 시각화 (인터랙티브 HTML) |
| pytest | >= 8.0.0 | 테스트 프레임워크 |
| pytest-cov | >= 4.0.0 | 테스트 커버리지 |

---

## 12. 코드 계보

| 원본 | 대상 | 변경 수준 |
|------|------|----------|
| MobileGPT V1 (연구 논문) | 전체 시스템 | 대규모 수정 |
| V1 에이전트 구조 | Server/agents/ | LangGraph 노드로 재구성 |
| V1 메모리 시스템 | Server/memory/ | Subtask Graph 도입 |
| V1 Android 클라이언트 | App/ | 구조 유지, 프로토콜 확장 |
| (신규) | Server/graphs/ | LangGraph StateGraph 신규 작성 |
| (신규) | App_Auto_Explorer/ | Auto-Explore 전용 클라이언트 신규 |

**V1 → V2 주요 변경사항:**

- **파이프라인**: 선형 순차 실행 → LangGraph StateGraph (조건부 라우팅, 체크포인터)
- **메모리**: 단순 CSV 저장 → Subtask Graph (JSON) + 시맨틱 요약/가이드라인
- **계획**: LLM 직접 선택 → 4-Step Workflow (Load → Filter → Plan → Execute)
- **검증**: 없음 → 2-Layer 검증 (규칙 기반 + LLM)
- **탐색**: 수동 → Auto-Explore (DFS/BFS/GREEDY 3가지 알고리즘)
- **재계획**: 없음 → 적응형 재계획 (PROCEED/SKIP/REPLAN)
- **Vision**: 없음 → Vision API 통합 (스크린샷 기반 UI 인식)

---

## 13. 용어 정리

| 용어 | 정의 |
|------|------|
| **Subtask** | 사용자가 화면에서 수행할 수 있는 고수준 작업 단위 (예: "send_message", "set_alarm"). 2개 이상의 액션으로 구성 |
| **Subtask Graph** | 페이지 간 네비게이션 구조를 표현하는 방향 그래프. 노드=페이지, 엣지=subtask 전이 |
| **Page** | 앱의 한 화면 상태. page_index로 식별하며 사용 가능한 subtask 목록을 보유 |
| **Trigger UI** | subtask의 진입점이 되는 UI 요소. 인덱스로 식별 (예: 검색 아이콘의 index=5) |
| **Action Sequence** | subtask를 완료하기 위한 순서화된 UI 액션 목록 (click, input, scroll 등) |
| **Transit Subtask** | planned_path에서 목표 subtask에 도달하기 위해 거쳐야 하는 중간 subtask. is_transit=True |
| **Planned Path** | Subtask Graph 위 BFS로 생성된 최적 실행 경로. PlannedPathStep 리스트 |
| **4-Step Workflow** | Load → Filter → Plan → Execute/Replan. Planner의 subtask 경로 생성 프로세스 |
| **Adaptive Replanning** | 실행 중 예상치 못한 화면 전환 시 현재 위치에서 경로를 재생성하는 메커니즘 (최대 5회) |
| **2-Layer 검증** | Step Verification (규칙 기반 경량 검증) + Path Verification (LLM 기반 경로 검증) |
| **Auto-Explore** | DFS/BFS/GREEDY 알고리즘으로 앱 UI를 자율 탐색하여 Subtask Graph를 구축하는 모드 |
| **Safety Guardrails** | 5개 위험 카테고리(communication, data, financial, system, privacy)로 unsafe subtask를 탐색 시 자동 차단 |
| **Vision API** | OpenAI Vision을 활용하여 스크린샷 이미지에서 UI 요소를 인식하는 기능 |
| **Guideline** | subtask 실행 방법에 대한 시맨틱 가이드 (HOW-to). 액션별 가이드라인을 집합하여 subtask 가이드라인 생성 |
| **Description** | 액션 실행 전후 화면 변화에 대한 설명 (WHY+WHAT). 최대 50단어 |
| **Page Summary** | 페이지의 목적과 사용 가능한 작업을 2-3문장으로 요약한 시맨틱 설명 |
| **Node Matching** | 현재 화면을 기존 저장된 페이지와 비교하는 알고리즘. EQSET/SUBSET/SUPERSET/NEW 4가지 결과 |
| **Action Generalization** | 학습된 액션에서 구체적 값을 플레이스홀더로 치환하여 범용적으로 재사용 가능하게 만드는 과정 |
| **Action Adaptation** | 일반화된 액션을 현재 화면의 실제 UI 인덱스와 파라미터 값으로 구체화하는 과정 |
