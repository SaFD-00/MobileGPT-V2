"""Automatic exploration server for app UI discovery using LangGraph."""

import os
import socket
import threading
import traceback
import uuid
from datetime import datetime
from typing import Dict, List, Optional, Tuple

from agents.app_agent import AppAgent
from agents.explore_agent import ExploreAgent
from graphs.explore_graph import compile_explore_graph
from handlers.message_handlers import (
    MessageType,
    handle_app_list,
    handle_package_name,
    handle_screenshot,
    handle_external_app,
)
from memory.memory_manager import Memory
from screenParser.Encoder import xmlEncoder
from utils.network import get_local_ip, recv_xml_with_package, send_json_response
from loguru import logger


class AutoExplorer:
    """Server for automatic app exploration using LangGraph.

    Uses LangGraph multi-agent system for intelligent exploration:
    1. DiscoverNode: Find and learn new screens
    2. ExploreActionNode: Determine next exploration action
       - DFS, BFS, GREEDY algorithms
    """

    DEFAULT_HOST = '0.0.0.0'
    DEFAULT_PORT = 12345
    DEFAULT_BUFFER_SIZE = 4096

    def __init__(
        self,
        host: str = DEFAULT_HOST,
        port: int = DEFAULT_PORT,
        buffer_size: int = DEFAULT_BUFFER_SIZE,
        memory_directory: str = './memory',
        algorithm: str = "DFS",
        vision_enabled: bool = True
    ):
        """Initialize auto explorer with exploration algorithm.

        Args:
            host: Server host address
            port: Server port number
            buffer_size: Socket buffer size
            memory_directory: Base directory for logs
            algorithm: Exploration algorithm ("DFS", "BFS", "GREEDY")
            vision_enabled: Enable Vision mode (screenshots sent to LLM)
        """
        self.host = host
        self.port = port
        self.buffer_size = buffer_size
        self.memory_directory = memory_directory
        self.algorithm = algorithm
        self.vision_enabled = vision_enabled

        # Compile LangGraph explore graph
        # Note: checkpointer=False because Memory/ExploreAgent are not serializable
        self._explore_graph = compile_explore_graph(checkpointer=False)

        # Session states for each connection
        self._sessions: Dict[str, dict] = {}

        self._ensure_directory(self.memory_directory)

    def open(self) -> None:
        """Start server and listen for client connections.

        Creates TCP socket, binds to configured address, and spawns
        threads for each client connection.
        """
        real_ip = get_local_ip()

        server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server.bind((self.host, self.port))
        server.listen()

        self._log_server_start(real_ip)
        self._accept_clients(server)

    def _log_server_start(self, real_ip: str) -> None:
        """Log server startup information."""
        vision_status = "Vision+Text" if self.vision_enabled else "Text-only"
        logger.error(f"AutoExplorer is listening on {real_ip}:{self.port} (algorithm: {self.algorithm}, vision: {vision_status})")

    def _accept_clients(self, server: socket.socket) -> None:
        """Accept and handle client connections in separate threads."""
        while True:
            client_socket, client_address = server.accept()
            client_thread = threading.Thread(
                target=self.handle_client,
                args=(client_socket, client_address)
            )
            client_thread.start()

    def _ensure_directory(self, path: str) -> None:
        """Create directory if it doesn't exist."""
        if not os.path.exists(path):
            os.makedirs(path)

    def _handle_disconnection(
        self,
        client_socket: socket.socket,
        client_address: Tuple[str, int]
    ) -> None:
        """Handle client disconnection."""
        logger.error(f"Connection closed by {client_address}")
        client_socket.close()

    def handle_client(
        self,
        client_socket: socket.socket,
        client_address: Tuple[str, int]
    ) -> None:
        """Handle client connection for automatic exploration.

        Args:
            client_socket: Connected client socket
            client_address: Client address tuple (IP, port)
        """
        logger.info(f"Connected to Client: {client_address}")

        log_directory = self.memory_directory
        app_agent = AppAgent()
        screen_parser = xmlEncoder()
        screen_count = 0
        screens: List[dict] = []

        # Session state (replaces MobileGPT instance)
        session_id: Optional[str] = None
        memory: Optional[Memory] = None
        explore_agent: Optional[ExploreAgent] = None
        app_name: Optional[str] = None

        while True:
            logger.debug(f"Waiting for message... (screen_count: {screen_count})")
            raw_message_type = client_socket.recv(1)
            logger.debug(f"Received 1 byte: {raw_message_type}")

            if not raw_message_type:
                self._handle_disconnection(client_socket, client_address)
                return

            message_type = raw_message_type.decode('utf-8')
            logger.debug(f"Message type: '{message_type}' (screen_count: {screen_count})")

            if message_type == MessageType.APP_LIST:
                handle_app_list(client_socket, app_agent)

            elif message_type == MessageType.APP_PACKAGE:
                log_directory, memory, explore_agent, app_name, session_id = self._handle_app_init(
                    client_socket, app_agent, screen_parser
                )

            elif message_type == MessageType.XML:
                if not memory or not explore_agent:
                    logger.error("Error: memory or explore_agent not initialized")
                    continue

                result = self._handle_xml_exploration(
                    client_socket, screen_parser, memory, explore_agent,
                    app_name, session_id, screens, log_directory, screen_count
                )
                if result is None:
                    break
                screen_count = result

            elif message_type == MessageType.SCREENSHOT:
                logger.info(f"Receiving screenshot for screen #{screen_count}")
                screenshot_path = handle_screenshot(
                    client_socket, self.buffer_size,
                    log_directory, screen_count
                )
                # Save screenshot path to session (for Vision API)
                if session_id and session_id in self._sessions:
                    self._sessions[session_id]["last_screenshot_path"] = screenshot_path

            elif message_type == MessageType.EXTERNAL_APP:
                external_info = handle_external_app(client_socket)
                if external_info and session_id and memory:
                    self._handle_external_app_cleanup(memory, session_id, external_info)

            elif message_type == MessageType.FINISH:
                self._handle_finish(client_socket, screens)

            else:
                logger.error(f"Unknown message type: {message_type}")

    def _handle_app_init(
        self,
        client_socket: socket.socket,
        app_agent: AppAgent,
        screen_parser: xmlEncoder
    ) -> Tuple[str, Optional[Memory], Optional[ExploreAgent], Optional[str], Optional[str]]:
        """Initialize exploration for an app.

        Returns:
            Tuple of (log_directory, memory, explore_agent, app_name, session_id)
        """
        package_name, app_name = handle_package_name(client_socket, app_agent)

        if not package_name:
            return self.memory_directory, None, None, None, None

        # Create timestamped log directory
        dt_string = datetime.now().strftime("%Y_%m_%d %H:%M:%S")
        log_directory = f"{self.memory_directory}/log/{app_name}/hardcode/{dt_string}/"
        screen_parser.init(log_directory)

        # Initialize memory and explore_agent (replaces mobile_gpt.init_explore)
        memory = Memory(app_name, "hardcode", "hardcode")
        explore_agent = ExploreAgent(memory)
        session_id = str(uuid.uuid4())

        # Initialize session state for exploration persistence
        self._sessions[session_id] = {
            "page_index": -1,
            "visited_pages": set(),
            "explored_subtasks": {},
            "exploration_stack": [],
            "exploration_queue": [],
            "subtask_graph": {},
            "back_edges": {},
            "unexplored_subtasks": {},
            "traversal_path": [],
            "navigation_plan": [],
            "last_action_was_back": False,
        }

        logger.info(f"Initialized exploration for app '{app_name}' with {self.algorithm} algorithm")

        return log_directory, memory, explore_agent, app_name, session_id

    def _handle_xml_exploration(
        self,
        client_socket: socket.socket,
        screen_parser: xmlEncoder,
        memory: Memory,
        explore_agent: ExploreAgent,
        app_name: Optional[str],
        session_id: Optional[str],
        screens: List[dict],
        log_directory: str,
        screen_count: int
    ) -> Optional[int]:
        """Process XML and perform auto exploration using LangGraph.

        Returns:
            Updated screen_count or None to stop
        """
        try:
            logger.info(f"Receiving XML for screen #{screen_count}")
            xml_path = f"{log_directory}/xmls/{screen_count}.xml"
            raw_xml, top_package, target_package = recv_xml_with_package(
                client_socket, self.buffer_size, xml_path
            )
            logger.info(f"XML received - top: {top_package}, target: {target_package}")

            # Handle empty top_package (no application window found - transition state)
            if not top_package or not raw_xml.strip():
                logger.warning("No application window found, requesting retry")
                send_json_response(client_socket, {"name": "retry", "parameters": {}})
                return screen_count

            # Handle package mismatch (overlay or external app)
            if top_package and target_package and top_package != target_package:
                logger.warning(f"Detected '{top_package}' instead of '{target_package}'")

                # Record external app subtask
                state = self._sessions.get(session_id, {})
                last_page = state.get("last_explored_page_index")
                last_subtask = state.get("last_explored_subtask_name")
                last_ui = state.get("last_explored_ui_index")

                if last_page is not None and last_subtask and last_ui is not None:
                    self._record_external_app_subtask(
                        memory, last_page, last_subtask, last_ui, top_package
                    )

                # Send back action to return to target app
                send_json_response(client_socket, {"name": "back", "parameters": {}})
                return screen_count

            logger.info("XML received, parsing...")

            parsed_xml, hierarchy_xml, encoded_xml = screen_parser.encode(
                raw_xml, screen_count
            )
            logger.info("XML parsed successfully")

            screens.append({
                "parsed": parsed_xml,
                "hierarchy": hierarchy_xml,
                "encoded": encoded_xml
            })
            screen_count += 1

            # Run LangGraph exploration
            config = {"configurable": {"thread_id": session_id}}

            # Load previous session state
            prev_state = self._sessions.get(session_id, {}) if session_id else {}

            logger.debug("Starting LangGraph exploration...")
            logger.warning(f"prev_state explored_subtasks = {prev_state.get('explored_subtasks', {})}")
            logger.warning(f"prev_state visited_pages = {prev_state.get('visited_pages', set())}")

            # Get screenshot path for Vision API (only when vision is enabled)
            screenshot_path = prev_state.get("last_screenshot_path") if self.vision_enabled else None
            if screenshot_path:
                logger.debug(f"Using screenshot: {screenshot_path}")

            result = self._explore_graph.invoke({
                "session_id": session_id,
                "app_name": app_name,
                "algorithm": self.algorithm,
                "current_xml": parsed_xml,
                "hierarchy_xml": hierarchy_xml,
                "encoded_xml": encoded_xml,
                "screenshot_path": screenshot_path,  # Screenshot path for Vision API
                "memory": memory,
                "explore_agent": explore_agent,
                # Load persisted state from session (or use defaults)
                "page_index": -1,  # Always -1 for new screen (let discover find it)
                "visited_pages": prev_state.get("visited_pages", set()),
                "exploration_stack": prev_state.get("exploration_stack", []),
                "exploration_queue": prev_state.get("exploration_queue", []),
                "subtask_graph": prev_state.get("subtask_graph", {}),
                "back_edges": prev_state.get("back_edges", {}),
                "unexplored_subtasks": prev_state.get("unexplored_subtasks", {}),
                "traversal_path": prev_state.get("traversal_path", []),
                "navigation_plan": prev_state.get("navigation_plan", []),
                "explored_subtasks": prev_state.get("explored_subtasks", {}),
                "last_action_was_back": prev_state.get("last_action_was_back", False),
                "last_back_from_page": prev_state.get("last_back_from_page"),
                # Pass last explored info for end_page update in discover_node
                "last_explored_page_index": prev_state.get("last_explored_page_index"),
                "last_explored_subtask_name": prev_state.get("last_explored_subtask_name"),
                "last_explored_ui_index": prev_state.get("last_explored_ui_index"),
                # Subtask Graph: action history for description generation
                "action_history": prev_state.get("action_history", []),
                "before_xml": prev_state.get("before_xml"),
                "before_screenshot_path": prev_state.get("before_screenshot_path"),
            }, config=config)

            # Save exploration state back to session for next invocation
            logger.warning(f"result explored_subtasks = {result.get('explored_subtasks', 'NOT_IN_RESULT')}")
            logger.warning(f"result visited_pages = {result.get('visited_pages', 'NOT_IN_RESULT')}")
            if session_id:
                self._sessions[session_id] = {
                    "page_index": result.get("page_index", -1),
                    "visited_pages": result.get("visited_pages", set()),
                    "explored_subtasks": result.get("explored_subtasks", {}),
                    "exploration_stack": result.get("exploration_stack", []),
                    "exploration_queue": result.get("exploration_queue", []),
                    "subtask_graph": result.get("subtask_graph", {}),
                    "back_edges": result.get("back_edges", {}),
                    "unexplored_subtasks": result.get("unexplored_subtasks", {}),
                    "traversal_path": result.get("traversal_path", []),
                    "navigation_plan": result.get("navigation_plan", []),
                    "last_action_was_back": result.get("last_action_was_back", False),
                    "last_back_from_page": result.get("last_back_from_page"),
                    # Track last explored subtask for end_page update
                    "last_explored_page_index": result.get("last_explored_page_index"),
                    "last_explored_subtask_name": result.get("last_explored_subtask_name"),
                    "last_explored_ui_index": result.get("last_explored_ui_index"),
                    # Subtask Graph: action history for description generation
                    "action_history": result.get("action_history", []),
                    "before_xml": result.get("before_xml"),
                    "before_screenshot_path": result.get("before_screenshot_path"),
                }

            # Extract result
            action = result.get("action")
            status = result.get("status", "unknown")

            logger.info(f"Exploration result: status={status}")

            if action is not None:
                logger.debug(f"Auto exploration action: {action}")
                send_json_response(client_socket, action)
                logger.debug("Action sent to client, waiting for next message...")
                return screen_count

            # Exploration complete
            if status == "exploration_complete":
                logger.info("Exploration complete, no more actions")
                return None

            # No action but not complete - shouldn't happen often
            logger.warning("No action from exploration")
            return screen_count

        except Exception as e:
            logger.error(f"Error processing XML: {str(e)}")
            logger.error(traceback.format_exc())
            # Send back action to prevent getting stuck
            send_json_response(client_socket, {"name": "back", "parameters": {}})
            return screen_count

    def _handle_finish(
        self,
        client_socket: socket.socket,
        screens: List[dict]
    ) -> None:
        """Handle exploration finish message."""
        logger.info(f"Auto exploration finished. Total screens explored: {len(screens)}")
        finish_message = {
            "status": "exploration_complete",
            "screens_explored": len(screens)
        }
        send_json_response(client_socket, finish_message)

    def _record_external_app_subtask(
        self,
        memory: Memory,
        page_index: int,
        subtask_name: str,
        trigger_ui_index: int,
        external_package: str
    ) -> None:
        """Record external app transition as a subtask.

        - subtasks.csv: end_page=-1, guideline=EXTERNAL_APP: {pkg}
        - actions.csv: click + immediate finish

        Args:
            memory: Memory manager instance
            page_index: Page where the subtask was triggered
            subtask_name: Name of the subtask
            trigger_ui_index: UI element index that triggered the transition
            external_package: Package name of the external app
        """
        logger.warning(f"Recording external app subtask: {subtask_name} -> {external_package}")

        if page_index not in memory.page_managers:
            memory.init_page_manager(page_index)

        page_manager = memory.page_managers.get(page_index)
        if not page_manager:
            logger.error(f"Failed to get page manager for page {page_index}")
            return

        # Record to subtasks.csv with end_page=-1
        subtask_data = {
            'name': subtask_name,
            'description': f'Opens external app ({external_package})',
            'parameters': {}
        }
        guideline = f'EXTERNAL_APP: {external_package}'

        page_manager.save_subtask(
            subtask_data, {}, guideline,
            trigger_ui_index=trigger_ui_index,
            start_page=page_index,
            end_page=-1
        )

        # Add finish action to actions.csv (step 1)
        finish_action = {
            "name": "finish",
            "parameters": {
                "reason": "external_app",
                "package": external_package
            }
        }
        page_manager.save_action(
            subtask_name, trigger_ui_index, 1, finish_action, {},
            start_page=-1, end_page=-1
        )

        logger.info(f"External app subtask recorded: {subtask_name}")

    def _handle_external_app_cleanup(
        self,
        memory: Memory,
        session_id: str,
        external_info: dict
    ) -> None:
        """Cleanup subtask data when external app is detected.

        When the client detects a transition to an external app (e.g., Camera,
        Photos), this method removes the subtask that triggered the transition
        from all CSV files and the Subtask Graph.

        Args:
            memory: Memory manager instance
            session_id: Current session ID
            external_info: Dict with detected_package, target_package, timestamp
        """
        state = self._sessions.get(session_id, {})
        page_idx = state.get("last_explored_page_index")
        subtask = state.get("last_explored_subtask_name")
        ui_idx = state.get("last_explored_ui_index")

        detected_pkg = external_info.get("detected_package", "unknown")
        target_pkg = external_info.get("target_package", "unknown")

        logger.warning(f"Detected '{detected_pkg}' while exploring '{target_pkg}'")

        if page_idx is None or subtask is None:
            logger.warning("No last explored subtask to cleanup")
            return

        logger.warning(f"Cleaning up subtask '{subtask}' (page={page_idx}, ui_idx={ui_idx})")

        # Delete subtask from CSV files and Subtask Graph
        memory.delete_subtask(
            page_index=page_idx,
            subtask_name=subtask,
            trigger_ui_index=ui_idx if ui_idx is not None else -1,
            reason="external_app"
        )

        # Clear last explored info from session state
        self._sessions[session_id]["last_explored_page_index"] = None
        self._sessions[session_id]["last_explored_subtask_name"] = None
        self._sessions[session_id]["last_explored_ui_index"] = None

        logger.info(f"Cleanup complete for subtask '{subtask}'")
