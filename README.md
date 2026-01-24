# MobileGPT-V2

A LangGraph-based Multi-Agent Framework for Intelligent Mobile Automation

---

## 1. Introduction

### 1.1 Overview

MobileGPT-V2 is an intelligent automation system that performs complex tasks on Android devices through a multi-agent architecture. Building upon the foundation of the original MobileGPT research, this framework introduces a novel **Auto-Explore** module that enables autonomous UI exploration and learning, significantly reducing the manual effort required for app knowledge acquisition.

The system leverages LLM-based multi-agent coordination through LangGraph workflows, enabling sophisticated task planning, execution, and adaptive replanning capabilities.

### 1.2 Key Contributions

1. **Auto-Explore Module**: Autonomous UI exploration with three configurable algorithms (DFS, BFS, GREEDY)
2. **Subtask Transition Graph (STG)**: Explicit graph-based representation of app navigation structure
3. **Adaptive Replanning**: Dynamic path adjustment based on execution verification
4. **Vision-Enhanced Perception**: Screenshot-based UI recognition via Vision API integration
5. **Safety Guardrails**: Automatic filtering of potentially dangerous actions during exploration

---

## 2. System Architecture

### 2.1 Multi-Agent Framework

MobileGPT-V2 employs a collaborative multi-agent architecture where specialized agents handle distinct aspects of task execution:

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
│  │  │  │  Supervisor → Memory →    │  │  │ XML   │   Client    │        │
│  │  │  │  Planner → Selector →     │  │  │ JSON  │             │        │
│  │  │  │  Verifier → Deriver       │  │  │ Image │             │        │
│  │  │  └───────────────────────────┘  │  │       │             │        │
│  │  │  ┌───────────────────────────┐  │  │       │  ┌───────┐  │        │
│  │  │  │  Explore Graph            │  │  │       │  │Access-│  │        │
│  │  │  │  Supervisor → Discover →  │  │  │       │  │ibility│  │        │
│  │  │  │  ExploreAction            │  │  │       │  │Service│  │        │
│  │  │  └───────────────────────────┘  │  │       │  └───────┘  │        │
│  │  └─────────────────────────────────┘  │       └─────────────┘        │
│  │                                       │                              │
│  │  ┌─────────────────────────────────┐  │                              │
│  │  │       Memory Manager            │  │                              │
│  │  │  ┌───────┐ ┌───────┐ ┌───────┐  │  │                              │
│  │  │  │ STG   │ │ Pages │ │Subtask│  │  │                              │
│  │  │  │.json  │ │ .csv  │ │ .csv  │  │  │                              │
│  │  │  └───────┘ └───────┘ └───────┘  │  │                              │
│  │  └─────────────────────────────────┘  │                              │
│  └───────────────────────────────────────┘                              │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

### 2.2 Auto-Explore Module (Unique Contribution)

The Auto-Explore module is MobileGPT-V2's distinctive feature that enables **autonomous app structure learning** without manual intervention. The system automatically:

1. **Discovers** new screens and extracts available subtasks
2. **Explores** each subtask systematically using configurable algorithms
3. **Records** navigation patterns in the Subtask Transition Graph (STG)
4. **Filters** unsafe actions through built-in guardrails

**Exploration Algorithms**:

| Algorithm | Strategy | Use Case |
|-----------|----------|----------|
| **DFS** | Depth-first, stack-based | Deep exploration of single paths |
| **BFS** | Breadth-first, queue-based | Uniform coverage of current level |
| **GREEDY** | Shortest-path to nearest unexplored | Efficient global coverage (recommended) |

### 2.3 Core Pipeline

The system operates through a **6-step execution pipeline**:

```
Auto-Explore → Plan → Select → Derive → Verify → Recall
```

| Step | Purpose | Agent/Node |
|------|---------|------------|
| **Auto-Explore** | Autonomous UI learning | ExploreAgent |
| **Plan** | STG-based path planning (UICompass) | PlannerAgent |
| **Select** | Next subtask selection | SelectAgent |
| **Derive** | Action generation | DeriveAgent |
| **Verify** | Result verification & replanning | VerifyAgent |
| **Recall** | Memory retrieval | MemoryNode |

