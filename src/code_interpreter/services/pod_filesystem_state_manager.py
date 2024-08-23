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

import re
import shlex
from typing import Mapping

from frozendict import frozendict
from pydantic import validate_call
from code_interpreter.services.kubectl import Kubectl
from code_interpreter.services.pod_file_manager import PodFileManager
from code_interpreter.services.storage import Storage
from code_interpreter.utils.validation import AbsolutePath, Hash


class PodFilesystemStateManager:
    """
    Service responsible for managing filesystem for executor pods.

    This service manages only the "managed folders" of the pod, which are supposed to correspond to all user-writable folders.

    Similarly to Git, empty folders are not tracked, and files are tracked by their content hash.
    """

    def __init__(
        self,
        kubectl: Kubectl,
        pod_file_manager: PodFileManager,
        file_storage: Storage,
        managed_folders: list[str],
        buffer_size: int = 4096,
    ):
        self.kubectl = kubectl
        self.pod_file_manager = pod_file_manager
        self.file_storage = file_storage
        self.managed_folders = managed_folders
        self.buffer_size = buffer_size

    async def scan(self, pod_name: str) -> frozendict[AbsolutePath, Hash]:
        """
        Read the state of the managed folders of the pod.
        """
        sha256sum_output = await self.kubectl.exec(
            pod_name,
            "--",
            "sh",
            "-c",
            f"find {shlex.join(self.managed_folders)} -type f | xargs --no-run-if-empty -- sha256sum --zero --binary",
        )
        return frozendict(
            {
                path: hash
                for line in sha256sum_output.split("\x00")
                if line
                for hash, path in [line.split(" *")]
            }
        )

    async def commit(self, pod_name: str) -> frozendict[AbsolutePath, Hash]:
        """
        Save newly created files in the managed folders of the pod to the file storage.
        """
        files = await self.scan(pod_name)
        for file_path, file_hash in files.items():
            if await self.file_storage.exists(file_hash):
                continue
            async with self.file_storage.writer() as stored_file, self.pod_file_manager.reader(
                pod_name, file_path
            ) as pod_file:
                while buffer := await pod_file.read(n=self.buffer_size):
                    await stored_file.write(buffer)
        return files

    @validate_call
    async def restore(
        self, pod_name: str, files: Mapping[AbsolutePath, Hash] = {}
    ) -> None:
        """
        Restore the managed folders of the pod to the given state.
        """
        current_files = await self.scan(pod_name)
        to_delete = frozendict(current_files.items() - files.items())
        to_upload = frozendict(files.items() - current_files.items())

        for path in to_delete.keys() | to_upload.keys():
            if not any(
                path.startswith(prefix + "/") for prefix in self.managed_folders
            ):
                raise ValueError(f"Path {path} is outside of managed folders")

        # remove unneeded files
        if to_delete:
            await self.kubectl.exec(pod_name, "--", "rm", "--", *to_delete.keys())

        # remove unneeded folders
        await self.kubectl.exec(
            pod_name,
            "--",
            "find",
            *self.managed_folders,
            "-type",
            "d",
            "-mindepth",
            "1",
            "-empty",
            "-delete",
        )

        if to_upload:
            # create needed folders
            folders_to_create = [
                file_path
                for file_path in (
                    re.sub(r"[^/]*$", "", file_path) for file_path in to_upload.keys()
                )
                if file_path
            ]
            if folders_to_create:
                await self.kubectl.exec(
                    pod_name, "--", "mkdir", "-p", "--", *folders_to_create
                )

            # upload needed files
            for file_path, file_hash in to_upload.items():
                async with self.file_storage.reader(
                    file_hash
                ) as stored_file, self.pod_file_manager.writer(
                    pod_name, file_path
                ) as pod_file:
                    while buffer := await stored_file.read(size=self.buffer_size):
                        pod_file.write(buffer)
                        await pod_file.drain()
