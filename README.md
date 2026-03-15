# MobileGPT-V2

LangGraph 기반 다중 에이전트 지능형 모바일 자동화 프레임워크

---

## 1. 소개 (Introduction)

### 1.1 개요 (Overview)

MobileGPT-V2는 다중 에이전트 아키텍처를 통해 Android 기기에서 복잡한 태스크를 수행하는 지능형 자동화 시스템입니다. 기존 버전을 기반으로, 자율적인 UI 탐색과 학습이 가능한 **Auto-Explore** 모듈을 도입하여 앱 지식 습득에 필요한 수동 작업을 크게 줄였습니다.

본 시스템은 LangGraph 워크플로우를 통한 LLM 기반 다중 에이전트 협업을 활용하여, 정교한 태스크 계획 수립, 실행, 적응형 재계획 기능을 제공합니다.

### 1.2 주요 기여 (Key Contributions)

1. **Auto-Explore 모듈**: 세 가지 알고리즘(DFS, BFS, GREEDY)을 지원하는 자율 UI 탐색
2. **Subtask Graph**: 풍부한 컨텍스트를 가진 그래프 기반 앱 네비게이션 구조
   - 페이지 요약
   - 액션 설명
   - 각 액션에 대한 시맨틱 가이던스
3. **4-Step 워크플로우**: Load → Filter → Plan → Execute/Replan (각 단계별 Verification 포함)
4. **적응형 재계획 (Adaptive Replanning)**: 실행 검증 기반 동적 경로 조정 (`verify_planned_path` 통합)
5. **Vision 강화 인식**: Vision API 통합을 통한 스크린샷 기반 UI 인식 (Text-only 모드 전환 가능)
6. **안전 가드레일 (Safety Guardrails)**: 탐색 중 잠재적 위험 액션 자동 필터링

---

## 2. 시스템 아키텍처 (System Architecture)

### 2.1 다중 에이전트 프레임워크 (Multi-Agent Framework)

MobileGPT-V2는 전문화된 에이전트들이 태스크 실행의 각 측면을 담당하는 협업 다중 에이전트 아키텍처를 채택합니다:

