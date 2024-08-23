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

from contextlib import asynccontextmanager
from dataclasses import dataclass
import logging
from datetime import UTC, datetime, timedelta
from typing import AsyncGenerator, Mapping

from frozendict import frozendict
from pydantic import validate_call
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from code_interpreter.services.pod_filesystem_state_manager import (
    PodFilesystemStateManager,
)
from code_interpreter.services.kubectl import Kubectl
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
        pod_filesystem_state_manager: PodFilesystemStateManager,
        executor_pod_spec_extra: dict,
    ) -> None:
        self.kubectl = kubectl
        self.executor_image = executor_image
        self.container_resources = container_resources
        self.pod_filesystem_state_manager = pod_filesystem_state_manager
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
        async with self._executor_pod(executor_id) as executor_pod_name:
            await self.pod_filesystem_state_manager.restore(executor_pod_name, files)
            process = await self.kubectl.exec_raw(
                executor_pod_name,
                "--",
                "/execute",
                stdin=True,
            )
            if process.stdin is None:
                raise RuntimeError("Error opening stdin for kubectl exec")
            process.stdin.write(source_code.encode())
            await process.stdin.drain()
            process.stdin.close()
            stdout, stderr = await process.communicate()
            new_files = await self.pod_filesystem_state_manager.commit(
                executor_pod_name
            )
            return KubernetesCodeExecutor.Result(
                stdout=stdout.decode(),
                stderr=stderr.decode(),
                exit_code=process.returncode or 0,
                files=new_files,
            )

    async def cleanup_executors(self, max_idle_time: timedelta) -> None:
        """
        Remove executor pods that have been idle for longer than `max_idle_time`.
        This is controlled using the `last_exec_at` annotation, which is updated every time a pod is used.

        This method is meant to be called periodically.
        """
        logging.info("Cleaning up old executors")
        for pod in (
            await self.kubectl.get("pods", selector="app=code-interpreter-executor")
        )["items"]:
            last_exec_at = pod["metadata"]["annotations"]["last_exec_at"]
            if not last_exec_at:
                continue
            if datetime.now(UTC) - datetime.fromisoformat(last_exec_at) > max_idle_time:
                logging.info(f"Deleting executor pod {pod['metadata']['name']}")
                await self.kubectl.delete("pod", pod["metadata"]["name"])

    @asynccontextmanager
    async def _executor_pod(self, executor_id: ExecutorId) -> AsyncGenerator[str, None]:
        executor_pods = await self.kubectl.get(
            "pods",
            selector=f"app=code-interpreter-executor,executor_id={executor_id}",
        )

        free_executor_pods = [
            pod
            for pod in executor_pods["items"]
            if not pod["metadata"]["annotations"].get("locked_at")
        ]

        if free_executor_pods:
            executor_pod = free_executor_pods[0]
            executor_pod["metadata"]["annotations"]["locked_at"] = datetime.now(
                UTC
            ).isoformat()
            # "kubectl replace" has compare-and-swap semantics, which ensures that only one client can lock the pod
            await self.kubectl.replace(
                "pod",
                executor_pod["metadata"]["name"],
                filename="-",
                input=executor_pod,
            )
            executor_pod_name = executor_pod["metadata"]["name"]
        else:
            executor_pod_names_in_use = {
                executor_pod["metadata"]["name"]
                for executor_pod in executor_pods["items"]
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
                        "annotations": {
                            "last_exec_at": datetime.now(UTC).isoformat(),
                            "locked_at": datetime.now(UTC).isoformat(),
                        },
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
                                "command": ["sleep", "infinity"],
                                "resources": self.container_resources,
                            }
                        ],
                        **self.executor_pod_spec_extra,
                    },
                },
            )

        pod = await self.kubectl.wait("pod", executor_pod_name, _for="condition=Ready")

        try:
            yield pod["metadata"]["name"]
        finally:
            await self.kubectl.annotate("pod", executor_pod_name, "locked_at-")
