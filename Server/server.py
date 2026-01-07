"""Task execution server for mobile device automation."""

import os
import socket
import threading
from datetime import datetime
from typing import Tuple

from agents.app_agent import AppAgent
from agents.task_agent import TaskAgent
from handlers.message_handlers import (
    MessageType,
    handle_app_list,
    handle_screenshot,
    handle_xml_message,
)
from mobilegpt import MobileGPT
from screenParser.Encoder import xmlEncoder
from utils.network import get_local_ip, recv_text_line, send_json_response
from utils.utils import log


class Server:
    """Server for executing automated tasks on mobile devices.

    Handles task instructions from users, processes screen data,
    and sends actions to the mobile client.
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
        """Log server startup with connection instructions."""
        log("--------------------------------------------------------")
        log(
            f"Server is listening on {real_ip}:{self.port}\n"
            f"Input this IP address into the app. : [{real_ip}]",
            "red"
        )

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
        """Handle client connection for task execution.

        Args:
            client_socket: Connected client socket
            client_address: Client address tuple (IP, port)
        """
        print(f"Connected to client: {client_address}")

        mobile_gpt = MobileGPT(client_socket)
        app_agent = AppAgent()
        task_agent = TaskAgent()
        screen_parser = xmlEncoder()
        screen_count = 0
        log_directory = self.memory_directory

        while True:
            raw_message_type = client_socket.recv(1)

            if not raw_message_type:
                self._handle_disconnection(client_socket, client_address)
                return

            message_type = raw_message_type.decode()

            if message_type == MessageType.APP_LIST:
                handle_app_list(client_socket, app_agent)

            elif message_type == MessageType.INSTRUCTION:
                log_directory = self._handle_instruction(
                    client_socket, app_agent, task_agent,
                    screen_parser, mobile_gpt
                )

            elif message_type == MessageType.SCREENSHOT:
                handle_screenshot(
                    client_socket, self.buffer_size,
                    log_directory, screen_count
                )

            elif message_type == MessageType.XML:
                screen_count = self._handle_xml(
                    client_socket, screen_parser, mobile_gpt,
                    log_directory, screen_count
                )

            elif message_type == MessageType.APP_PACKAGE:
                self._handle_qa_response(client_socket, mobile_gpt)

    def _handle_instruction(
        self,
        client_socket: socket.socket,
        app_agent: AppAgent,
        task_agent: TaskAgent,
        screen_parser: xmlEncoder,
        mobile_gpt: MobileGPT
    ) -> str:
        """Process user instruction and initialize task.

        Returns:
            str: Log directory path for this task
        """
        log("Instruction is received", "blue")

        instruction = recv_text_line(client_socket)
        task, is_new_task = task_agent.get_task(instruction)
        target_app = task['app']

        # Predict app if not specified
        if target_app == 'unknown' or target_app == "":
            target_app = app_agent.predict_app(instruction)
            task['app'] = target_app

        target_package = app_agent.get_package_name(target_app)

        # Create timestamped log directory
        dt_string = datetime.now().strftime("%Y_%m_%d %H:%M:%S")
        log_directory = f"{self.memory_directory}/log/{target_app}/{task['name']}/{dt_string}/"
        screen_parser.init(log_directory)

        # Send target package to client
        response = "##$$##" + target_package
        client_socket.send(response.encode())
        client_socket.send(b"\r\n")

        mobile_gpt.init(instruction, task, is_new_task)

        return log_directory

    def _handle_xml(
        self,
        client_socket: socket.socket,
        screen_parser: xmlEncoder,
        mobile_gpt: MobileGPT,
        log_directory: str,
        screen_count: int
    ) -> int:
        """Process XML screen data and determine next action.

        Returns:
            int: Updated screen count
        """
        _, parsed_xml, hierarchy_xml, encoded_xml = handle_xml_message(
            client_socket, self.buffer_size,
            log_directory, screen_count, screen_parser
        )

        action = mobile_gpt.get_next_action(parsed_xml, hierarchy_xml, encoded_xml)

        if action is not None:
            send_json_response(client_socket, action)

        return screen_count + 1

    def _handle_qa_response(
        self,
        client_socket: socket.socket,
        mobile_gpt: MobileGPT
    ) -> None:
        """Process Q&A response from user."""
        qa_string = recv_text_line(client_socket)
        info_name, question, answer = qa_string.split("\\", 2)
        log(f"QA is received ({question}: {answer})", "blue")

        action = mobile_gpt.set_qa_answer(info_name, question, answer)

        if action is not None:
            send_json_response(client_socket, action)