```
┌─────────────────────────────────────────────────────────────────────────┐
│                            MobileGPT-V2                                 │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  ┌───────────────────────────────────────┐                              │
│  │           Python Server               │  ← Python 서버               │
│  │  ┌─────────────────────────────────┐  │         TCP Socket           │
│  │  │      LangGraph Pipeline         │  │       ┌─────────────┐        │
│  │  │  ┌───────────────────────────┐  │  │       │             │        │
│  │  │  │  Task Graph (6-step)      │  │  │◄─────►│   Android   │        │
│  │  │  │  Supervisor → Memory →    │  │  │ XML   │   Client    │        │
│  │  │  │  Planner → Selector →     │  │  │ JSON  │             │        │
│  │  │  │  Verifier → Deriver       │  │  │ Image │  ← 클라이언트│        │
│  │  │  └───────────────────────────┘  │  │       │             │        │
│  │  │  ┌───────────────────────────┐  │  │       │  ┌───────┐  │        │
│  │  │  │  Explore Graph            │  │  │       │  │Access-│  │        │
│  │  │  │  Supervisor → Discover →  │  │  │       │  │ibility│  │        │
│  │  │  │  ExploreAction            │  │  │       │  │Service│  │        │
│  │  │  └───────────────────────────┘  │  │       │  └───────┘  │        │
│  │  └─────────────────────────────────┘  │       └─────────────┘        │
│  │                                       │       ↑ 접근성 서비스        │
│  │  ┌─────────────────────────────────┐  │                              │
│  │  │       Memory (메모리 시스템)      │  │  ← 메모리 관리자             │
│  │  │  ┌───────┐ ┌───────┐ ┌───────┐  │  │                              │
│  │  │  │Subtask│ │ Pages │ │Subtask│  │  │                              │
│  │  │  │ Graph │ │+sumry │ │+guide │  │  │                              │
│  │  │  └───────┘ └───────┘ └───────┘  │  │                              │
│  │  └─────────────────────────────────┘  │                              │
│  └───────────────────────────────────────┘                              │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

### 2.2 Auto-Explore 모듈 & Subtask Graph 생성

Auto-Explore 모듈은 **자율적인 앱 구조 학습**을 수행하고, 풍부한 네비게이션 그래프인 **Subtask Graph**를 구축합니다:

1. **발견 (Discovers)**: 새로운 화면을 발견하고 사용 가능한 서브태스크를 추출
2. **탐색 (Explores)**: 설정 가능한 알고리즘을 사용하여 각 서브태스크를 체계적으로 탐색
3. **생성 (Generates)**: 액션 설명 (각 액션 후 변경된 내용)
4. **작성 (Creates)**: 페이지 요약 (페이지가 보여주고 허용하는 것)
5. **결합 (Combines)**: 액션 가이던스를 서브태스크 레벨 가이던스로 통합
6. **기록 (Records)**: Subtask Graph에 네비게이션 패턴 기록

**Subtask Graph 구성요소**:
- **노드 (Nodes)**: 목적을 설명하는 요약이 포함된 페이지
- **엣지 (Edges)**: 설명, 가이던스, 액션 시퀀스가 포함된 서브태스크 전이

**탐색 알고리즘**:

| 알고리즘 | 전략 | 사용 사례 |
|----------|------|----------|
| **DFS** | 깊이 우선, 스택 기반 | 단일 경로 깊이 탐색 |
| **BFS** | 너비 우선, 큐 기반 | 현재 레벨 균일 커버리지 |
| **GREEDY** | 가장 가까운 미탐색 지점으로 최단 경로 | 효율적인 전역 커버리지 (권장) |

### 2.3 Subtask Graph 4-Step 워크플로우

태스크 실행은 Subtask Graph를 활용하는 **4-Step 워크플로우**를 따릅니다:

```
Load → Filter → Plan → Execute/Replan
로드     필터     계획    실행/재계획
```

| 단계 | 목적 | 에이전트 |
|------|------|----------|
| **Load** | 모든 페이지에서 모든 서브태스크 가져오기 → `verify_load()` | MemoryManager, StepVerifyAgent |
| **Filter** | 지시어에 관련된 서브태스크 선택 → `verify_filter()` | FilterAgent, StepVerifyAgent |
| **Plan** | Subtask Graph를 사용하여 최적 경로 생성 → `verify_plan()`. 필터링된 subtask에 `[RELEVANT]` 마커를 부여하고, BFS 경로 상 필요한 경유(transit) subtask를 `is_transit` 플래그와 함께 자동 포함 | PlannerAgent, StepVerifyAgent |
| **Execute/Replan** | 액션 실행, `verify_planned_path()` → 불일치 시 재계획 | VerifyAgent |

### 2.4 상세 파이프라인 (Detailed Pipeline)

시스템은 **6-Step 실행 파이프라인**을 통해 동작합니다:

| 단계 | 목적 | 에이전트/노드 |
|------|------|---------------|
| **Auto-Explore** | 자율 UI 학습, Subtask Graph 생성 | ExploreAgent |
| **Plan** | Subtask Graph 경로 계획 | PlannerAgent |
| **Select** | 다음 서브태스크 선택 | SelectAgent |
| **Derive** | 액션 생성 | DeriveAgent |
| **Verify** | 결과 검증 & 적응형 재계획 | VerifyAgent |
| **Recall** | 메모리 조회 | MemoryNode |

---

## 3. 에이전트 & 역할 (Agents & Roles)

MobileGPT-V2는 태스크 실행의 다양한 측면을 위해 전문화된 에이전트를 사용합니다.

> **구현 형태**: Class = 상태를 가진 클래스 인스턴스, Module = 독립 함수 (stateless).
> 상세는 [ARCHITECTURE.md](ARCHITECTURE.md) 참조.

#### 클래스 에이전트 (Class Agents)

| 에이전트 | 구현 형태 | 책임 |
|----------|-----------|------|
| **ExploreAgent** | Class | UI 인식, 서브태스크 추출, 요소 위치 파악 |
| **PlannerAgent** | Class | 목표 분석, Subtask Graph 경로 계획, 경유(transit) subtask 자동 포함 |
| **SelectAgent** | Class | 서브태스크 선택, 컨텍스트 인식 의사결정 |
| **DeriveAgent** | Class | 액션 파라미터화, UI 요소 타겟팅 |
| **TaskAgent** | Class | 사용자 지시어 분석, 태스크 구조화 |
| **AppAgent** | Class | 앱 예측, 패키지 관리, 앱 DB 유지 |
| **Memory** | Class | Subtask Graph 관리, 페이지 매칭, 지식 영속성 |

#### 모듈 함수 에이전트 (Module Function Agents)

| 모듈 | 구현 형태 | 책임 |
|------|-----------|------|
| **history_agent** | Module | 액션 설명, 시맨틱 가이던스 생성 |
| **summary_agent** | Module | 페이지 요약 생성 |
| **filter_agent** | Module | 지시어 관련성을 위한 서브태스크 필터링 (4-Step 워크플로우) |
| **step_verify_agent** | Module | 4-Step 각 단계별 경량 검증 (Load/Filter/Plan) |
| **verify_agent** | Module | 실행 검증, PROCEED/SKIP/REPLAN 결정, Page Summary 포함 |

---

## 4. 시작하기 (Getting Started)

### 4.1 요구사항 (Requirements)

**서버**:
- Python 3.10+
- OpenAI API Key (Vision 기능을 위해 GPT-5.2 권장)

**Android 클라이언트**:
- Android 13+ (API 33)
- 접근성 서비스 권한

### 4.2 설치 (Installation)

```bash
# 저장소 클론
git clone https://github.com/user/MobileGPT-V2.git
cd MobileGPT-V2

