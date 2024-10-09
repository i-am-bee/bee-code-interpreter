import json
from pathlib import Path
import hashlib
import pytest
import httpx
from code_interpreter.config import Config


@pytest.fixture
def config():
    return Config()


@pytest.fixture
def http_client():
    base_url = "http://localhost:8000"
    return httpx.Client(base_url=base_url)


def read_file(file_hash: str, file_storage_path: str):
    return (Path(file_storage_path) / file_hash).read_bytes()


def test_imports(http_client: httpx.Client):
    request_data = {
        "source_code": Path("./examples/using_imports.py").read_text(),
        "files": {},
    }
    response = http_client.post("/v1/execute", json=request_data)
    assert response.status_code == 200
    response_json = response.json()
    assert "P-Value" in response_json["stdout"], "P-Value not found in the output"


def test_ad_hoc_import(http_client: httpx.Client):
    request_data = {
        "source_code": Path("./examples/cowsay.py").read_text(),
        "files": {},
    }
    response = http_client.post("/v1/execute", json=request_data)
    assert response.status_code == 200
    response_json = response.json()
    assert (
        "Hello World" in response_json["stdout"]
    ), "Hello World not found in the output"


def test_create_file_in_interpreter(http_client: httpx.Client, config: Config):
    file_content = "Hello, World!"
    file_hash = hashlib.sha256(file_content.encode()).hexdigest()

    # Create the file in the workspace
    response = http_client.post(
        "/v1/execute",
        json={
            "source_code": f"""
with open('file.txt', 'w') as f:
    f.write("{file_content}")
""",
            "files": {},
        },
    )

    assert response.status_code == 200
    response_json = response.json()
    assert response_json["exit_code"] == 0
    assert response_json["files"]["/workspace/file.txt"] == file_hash

    # Read the file back
    response = http_client.post(
        "/v1/execute",
        json={
            "source_code": """
with open('file.txt', 'r') as f:
    print(f.read())
""",
            "files": {"/workspace/file.txt": file_hash},
        },
    )

    assert response.status_code == 200
    response_json = response.json()
    assert response_json["exit_code"] == 0
    assert response_json["stdout"] == file_content + "\n"


def test_parse_custom_tool_success(http_client: httpx.Client):
    response = http_client.post(
        "/v1/parse-custom-tool",
        json={
            "tool_source_code": '''
def my_tool(a: int, b: typing.Tuple[Optional[str], str] = ("hello", "world"), *, c: typing.Union[list[str], dict[str, typing.Optional[float]]]) -> int:
    """
    This tool is really really cool.
    Very toolish experience:
    - Toolable.
    - Toolastic.
    - Toolicious.
    :param a: something cool
    (very cool indeed)
    :param b: something nice
    :return: something great
    :param c: something awful
    """
    return 1 + 1
                '''
        },
    )

    assert response.status_code == 200
    response_json = response.json()
    assert response_json["tool_name"] == "my_tool"
    assert (
        response_json["tool_description"]
        == "This tool is really really cool.\nVery toolish experience:\n- Toolable.\n- Toolastic.\n- Toolicious.\n\nReturns: int -- something great"
    )
    assert json.loads(response_json["tool_input_schema_json"]) == {
        "$schema": "http://json-schema.org/draft-07/schema#",
        "type": "object",
        "title": "my_tool",
        "properties": {
            "a": {
                "type": "integer",
                "description": "something cool\n(very cool indeed)",
            },
            "b": {
                "type": "array",
                "minItems": 2,
                "items": [
                    {"anyOf": [{"type": "null"}, {"type": "string"}]},
                    {"type": "string"},
                ],
                "additionalItems": False,
                "description": "something nice",
            },
            "c": {
                "anyOf": [
                    {"type": "array", "items": {"type": "string"}},
                    {
                        "type": "object",
                        "additionalProperties": {
                            "anyOf": [{"type": "null"}, {"type": "number"}]
                        },
                    },
                ],
                "description": "something awful",
            },
        },
        "required": ["a", "c"],
        "additionalProperties": False,
    }


def test_parse_custom_tool_success_2(http_client: httpx.Client):
    response = http_client.post(
        "/v1/parse-custom-tool",
        json={
            "tool_source_code": '''
import typing
import requests

def current_weather(lat: float, lon: float):
    """
    Get the current weather at a location.

    :param lat: A latitude.
    :param lon: A longitude.
    :return: A dictionary with the current weather.
    """
    url = "https://fake-api.com/weather?lat=" + str(lat) + "&lon=" + str(lon)
    response = requests.get(url)
    response.raise_for_status()
    return response.json()'''
        },
    )

    assert response.status_code == 200
    response_json = response.json()
    assert response_json["tool_name"] == "current_weather"
    assert (
        response_json["tool_description"]
        == "Get the current weather at a location.\n\nReturns: A dictionary with the current weather."
    )
    assert json.loads(response_json["tool_input_schema_json"]) == {
        "$schema": "http://json-schema.org/draft-07/schema#",
        "type": "object",
        "title": "current_weather",
        "properties": {
            "lat": {
                "type": "number",
                "description": "A latitude.",
            },
            "lon": {
                "type": "number",
                "description": "A longitude.",
            },
        },
        "required": ["lat", "lon"],
        "additionalProperties": False,
    }


def test_execute_custom_tool_success(http_client: httpx.Client):
    response = http_client.post(
        "/v1/execute-custom-tool",
        json={
            "tool_source_code": "def adding_tool(a: int, b: int) -> int:\n  return a + b",
            "tool_input_json": '{"a": 1, "b": 2}',
        },
    )

    assert response.status_code == 200
    response_json = response.json()
    assert json.loads(response_json["tool_output_json"]) == 3


def test_parse_custom_tool_error(http_client: httpx.Client):
    response = http_client.post(
        "/v1/parse-custom-tool",
        json={
            "tool_source_code": "def my_tool(a, /, b, *args, **kwargs) -> int:\n  return 1 + 1"
        },
    )
    assert response.status_code == 400
    response_data = response.json()
    assert set(response_data["error_messages"]) == {
        "The tool function must not have positional-only arguments",
        "The tool function must not have *args",
        "The tool function must not have **kwargs",
        "The tool function arguments must have type annotations",
    }


def test_execute_custom_tool_error(http_client: httpx.Client):
    response = http_client.post(
        "/v1/execute-custom-tool",
        json={
            "tool_source_code": "def division_tool(a: int, b: int) -> int:\n  return a / b",
            "tool_input_json": '{"a": 0, "b": 0}',
        },
    )

    assert response.status_code == 400
    response_json = response.json()
    assert "division by zero" in response_json["stderr"]
