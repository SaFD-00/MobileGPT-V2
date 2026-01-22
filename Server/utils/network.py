"""Network communication utilities for server operations."""

import json
import os
import socket
from typing import Optional, Tuple


def get_local_ip() -> str:
    """Detect the local network IP address using UDP socket trick.

    Returns:
        str: Local IP address (e.g., '192.168.1.100')
    """
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]
    finally:
        s.close()


def recv_text_line(client_socket: socket.socket) -> str:
    """Receive text data until newline character.

    Args:
        client_socket: Connected client socket

    Returns:
        str: Decoded and stripped text message
    """
    data = b''
    while not data.endswith(b'\n'):
        data += client_socket.recv(1)
    return data.decode().strip()


def recv_binary_file(client_socket: socket.socket, buffer_size: int = 4096) -> bytes:
    """Receive binary file with size prefix.

    Protocol: Size as text line, then binary data

    Args:
        client_socket: Connected client socket
        buffer_size: Chunk size for receiving data

    Returns:
        bytes: Complete binary file data
    """
    file_size = int(recv_text_line(client_socket))

    data = b""
    bytes_remaining = file_size
    while bytes_remaining > 0:
        chunk = client_socket.recv(min(bytes_remaining, buffer_size))
        data += chunk
        bytes_remaining -= len(chunk)
    return data


def recv_xml(
    client_socket: socket.socket,
    buffer_size: int,
    save_path: str
) -> str:
    """Receive XML file and save to disk.

    Args:
        client_socket: Connected client socket
        buffer_size: Chunk size for receiving data
        save_path: Full path to save the XML file

    Returns:
        str: Preprocessed XML string
    """
    raw_data = recv_binary_file(client_socket, buffer_size)
    raw_xml = raw_data.decode().strip().replace('class=""', 'class="unknown"')

    os.makedirs(os.path.dirname(save_path), exist_ok=True)
    with open(save_path, 'w', encoding='utf-8') as f:
        f.write(raw_xml)

    return raw_xml


def recv_xml_with_package(
    client_socket: socket.socket,
    buffer_size: int,
    save_path: str
) -> Tuple[str, str, str]:
    """Receive XML with package information.

    Protocol: top_pkg + '\n' + target_pkg + '\n' + size + '\n' + xml

    Args:
        client_socket: Connected client socket
        buffer_size: Chunk size for receiving data
        save_path: Full path to save the XML file

    Returns:
        Tuple of (raw_xml, top_package, target_package)
    """
    top_package = recv_text_line(client_socket)
    target_package = recv_text_line(client_socket)

    raw_data = recv_binary_file(client_socket, buffer_size)
    raw_xml = raw_data.decode().strip().replace('class=""', 'class="unknown"')

    os.makedirs(os.path.dirname(save_path), exist_ok=True)
    with open(save_path, 'w', encoding='utf-8') as f:
        f.write(raw_xml)

    return raw_xml, top_package, target_package


def save_screenshot(
    client_socket: socket.socket,
    buffer_size: int,
    save_path: str
) -> None:
    """Receive and save screenshot image.

    Args:
        client_socket: Connected client socket
        buffer_size: Chunk size for receiving data
        save_path: Full path to save the image file
    """
    image_data = recv_binary_file(client_socket, buffer_size)

    os.makedirs(os.path.dirname(save_path), exist_ok=True)
    with open(save_path, 'wb') as f:
        f.write(image_data)


def send_json_response(client_socket: socket.socket, data: dict) -> None:
    """Send JSON response with newline terminator.

    Args:
        client_socket: Connected client socket
        data: Dictionary to serialize and send
    """
    message = json.dumps(data)
    client_socket.send(message.encode())
    client_socket.send(b"\r\n")
