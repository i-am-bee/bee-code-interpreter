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
import hashlib
import secrets
from typing import AsyncIterator, Protocol
from anyio import AsyncFile, Path
from pydantic import validate_call

from code_interpreter.utils.validation import Hash


class ObjectReader(Protocol):
    async def read(self, size: int = -1) -> bytes: ...


class ObjectWriter(Protocol):
    async def write(self, data: bytes) -> None: ...
    def hash(self) -> str: ...


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

        Internally, we write to a temporary file first, then rename it to the final name after writing is complete.
        This is because the file hash is computed on-the-fly as the data is written.
        This is internally done by wrapping the `write` function of the returned `ObjectWriter` to also call update the hash.
        The final hash can be retrieved by using the `.hash()` method after the writing is completed.
        """

        class _AsyncFileWrapper:
            def __init__(self, file: AsyncFile[bytes]):
                self._file = file
                self._hash = hashlib.sha256()

            async def write(self, data: bytes) -> None:
                self._hash.update(data)
                await self._file.write(data)

            def hash(self) -> str:
                return self._hash.hexdigest()

        await self.storage_path.mkdir(parents=True, exist_ok=True)
        tmp_name = f"tmp-{secrets.token_hex(32)}"
        tmp_file = self.storage_path / tmp_name
        try:
            async with await tmp_file.open("wb") as f:
                wrapped_file = _AsyncFileWrapper(f)
                yield wrapped_file
            final_name = wrapped_file.hash()
            final_file = self.storage_path / final_name
            if not await final_file.exists():
                await tmp_file.rename(final_file)
        finally:
            if await tmp_file.exists():
                await tmp_file.unlink()

    async def write(self, data: bytes) -> str:
        """
        Writes the data to the storage and returns the hash of the object.
        """
        async with self.writer() as f:
            await f.write(data)
            return f.hash()

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
