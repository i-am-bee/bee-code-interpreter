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

import importlib
import logging
import grpc
from grpc_reflection.v1alpha import reflection


class GrpcServer:
    def __init__(self, servicers: list, server_credentials: grpc.ServerCredentials | None = None) -> None:
        self.server = grpc.aio.server()
        self.server_credentials = server_credentials
        self._register_servicers(servicers)

    async def start(self, listen_addr: str) -> None:
        if self.server_credentials is None:
            logging.info("Starting server on insecure port %s", listen_addr)
            self.server.add_insecure_port(listen_addr)
        else:
            logging.info("Starting server on secure port %s", listen_addr)
            self.server.add_secure_port(listen_addr, self.server_credentials)

        try:
            await self.server.start()
            await self.server.wait_for_termination()
        finally:
            await self.server.stop(grace=5)
    
    def _register_servicers(self, servicers) -> None:
        """
        Automates the boilerplate code for registering servicers to the server
        """
        
        service_names = []
        for servicer in servicers:
            logging.info("Registering servicer %s", servicer.__class__.__name__)
            servicer_parent_class = servicer.__class__.__bases__[0]
            servicer_module_pb2_grpc = importlib.import_module(
                servicer_parent_class.__module__
            )
            servicer_module_pb2 = importlib.import_module(
                servicer_parent_class.__module__.removesuffix("_grpc")
            )
            getattr(
                servicer_module_pb2_grpc,
                f"add_{servicer_parent_class.__name__}_to_server",
            )(servicer, self.server)
            service_names.append(
                servicer_module_pb2.DESCRIPTOR.services_by_name[
                    servicer_parent_class.__name__.removesuffix("Servicer")
                ].full_name
            )

        reflection.enable_server_reflection(
            service_names + [reflection.SERVICE_NAME], self.server
        )
        
        # TODO: Add service health-checks (https://grpc.github.io/grpc/core/md_doc_health-checking.html)
