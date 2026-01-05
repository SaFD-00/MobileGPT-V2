"""Manual exploration server for app screen structure learning."""

import socket
from datetime import datetime
from typing import List, Optional, Tuple

from agents.app_agent import AppAgent
from agents.explore_agent import ExploreAgent
from base_server import BaseServer
from handlers.message_handlers import (
    MessageType,
    handle_package_name,
    handle_screenshot,
    handle_xml_message,
)
from memory.memory_manager import Memory
from screenParser.Encoder import xmlEncoder
from utils.utils import log


class Explorer(BaseServer):
    """Server for manual app exploration and screen structure learning.

    Collects screen data during user interaction and learns
    UI structure patterns for future automation.
    """

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
