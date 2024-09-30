# Copyright 2024 IBM Corp.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
import os
import json
from pathlib import Path
import shutil
import grpc
import hashlib
import pytest
from code_interpreter.config import Config
from proto.code_interpreter.v1.code_interpreter_service_pb2 import (
    ExecuteCustomToolRequest,
    ExecuteRequest,
    ExecuteResponse,
    ParseCustomToolRequest,
    ParseCustomToolResponse,
)
from proto.code_interpreter.v1.code_interpreter_service_pb2_grpc import (
    CodeInterpreterServiceStub,
)


@pytest.fixture
def config():
    return Config()


@pytest.fixture
def grpc_stub(config: Config):
    if (
        not config.grpc_tls_cert
        or not config.grpc_tls_cert_key
        or not config.grpc_tls_ca_cert
    ):
        channel = grpc.insecure_channel(config.grpc_listen_addr)
    else:
        channel = grpc.secure_channel(
            config.grpc_listen_addr,
            grpc.ssl_server_credentials(
                private_key_certificate_chain_pairs=[
                    (config.grpc_tls_cert_key, config.grpc_tls_cert)
                ],
                root_certificates=config.grpc_tls_ca_cert,
            ),
        )

    return CodeInterpreterServiceStub(channel)


@pytest.fixture(autouse=True)
def clear_storage(config: Config):
    for dirpath, dirnames, filenames in os.walk(config.file_storage_path):
        for name in filenames + dirnames:
            shutil.rmtree(os.path.join(dirpath, name), ignore_errors=True)


def read_file(file_hash: str, file_storage_path: str):
    return (Path(file_storage_path) / file_hash).read_bytes()


def test_imports(grpc_stub: CodeInterpreterServiceStub):
    request = ExecuteRequest(
        source_code=Path("./examples/using_imports.py").read_text(),
    )
    response = grpc_stub.Execute(request, timeout=60)
    assert "P-Value" in response.stdout, "P-Value not found in the output"


def test_ad_hoc_import(grpc_stub: CodeInterpreterServiceStub):
    request = ExecuteRequest(
        source_code=Path("./examples/cowsay.py").read_text(),
    )
    response = grpc_stub.Execute(request, timeout=60)
    assert "Hello World" in response.stdout, "Hello World not found in the output"


def test_create_file_in_interpreter(
    grpc_stub: CodeInterpreterServiceStub, config: Config
):
    file_content = "Hello, World!"
    file_hash = hashlib.sha256(file_content.encode()).hexdigest()

    response: ExecuteResponse = grpc_stub.Execute(
        ExecuteRequest(
            source_code=f"""
with open('file.txt', 'w') as f:
    f.write("{file_content}")
""",
        )
    )

    assert response.exit_code == 0
    assert response.files["/workspace/file.txt"] == file_hash


def test_parse_custom_tool_success(grpc_stub: CodeInterpreterServiceStub):
    response: ParseCustomToolResponse = grpc_stub.ParseCustomTool(
        ParseCustomToolRequest(
            tool_source_code='''
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
                ''',
        )
    )

    assert response.WhichOneof("response") == "success"

    assert response.success.tool_name == "my_tool"
    assert (
        response.success.tool_description
        == "This tool is really really cool.\nVery toolish experience:\n- Toolable.\n- Toolastic.\n- Toolicious.\n\nReturns: int -- something great"
    )
    print(response.success.tool_input_schema_json)
    assert json.loads(response.success.tool_input_schema_json) == {
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

def test_parse_custom_tool_success_2(grpc_stub: CodeInterpreterServiceStub):
    response: ParseCustomToolResponse = grpc_stub.ParseCustomTool(
        ParseCustomToolRequest(
            tool_source_code='''
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
    return response.json()''',
        )
    )

    assert response.WhichOneof("response") == "success"

    assert response.success.tool_name == "current_weather"
    assert (
        response.success.tool_description
        == "Get the current weather at a location.\n\nReturns: A dictionary with the current weather."
    )
    print(response.success.tool_input_schema_json)
    assert json.loads(response.success.tool_input_schema_json) == {
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


def test_parse_custom_tool_error(grpc_stub: CodeInterpreterServiceStub):
    response: ParseCustomToolResponse = grpc_stub.ParseCustomTool(
        ParseCustomToolRequest(
            tool_source_code="def my_tool(a, /, b, *args, **kwargs) -> int:\n  return 1 + 1",
        )
    )

    assert response.WhichOneof("response") == "error"
    assert set(response.error.error_messages) == {
        "The tool function must not have positional-only arguments",
        "The tool function must not have *args",
        "The tool function must not have **kwargs",
        "The tool function arguments must have type annotations",
    }


def test_execute_custom_tool_success(grpc_stub: CodeInterpreterServiceStub):
    result = grpc_stub.ExecuteCustomTool(
        ExecuteCustomToolRequest(
            tool_source_code="def adding_tool(a: int, b: int) -> int:\n  return a + b",
            tool_input_json='{"a": 1, "b": 2}',
        )
    )

    assert result.WhichOneof("response") == "success"
    assert result.success.tool_output_json == "3"


def test_execute_custom_tool_error(grpc_stub: CodeInterpreterServiceStub):
    result = grpc_stub.ExecuteCustomTool(
        ExecuteCustomToolRequest(
            tool_source_code="def division_tool(a: int, b: int) -> int:\n  return a / b",
            tool_input_json='{"a": 0, "b": 0}',
        )
    )

    assert result.WhichOneof("response") == "error"
    assert "division by zero" in result.error.stderr
