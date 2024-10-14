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
import json
import logging
import grpc
import protovalidate
from contextvars import ContextVar
import uuid
from code_interpreter.services.custom_tool_executor import (
    CustomToolExecuteError,
    CustomToolExecutor,
    CustomToolParseError,
)
from code_interpreter.services.kubernetes_code_executor import KubernetesCodeExecutor
from google.protobuf.message import Message

import proto.code_interpreter.v1.code_interpreter_service_pb2 as code_interpreter_pb2
import proto.code_interpreter.v1.code_interpreter_service_pb2_grpc as code_interpreter_pb2_grpc

logger = logging.getLogger("code_interpreter_servicer")

class CodeInterpreterServicer(code_interpreter_pb2_grpc.CodeInterpreterServiceServicer):
    def __init__(
        self,
        code_executor: KubernetesCodeExecutor,
        custom_tool_executor: CustomToolExecutor,
        request_id_context_var: ContextVar,
    ):
        self.code_executor = code_executor
        self.custom_tool_executor = custom_tool_executor
        self.request_id_context_var = request_id_context_var

    async def _validate_request(
        self, request: Message, context: grpc.aio.ServicerContext
    ):
        try:
            protovalidate.validate(request)
        except protovalidate.ValidationError as e:
            logger.warning(
                "Invalid request: error when validating %s", request, exc_info=True
            )
            await context.abort(grpc.StatusCode.INVALID_ARGUMENT, str(e.errors()))

    async def Execute(
        self,
        request: code_interpreter_pb2.ExecuteRequest,
        context: grpc.aio.ServicerContext,
    ) -> code_interpreter_pb2.ExecuteResponse:
        self.request_id_context_var.set(str(uuid.uuid4()))
        logger.info(
            "Executing code with files %s: %s", request.files, request.source_code
        )
        await self._validate_request(request, context)

        try:
            result = await self.code_executor.execute(
                source_code=request.source_code,
                files=request.files,
            )
        except Exception as e:
            logger.exception("Error executing code")
            raise e

        logger.info("Code execution completed with result %s", result)
        return code_interpreter_pb2.ExecuteResponse(
            stdout=result.stdout,
            stderr=result.stderr,
            exit_code=result.exit_code,
            files=result.files,
        )

    async def ParseCustomTool(
        self,
        request: code_interpreter_pb2.ParseCustomToolRequest,
        context: grpc.aio.ServicerContext,
    ) -> code_interpreter_pb2.ParseCustomToolResponse:
        self.request_id_context_var.set(str(uuid.uuid4()))
        logger.info("Parsing custom tool with source code %s", request.tool_source_code)
        await self._validate_request(request, context)

        try:
            custom_tool = self.custom_tool_executor.parse(
                tool_source_code=request.tool_source_code
            )
        except CustomToolParseError as e:
            logger.warning("Invalid custom tool: %s", e.errors)
            return code_interpreter_pb2.ParseCustomToolResponse(
                error={"error_messages": e.errors}
            )

        result = {
            "tool_name": custom_tool.name,
            "tool_input_schema_json": json.dumps(custom_tool.input_schema),
            "tool_description": custom_tool.description,
        }
        logger.info("Parsed custom tool %s", result)
        return code_interpreter_pb2.ParseCustomToolResponse(success=result)

    async def ExecuteCustomTool(
        self,
        request: code_interpreter_pb2.ExecuteCustomToolRequest,
        context: grpc.aio.ServicerContext,
    ) -> code_interpreter_pb2.ExecuteCustomToolResponse:
        self.request_id_context_var.set(str(uuid.uuid4()))
        logger.info(
            "Executing custom tool with source code %s", request.tool_source_code
        )
        await self._validate_request(request, context)

        try:
            result = await self.custom_tool_executor.execute(
                tool_input=json.loads(request.tool_input_json),
                tool_source_code=request.tool_source_code,
            )
        except CustomToolExecuteError as e:
            logger.warning("Error executing custom tool: %s", e)
            return code_interpreter_pb2.ExecuteCustomToolResponse(
                error={"stderr": str(e)}
            )

        logger.info("Executed custom tool with result %s", result)
        return code_interpreter_pb2.ExecuteCustomToolResponse(
            success={"tool_output_json": json.dumps(result)}
        )
