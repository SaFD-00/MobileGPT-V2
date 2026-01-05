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
# GPT Model Configuration
# ============================================================================
# Supported models (as of 2026):
#   - gpt-5.2       : Latest reasoning model (highest performance, highest cost)
#   - gpt-5         : Reasoning model (high performance)
#   - gpt-4.1       : General purpose model (balanced performance/cost)
#   - gpt-4.1-mini  : Lightweight model (fast, low cost)
#   - gpt-4.1-nano  : Ultra-lightweight model (fastest, lowest cost)
#
# You can customize each agent's model based on your needs.
# ============================================================================

# Agent-specific model configuration
os.environ["TASK_AGENT_GPT_VERSION"] = "gpt-5.2"
os.environ["APP_AGENT_GPT_VERSION"] = "gpt-5.2"
os.environ["SELECT_AGENT_HISTORY_GPT_VERSION"] = "gpt-5.2"
os.environ["EXPLORE_AGENT_GPT_VERSION"] = "gpt-5.2"
os.environ["SELECT_AGENT_GPT_VERSION"] = "gpt-5.2"
os.environ["DERIVE_AGENT_GPT_VERSION"] = "gpt-5.2"
os.environ["PARAMETER_FILLER_AGENT_GPT_VERSION"] = "gpt-5.2"
os.environ["ACTION_SUMMARIZE_AGENT_GPT_VERSION"] = "gpt-5.2"
os.environ["SUBTASK_MERGE_AGENT_GPT_VERSION"] = "gpt-5.2"

# Legacy model aliases (for backward compatibility)
os.environ["gpt_5"] = "gpt-5.2"
os.environ["gpt_4"] = "gpt-4.1"
os.environ["gpt_4_turbo"] = "gpt-4.1"
os.environ["gpt_3_5_turbo"] = "gpt-4.1-mini"

# Vision model
os.environ["vision_model"] = "gpt-5.2"
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