# Python 의존성 설치
pip install -r requirements.txt

# 환경 변수 설정
cp Server/.env.example Server/.env
# Server/.env 파일을 열어 API 키를 입력
```

**필수/선택 환경변수**:

| 변수 | 필수 여부 | 설명 |
|------|-----------|------|
| `OPENAI_API_KEY` | **필수** | OpenAI API 호출에 사용 |
| `GOOGLESEARCH_KEY` | 선택 | Google Search API (향후 확장용) |

> **참고**: 모든 서버 명령은 `Server/` 디렉토리에서 실행합니다. (`cd Server`)

### 4.3 Android 클라이언트 설정

**모드별 Android 프로젝트**:

| 모드 | 프로젝트 | 설명 |
|------|----------|------|
| Task Mode | `App/` | 학습된 지식으로 태스크 실행 |
| Auto-Explore | `App_Auto_Explorer/` | 자율 UI 탐색 및 Subtask Graph 구축 |

**설정 방법**:

1. 해당 모드의 Android 프로젝트를 Android Studio에서 열기
2. `MobileGPTGlobal.java`에서 서버 IP 설정:
   ```java
   public static final String HOST_IP = "192.168.0.9";  // 서버 IP
   public static final int HOST_PORT = 12345;
   ```
3. 기기에 빌드 및 설치
4. 접근성 서비스 활성화: 설정 → 접근성 → MobileGPT 서비스

---

## 5. 사용 모드 (Usage Modes)

### 5.0 CLI 레퍼런스 (CLI Reference)

진입점: `Server/main.py`

```bash
cd Server
python main.py [OPTIONS]
```

| 옵션 | 타입 | 선택값 | 기본값 | 설명 |
|------|------|--------|--------|------|
| `--mode` | str | `task`, `auto_explore`, `visualize` | `task` | 서버 모드 선택 |
| `--algorithm` | str | `DFS`, `BFS`, `GREEDY` | `GREEDY` | 탐색 알고리즘 (`auto_explore` 모드 전용) |
| `--port` | int | - | `12345` | TCP 서버 포트 |
| `--vision` | flag | - | 활성화 | Vision+Text 모드 (기본값) |
| `--no-vision` | flag | - | - | Text-only 모드 (`--vision`과 상호 배타) |
| `--app` | str | - | - | 앱 패키지명 (`visualize` 모드 필수) |

**최소 실행 커맨드** (기본값: task 모드, port 12345, vision 활성화):

```bash
python main.py
```

> **참고**: `--algorithm`은 `--mode auto_explore`일 때만 사용됩니다. Task 모드에서는 무시됩니다.

### 5.1 Auto-Explore 모드

자율 UI 탐색 및 Subtask Graph 구축:

```bash
cd Server