---

## 3. Agents & Roles

MobileGPT-V2 employs specialized agents for different aspects of task execution:

| Agent | Responsibility |
|-------|----------------|
| **ExploreAgent** | UI recognition, subtask extraction, element localization |
| **PlannerAgent** | Goal analysis, BFS path planning, route optimization |
| **SelectAgent** | Subtask selection, context-aware decision making |
| **DeriveAgent** | Action parameterization, UI element targeting |
| **VerifyAgent** | Execution verification, PROCEED/SKIP/REPLAN decisions |
| **MemoryManager** | STG management, page matching, knowledge persistence |

---

## 4. Getting Started

### 4.1 Requirements

**Server**:
- Python 3.10+
- OpenAI API Key (GPT-5.2 recommended for Vision capabilities)

**Android Client**:
- Android 13+ (API 33)
- Accessibility Service permission

### 4.2 Installation

```bash
# Clone repository
git clone https://github.com/user/MobileGPT-V2.git
cd MobileGPT-V2

# Install Python dependencies
pip install -r requirements.txt

# Set environment variable
export OPENAI_API_KEY="your-api-key"
```

### 4.3 Android Client Setup

1. Open `App_Auto_Explorer` project in Android Studio
2. Configure server IP in `MobileGPTGlobal.java`:
   ```java
   public static final String HOST_IP = "192.168.0.9";  // Your server IP
   public static final int HOST_PORT = 12345;
   ```
3. Build and install on device
4. Enable Accessibility Service: Settings → Accessibility → MobileGPT Auto Explorer

---

## 5. Usage Modes

### 5.1 Auto-Explore Mode

Autonomous UI exploration and STG construction:

```bash
# DFS exploration
python main.py --mode auto_explore --algorithm DFS --port 12345

# BFS exploration
python main.py --mode auto_explore --algorithm BFS --port 12345

# GREEDY exploration (recommended)
python main.py --mode auto_explore --algorithm GREEDY --port 12345
```

### 5.2 Task Mode

Execute user tasks using learned knowledge:

```bash
python main.py --mode task --port 12345
```

### 5.3 Manual Explore Mode

Interactive exploration with manual control:

```bash
python main.py --mode explore --port 12345
```

---

## 6. Configuration

### Agent Model Settings

Configure LLM models in `Server/main.py`:

```python
os.environ["TASK_AGENT_GPT_VERSION"] = "gpt-5.2"
os.environ["EXPLORE_AGENT_GPT_VERSION"] = "gpt-5.2"
os.environ["PLANNER_AGENT_GPT_VERSION"] = "gpt-5.2"
os.environ["VERIFY_AGENT_GPT_VERSION"] = "gpt-5.2"
os.environ["SELECT_AGENT_GPT_VERSION"] = "gpt-5.2"
```

---

## 7. Project Structure

```
MobileGPT-V2/
├── Server/                      # Python server
│   ├── main.py                  # Entry point
│   ├── server.py                # Task mode server
│   ├── server_explore.py        # Manual explore server
│   ├── server_auto_explore.py   # Auto-explore server
│   ├── agents/                  # LLM agents
│   ├── graphs/                  # LangGraph definitions
│   ├── memory/                  # Memory management
│   └── utils/                   # Utilities
│
├── App_Auto_Explorer/           # Android client
└── requirements.txt             # Python dependencies
```

---

## 8. Citation

If you use MobileGPT-V2 in your research, please cite:

```bibtex
@software{mobilegpt-v2,
  title = {MobileGPT-V2: A LangGraph-based Multi-Agent Framework for Intelligent Mobile Automation},
  year = {2026},
  url = {https://github.com/user/MobileGPT-V2}
}
```

---

## 9. Related Work

- **MobileGPT**: Original research on LLM-based mobile automation
- **LangGraph**: Framework for building stateful, multi-actor applications with LLMs

---

## 10. License

MIT License - See [LICENSE](LICENSE) for details.
