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
import collections
import logging
import os
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
from code_interpreter.utils.validation import AbsolutePath, Hash

logger = logging.getLogger("kubernetes_code_executor")

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
        executor_pod_queue_target_length: int,
    ) -> None:
        self.kubectl = kubectl
        self.executor_image = executor_image
        self.container_resources = container_resources
        self.file_storage = file_storage
        self.executor_pod_spec_extra = executor_pod_spec_extra
        self.self_pod = None
        self.executor_pod_queue_target_length = executor_pod_queue_target_length
        self.executor_pod_queue_spawning_count = 0
        self.executor_pod_queue = collections.deque()

    @retry(
        retry=retry_if_exception_type(RuntimeError),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=4, max=10),
    )
    @validate_call
    async def execute(
        self,
        source_code: str,
        files: Mapping[AbsolutePath, Hash] = frozendict(),
    ) -> Result:
        """
        Executes the given Python source code in a Kubernetes pod.

        Optionally, a file mapping can be provided to restore the pod filesystem to a specific state.
        If none is provided, starts from a blank slate.

        Every time, a fresh pod is taken from a queue. It is discarded after use.
        """
        async with self.executor_pod() as executor_pod, httpx.AsyncClient(
            timeout=60.0
        ) as client:
            executor_pod_ip = executor_pod["status"]["podIP"]

            async def upload_file(file_path, file_hash):
                async with self.file_storage.reader(file_hash) as file_reader:
                    return await client.put(
                        f"http://{executor_pod_ip}:8000/workspace/{file_path.removeprefix("/workspace/")}",
                        data=file_reader,
                    )

            logger.info("Uploading %s files to executor pod", len(files))
            await asyncio.gather(
                *(
                    upload_file(file_path, file_hash)
                    for file_path, file_hash in files.items()
                )
            )

            logger.info("Requesting code execution")
            response = (
                await client.post(
                    f"http://{executor_pod_ip}:8000/execute",
                    json={
                        "source_code": source_code,
                    },
                )
            ).json()

            changed_files = {
                file["path"]: file["new_hash"]
                for file in response["files"]
                if file["old_hash"] != file["new_hash"] and file["new_hash"]
            }

            async def download_file(file_path, file_hash) -> str:
                if await self.file_storage.exists(file_hash):
                    return
                async with self.file_storage.writer() as stored_file, client.stream(
                    "GET",
                    f"http://{executor_pod_ip}:8000/workspace/{file_path.removeprefix("/workspace/")}",
                ) as pod_file:
                    pod_file.raise_for_status()
                    async for chunk in pod_file.aiter_bytes():
                        await stored_file.write(chunk)
                return file_path, stored_file.hash

            logger.info("Collecting %s changed files", len(changed_files))
            stored_files = {
                stored_file_path: stored_file_hash
                for stored_file_path, stored_file_hash in await asyncio.gather(
                    *(
                        download_file(file_path, file_hash)
                        for file_path, file_hash in changed_files.items()
                    )
                )
            }

            return KubernetesCodeExecutor.Result(
                stdout=response["stdout"],
                stderr=response["stderr"],
                exit_code=response["exit_code"],
                files=stored_files,
            )

    async def fill_executor_pod_queue(self):
        """
        Ensure that we have enough ready executor pods.
        """
        count_to_spawn = (
            self.executor_pod_queue_target_length
            - len(self.executor_pod_queue)
            - self.executor_pod_queue_spawning_count
        )
        if count_to_spawn <= 0:
            return
        logger.info(
            "Extending executor pod queue to target length %s, current queue length: %s, already spawning: %s, to spawn: %s",
            self.executor_pod_queue_target_length,
            len(self.executor_pod_queue),
            self.executor_pod_queue_spawning_count,
            count_to_spawn,
        )
        self.executor_pod_queue_spawning_count += count_to_spawn

        spawned_pods = 0
        for pod_spawn_task in asyncio.as_completed(
            asyncio.create_task(self.spawn_executor_pod())
            for _ in range(count_to_spawn)
        ):
            try:
                self.executor_pod_queue.append(await pod_spawn_task)
                spawned_pods += 1
            except Exception as e:
                logger.error(f"Failed to spawn executor pod: {e}")
            finally:
                self.executor_pod_queue_spawning_count -= 1
        logger.info(
            "Executor pod queue extended, spawned: %s, failed to spawn: %s, current queue length: %s, still spawning: %s",
            spawned_pods,
            count_to_spawn - spawned_pods,
            len(self.executor_pod_queue),
            self.executor_pod_queue_spawning_count,
        )

    @retry(
        retry=retry_if_exception_type(RuntimeError),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=4, max=10),
    )
    async def spawn_executor_pod(self):
        """
        Create a new executor pod and return its JSON
        """
        if self.self_pod is None:
            self.self_pod = await self.kubectl.get("pod", os.environ["HOSTNAME"])
        pod = await self.kubectl.create(
            filename="-",
            input={
                "apiVersion": "v1",
                "kind": "Pod",
                "metadata": {
                    "generateName": "code-interpreter-executor-",
                    "labels": {
                        "app": "code-interpreter-executor",
                    },
                    "ownerReferences": [
                        {
                            "apiVersion": "v1",
                            "kind": "Pod",
                            "name": self.self_pod["metadata"]["name"],
                            "uid": self.self_pod["metadata"]["uid"],
                            "controller": True,
                            "blockOwnerDeletion": False,
                        }
                    ],
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
        pod = await self.kubectl.wait(
            "pod", pod["metadata"]["name"], _for="condition=Ready"
        )
        return pod

    @asynccontextmanager
    async def executor_pod(self) -> AsyncGenerator[dict, None]:
        """
        Context manager that grabs a ready executor pod from the queue and deletes it when done.
        """
        pod = (
            self.executor_pod_queue.popleft()
            if self.executor_pod_queue
            else await self.spawn_executor_pod()
        )
        asyncio.create_task(self.fill_executor_pod_queue())
        try:
            logger.info("Grabbing executor pod %s", pod["metadata"]["name"])
            yield pod
        finally:
            logger.info("Removing used executor pod %s", pod["metadata"]["name"])
            asyncio.create_task(self.kubectl.delete("pod", pod["metadata"]["name"]))