# GREEDY 탐색 (권장, 기본 알고리즘)
python main.py --mode auto_explore

# DFS 탐색
python main.py --mode auto_explore --algorithm DFS

# BFS 탐색
python main.py --mode auto_explore --algorithm BFS

# 포트 변경 + Text-only 모드
python main.py --mode auto_explore --port 8080 --no-vision
```

### 5.2 Task 모드

학습된 지식을 사용하여 사용자 태스크 실행:

```bash
cd Server

# 기본 실행 (mode=task가 기본값이므로 생략 가능)
python main.py

# 명시적 지정
python main.py --mode task --port 12345

# Text-only 모드
python main.py --mode task --no-vision
```

### 5.3 Vision 모드 옵션

`--vision`과 `--no-vision`은 상호 배타적 옵션입니다 (동시 사용 불가).

| 옵션 | 설명 |
|------|------|
| `--vision` (기본값) | Vision+Text 모드: 스크린샷을 LLM에 전송 |
| `--no-vision` | Text-only 모드: 스크린샷 저장은 유지하되 LLM에 전송하지 않음 |

> **참고**: `--no-vision` 모드에서도 스크린샷은 로그 디렉토리에 저장됩니다.

### 5.4 Visualize 모드

Auto-Explore로 구축된 Subtask Graph를 인터랙티브 HTML로 시각화:

```bash
cd Server

# 기본 시각화 (브라우저 자동 오픈)
python main.py --mode visualize --app com.google.android.deskclock

# 독립 실행 (main.py 없이)
python -m visualization.graph_visualizer --app com.google.android.deskclock

# 브라우저 열지 않기
python -m visualization.graph_visualizer --app com.google.android.deskclock --no-open
```

**시각화 요소**:

| 요소 | 표현 |
|------|------|
| 노드 (페이지) | 파란색 원, 크기=outgoing subtask 수 비례 |
| explored 엣지 | 초록 실선, subtask 이름 라벨 |
| unexplored 엣지 | 빨간 점선 |
| 툴팁 | 노드: 페이지 요약 / 엣지: action sequence 요약 |

출력 파일: `./memory/{app_name}/subtask_graph.html`

---

## 6. Subtask Graph 데이터 스키마 (Data Schema)

Subtask Graph는 앱 네비게이션 지식을 구조화된 파일로 저장합니다:

### 6.1 pages.csv
| 컬럼 | 설명 |
|------|------|
| index | 페이지 인덱스 |
| available_subtasks | 서브태스크 이름 목록 |
| trigger_uis | 트리거 UI 인덱스 |
| screen | 페이지 XML 시그니처 |
| **summary** | 페이지 설명 |

### 6.2 subtasks.csv
| 컬럼 | 설명 |
|------|------|
| name | 서브태스크 이름 |
| description | 서브태스크 기능 설명 |
| guideline | 서브태스크 수행 방법 (통합 가이던스 포함) |
| start_page, end_page | 네비게이션 전이 |

### 6.3 actions.csv
| 컬럼 | 설명 |
|------|------|
| subtask_name | 상위 서브태스크 |
| step | 액션 시퀀스 번호 |
| action | 액션 파라미터 (JSON) |
| **description** | 액션 후 변경 내용 |
| **guideline** | 액션의 시맨틱 의미 |

### 6.4 subtask_graph.json
```json
{
  "nodes": [0, 1, 2],
  "edges": [
    {
      "from_page": 0, "to_page": 1,
      "subtask": "search_emails",
      "trigger_ui_index": 5,
      "action_sequence": [{"name": "click", "description": "...", "guideline": "..."}],
      "explored": true
    }
  ]
}
```

---

## 7. 설정 (Configuration)

### 7.1 에이전트 모델 설정

`Server/main.py`에서 LLM 모델 설정:

```python
# 핵심 에이전트 모델
os.environ["TASK_AGENT_GPT_VERSION"] = "gpt-5.2"       # TaskAgent
os.environ["APP_AGENT_GPT_VERSION"] = "gpt-5.2"        # app_agent
os.environ["EXPLORE_AGENT_GPT_VERSION"] = "gpt-5.2"    # ExploreAgent
os.environ["SELECT_AGENT_GPT_VERSION"] = "gpt-5.2"     # SelectAgent
os.environ["DERIVE_AGENT_GPT_VERSION"] = "gpt-5.2"     # DeriveAgent
os.environ["VERIFY_AGENT_GPT_VERSION"] = "gpt-5.2"     # verify_agent

