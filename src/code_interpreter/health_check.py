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

from code_interpreter.config import Config
import grpc
from proto.code_interpreter.v1.code_interpreter_service_pb2 import (
    ExecuteRequest,
)
from proto.code_interpreter.v1.code_interpreter_service_pb2_grpc import (
    CodeInterpreterServiceStub,
)


def health_check():
    config = Config()

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

    assert (
        CodeInterpreterServiceStub(channel)
        .Execute(
            ExecuteRequest(source_code="print(21 * 2)"),
            timeout=9999,  # no need to timeout here -- k8s health checks have their own timeouts
        )
        .stdout
        == "42\n"
    )


if __name__ == "__main__":
    health_check()
