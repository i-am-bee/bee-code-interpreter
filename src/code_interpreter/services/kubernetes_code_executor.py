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
import httpx
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import AsyncGenerator, Mapping

from frozendict import frozendict
from pydantic import validate_call
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from code_interpreter.services.kubectl import Kubectl
from code_interpreter.services.storage import Storage
from code_interpreter.utils.validation import AbsolutePath, ExecutorId, Hash


class KubernetesCodeExecutor:
    """
    Heart of the code interpreter service, this class is responsible for:
    - Provisioning and managing executor pods
    - Executing Python code in the pods
    - Cleaning up old executor pods
    """

    @dataclass
    class Result:
        stdout: str
        stderr: str
        exit_code: int
        files: Mapping[AbsolutePath, Hash]

    def __init__(
        self,
        kubectl: Kubectl,
        executor_image: str,
        container_resources: dict,
        file_storage: Storage,
        executor_pod_spec_extra: dict,
    ) -> None:
        self.kubectl = kubectl
        self.executor_image = executor_image
        self.container_resources = container_resources
        self.file_storage = file_storage
        self.executor_pod_spec_extra = executor_pod_spec_extra

    @retry(
        retry=retry_if_exception_type(RuntimeError),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=4, max=10),
    )
    @validate_call
    async def execute(
        self,
        executor_id: ExecutorId,
        source_code: str,
        files: Mapping[AbsolutePath, Hash] = frozendict(),
    ) -> Result:
        """
        Executes the given Python source code in a Kubernetes pod.

        Optionally, a file mapping can be provided to restore the pod filesystem to a specific state.
        If none is provided, starts from a blank slate.

        As pods are left running for some time, we primarily try to reuse existing pods. If none are available, we spawn a new one.
        The pod is locked to prevent concurrent use, and the lock is removed when the context manager exits.

        The `executor_id` serves to differentiate between users, as only pods with matching `executor_id` will ever be re-used.
        This is mainly a "just to be sure" security mechanism in case users find a way to tamper with the pods.
        """
        async with self._executor_pod(
            executor_id
        ) as executor_pod, httpx.AsyncClient() as client:
            executor_pod_ip = executor_pod["status"]["podIP"]

            async def upload_file(file_path, file_hash):
                async with self.file_storage.reader(file_hash) as file_reader:
                    return await client.put(
                        f"http://{executor_pod_ip}:8000/workspace/{file_path}",
                        data=file_reader,
                    )

            await asyncio.gather(
                *(
                    upload_file(file_path, file_hash)
                    for file_path, file_hash in files.items()
                )
            )

            response = (
                await client.post(
                    f"http://{executor_pod_ip}:8000/execute",
                    json={
                        "source_code": source_code,
                    },
                )
            ).json()

            return KubernetesCodeExecutor.Result(
                stdout=response["stdout"],
                stderr=response["stderr"],
                exit_code=response["exit_code"],
                files={
                    file["path"]: file["new_hash"]
                    for file in response["files"]
                    if file["old_hash"] != file["new_hash"] and file["new_hash"]
                },
            )

    @asynccontextmanager
    async def _executor_pod(
        self, executor_id: ExecutorId
    ) -> AsyncGenerator[dict, None]:
        executor_pods = await self.kubectl.get(
            "pods",
            selector=f"app=code-interpreter-executor,executor_id={executor_id}",
        )

        executor_pod_names_in_use = {
            executor_pod["metadata"]["name"] for executor_pod in executor_pods["items"]
        }
        executor_pod_name = next(
            f"code-interpreter-executor-{executor_id}-{i}"
            for i in range(len(executor_pods["items"]) + 1)
            if f"code-interpreter-executor-{executor_id}-{i}"
            not in executor_pod_names_in_use
        )

        await self.kubectl.create(
            filename="-",
            input={
                "apiVersion": "v1",
                "kind": "Pod",
                "metadata": {
                    "name": executor_pod_name,
                    "labels": {
                        "app": "code-interpreter-executor",
                        "executor_id": executor_id,
                    },
                },
                "spec": {
                    "containers": [
                        {
                            "name": "executor",
                            "image": self.executor_image,
                            "resources": self.container_resources,
                            "ports": [{"containerPort": 8000}],
                        }
                    ],
                    **self.executor_pod_spec_extra,
                },
            },
        )

        pod = await self.kubectl.wait("pod", executor_pod_name, _for="condition=Ready")

        try:
            yield pod
        finally:
            pass
            # asyncio.create_task(self.kubectl.delete("pod", executor_pod_name))
