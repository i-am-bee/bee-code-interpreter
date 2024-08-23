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
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from code_interpreter.services.kubectl import Kubectl


class PodFileManager:
    def __init__(self, kubectl: Kubectl):
        self.kubectl = kubectl

    @asynccontextmanager
    async def writer(
        self, pod: str, file_path: str
    ) -> AsyncGenerator[asyncio.streams.StreamWriter, None]:
        process = await self.kubectl.exec_raw(
            pod,
            "--",
            "tee",
            file_path,
            stdin=True,
        )
        if not process.stdin:
            raise RuntimeError("Error opening stdin for kubectl exec")
        try:
            yield process.stdin
        finally:
            if process.stdin:
                await process.stdin.drain()
                process.stdin.close()
            _, stderr = await process.communicate()
            if process.returncode != 0:
                raise RuntimeError(
                    f"Error ({process.returncode}) writing to pod: {stderr.decode()}"
                )

    async def write(self, data: bytes, pod: str, file_path: str) -> None:
        async with self.writer(pod, file_path) as writer:
            writer.write(data)

    @asynccontextmanager
    async def reader(
        self, pod: str, file_path: str
    ) -> AsyncGenerator[asyncio.streams.StreamReader, None]:
        process = await self.kubectl.exec_raw(pod, "--", "cat", file_path)
        if not process.stdout:
            raise RuntimeError("Error opening stdout for kubectl exec")
        try:
            yield process.stdout
        finally:
            _, stderr = await process.communicate()
            if process.returncode != 0:
                raise RuntimeError(
                    f"Error ({process.returncode}) reading from pod: {stderr.decode()}"
                )

    async def read(self, pod: str, file_path: str) -> bytearray:
        buffer = bytearray()
        async with self.reader(pod, file_path) as reader:
            while read_bytes := await reader.read():
                buffer += read_bytes
        return buffer
