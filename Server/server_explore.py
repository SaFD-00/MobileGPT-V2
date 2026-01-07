"""Manual exploration server for app screen structure learning."""

import os
import socket
import threading
from datetime import datetime
from typing import List, Optional, Tuple

from agents.app_agent import AppAgent
from agents.explore_agent import ExploreAgent
from handlers.message_handlers import (
    MessageType,
    handle_package_name,
    handle_screenshot,
    handle_xml_message,
)
from memory.memory_manager import Memory
from screenParser.Encoder import xmlEncoder
from utils.network import get_local_ip
from utils.utils import log


class Explorer:
    """Server for manual app exploration and screen structure learning.

    Collects screen data during user interaction and learns
    UI structure patterns for future automation.
    """

    DEFAULT_HOST = '0.0.0.0'
    DEFAULT_PORT = 12345
    DEFAULT_BUFFER_SIZE = 4096

    def __init__(
        self,
        host: str = DEFAULT_HOST,
        port: int = DEFAULT_PORT,
        buffer_size: int = DEFAULT_BUFFER_SIZE,
        memory_directory: str = './memory'
    ):
        """Initialize server configuration.

        Args:
            host: Server host address (default: all interfaces)
            port: Server port number
            buffer_size: Socket buffer size for data reception
            memory_directory: Base directory for logs and received files
        """
        self.host = host
        self.port = port
        self.buffer_size = buffer_size
        self.memory_directory = memory_directory

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
        log(f"Explorer is listening on {real_ip}:{self.port}", "red")

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
        """Handle client connection for exploration mode.

        Args:
            client_socket: Connected client socket
            client_address: Client address tuple (IP, port)
        """
        print(f"Connected to client: {client_address}")

        log_directory = self.memory_directory
        memory = None
        explore_agent = None

        app_agent = AppAgent()
        screen_parser = xmlEncoder()
        screens: List[dict] = []
        screen_count = 0

        while True:
            raw_message_type = client_socket.recv(1)

            if not raw_message_type:
                self._handle_disconnection(client_socket, client_address)
                return

            message_type = raw_message_type.decode()

            if message_type == MessageType.APP_PACKAGE:
                log_directory, memory, explore_agent = self._handle_app_init(
                    client_socket, app_agent, screen_parser
                )

            elif message_type == MessageType.XML:
                screen_count = self._handle_xml(
                    client_socket, screen_parser, screens,
                    log_directory, screen_count
                )

            elif message_type == MessageType.SCREENSHOT:
                handle_screenshot(
                    client_socket, self.buffer_size,
                    log_directory, screen_count
                )

            elif message_type == MessageType.FINISH:
                self._process_collected_screens(screens, memory, explore_agent)

            else:
                log(f"Unknown message type: {message_type}", "red")

    def _handle_app_init(
        self,
        client_socket: socket.socket,
        app_agent: AppAgent,
        screen_parser: xmlEncoder
    ) -> Tuple:
        """Initialize exploration for an app.

        Returns:
            Tuple of (log_directory, memory, explore_agent)
        """
        package_name, app_name = handle_package_name(client_socket, app_agent)

        if not package_name:
            return self.memory_directory, None, None

        # Create timestamped log directory
        dt_string = datetime.now().strftime("%Y_%m_%d %H:%M:%S")
        log_directory = f"{self.memory_directory}/log/{app_name}/hardcode/{dt_string}/"
        screen_parser.init(log_directory)

        # Initialize memory and exploration agent
        memory = Memory(app_name, "hardcode", "hardcode")
        explore_agent = ExploreAgent(memory)

        return log_directory, memory, explore_agent

    def _handle_xml(
        self,
        client_socket: socket.socket,
        screen_parser: xmlEncoder,
        screens: List[dict],
        log_directory: str,
        screen_count: int
    ) -> int:
        """Process XML screen data and store for later analysis.

        Returns:
            int: Updated screen count
        """
        _, parsed_xml, hierarchy_xml, encoded_xml = handle_xml_message(
            client_socket, self.buffer_size,
            log_directory, screen_count, screen_parser
        )

        screens.append({
            "parsed": parsed_xml,
            "hierarchy": hierarchy_xml,
            "encoded": encoded_xml
        })
        log(f"Captured new screen: #{screen_count + 1}", "green")

        return screen_count + 1

    def _process_collected_screens(
        self,
        screens: List[dict],
        memory: Optional[Memory],
        explore_agent: Optional[ExploreAgent]
    ) -> None:
        """Process all collected screens after exploration ends."""
        if not memory or not explore_agent:
            log("Memory or explore agent not initialized", "red")
            return

        for screen_num, screen in enumerate(screens):
            # Search for similar screen in memory
            page_index, _ = memory.search_node(
                screen['parsed'], screen['hierarchy'], screen['encoded']
            )
            print(page_index)

            # Learn new screen if not found
            if page_index == -1:
                page_index = explore_agent.explore(
                    screen['parsed'], screen['hierarchy'],
                    screen['encoded'], screen_num
                )
