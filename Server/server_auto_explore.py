"""Automatic exploration server for app UI discovery."""

import os
import socket
import threading
import traceback
from datetime import datetime
from typing import List, Optional, Tuple

from agents.app_agent import AppAgent
from handlers.message_handlers import (
    MessageType,
    handle_app_list,
    handle_package_name,
    handle_screenshot,
)
from mobilegpt import MobileGPT, Status
from screenParser.Encoder import xmlEncoder
from utils.network import get_local_ip, recv_xml, send_json_response
from utils.utils import log


class AutoExplorer:
    """Server for automatic app exploration using AI-driven navigation.

    Automatically explores app UI by discovering screens and
    interacting with elements using configurable algorithms.
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
            algorithm: Exploration algorithm ("DFS", "BFS", "GREEDY")
        """
        self.host = host
        self.port = port
        self.buffer_size = buffer_size
        self.memory_directory = memory_directory
        self.algorithm = algorithm

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
        mobile_gpt = MobileGPT(client_socket)
        app_agent = AppAgent()
        screen_parser = xmlEncoder()
        screen_count = 0
        screens: List[dict] = []
        last_action_was_back = False

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
                log_directory = self._handle_app_init(
                    client_socket, app_agent, screen_parser, mobile_gpt
                )

            elif message_type == MessageType.XML:
                result = self._handle_xml_exploration(
                    client_socket, screen_parser, mobile_gpt,
                    screens, log_directory, screen_count, last_action_was_back
                )
                if result is None:
                    break
                screen_count, last_action_was_back = result

            elif message_type == MessageType.SCREENSHOT:
                log(f"Receiving screenshot for screen #{screen_count}", "blue")
                handle_screenshot(
                    client_socket, self.buffer_size,
                    log_directory, screen_count
                )
                log("Screenshot saved successfully", "green")

            elif message_type == MessageType.FINISH:
                self._handle_finish(client_socket, screens)

            else:
                log(f"Unknown message type: {message_type}", "red")

    def _handle_app_init(
        self,
        client_socket: socket.socket,
        app_agent: AppAgent,
        screen_parser: xmlEncoder,
        mobile_gpt: MobileGPT
    ) -> str:
        """Initialize exploration for an app.

        Returns:
            str: Log directory path
        """
        package_name, app_name = handle_package_name(client_socket, app_agent)

        if not package_name:
            return self.memory_directory

        # Create timestamped log directory
        dt_string = datetime.now().strftime("%Y_%m_%d %H:%M:%S")
        log_directory = f"{self.memory_directory}/log/{app_name}/hardcode/{dt_string}/"
        screen_parser.init(log_directory)

        # Initialize MobileGPT exploration mode
        mobile_gpt.init_explore(app_name, algorithm=self.algorithm)

        return log_directory

    def _handle_xml_exploration(
        self,
        client_socket: socket.socket,
        screen_parser: xmlEncoder,
        mobile_gpt: MobileGPT,
        screens: List[dict],
        log_directory: str,
        screen_count: int,
        last_action_was_back: bool
    ) -> Optional[Tuple[int, bool]]:
        """Process XML and perform auto exploration.

        Returns:
            Tuple of (screen_count, last_action_was_back) or None to stop
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

            if mobile_gpt.task_status == Status.AUTO_EXPLORE:
                result = self._process_auto_explore(
                    client_socket, mobile_gpt,
                    parsed_xml, hierarchy_xml, encoded_xml,
                    screen_count, last_action_was_back
                )
                if result is None:
                    return None
                last_action_was_back = result
            else:
                # Non-explore mode: use standard action
                action = mobile_gpt.get_next_action(
                    parsed_xml, hierarchy_xml, encoded_xml
                )
                if action is not None:
                    send_json_response(client_socket, action)

            return screen_count, last_action_was_back

        except Exception as e:
            log(f"Error processing XML: {str(e)}", "red")
            log(traceback.format_exc(), "red")
            # Send back action to prevent getting stuck
            send_json_response(client_socket, {"name": "back", "parameters": {}})
            return screen_count, last_action_was_back

    def _process_auto_explore(
        self,
        client_socket: socket.socket,
        mobile_gpt: MobileGPT,
        parsed_xml: str,
        hierarchy_xml: str,
        encoded_xml: str,
        screen_count: int,
        last_action_was_back: bool
    ) -> Optional[bool]:
        """Process auto exploration for current screen.

        Returns:
            Updated last_action_was_back flag, or None to stop exploration
        """
        # Search for similar screen in memory
        log("Searching for similar screens...", "blue")
        page_index, similarity = mobile_gpt.memory.search_node(
            parsed_xml, hierarchy_xml, encoded_xml
        )
        log(f"Search complete. Page index: {page_index}, Similarity: {similarity}", "blue")

        if page_index == -1:
            # New screen discovered
            log("New screen detected, exploring...", "green")
            page_index = mobile_gpt.explore_agent.explore(
                parsed_xml, hierarchy_xml, encoded_xml, screen_count - 1
            )
            log(f"New screen discovered and explored: Page #{page_index}", "green")
        else:
            log(f"Screen already visited: Page #{page_index} (similarity: {similarity:.2f})", "yellow")

        # Record back transition for navigation planning
        if last_action_was_back and mobile_gpt.last_explored_page_index is not None:
            mobile_gpt.record_back_transition(
                from_page=mobile_gpt.last_explored_page_index,
                to_page=page_index
            )

        # Mark previous action as explored with end_page
        mobile_gpt.mark_last_action_explored(end_page=page_index)

        # Get next exploration action
        log(f"Getting next action for page #{page_index}...", "blue")
        action = mobile_gpt.get_explore_action(
            parsed_xml, hierarchy_xml, encoded_xml, page_index
        )

        if action is not None:
            log(f"Auto exploration action: {action}", "cyan")
            send_json_response(client_socket, action)
            log("Action sent to client, waiting for next message...", "cyan")
            return False  # Reset back flag

        # No more actions to explore
        if last_action_was_back:
            log("No more actions and already sent back. Stopping exploration.", "red")
            return None  # Signal to stop

        # Send back action once
        log("No more actions on this screen", "yellow")
        send_json_response(client_socket, {"name": "back", "parameters": {}})
        log("Back action sent to client, waiting for next message...", "yellow")
        return True  # Set back flag

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
