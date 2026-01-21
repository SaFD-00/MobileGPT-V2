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
from utils.network import get_local_ip, recv_xml, send_json_response
from utils.utils import log


class AutoExplorer:
    """Server for automatic app exploration using LangGraph.

    Uses LangGraph multi-agent system for intelligent exploration:
    1. DiscoverNode: Find and learn new screens
    2. ExploreActionNode: Determine next exploration action
       - DFS, BFS, GREEDY_BFS, GREEDY_DFS algorithms
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
        algorithm: str = "DFS"
    ):
        """Initialize auto explorer with exploration algorithm.

        Args:
            host: Server host address
            port: Server port number
            buffer_size: Socket buffer size
            memory_directory: Base directory for logs
            algorithm: Exploration algorithm ("DFS", "BFS", "GREEDY_BFS", "GREEDY_DFS")
        """
        self.host = host
        self.port = port
        self.buffer_size = buffer_size
        self.memory_directory = memory_directory
        self.algorithm = algorithm

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
        log(f"AutoExplorer is listening on {real_ip}:{self.port} (algorithm: {self.algorithm})", "red")

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
        log(f"Connection closed by {client_address}", 'red')
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
        print(f"Connected to Client: {client_address}")

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
            log(f"Waiting for message... (screen_count: {screen_count})", "magenta")
            raw_message_type = client_socket.recv(1)
            log(f"Received 1 byte: {raw_message_type}", "magenta")

            if not raw_message_type:
                self._handle_disconnection(client_socket, client_address)
                return

            message_type = raw_message_type.decode('utf-8')
            log(f"Message type: '{message_type}' (screen_count: {screen_count})", "cyan")

            if message_type == MessageType.APP_LIST:
                handle_app_list(client_socket, app_agent)

            elif message_type == MessageType.APP_PACKAGE:
                log_directory, memory, explore_agent, app_name, session_id = self._handle_app_init(
                    client_socket, app_agent, screen_parser
                )

            elif message_type == MessageType.XML:
                if not memory or not explore_agent:
                    log("Error: memory or explore_agent not initialized", "red")
                    continue

                result = self._handle_xml_exploration(
                    client_socket, screen_parser, memory, explore_agent,
                    app_name, session_id, screens, log_directory, screen_count
                )
                if result is None:
                    break
                screen_count = result

            elif message_type == MessageType.SCREENSHOT:
                log(f"Receiving screenshot for screen #{screen_count}", "blue")
                handle_screenshot(
                    client_socket, self.buffer_size,
                    log_directory, screen_count
                )
                log("Screenshot saved successfully", "green")

            elif message_type == MessageType.EXTERNAL_APP:
                external_info = handle_external_app(client_socket)
                if external_info and session_id and memory:
                    self._handle_external_app_cleanup(memory, session_id, external_info)

            elif message_type == MessageType.FINISH:
                self._handle_finish(client_socket, screens)

            else:
                log(f"Unknown message type: {message_type}", "red")

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

        log(f"Initialized exploration for app '{app_name}' with {self.algorithm} algorithm", "green")

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
            log(f"Receiving XML for screen #{screen_count}", "blue")
            xml_path = f"{log_directory}/xmls/{screen_count}.xml"
            raw_xml = recv_xml(client_socket, self.buffer_size, xml_path)
            log("XML received, parsing...", "blue")

            parsed_xml, hierarchy_xml, encoded_xml = screen_parser.encode(
                raw_xml, screen_count
            )
            log("XML parsed successfully", "blue")

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

            log("Starting LangGraph exploration...", "cyan")
            log(f":::DEBUG::: prev_state explored_subtasks = {prev_state.get('explored_subtasks', {})}", "yellow")
            log(f":::DEBUG::: prev_state visited_pages = {prev_state.get('visited_pages', set())}", "yellow")
            result = self._explore_graph.invoke({
                "session_id": session_id,
                "app_name": app_name,
                "algorithm": self.algorithm,
                "current_xml": parsed_xml,
                "hierarchy_xml": hierarchy_xml,
                "encoded_xml": encoded_xml,
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
                # Pass last explored info for end_page update in discover_node
                "last_explored_page_index": prev_state.get("last_explored_page_index"),
                "last_explored_subtask_name": prev_state.get("last_explored_subtask_name"),
                "last_explored_ui_index": prev_state.get("last_explored_ui_index"),
            }, config=config)

            # Save exploration state back to session for next invocation
            log(f":::DEBUG::: result explored_subtasks = {result.get('explored_subtasks', 'NOT_IN_RESULT')}", "yellow")
            log(f":::DEBUG::: result visited_pages = {result.get('visited_pages', 'NOT_IN_RESULT')}", "yellow")
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
                    # Track last explored subtask for end_page update
                    "last_explored_page_index": result.get("last_explored_page_index"),
                    "last_explored_subtask_name": result.get("last_explored_subtask_name"),
                    "last_explored_ui_index": result.get("last_explored_ui_index"),
                }

            # Extract result
            action = result.get("action")
            status = result.get("status", "unknown")

            log(f"Exploration result: status={status}", "green")

            if action is not None:
                log(f"Auto exploration action: {action}", "cyan")
                send_json_response(client_socket, action)
                log("Action sent to client, waiting for next message...", "cyan")
                return screen_count

            # Exploration complete
            if status == "exploration_complete":
                log("Exploration complete, no more actions", "green")
                return None

            # No action but not complete - shouldn't happen often
            log("No action from exploration", "yellow")
            return screen_count

        except Exception as e:
            log(f"Error processing XML: {str(e)}", "red")
            log(traceback.format_exc(), "red")
            # Send back action to prevent getting stuck
            send_json_response(client_socket, {"name": "back", "parameters": {}})
            return screen_count

    def _handle_finish(
        self,
        client_socket: socket.socket,
        screens: List[dict]
    ) -> None:
        """Handle exploration finish message."""
        log(f"Auto exploration finished. Total screens explored: {len(screens)}", "green")
        finish_message = {
            "status": "exploration_complete",
            "screens_explored": len(screens)
        }
        send_json_response(client_socket, finish_message)

    def _handle_external_app_cleanup(
        self,
        memory: Memory,
        session_id: str,
        external_info: dict
    ) -> None:
        """Cleanup subtask data when external app is detected.

        When the client detects a transition to an external app (e.g., Camera,
        Photos), this method removes the subtask that triggered the transition
        from all CSV files and the STG.

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

        log(f":::EXTERNAL_APP::: Detected '{detected_pkg}' while exploring '{target_pkg}'", "yellow")

        if page_idx is None or subtask is None:
            log(":::EXTERNAL_APP::: No last explored subtask to cleanup", "yellow")
            return

        log(f":::EXTERNAL_APP::: Cleaning up subtask '{subtask}' (page={page_idx}, ui_idx={ui_idx})", "yellow")

        # Delete subtask from CSV files and STG
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

        log(f":::EXTERNAL_APP::: Cleanup complete for subtask '{subtask}'", "green")
