import argparse
import os
import sys

from dotenv import load_dotenv

from server import Server
from server_explore import Explorer
from server_auto_explore import AutoExplorer
from server_inference import InferenceServer

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

# GPT-5 alias
os.environ["gpt_5"] = "gpt-5.2-chat-latest"

os.environ["MOBILEGPT_USER_NAME"] = "user"


def main():
    parser = argparse.ArgumentParser(description='MobileGPT Server')
    parser.add_argument(
        '--mode',
        choices=['task', 'explore', 'auto_explore', 'inference'],
        default='inference',
        help='Server mode (default: inference)'
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
    # - task: Execute tasks using learned memory
    # - explore: Manual exploration for screen structure learning
    # - auto_explore: Automatic UI exploration using algorithms
    # - inference: LangGraph-based intelligent subtask selection

    if args.mode == 'task':
        server = Server(host=server_ip, port=server_port)
        server.open()

    elif args.mode == 'explore':
        explorer = Explorer(host=server_ip, port=server_port)
        explorer.open()

    elif args.mode == 'auto_explore':
        # Exploration algorithm:
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

    elif args.mode == 'inference':
        # LangGraph-based inference server
        # Automatically selects and verifies subtasks using multi-agent system
        inference_server = InferenceServer(
            host=server_ip,
            port=server_port
        )
        inference_server.open()


if __name__ == '__main__':
    main()
