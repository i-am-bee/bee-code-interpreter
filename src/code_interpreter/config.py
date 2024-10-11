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

from pydantic_settings import BaseSettings, SettingsConfigDict


class Config(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="APP_", env_ignore_empty=True)

    # logging config: https://docs.python.org/3/library/logging.config.html#logging-config-dictschema
    logging_config: dict = {
        "version": 1,
        "disable_existing_loggers": False,
        "handlers": {
            "console": {
                "class": "logging.StreamHandler",
                "formatter": "standard",
            },
        },
        "formatters": {
            "standard": {
                "format": "[%(levelname)s] [%(request_id)s] %(name)s: %(message)s",
            },
        },
        "root": {
            "level": "WARNING",
            "handlers": ["console"],
            "propagate": True,
        },
        "loggers": {
            "kubectl": {"level": "INFO"},
            "grpc_server": {"level": "INFO"},
            "code_interpreter_servicer": {"level": "INFO"},
            "kubernetes_code_executor": {"level": "INFO"},
        },
    }

    # the address and port gRPC server will listen on
    grpc_listen_addr: str = "0.0.0.0:50051"

    # the address and port HTTP server will listen on
    http_listen_addr: str = "0.0.0.0:8000"

    # text content of the TLS certificate file
    grpc_tls_cert: bytes | None = None

    # text content of the TLS key file
    grpc_tls_cert_key: bytes | None = None

    # text content of the CA certificate file
    grpc_tls_ca_cert: bytes | None = None

    # the image to use for the executor pods
    executor_image: str = "localhost/bee-code-executor:local"

    # 'resources' field for executor pod container
    executor_container_resources: dict = {}

    # extra fields for executor pod spec
    executor_pod_spec_extra: dict = {}

    # path to store files
    file_storage_path: str = "./.tmp/files"

    # how many executor pods to keep ready for immediate use
    executor_pod_queue_target_length: int = 5

    # first part of executor pod name, followed by number
    executor_pod_name_prefix: str = "code-executor-"
