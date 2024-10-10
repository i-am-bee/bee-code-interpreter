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
import secrets
from typing import AsyncIterator, Protocol
from anyio import Path
from pydantic import validate_call

from code_interpreter.utils.validation import Hash


class ObjectReader(Protocol):
    async def read(self, size: int = -1) -> bytes: ...


class ObjectWriter(Protocol):
    hash: str

    async def write(self, data: bytes) -> None: ...


class Storage:
    """
    Storage is a collection of objects. Objects consist of binary data and are identified by their SHA-256 hash.

    This implementation is backed by the filesystem, where each object is stored as a file named by its hash.
    """

    def __init__(self, storage_path: str):
        self.storage_path = Path(storage_path)

    @asynccontextmanager
    async def writer(self) -> AsyncIterator[ObjectWriter]:
        """
        Async context manager for writing a new object to the storage.

        The final hash can be retrieved by using the `.hash` attribute
        """
        await self.storage_path.mkdir(parents=True, exist_ok=True)
        hash = secrets.token_hex(32)
        async with await (self.storage_path / hash).open("wb") as file:
            file.__setattr__("hash", hash)
            yield file

    async def write(self, data: bytes) -> str:
        """
        Writes the data to the storage and returns the hash of the object.
        """
        async with self.writer() as f:
            await f.write(data)
            return f.hash

    @asynccontextmanager
    @validate_call
    async def reader(self, object_hash: Hash) -> AsyncIterator[ObjectReader]:
        """
        Async context manager that opens an object for reading.
        """
        target_file = self.storage_path / object_hash
        if not object_hash or not await target_file.exists():
            raise FileNotFoundError(f"File not found: {object_hash}")
        async with await target_file.open("rb") as f:
            yield f

    @validate_call
    async def read(self, object_hash: Hash) -> bytes:
        """
        Reads the object with the given hash and returns it.
        """
        async with self.reader(object_hash) as f:
            return await f.read()

    @validate_call
    async def exists(self, object_hash: Hash) -> bool:
        """
        Check if an object with the given hash exists in the storage.
        """
        return await (self.storage_path / object_hash).exists()
