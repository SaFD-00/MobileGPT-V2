import os, csv, re
import base64
import copy
import numpy as np
import json
import pandas as pd

from termcolor import colored
from openai import OpenAI
from typing import List, Optional
from ast import literal_eval


def log(msg, color='white'):
    if not color:
        print(msg)
        return

    colored_log = colored(msg, color, attrs=['bold'])
    print(colored_log)
    print()


def safe_literal_eval(x):
    if pd.isna(x):
        return np.nan  # or return np.array([]) for converting NaN to empty arrays
    else:
        return np.array(literal_eval(x))


def get_openai_embedding(text: str, model="text-embedding-3-small", **kwargs) -> List[float]:
    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    # replace newlines, which can negatively affect performance.
    text = text.replace("\n", " ")

    response = client.embeddings.create(input=[text], model=model, **kwargs)

    return response.data[0].embedding


def cosine_similarity(a, b):
    if isinstance(a, np.ndarray) and isinstance(b, np.ndarray):
        return np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b))
    else:
        return 0


def generate_numbered_list(data: list) -> str:
    result_string = ""

    for index, item in enumerate(data, start=1):
        if isinstance(item, dict):
            result_string += f"- {json.dumps(item)}\n"
        else:
            result_string += f"- {item}\n"

    return result_string


def _is_fixed_temperature_model(model: str) -> bool:
    """Check if the model doesn't support temperature parameter (gpt-5.2 series)."""
    model_lower = model.lower()
    return model_lower.startswith(('gpt-5.2'))


def query(messages, model="gpt-5.2", is_list=False):
    client = OpenAI()

    for message in messages:
        log("--------------------------")
        log(message["content"], 'yellow')
    # log("--------------------------")
    # log(messages[-1]["content"], 'yellow')

    # Models with fixed temperature (o1, o3, gpt-5.2) don't support temperature parameter
    if _is_fixed_temperature_model(model):
        response = client.chat.completions.create(
            model=model,
            messages=messages,
            max_completion_tokens=4096,
        )
    else:
        response = client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=0,
            max_completion_tokens=4096,
        )
    result = response.choices[0].message.content
    log(result, 'green')
    json_formatted_response = __parse_json(result, is_list=is_list)
    if json_formatted_response:
        return json.loads(json_formatted_response)
    else:
        # Return type-appropriate default value when JSON parsing fails
        log(f":::QUERY WARNING::: Failed to parse JSON from response. Returning empty {'list' if is_list else 'dict'}.", "yellow")
        if result:
            log(f":::QUERY WARNING::: Response preview: {result[:200]}...", "yellow")
        return [] if is_list else {}


def encode_image_to_base64(image_path: str) -> str:
    """Encode an image file to Base64"""
    with open(image_path, "rb") as image_file:
        return base64.standard_b64encode(image_file.read()).decode("utf-8")


def _add_image_to_messages(messages: list, image_path: str,
                           detail: str = "high") -> list:
    """Add an image to the last user message

    Chat Completions API Vision format:
    {"type": "text", "text": "..."}
    {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64,..."}}
    """
    new_messages = copy.deepcopy(messages)

    # Find the last user message
    for i in range(len(new_messages) - 1, -1, -1):
        if new_messages[i]["role"] == "user":
            content = new_messages[i]["content"]

            # Encode image to Base64
            base64_image = encode_image_to_base64(image_path)

            # Convert to Vision API format
            if isinstance(content, str):
                new_messages[i]["content"] = [
                    {"type": "text", "text": content},
                    {"type": "image_url", "image_url": {
                        "url": f"data:image/jpeg;base64,{base64_image}",
                        "detail": detail
                    }}
                ]
            break

    return new_messages


def query_with_vision(messages, model: str = "gpt-5.2",
                      screenshot_path: Optional[str] = None,
                      is_list: bool = False,
                      image_detail: str = "high"):
    """Query function with Vision API support

    Args:
        messages: List of prompt messages
        model: Model name to use (default: gpt-5.2)
        screenshot_path: Screenshot file path (Optional)
        is_list: Whether the response is a list
        image_detail: Image detail level (low/high/auto)

    Returns:
        Parsed JSON response (dict or list)
    """
    # Convert to Vision API format if screenshot is available
    if screenshot_path and os.path.exists(screenshot_path):
        log(f":::VISION::: Adding screenshot: {screenshot_path}", "magenta")
        messages = _add_image_to_messages(messages, screenshot_path, image_detail)

    # Use existing query logic
    return query(messages, model=model, is_list=is_list)


def parse_completion_rate(completion_rate) -> int:
    # Convert the input to a string in case it's an integer
    input_str = str(completion_rate).strip()

    # Check if the string ends with a '%'
    if input_str.endswith('%'):
        # Remove the '%' and convert to integer
        return int(float(input_str[:-1]))
    else:
        # Convert to float to handle decimal or integer strings
        value = float(input_str)

        # If the value is less than 1, it's likely a decimal representation of a percentage
        if value < 1:
            return int(value * 100)
        # Otherwise, it's already in percentage form
        else:
            return int(value)


def __parse_json(s: str, is_list=False):
    """Parse and extract a JSON string.

    Args:
        s: String to parse
        is_list: If True, search for list format [...]; if False, search for dict format {...}

    Returns:
        str: Matched JSON string, or None on failure
    """
    if not s or not isinstance(s, str):
        return None

    if is_list:
        matches = re.search(r'\[.*\]', s, re.DOTALL)
        if matches:
            return matches.group(0)
    else:
        matches = re.search(r'\{.*\}', s, re.DOTALL)
        if matches:
            return matches.group(0)

    return None
