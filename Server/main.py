import argparse
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
os.environ["GUIDELINE_AGENT_GPT_VERSION"] = "gpt-5.2-chat-latest"
os.environ["VERIFY_AGENT_GPT_VERSION"] = "gpt-5.2-chat-latest"


def main():
    parser = argparse.ArgumentParser(description='MobileGPT Server')
    parser.add_argument(
        '--mode',
        choices=['task', 'explore', 'auto_explore'],
        default='task',
        help='Server mode (default: task)'
    )
    parser.add_argument(
        '--algorithm',
        choices=['DFS', 'BFS', 'GREEDY_BFS', 'GREEDY_DFS'],
        default='GREEDY_BFS',
        help='Exploration algorithm for auto_explore mode (default: GREEDY_BFS)'
    )
    parser.add_argument(
        '--port',
        type=int,
        default=12345,
        help='Server port (default: 12345)'
    )
    args = parser.parse_args()

    server_ip = "0.0.0.0"
    server_port = args.port

    # Server mode selection
    # - task: Execute tasks using LangGraph multi-agent system
    # - explore: Manual exploration for screen structure learning
    # - auto_explore: Automatic UI exploration using LangGraph algorithms

    if args.mode == 'task':
        # LangGraph-based task execution with intelligent subtask selection
        server = Server(host=server_ip, port=server_port)
        server.open()

    elif args.mode == 'explore':
        explorer = Explorer(host=server_ip, port=server_port)
        explorer.open()

    elif args.mode == 'auto_explore':
        # Exploration algorithm (all use LangGraph):
        # - DFS: Depth-first search, explores one path fully then backtracks
        # - BFS: Breadth-first search, explores all UI at same level first
        # - GREEDY_BFS: BFS to nearest unexplored subtask (shortest path)
        # - GREEDY_DFS: DFS to deepest unexplored subtask (depth priority)
        auto_explorer = AutoExplorer(
            host=server_ip,
            port=server_port,
            algorithm=args.algorithm
        )
        auto_explorer.open()


if __name__ == '__main__':
    main()