# 모듈 함수 에이전트 모델
os.environ["FILTER_AGENT_GPT_VERSION"] = "gpt-5.2"     # filter_agent
os.environ["PLANNER_AGENT_GPT_VERSION"] = "gpt-5.2"    # PlannerAgent
os.environ["HISTORY_AGENT_GPT_VERSION"] = "gpt-5.2"    # history_agent
os.environ["SUMMARY_AGENT_GPT_VERSION"] = "gpt-5.2"    # summary_agent
```

> **주의**: 위 환경변수는 `main.py`에서 `os.environ[]`으로 **직접 할당**되므로, `.env` 파일에 동일한 변수를 설정해도 덮어쓰입니다. 모델을 변경하려면 `main.py`를 직접 수정해야 합니다.

> 전체 환경 변수 목록은 [EXAMPLE.md 섹션 3.3](EXAMPLE.md#33-환경-변수)에서 확인할 수 있습니다.

### 7.2 네트워크 설정 (Network Configuration)

| 설정 | 값 | 변경 방법 |
|------|-----|-----------|
| Host | `0.0.0.0` (모든 네트워크 인터페이스) | 소스 코드 수정 (`server.py`, `server_auto_explore.py`) |
| Port | `12345` | `--port` CLI 옵션 |
| Buffer Size | `4096` bytes | 소스 코드 수정 (CLI 미노출) |
| Memory Directory | `./memory` | 소스 코드 수정 (CLI 미노출) |
| Socket 재사용 | `SO_REUSEADDR = 1` | 하드코딩 (자동 활성화) |

> 서버는 시작 시 UDP 소켓을 이용해 실제 로컬 IP를 자동 탐지하여 콘솔에 출력합니다 (`utils/network.py`).

### 7.3 환경변수 전체 목록 (Environment Variables)

| 카테고리 | 변수 | 필수 | 기본값 | 설정 위치 |
|----------|------|------|--------|-----------|
| API 키 | `OPENAI_API_KEY` | **필수** | - | `.env` |
| API 키 | `GOOGLESEARCH_KEY` | 선택 | - | `.env` |
| 에이전트 모델 | `TASK_AGENT_GPT_VERSION` | 자동 | `gpt-5.2` | `main.py` 하드코딩 |
| 에이전트 모델 | `APP_AGENT_GPT_VERSION` | 자동 | `gpt-5.2` | `main.py` 하드코딩 |
| 에이전트 모델 | `EXPLORE_AGENT_GPT_VERSION` | 자동 | `gpt-5.2` | `main.py` 하드코딩 |
| 에이전트 모델 | `SELECT_AGENT_GPT_VERSION` | 자동 | `gpt-5.2` | `main.py` 하드코딩 |
| 에이전트 모델 | `DERIVE_AGENT_GPT_VERSION` | 자동 | `gpt-5.2` | `main.py` 하드코딩 |
| 에이전트 모델 | `VERIFY_AGENT_GPT_VERSION` | 자동 | `gpt-5.2` | `main.py` 하드코딩 |
| 에이전트 모델 | `FILTER_AGENT_GPT_VERSION` | 자동 | `gpt-5.2` | `main.py` 하드코딩 |
| 에이전트 모델 | `PLANNER_AGENT_GPT_VERSION` | 자동 | `gpt-5.2` | `main.py` 하드코딩 |
| 에이전트 모델 | `HISTORY_AGENT_GPT_VERSION` | 자동 | `gpt-5.2` | `main.py` 하드코딩 |
| 에이전트 모델 | `SUMMARY_AGENT_GPT_VERSION` | 자동 | `gpt-5.2` | `main.py` 하드코딩 |

---

## 8. 프로젝트 구조 (Project Structure)

```
MobileGPT-V2/
├── Server/                              # Python 서버
│   ├── main.py                          # 진입점 (환경변수 설정, 모드 선택)
│   ├── server.py                        # Task 모드 서버
│   ├── server_auto_explore.py           # Auto-Explore 서버
│   ├── agents/                          # LLM 에이전트 (7 Class + 5 Module)
│   │   └── prompts/                     # 프롬프트 템플릿 (12개)
│   ├── graphs/                          # LangGraph 정의
│   │   ├── state.py                     # TaskState, ExploreState 정의
│   │   └── nodes/                       # 그래프 노드 (9개)
│   │       ├── supervisor.py            # Task Graph 라우팅
│   │       ├── explore_supervisor.py    # Explore Graph 라우팅
│   │       ├── memory_node.py           # 페이지 매칭/subtask 로딩
│   │       ├── planner_node.py          # 4-Step 워크플로우 실행
│   │       ├── selector_node.py         # subtask 선택
│   │       ├── verifier_node.py         # 경로 검증/재계획
│   │       ├── deriver_node.py          # 액션 도출
│   │       ├── discover_node.py         # 화면 발견/탐색
│   │       └── explore_action_node.py   # 탐색 알고리즘 실행
│   ├── memory/                          # 메모리 시스템
│   │   ├── memory_manager.py            # Memory 클래스 (핵심)
│   │   ├── page_manager.py              # 페이지별 데이터 관리
│   │   └── node_manager.py              # 노드 관리
│   ├── handlers/                        # 메시지 핸들러
│   ├── visualization/                   # Subtask Graph 시각화 (PyVis)
│   │   └── graph_visualizer.py          # 인터랙티브 HTML 생성
│   ├── utils/                           # 유틸리티
│   └── tests/                           # 테스트
│       ├── unit/                        # 단위 테스트 (agents, graphs, memory)
│       ├── integration/                 # 통합 테스트
│       ├── mocks/                       # Mock 객체
│       └── fixtures/                    # 테스트 데이터
│
├── App/                                 # Android 클라이언트 (Task Mode)
├── App_Auto_Explorer/                   # Android 클라이언트 (Auto-Explore)
│
└── requirements.txt                     # Python 의존성
```

---

## 9. 테스트 (Testing)

### 9.1 테스트 실행

```bash
# 전체 테스트
pytest Server/tests/

# 단위 테스트만
pytest Server/tests/unit/

# 통합 테스트만
pytest Server/tests/integration/

# 상세 출력
pytest Server/tests/ -v
```

### 9.2 테스트 구조

| 디렉토리 | 설명 |
|----------|------|
| `tests/unit/` | 단위 테스트 |
| `tests/integration/` | 통합 테스트 |
| `tests/mocks/` | Mock 객체 |
| `tests/fixtures/` | 테스트 데이터 |

---

## 10. 인용 (Citation)

연구에 MobileGPT-V2를 사용하시면 아래와 같이 인용해 주세요:

```bibtex
@software{mobilegpt-v2,
  title = {MobileGPT-V2: A LangGraph-based Multi-Agent Framework for Intelligent Mobile Automation},
  year = {2026},
  url = {https://github.com/user/MobileGPT-V2}
}
```

---

## 11. 라이선스 (License)

MIT License - 자세한 내용은 [LICENSE](LICENSE)를 참조하세요.
