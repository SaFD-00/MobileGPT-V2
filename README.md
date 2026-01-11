# MobileGPT Auto-Explorer

LLM 기반 모바일 작업 자동화 시스템 (LangGraph Multi-Agent System)

> **Paper**: [MobileGPT: Augmenting LLM with Human-like App Memory for Mobile Task Automation](https://arxiv.org/abs/2312.03003)
> **Venue**: ACM MobiCom '24 (November 18–22, 2024, Washington D.C.)

**Benchmark Dataset**: [Google Cloud Download](https://drive.google.com/file/d/18Te3l0VtoxsZtEQYPTUylivVSqa-WBdG/view?usp=sharing)

---

## 목차

1. [개요](#1-개요)
2. [시스템 요구사항](#2-시스템-요구사항)
3. [설치 및 설정](#3-설치-및-설정)
4. [실행 방법](#4-실행-방법)
   - [4.1 서버 실행](#41-서버-실행)
   - [4.2 작업 모드](#42-작업-모드-task)
   - [4.3 수동 탐색 모드](#43-수동-탐색-모드)
   - [4.4 자동 탐색 모드](#44-자동-탐색-모드)
5. [메모리 구조](#5-메모리-구조)
6. [벤치마크 데이터셋](#6-벤치마크-데이터셋)
7. [아키텍처](#7-아키텍처)
8. [주의사항 및 라이선스](#8-주의사항-및-라이선스)

---

## 1. 개요

MobileGPT는 대규모 언어 모델(LLM)을 활용하여 모바일 앱의 복잡한 작업을 자동으로 수행하는 시스템입니다. 인간이 앱을 사용하는 인지 과정을 모방하여 4단계 프로세스로 작업을 학습하고 실행합니다:

1. **Explore (탐색)**: 새로운 화면을 분석하여 가능한 동작(서브태스크) 발견
2. **Select (선택)**: 사용자 목표에 맞는 최적의 서브태스크 선택
3. **Derive (도출)**: 서브태스크를 구체적인 UI 액션(클릭, 입력 등)으로 변환
4. **Recall (재현)**: 학습된 작업을 새로운 상황에 적응하여 재실행

### 주요 기능

| 기능 | 설명 |
|------|------|
| **작업 자동화** | 사용자 명령어를 이해하고 앱에서 자동으로 수행 |
| **메모리 기반 학습** | 한 번 수행한 작업을 저장하여 재사용 |
| **자동 탐색** | 앱 전체를 자동으로 탐색하여 UI 구조 학습 |
| **적응적 실행** | 학습된 작업을 다른 매개변수로 적응 실행 |
| **LangGraph Multi-Agent** | Supervisor 기반 자동 subtask 선택 및 검증 |

### 에이전트 파이프라인

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              사용자 명령어 입력                               │
└─────────────────────────────────────────────────────────────────────────────┘
                                       │
                                       ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│  [TaskAgent]  명령어 파싱 → {앱, 작업명, 매개변수} 구조화                      │
└─────────────────────────────────────────────────────────────────────────────┘
                                       │
                                       ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│  [AppAgent]  대상 앱 예측 (임베딩 유사도 + GPT 선택)                          │
└─────────────────────────────────────────────────────────────────────────────┘
                                       │
                                       ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                    LangGraph Task Graph 실행                                │
│  ┌───────────────────────────────────────────────────────────────────────┐ │
│  │                         Supervisor Node                                │ │
│  │                    (라우팅 결정: 다음 실행할 노드)                        │ │
│  └───────────────────────────────────────────────────────────────────────┘ │
│                                     │                                      │
│         ┌───────────────────────────┼───────────────────────────┐          │
│         ▼                           ▼                           ▼          │
│  ┌─────────────┐             ┌─────────────┐             ┌─────────────┐  │
│  │ Memory Node │             │Selector Node│             │Verifier Node│  │
│  │ page/state  │────────────▶│  subtask    │────────────▶│  다음 화면  │  │
│  │ 조회        │             │  선택       │             │  검증       │  │
│  └─────────────┘             └─────────────┘             └──────┬──────┘  │
│                                                                 │          │
│                                    ┌────────────────────────────┴────┐     │
│                                    ▼                                 ▼     │
│                          "가면 안된다"                           "간다"     │
│                          (재선택 Loop)                          (확정)     │
│                                    │                                 │     │
│                                    ▼                                 ▼     │
│                          rejected_subtasks에              ┌─────────────┐  │
│                          추가 후 재선택                    │Deriver Node │  │
│                                                           │ action 도출 │  │
│                                                           └─────────────┘  │
└─────────────────────────────────────────────────────────────────────────────┘
                                       │
                                       ▼
                    ┌──────────────────────────────────────┐
                    │      액션 실행 → 다음 화면 수신        │
                    │      (작업 완료까지 루프 반복)         │
                    └──────────────────────────────────────┘
```

**LangGraph 노드:**

| 노드 | 역할 | 입력 | 출력 |
|------|------|------|------|
| **Supervisor** | 라우팅 결정 | TaskState | next_agent (memory/selector/verifier/deriver/FINISH) |
| **Memory** | page/state 조회, subtask 로드 | XML 화면 | page_index, available_subtasks |
| **Selector** | 거부된 subtask 제외 후 선택 | available_subtasks, rejected_subtasks | selected_subtask |
| **Verifier** | 선택된 subtask의 다음 화면 검증 | selected_subtask | verification_passed (True/False) |
| **Deriver** | subtask → 구체적 UI 액션 도출 | selected_subtask, current_xml | action (click/input/scroll 등) |

**기타 에이전트:**

| 에이전트 | 역할 | 입력 | 출력 |
|---------|------|------|------|
| **TaskAgent** | 명령어 파싱 | 사용자 명령 | {앱, 작업명, 매개변수} |
| **AppAgent** | 앱 예측 | 명령어 + 앱 목록 | 패키지명 |
| **ExploreAgent** | 화면 탐색 | XML 화면 | 서브태스크 목록 |
| **ActionSummarizeAgent** | 액션 요약 | 액션 히스토리 | 1문장 요약 |
| **SubtaskMergeAgent** | 서브태스크 병합 | 서브태스크 리스트 | 병합된 리스트 |

---

## 2. 시스템 요구사항

- Python 3.12
- Android SDK >= 33
- OpenAI API Key
- Google Search API Key (선택사항)

---

## 3. 설치 및 설정

### 3.1 설치

```bash
git clone https://github.com/mobile-gpt/MobileGPT.git
cd MobileGPT
pip install --upgrade pip
pip install -r ./Server/requirements.txt
```

### 3.2 API 키 설정

`Server/.env` 파일을 생성하고 API 키를 설정합니다:

```env
OPENAI_API_KEY = "<OpenAI API 키>"
GOOGLESEARCH_KEY = "<Google Search API 키 (선택)>"
```

### 3.3 GPT 모델 설정

`Server/main.py` 파일에서 각 에이전트가 사용할 GPT 모델을 설정할 수 있습니다.

#### 지원 모델 (GPT-5.2 계열)

| 모델 | 용도 | 특징 |
|------|------|------|
| `gpt-5.2` | GPT-5.2 Thinking | 추론 모델, 복잡한 작업에 적합 |
| `gpt-5.2-chat-latest` | GPT-5.2 Instant | 빠른 채팅, 속도 최적화 (기본값) |

#### 에이전트별 모델 설정

```python
# 에이전트별 GPT 모델 버전 (gpt-5.2-chat-latest 사용)
os.environ["TASK_AGENT_GPT_VERSION"] = "gpt-5.2-chat-latest"          # 사용자 명령 파싱
os.environ["APP_AGENT_GPT_VERSION"] = "gpt-5.2-chat-latest"           # 대상 앱 예측
os.environ["EXPLORE_AGENT_GPT_VERSION"] = "gpt-5.2-chat-latest"       # 화면 탐색/서브태스크 발견
os.environ["SELECT_AGENT_GPT_VERSION"] = "gpt-5.2-chat-latest"        # 서브태스크 선택
os.environ["SELECT_AGENT_HISTORY_GPT_VERSION"] = "gpt-5.2-chat-latest"# 히스토리 기반 선택
os.environ["DERIVE_AGENT_GPT_VERSION"] = "gpt-5.2-chat-latest"        # UI 액션 도출
os.environ["PARAMETER_FILLER_AGENT_GPT_VERSION"] = "gpt-5.2-chat-latest"  # 매개변수 채우기
os.environ["ACTION_SUMMARIZE_AGENT_GPT_VERSION"] = "gpt-5.2-chat-latest"  # 액션 요약
os.environ["SUBTASK_MERGE_AGENT_GPT_VERSION"] = "gpt-5.2-chat-latest" # 서브태스크 병합
os.environ["GUIDELINE_AGENT_GPT_VERSION"] = "gpt-5.2-chat-latest"    # 가이드라인 생성
os.environ["VERIFY_AGENT_GPT_VERSION"] = "gpt-5.2-chat-latest"       # LangGraph: 다음 화면 검증
```

### 3.4 서버 모드 선택

CLI 인자로 서버 모드를 선택합니다:

```bash
# 작업 모드 (기본값): LangGraph 기반 사용자 명령 실행
python main.py --mode task

# 수동 탐색 모드: 사용자가 직접 화면 캡처
python main.py --mode explore

# 자동 탐색 모드: 앱 자동 탐색
python main.py --mode auto_explore --algorithm BFS
python main.py --mode auto_explore --algorithm DFS
python main.py --mode auto_explore --algorithm GREEDY_BFS
python main.py --mode auto_explore --algorithm GREEDY_DFS
```

| 모드 | 설명 | 서버 클래스 |
|------|------|------------|
| `task` | LangGraph 기반 사용자 명령 실행 (기본값) | `Server` |
| `explore` | 수동 화면 탐색 | `Explorer` |
| `auto_explore` | 자동 UI 탐색 | `AutoExplorer` |

### 3.5 클라이언트 앱 설정

각 앱의 `MobileGPTGlobal.java` 파일에서 서버 IP를 설정합니다:

```java
// 서버의 IP 주소로 변경
public static final String HOST_IP = "192.168.0.100";
```

**파일 위치:**
- `App/app/src/main/java/com/example/MobileGPT/MobileGPTGlobal.java`
- `App_Explorer/app/src/main/java/com/example/hardcode/MobileGPTGlobal.java`
- `App_Auto_Explorer/app/src/main/java/com/mobilegpt/autoexplorer/MobileGPTGlobal.java`

---

## 4. 실행 방법

### 4.1 서버 실행

```bash
cd Server

# 기본 실행 (task 모드)
python ./main.py

# 모드 지정 실행
python ./main.py --mode task         # LangGraph 기반 작업 실행 (기본값)
python ./main.py --mode explore      # 수동 탐색
python ./main.py --mode auto_explore --algorithm GREEDY_BFS  # 자동 탐색

# 포트 변경
python ./main.py --port 8080

# 출력 예시:
# Server is listening on 192.168.0.100:12345
# 이 IP 주소를 앱에 입력하세요: [192.168.0.100]
```

#### CLI 옵션

| 옵션 | 기본값 | 설명 |
|------|--------|------|
| `--mode` | `task` | 서버 모드 (`task`, `explore`, `auto_explore`) |
| `--algorithm` | `GREEDY_BFS` | 자동 탐색 알고리즘 (`DFS`, `BFS`, `GREEDY_BFS`, `GREEDY_DFS`) |
| `--port` | `12345` | 서버 포트 |

### 4.2 작업 모드 (task)

LangGraph 기반 Multi-Agent 시스템으로 자동 subtask 선택 및 검증을 수행합니다.

#### 사용 방법

1. 서버가 실행 중인지 확인
2. MobileGPT 앱을 처음 실행하면 접근성 서비스 권한을 요청합니다
   - 설정에서 MobileGPT 앱의 접근성 서비스를 활성화
3. 앱이 설치된 앱 목록을 분석합니다 (최초 1회, 시간 소요)
4. 명령어를 입력하고 [Set New Instruction] 버튼을 클릭
5. MobileGPT가 자동으로 앱을 실행하고 작업을 수행합니다

![실행 화면](explain.png)

#### LangGraph Task Graph 구조

```
┌───────────────────────────────────────────────────────────────┐
│                    LangGraph Task Graph                        │
├───────────────────────────────────────────────────────────────┤
│                                                                │
│  START → supervisor → (conditional routing)                    │
│                │                                               │
│                ├── memory → supervisor                         │
│                ├── selector → supervisor                       │
│                ├── verifier → supervisor                       │
│                ├── deriver → END                               │
│                └── FINISH → END                                │
│                                                                │
│  Flow:                                                         │
│    1. supervisor: 다음 실행할 노드 결정                          │
│    2. memory: page/state 조회, available subtasks 로드          │
│    3. selector: rejected 제외 후 best subtask 선택              │
│    4. verifier: 선택된 subtask 검증                             │
│       - "가면 안된다" → rejected에 추가, selector로              │
│       - "간다" → deriver로                                     │
│    5. deriver: 구체적 action 도출 → END                         │
│                                                                │
└───────────────────────────────────────────────────────────────┘
```

#### 특징

- **자동 검증**: Verifier Node가 선택한 subtask의 다음 화면을 분석하여 "가면 안된다" / "간다" 판정
- **재선택 루프**: 검증 실패 시 해당 subtask를 거부 목록에 추가하고 재선택
- **상태 관리**: LangGraph TaskState로 세션, subtask, 검증 상태 관리
- **MemorySaver**: 체크포인터로 세션 상태 영속화

### 4.3 수동 탐색 모드

1. `--mode explore`로 서버 실행
2. `App_Explorer` 앱 설치 및 실행
3. 화면 우측의 녹색 플로팅 버튼 확인
4. 탐색할 앱을 실행하고 Start 버튼 클릭
5. 원하는 페이지에서 Capture 버튼 클릭
6. 탐색 완료 후 Finish 버튼 클릭
7. 서버가 캡처된 페이지를 분석하여 메모리 생성

### 4.4 자동 탐색 모드

1. `--mode auto_explore`로 서버 실행
2. `App_Auto_Explorer` 앱 설치 및 실행
3. 탐색할 앱을 선택하면 자동으로 모든 UI 탐색

#### 탐색 알고리즘 선택

```bash
# 탐색 알고리즘 선택: DFS, BFS, GREEDY_BFS, GREEDY_DFS
python main.py --mode auto_explore --algorithm GREEDY_BFS  # 기본값
python main.py --mode auto_explore --algorithm DFS
python main.py --mode auto_explore --algorithm BFS
python main.py --mode auto_explore --algorithm GREEDY_DFS
```

#### 알고리즘 비교

| 알고리즘 | 특징 | 적합한 상황 |
|---------|------|------------|
| **DFS** | 깊이 우선, 한 경로 끝까지 탐색 후 back 복귀 | 깊은 네비게이션 구조, 메모리 효율적 |
| **BFS** | 너비 우선, 같은 레벨 모든 UI 먼저 탐색 | 복잡한 앱, 체계적 탐색 |
| **GREEDY_BFS** | BFS + 가장 가까운 unexplored 우선 | 최단 경로 중요, 일부 탐색된 앱 |
| **GREEDY_DFS** | DFS + 가장 깊은 unexplored 우선 | 깊은 기능 빠른 발견 |

#### 알고리즘 상세 설명

- **DFS (깊이 우선 탐색)**: 스택 기반으로 동작하며, 한 경로를 끝까지 탐색한 후 back 액션으로 복귀합니다. 메모리 효율적이고 깊은 네비게이션 구조에 적합합니다.

- **BFS (너비 우선 탐색)**: 큐 기반으로 동작하며, 같은 레벨의 모든 서브태스크를 먼저 탐색합니다. 다른 페이지로 이동이 필요한 경우 네비게이션 시스템을 사용합니다.

- **GREEDY_BFS (탐욕-BFS 탐색)**: 현재 위치에서 **BFS로 가장 가까운** `unexplored` 상태의 서브태스크를 찾아 탐색합니다. 최단 경로를 보장합니다.

- **GREEDY_DFS (탐욕-DFS 탐색)**: 현재 위치에서 **DFS로 가장 깊은** `unexplored` 상태의 서브태스크를 찾아 탐색합니다. 앱의 깊숙한 기능까지 빠르게 도달해야 할 때 유용합니다.

#### 탐색 순서 예제

![페이지 그래프 예제](graph_example.png)

| 알고리즘 | 탐색 순서 | 총 이동 |
|---------|----------|--------|
| **DFS** | Start → 1 → 4 → 11 → 15 → 16 → (back×3) → 5 → 6 → 3 → 7 → 8 → 9 → (back×4) → 2 → 10 → 12 → 13 → 14 | 클릭 16 + back 7 = **23** |
| **BFS** | Start → 1 → 2 → 3 → 4 → 5 → 6 → 10 → 11 → 7 → 8 → 9 → 12 → 13 → 14 → 15 → 16 | 클릭 16 + nav ~15 = **~31** |
| **GREEDY_BFS** | Start → 1 → 4 → 5 → 6 → (nav) → 2 → 10 → 11 → 12 → 13 → 14 → (nav) → 3 → 7 → 8 → 9 → (nav) → 15 → 16 | 클릭 16 + nav ~10 = **~26** |
| **GREEDY_DFS** | Start → 1 → 4 → 11 → 15 → 16 → (nav) → 5 → 6 → 3 → 7 → 8 → 9 → (nav) → 2 → 10 → 12 → 13 → 14 | 클릭 16 + nav ~6 = **~22** |

---

## 5. 메모리 구조

MobileGPT는 학습한 내용을 `Server/memory/` 폴더에 저장합니다:

```
memory/
├── apps.csv                   # 전체 앱 목록 (이름, 패키지, 설명, 임베딩)
├── {앱_이름}/
│   ├── tasks.csv              # 학습된 작업 목록 및 실행 경로
│   ├── pages.csv              # 페이지(화면) 정보 및 서브태스크
│   ├── hierarchy.csv          # 화면 계층 구조 + OpenAI 임베딩 벡터
│   └── pages/
│       ├── 0/                 # 페이지 0
│       │   ├── subtasks.csv       # 학습된 서브태스크 (사용법 포함)
│       │   ├── available_subtasks.csv  # 발견된 서브태스크 (탐색 상태)
│       │   ├── actions.csv        # 일반화된 액션 시퀀스
│       │   └── screen/            # 화면 캡처
│       │       ├── screenshot.jpg
│       │       ├── raw.xml
│       │       ├── parsed.xml
│       │       ├── html.xml
│       │       └── hierarchy.xml
│       ├── 1/                 # 페이지 1
│       └── ...
└── log/                       # 실행 로그
    └── {앱_이름}/{작업명}/{타임스탬프}/
        ├── screenshots/       # 스크린샷
        └── xmls/              # XML 화면 구조
```

### 메모리 관리 클래스

| 클래스 | 파일 | 역할 |
|-------|------|------|
| **Memory** | `memory_manager.py` | 전체 메모리 관리, 작업/페이지 DB |
| **PageManager** | `page_manager.py` | 페이지별 서브태스크/액션 관리 |
| **NodeManager** | `node_manager.py` | 화면 구조 매칭, 유사 페이지 검색 |

### CSV 스키마

**tasks.csv** - 학습된 작업 경로
```csv
name,path
send_message,"{\"0\": [\"search_contact\"], \"1\": [\"select_contact\"], \"2\": [\"input_message\", \"send\"]}"
```

**subtasks.csv** - 학습된 서브태스크
```csv
name,start,end,description,usage,parameters,example
search_contact,0,1,연락처 검색,검색 버튼 클릭 후 이름 입력,"{\"query\":\"검색할 이름\"}","{\"query\":\"John\"}"
```

**available_subtasks.csv** - 발견된 서브태스크 (탐색 상태 포함)
```csv
name,description,parameters,exploration
search_contact,연락처 검색,"{\"query\":\"string\"}",explored
open_drawer,네비게이션 드로어 열기,"{}",unexplored
```

**hierarchy.csv** - 화면 임베딩 (유사도 검색용)
```csv
index,screen,embedding
0,"<hierarchy_xml>","[0.123, -0.456, ...]"  # OpenAI text-embedding-3-small 벡터
```

---

## 6. 벤치마크 데이터셋

### 데이터셋 구조

```
Benchmark Dataset/
├── <app1>/
│   ├── <task1>/
│   │   ├── user_instruction1.json
│   │   └── user_instruction2.json
│   ├── <task2>/
│   │   └── ...
│   ├── Screenshots/
│   │   └── <index>.png
│   └── Xmls/
│       └── <index>.xml
├── <app2>/
└── ...
```

**포함된 앱**: YT Music, Uber Eats, Twitter, TripAdvisor, Telegram, Microsoft To-Do, Google Dialer, Gmail

### JSON 구조

```json
{
    "instruction": "<사용자 명령어>",
    "steps": [
        {
            "step": "<단계 번호>",
            "HTML representation": "<HTML 형식 화면 표현>",
            "action": {
                "name": "<액션 이름>",
                "args": {
                    "index": "<UI 인덱스>"
                }
            },
            "screenshot": "<스크린샷 파일명>",
            "xml": "<XML 파일명>"
        }
    ]
}
```

---

## 7. 아키텍처

상세한 시스템 아키텍처는 [ARCHITECTURE.md](ARCHITECTURE.md)를 참조하세요.

**주요 내용:**
- 시스템 개요 및 4단계 인지 프로세스
- 디렉토리 구조
- 핵심 클래스 (Server, Explorer, AutoExplorer)
- **LangGraph Task Graph** (TaskState, ExploreState, 노드별 역할)
- 에이전트 파이프라인 상세
- 메모리 시스템 클래스 다이어그램
- 탐색 알고리즘 상세 분석 (DFS, BFS, GREEDY_BFS, GREEDY_DFS)
- 통신 프로토콜
- CSV 스키마 상세

---

## 8. 주의사항 및 라이선스

### 주의사항

- **연구용 소프트웨어**: 예상치 못한 동작(자동 결제, 계정 해지 등)이 발생할 수 있으므로 주의하세요.
- **API 비용**: 작업당 평균 약 $0.13 (약 13k 토큰) 소요됩니다.
- **메모리 수정**: `Server/memory/` 폴더에서 학습된 내용을 수동으로 수정할 수 있습니다.
- **언어 설정**: 스마트폰 언어를 영어로 설정하는 것을 권장합니다.

### 로그 확인

실행 중 서버 콘솔에 다음과 같은 로그가 출력됩니다:

- **파란색**: Explore, Select, Derive 단계 진행
- **노란색**: GPT 입력 프롬프트
- **초록색**: GPT 출력 응답

### 라이선스

이 프로젝트는 연구 목적으로 제공됩니다.

