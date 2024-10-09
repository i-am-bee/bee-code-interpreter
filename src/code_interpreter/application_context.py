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

import asyncio
from contextvars import ContextVar
import logging
import logging.config
from functools import cached_property

import os
from fastapi import FastAPI
import grpc
from code_interpreter.config import Config
from code_interpreter.services.custom_tool_executor import CustomToolExecutor
from code_interpreter.services.grpc_server import GrpcServer
from code_interpreter.services.grpc_servicers.code_interpreter_servicer import (
    CodeInterpreterServicer,
)
from code_interpreter.services.http_server import create_http_server
from code_interpreter.services.kubectl import Kubectl
from code_interpreter.services.kubernetes_code_executor import KubernetesCodeExecutor
from code_interpreter.services.storage import Storage


class ApplicationContext:
    def __init__(self) -> None:
        self.setup_logging()

    def setup_logging(self):
        logging.config.dictConfig(self.config.logging_config)
        request_id_context_var = self.request_id_context_var

        class RequestIdFilter(logging.Filter):
            def filter(self, record):
                record.request_id = (
                    request_id_context_var.get()
                    or "00000000-0000-0000-0000-000000000000"
                )
                return True

        for handler in logging.root.handlers:
            handler.addFilter(RequestIdFilter())

    @cached_property
    def request_id_context_var(self):
        return ContextVar("request_id", default=None)
    
    @cached_property
    def config(self) -> Config:
        return Config()

    @cached_property
    def kubectl(self) -> Kubectl:
        return Kubectl()

    @cached_property
    def file_storage(self) -> Storage:
        os.makedirs(self.config.file_storage_path, exist_ok=True)
        return Storage(storage_path=self.config.file_storage_path)

    @cached_property
    def code_executor(self) -> KubernetesCodeExecutor:
        code_executor = KubernetesCodeExecutor(
            kubectl=self.kubectl,
            executor_image=self.config.executor_image,
            container_resources=self.config.executor_container_resources,
            file_storage=self.file_storage,
            executor_pod_spec_extra=self.config.executor_pod_spec_extra,
            executor_pod_queue_target_length=self.config.executor_pod_queue_target_length,
        )
        asyncio.create_task(code_executor.fill_executor_pod_queue())
        return code_executor

    @cached_property
    def custom_tool_executor(self) -> CustomToolExecutor:
        return CustomToolExecutor(
            code_executor=self.code_executor,
        )

    @cached_property
    def grpc_servicers(self) -> list:
        return [
            CodeInterpreterServicer(
                code_executor=self.code_executor,
                custom_tool_executor=self.custom_tool_executor,
                request_id_context_var=self.request_id_context_var,
            )
        ]
    
    @cached_property
    def grpc_server_credentials(self) -> grpc.ServerCredentials | None:
        if not self.config.grpc_tls_cert or not self.config.grpc_tls_cert_key or not self.config.grpc_tls_ca_cert:
            return None
        
        return grpc.ssl_server_credentials(
            private_key_certificate_chain_pairs=[(self.config.grpc_tls_cert_key, self.config.grpc_tls_cert)],
            root_certificates=self.config.grpc_tls_ca_cert
        )

    @cached_property
    def grpc_server(self) -> GrpcServer:
        return GrpcServer(
            servicers=self.grpc_servicers,
            server_credentials=self.grpc_server_credentials
        )

    @cached_property
    def http_server(self) -> FastAPI:
        return create_http_server(
            code_executor=self.code_executor,
            custom_tool_executor=self.custom_tool_executor,
            request_id_context_var=self.request_id_context_var,
        )
