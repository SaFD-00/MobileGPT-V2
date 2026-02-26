import argparse
import os
import sys

from dotenv import load_dotenv

sys.path.append('.')
load_dotenv()

from utils.logging import setup_logging
from loguru import logger

# ============================================================================
# GPT Model Configuration (GPT-5.2 Only)
# ============================================================================
# Supported models:
#   - gpt-5.2            : GPT-5.2 Thinking (reasoning model, complex tasks)
#   - gpt-5.2-mini       : GPT-5.2 Mini (fast chat, optimized for speed)
# ============================================================================

# Agent-specific model configuration
os.environ["TASK_AGENT_GPT_VERSION"] = "gpt-5.2"
os.environ["APP_AGENT_GPT_VERSION"] = "gpt-5.2"
os.environ["EXPLORE_AGENT_GPT_VERSION"] = "gpt-5.2"
os.environ["SELECT_AGENT_GPT_VERSION"] = "gpt-5.2"
os.environ["DERIVE_AGENT_GPT_VERSION"] = "gpt-5.2"
os.environ["VERIFY_AGENT_GPT_VERSION"] = "gpt-5.2"
os.environ["FILTER_AGENT_GPT_VERSION"] = "gpt-5.2"
os.environ["HISTORY_AGENT_GPT_VERSION"] = "gpt-5.2"
os.environ["PLANNER_AGENT_GPT_VERSION"] = "gpt-5.2"
os.environ["SUMMARY_AGENT_GPT_VERSION"] = "gpt-5.2"


def main():
    parser = argparse.ArgumentParser(description='MobileGPT Server')
    parser.add_argument(
        '--mode',
        choices=['task', 'auto_explore'],
        default='task',
        help='Server mode (default: task)'
    )
    parser.add_argument(
        '--algorithm',
        choices=['DFS', 'BFS', 'GREEDY'],
        default='GREEDY',
        help='Exploration algorithm for auto_explore mode (default: GREEDY)'
    )
    parser.add_argument(
        '--port',
        type=int,
        default=12345,
        help='Server port (default: 12345)'
    )

    # Vision mode: --vision (default) or --no-vision (text-only)
    vision_group = parser.add_mutually_exclusive_group()
    vision_group.add_argument(
        '--vision',
        action='store_true',
        default=True,
        dest='vision',
        help='Enable Vision mode: screenshot + text (default)'
    )
    vision_group.add_argument(
        '--no-vision',
        action='store_false',
        dest='vision',
        help='Disable Vision mode: text-only (screenshots saved but not sent to LLM)'
    )

    args = parser.parse_args()

    # Setup logging
    log_file = os.path.join('./memory', 'server.log')
    os.makedirs('./memory', exist_ok=True)
    setup_logging(log_file)

    logger.info("MobileGPT-V2 starting...")
    logger.info(f"  Mode: {args.mode}")
    logger.info(f"  Port: {args.port}")
    logger.info(f"  Vision: {args.vision}")
    if args.mode == 'auto_explore':
        logger.info(f"  Algorithm: {args.algorithm}")

    from server import Server
    from server_auto_explore import AutoExplorer

    server_ip = "0.0.0.0"
    server_port = args.port

    if args.mode == 'task':
        server = Server(host=server_ip, port=server_port, vision_enabled=args.vision)
        server.open()

    elif args.mode == 'auto_explore':
        auto_explorer = AutoExplorer(
            host=server_ip,
            port=server_port,
            algorithm=args.algorithm,
            vision_enabled=args.vision
        )
        auto_explorer.open()


if __name__ == '__main__':
    main()
