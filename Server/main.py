import os
import sys

from dotenv import load_dotenv

from server import Server
from server_explore import Explorer
from server_auto_explore import AutoExplorer

# os.chdir('./MobileGPT_server')
sys.path.append('.')

load_dotenv()

# ============================================================================
# GPT Model Configuration (GPT-5.2 Only)
# ============================================================================
# Supported models:
#   - gpt-5.2            : GPT-5.2 Thinking (reasoning model, complex tasks)
#   - gpt-5.2-chat-latest: GPT-5.2 Instant (fast chat, optimized for speed)
# ============================================================================

# Agent-specific model configuration
os.environ["TASK_AGENT_GPT_VERSION"] = "gpt-5.2-chat-latest"
os.environ["APP_AGENT_GPT_VERSION"] = "gpt-5.2-chat-latest"
os.environ["SELECT_AGENT_HISTORY_GPT_VERSION"] = "gpt-5.2-chat-latest"
os.environ["EXPLORE_AGENT_GPT_VERSION"] = "gpt-5.2-chat-latest"
os.environ["SELECT_AGENT_GPT_VERSION"] = "gpt-5.2-chat-latest"
os.environ["DERIVE_AGENT_GPT_VERSION"] = "gpt-5.2-chat-latest"
os.environ["PARAMETER_FILLER_AGENT_GPT_VERSION"] = "gpt-5.2-chat-latest"
os.environ["ACTION_SUMMARIZE_AGENT_GPT_VERSION"] = "gpt-5.2-chat-latest"
os.environ["SUBTASK_MERGE_AGENT_GPT_VERSION"] = "gpt-5.2-chat-latest"

# GPT-5 alias
os.environ["gpt_5"] = "gpt-5.2-chat-latest"

# Vision model
os.environ["vision_model"] = "gpt-5.2-chat-latest"
os.environ["MOBILEGPT_USER_NAME"] = "user"


def main():
    server_ip = "0.0.0.0"
    server_port = 12345
    server_vision = False

    # Exploration algorithm: "DFS", "BFS", "GREEDY_BFS", "GREEDY_DFS"
    # - DFS: Depth-first search, explores one path fully then backtracks
    # - BFS: Breadth-first search, explores all UI at same level first
    # - GREEDY_BFS: BFS to nearest unexplored subtask (shortest path)
    # - GREEDY_DFS: DFS to deepest unexplored subtask (depth priority)
    exploration_algorithm = "GREEDY_BFS"

    # server = Server(host=server_ip, port=server_port)
    # server.open()

    # explorer = Explorer(host=server_ip, port=server_port)
    # explorer.open()

    auto_explorer = AutoExplorer(
        host=server_ip,
        port=server_port,
        algorithm=exploration_algorithm
    )
    auto_explorer.open()


if __name__ == '__main__':
    main()
