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

    # logging level
    log_level: str = "DEBUG"

    # the address and port gRPC server will listen on
    grpc_listen_addr: str = "0.0.0.0:50051"

    # text content of the TLS certificate file
    grpc_tls_cert: bytes | None = None

    # text content of the TLS key file
    grpc_tls_cert_key: bytes | None = None

    # text content of the CA certificate file
    grpc_tls_ca_cert: bytes | None = None

    # Kubernetes context from ~/.kube/config to use -- defaults to current context or in-cluster config
    kubernetes_context: str | None = None

    # Kubernetes namespace to use -- defaults to current namespace according to context or in-cluster config
    kubernetes_namespace: str | None = None

    # the image to use for the executor pods
    executor_image: str = "localhost/bee-code-interpreter-executor:local"

    # maximum time in seconds an executor pod can be idle before being deleted
    executor_max_idle_time: int = 3600

    # interval in seconds to check for idle executors and delete them
    executor_cleanup_interval: int = 300

    # 'resources' field for executor pod container
    executor_container_resources: dict = {}

    # extra fields for executor pod spec
    executor_pod_spec_extra: dict = {}

    # folders to manage in executor pods by saving and restoring them
    executor_managed_folders: list[str] = ["/workspace"]

    # path to store files
    file_storage_path: str = "./.tmp/files"

    # how many executor pods to keep ready for immediate use
    executor_pod_queue_target_length: int = 5
