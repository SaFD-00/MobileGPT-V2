"""TCP-based inference server using LangGraph multi-agent system.

Follows the server_auto_explore.py pattern for TCP communication,
but uses LangGraph for intelligent subtask selection and verification.
"""

import os
import socket
import threading
import traceback
import uuid
from datetime import datetime
from typing import Optional, Tuple

from agents.app_agent import AppAgent
from handlers.message_handlers import (
    MessageType,
    handle_app_list,
    handle_package_name,
    handle_screenshot,
)
from inference.graphs.inference_graph import compile_graph
from memory.memory_manager import Memory
from screenParser.Encoder import xmlEncoder
from utils.network import get_local_ip, recv_xml, recv_text_line, send_json_response
from utils.utils import log


class InferenceServer:
    """LangGraph-based inference TCP server.

    Automatically selects and verifies subtasks using a multi-agent system:
    1. MemoryAgent: Load page/state and available subtasks
    2. SelectAgent: Select best subtask for the instruction
    3. VerifyAgent: Verify if selected subtask leads to a good path
       - "가면 안된다" (shouldn't go) -> reselect
       - "간다" (should go) -> confirmed
    4. DeriveAgent: Derive concrete action from confirmed subtask

    Follows server_auto_explore.py TCP communication pattern.
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
        """Initialize inference server.

        Args:
            host: Server host address
            port: Server port number
            buffer_size: Socket buffer size
            memory_directory: Base directory for app memory
        """
        self.host = host
        self.port = port
        self.buffer_size = buffer_size
        self.memory_directory = memory_directory

        # Compile LangGraph inference graph
        self._inference_graph = compile_graph(checkpointer=True)

        self._ensure_directory(self.memory_directory)

    def open(self) -> None:
        """Start server and listen for client connections."""
        real_ip = get_local_ip()

        server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server.bind((self.host, self.port))
        server.listen()

        self._log_server_start(real_ip)
        self._accept_clients(server)

    def _log_server_start(self, real_ip: str) -> None:
        """Log server startup information."""
        log(f"InferenceServer listening on {real_ip}:{self.port}", "red")
        log("Using LangGraph multi-agent system for intelligent subtask selection", "cyan")

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
        """Handle client connection for inference mode.

        Args:
            client_socket: Connected client socket
            client_address: Client address tuple (IP, port)
        """
        print(f"Connected to Client: {client_address}")

        app_agent = AppAgent()
        screen_parser = xmlEncoder()

        # Session state
        memory: Optional[Memory] = None
        instruction: Optional[str] = None
        app_name: Optional[str] = None
        log_directory = self.memory_directory

        while True:
            try:
                raw_message_type = client_socket.recv(1)

                if not raw_message_type:
                    self._handle_disconnection(client_socket, client_address)
                    return

                message_type = raw_message_type.decode('utf-8')
                log(f"Message type: '{message_type}'", "cyan")

                if message_type == MessageType.APP_LIST:
                    handle_app_list(client_socket, app_agent)

                elif message_type == MessageType.APP_PACKAGE:
                    package_name, app_name = handle_package_name(client_socket, app_agent)
                    if app_name:
                        log_directory = self._init_log_directory(app_name)
                        screen_parser.init(log_directory)

                elif message_type == MessageType.INSTRUCTION:
                    instruction = self._handle_instruction(client_socket)
                    if instruction and app_name:
                        # Initialize memory with instruction
                        memory = Memory(app_name, instruction, instruction)
                        log(f"Initialized memory for app '{app_name}' with instruction: {instruction}", "green")

                elif message_type == MessageType.XML:
                    if not instruction:
                        log("Error: instruction not set, cannot process XML", "red")
                        continue
                    if not memory:
                        log("Error: memory not initialized, cannot process XML", "red")
                        continue

                    action = self._handle_inference(
                        client_socket, screen_parser, memory, instruction, log_directory
                    )
                    if action:
                        send_json_response(client_socket, action)

                elif message_type == MessageType.SCREENSHOT:
                    handle_screenshot(client_socket, self.buffer_size, log_directory, 0)

                elif message_type == MessageType.FINISH:
                    self._handle_finish(client_socket)
                    break

                else:
                    log(f"Unknown message type: {message_type}", "red")

            except Exception as e:
                log(f"Error handling client: {str(e)}", "red")
                log(traceback.format_exc(), "red")
                # Try to send error response
                try:
                    send_json_response(client_socket, {"name": "error", "parameters": {"message": str(e)}})
                except Exception:
                    pass

    def _init_log_directory(self, app_name: str) -> str:
        """Initialize timestamped log directory for the app.

        Args:
            app_name: Name of the app

        Returns:
            str: Log directory path
        """
        dt_string = datetime.now().strftime("%Y_%m_%d %H:%M:%S")
        log_directory = f"{self.memory_directory}/log/{app_name}/inference/{dt_string}/"
        self._ensure_directory(log_directory)
        return log_directory

    def _handle_instruction(self, client_socket: socket.socket) -> Optional[str]:
        """Handle instruction message.

        Args:
            client_socket: Connected client socket

        Returns:
            str: Received instruction, or None if failed
        """
        instruction = recv_text_line(client_socket)
        log(f"Instruction received: {instruction}", "blue")
        return instruction

    def _handle_inference(
        self,
        client_socket: socket.socket,
        screen_parser: xmlEncoder,
        memory: Memory,
        instruction: str,
        log_directory: str
    ) -> Optional[dict]:
        """Process XML and run LangGraph inference to get action.

        Automatically performs:
        1. MemoryAgent: page/state lookup
        2. SelectAgent: subtask selection
        3. VerifyAgent: next screen verification
           - "가면 안된다" -> reselect (loop)
           - "간다" -> confirmed
        4. DeriveAgent: action derivation

        Args:
            client_socket: Connected client socket
            screen_parser: XML parser instance
            memory: Memory instance
            instruction: User instruction
            log_directory: Directory for saving logs

        Returns:
            dict: Action to execute, or None if failed
        """
        try:
            # Receive and parse XML
            xml_path = os.path.join(log_directory, "xmls", "current.xml")
            self._ensure_directory(os.path.dirname(xml_path))
            raw_xml = recv_xml(client_socket, self.buffer_size, xml_path)

            parsed_xml, hierarchy_xml, encoded_xml = screen_parser.encode(raw_xml, 0)
            log("XML received and parsed", "blue")

            # Run LangGraph inference
            session_id = str(uuid.uuid4())
            config = {"configurable": {"thread_id": session_id}}

            log("Starting LangGraph inference...", "cyan")
            result = self._inference_graph.invoke({
                "session_id": session_id,
                "instruction": instruction,
                "current_xml": parsed_xml,
                "hierarchy_xml": hierarchy_xml,
                "encoded_xml": encoded_xml,
                "memory": memory,
                "rejected_subtasks": [],
                "iteration": 0,
            }, config=config)

            # Extract result
            action = result.get("action")
            status = result.get("status", "unknown")
            iterations = result.get("iteration", 0)

            log(f"Inference complete: status={status}, iterations={iterations}", "green")

            if action:
                log(f"Action: {action}", "cyan")
            else:
                log("No action derived", "yellow")

            return action

        except Exception as e:
            log(f"Error in inference: {str(e)}", "red")
            log(traceback.format_exc(), "red")
            return None

    def _handle_finish(self, client_socket: socket.socket) -> None:
        """Handle finish message.

        Args:
            client_socket: Connected client socket
        """
        log("Inference session finished", "green")
        finish_message = {
            "status": "inference_complete"
        }
        send_json_response(client_socket, finish_message)
