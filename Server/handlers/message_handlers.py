"""Reusable message handlers for server communication."""

import os
from typing import Optional, Tuple, List

from utils.utils import log
from utils.network import recv_text_line, recv_xml, save_screenshot, send_json_response


class MessageType:
    """Message type constants for protocol."""
    APP_LIST = 'L'
    INSTRUCTION = 'I'
    APP_PACKAGE = 'A'
    XML = 'X'
    SCREENSHOT = 'S'
    FINISH = 'F'
    EXTERNAL_APP = 'E'


def handle_app_list(client_socket, app_agent) -> List[str]:
    """Handle app list message (type 'L').

    Args:
        client_socket: Connected client socket
        app_agent: AppAgent instance for app management

    Returns:
        List of package names
    """
    log("App list received", "blue")

    package_string = recv_text_line(client_socket)
    package_list = package_string.split("##")

    app_agent.update_app_list(package_list)
    return package_list


def handle_package_name(client_socket, app_agent) -> Tuple[str, str]:
    """Handle app package name message (type 'A' in explore modes).

    Args:
        client_socket: Connected client socket
        app_agent: AppAgent instance for app management

    Returns:
        Tuple of (package_name, app_name)
    """
    package_name = recv_text_line(client_socket)
    log(f"Package name: {package_name}", "blue")

    if not package_name:
        log("Package name is empty", "red")
        return "", ""

    app_name = app_agent.get_app_name(package_name)

    # Add to database if not found
    if not app_name:
        app_agent.update_app_list([package_name])
        app_name = app_agent.get_app_name(package_name)

    log(f"App name: {app_name}", "blue")
    return package_name, app_name


def handle_qa_response(client_socket, mobile_gpt) -> Optional[dict]:
    """Handle Q&A response message (type 'A' in task mode).

    Args:
        client_socket: Connected client socket
        mobile_gpt: MobileGPT instance

    Returns:
        Action dict if determined, None otherwise
    """
    qa_string = recv_text_line(client_socket)
    info_name, question, answer = qa_string.split("\\", 2)

    log(f"QA received ({question}: {answer})", "blue")
    return mobile_gpt.set_qa_answer(info_name, question, answer)


def handle_screenshot(
    client_socket,
    buffer_size: int,
    log_directory: str,
    screen_count: int
) -> str:
    """Handle screenshot message (type 'S').

    Args:
        client_socket: Connected client socket
        buffer_size: Buffer size for data reception
        log_directory: Base directory for saving files
        screen_count: Current screen number for filename

    Returns:
        Path where screenshot was saved
    """
    save_path = os.path.join(log_directory, "screenshots", f"{screen_count}.jpg")
    save_screenshot(client_socket, buffer_size, save_path)
    log(f"Screenshot saved: {save_path}", "green")
    return save_path


def handle_xml_message(
    client_socket,
    buffer_size: int,
    log_directory: str,
    screen_count: int,
    screen_parser
) -> Tuple[str, str, str, str]:
    """Handle XML message (type 'X').

    Args:
        client_socket: Connected client socket
        buffer_size: Buffer size for data reception
        log_directory: Base directory for saving files
        screen_count: Current screen number for filename
        screen_parser: xmlEncoder instance for parsing

    Returns:
        Tuple of (raw_xml, parsed_xml, hierarchy_xml, encoded_xml)
    """
    save_path = os.path.join(log_directory, "xmls", f"{screen_count}.xml")
    raw_xml = recv_xml(client_socket, buffer_size, save_path)

    parsed_xml, hierarchy_xml, encoded_xml = screen_parser.encode(raw_xml, screen_count)
    return raw_xml, parsed_xml, hierarchy_xml, encoded_xml


def handle_external_app(client_socket) -> dict:
    """Handle external app detection message (type 'E').

    Called when the Android client detects transition to an external app
    (e.g., Camera, Photos) while exploring the target app.

    Args:
        client_socket: Connected client socket

    Returns:
        Dict with external app info: {detected_package, target_package, timestamp}
    """
    import json

    payload_str = recv_text_line(client_socket)
    log(f":::EXTERNAL_APP::: Detected: {payload_str}", "yellow")

    try:
        payload = json.loads(payload_str)
        return {
            "detected_package": payload.get("detected_package", ""),
            "target_package": payload.get("target_package", ""),
            "timestamp": payload.get("timestamp", 0)
        }
    except json.JSONDecodeError:
        log(":::EXTERNAL_APP::: Failed to parse payload", "red")
        return {}
