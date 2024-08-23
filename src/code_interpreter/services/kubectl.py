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
from inspect import signature
import json
import logging
import shlex
from typing import Any, Awaitable, Callable, Literal, get_overloads, overload


class Kubectl:
    """
    A dumb wrapper around the `kubectl` CLI. It depends on the `kubectl` binary being available in the PATH.
    Unlike the official and unofficial Python clients for Kubernetes, this wrapper is both async and fully supports `kubectl exec`.

    The sub-command of `kubectl` translates to method name, the rest of the arguments are passed as string arguments:
    `kubectl.exec("my-pod", "--", "ls", "-l")` -> `kubectl exec my-pod -- ls -l`

    Keyword arguments are passed as `--key=value` or `--key` if the value is `True`:
    `kubectl.delete("pod", "my-pod", now=True, grace_period=0)` -> `kubectl delete pod my-pod --now --grace-period=0`

    For commands that support JSON, `--output=json` is automatically added and the output is parsed and returned as a Python dict:
    `kubectl.get("pod", "my-pod")` -> `kubectl get pod my-pod --output=json`

    As a special case, `exec_raw` is provided to run a command and get the `asyncio.subprocess.Process` object back. This is useful for streaming data to/from the process.

    The keyword arguments passed to the constructor are used as default arguments for all commands. Useful for setting the namespace or context.
    """

    _default_kwargs: dict[str, str | bool] = {}

    def __init__(self, **kwargs: str | bool | None):
        self._default_kwargs = self._fix_kwargs(kwargs)

    def _fix_kwargs(
        self, kwargs: dict[str, str | bool | None]
    ) -> dict[str, str | bool]:
        return {key.removeprefix("_"): value for key, value in kwargs.items() if value}

    async def _spawn_process(
        self, *args: str, **kwargs: str | bool | None
    ) -> asyncio.subprocess.Process:
        dashdash_position = next(
            (i for i, arg in enumerate(args) if arg == "--"), len(args)
        )
        all_args = (
            list(args[:dashdash_position])
            + [
                (f"--{key}={value}" if value is not True else f"--{key}")
                for key, value in (
                    self._default_kwargs | self._fix_kwargs(kwargs)
                ).items()
            ]
            + list(args[dashdash_position:])
        )
        logging.info(f"Running kubectl command: kubectl {shlex.join(all_args)}")
        return await asyncio.create_subprocess_exec(
            "kubectl",
            *all_args,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

    async def _command(
        self,
        *args: str,
        input: bytes | str | list | dict | None = None,
        **kwargs: str | bool | None,
    ) -> str:
        process = await self._spawn_process(*args, **kwargs)
        if input and process.stdin:
            if isinstance(input, list) or isinstance(input, dict):
                input = json.dumps(input)
            if isinstance(input, str):
                input = input.encode()
            process.stdin.write(input)
            process.stdin.write_eof()
        stdout, stderr = await process.communicate()
        if process.returncode != 0:
            raise RuntimeError(
                f"Error ({process.returncode}) running kubectl command: {stderr.decode()}"
            )
        return stdout.decode()

    @overload
    def __getattr__(
        self,
        name: Literal[
            "annotate",
            "apply",
            "autoscale",
            "create",
            "edit",
            "events",
            "expose",
            "get",
            "label",
            "patch",
            "replace",
            "run",
            "scale",
            "taint",
            "version",
            "wait",
        ],
    ) -> Callable[..., Awaitable[dict]]:
        async def command_json(
            *args: str,
            input: bytes | str | list | dict | None = None,
            **kwargs: str | bool | None,
        ) -> dict:
            output_str = await self._command(
                name.replace("_", "-"), *args, input=input, output="json", **kwargs
            )
            return json.loads(output_str)

        return command_json

    @overload
    def __getattr__(
        self,
        name: Literal[
            "api_resources",
            "api_versions",
            "attach",
            "auth",
            "certificate",
            "cluster_info",
            "completion",
            "config",
            "cordon",
            "cp",
            "ctx",
            "debug",
            "delete",
            "describe",
            "diff",
            "drain",
            "exec",
            "explain",
            "help",
            "kustomize",
            "logs",
            "ns",
            "options",
            "plugin",
            "port_forward",
            "proxy",
            "rollout",
            "set",
            "top",
            "uncordon",
        ],
    ) -> Callable[..., Awaitable[str]]:
        async def command(
            *args: str,
            input: bytes | str | list | dict | None = None,
            **kwargs: str | bool | None,
        ) -> str:
            return await self._command(
                name.replace("_", "-"), *args, input=input, **kwargs
            )

        return command

    def __getattr__(self, name: str) -> Callable[..., Awaitable[Any]]:
        getattr_overloads = get_overloads(self.__getattr__)
        for getattr_overload in getattr_overloads:
            if (
                name
                in signature(getattr_overload).parameters["name"].annotation.__args__
            ):
                return getattr_overload(self, name)  # type: ignore
        raise AttributeError(f"Command {name} not found")

    async def exec_raw(
        self, *args, **kwargs: str | bool | None
    ) -> asyncio.subprocess.Process:
        return await self._spawn_process("exec", *args, **kwargs)
