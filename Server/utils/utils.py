import os, csv, re
import numpy as np
import json
import pandas as pd

from termcolor import colored
from openai import OpenAI
from typing import List
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
    """Check if the model doesn't support temperature parameter (o1, o3, gpt-5.2 series)."""
    model_lower = model.lower()
    return model_lower.startswith(('o1', 'o3', 'gpt-5.2'))


def query(messages, model="gpt-5.2-chat-latest", is_list=False):
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
            max_completion_tokens=2000,
        )
    else:
        response = client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=0,
            max_completion_tokens=2000,
        )
    result = response.choices[0].message.content
    log(result, 'green')
    json_formatted_response = __parse_json(result, is_list=is_list)
    if json_formatted_response:
        return json.loads(json_formatted_response)
    else:
        # JSON 파싱 실패 시 타입에 맞는 기본값 반환
        log(f":::QUERY WARNING::: Failed to parse JSON from response. Returning empty {'list' if is_list else 'dict'}.", "yellow")
        if result:
            log(f":::QUERY WARNING::: Response preview: {result[:200]}...", "yellow")
        return [] if is_list else {}


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
    """JSON 문자열을 파싱하여 추출.

    Args:
        s: 파싱할 문자열
        is_list: True면 리스트 형태 [...], False면 딕셔너리 형태 {...} 검색

    Returns:
        str: 매칭된 JSON 문자열, 실패 시 None
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
