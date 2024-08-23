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

import ast
from dataclasses import dataclass
import json
import typing
import inspect
import re
import textwrap

from pydantic import validate_call

from code_interpreter.services.kubernetes_code_executor import KubernetesCodeExecutor
from code_interpreter.utils.validation import ExecutorId


@dataclass
class CustomTool:
    name: str
    description: str
    input_schema: dict


@dataclass
class CustomToolParseError(Exception):
    errors: list[str]


@dataclass
class CustomToolExecuteError(Exception):
    stderr: str


class CustomToolExecutor:
    def __init__(self, code_executor: KubernetesCodeExecutor):
        self.code_executor = code_executor

    def parse(self, tool_source_code: str) -> CustomTool:
        """
        Parse a Python function definition.

        The source code must contain a single function definition, optionally preceded by imports. The function must not have positional-only arguments, *args or **kwargs.
        The function arguments must have type annotations. The docstring must follow the ReST format -- :param something: and :return: directives are supported.

        Supported types for input arguments: int, float, str, bool, typing.Any, list[...], dict[str, ...], typing.Tuple[...], typing.Optional[...], typing.Union[...], where ... is any of the supported types.
        Supported types for return value: anything that can be JSON-serialized.
        """
        try:
            *imports, function_def = ast.parse(textwrap.dedent(tool_source_code)).body
        except SyntaxError as e:
            raise CustomToolParseError([f"Syntax error: {e.msg} on line {e.lineno}"])

        if not all(
            isinstance(node, (ast.Import, ast.ImportFrom)) for node in imports
        ) or not isinstance(function_def, ast.FunctionDef):
            raise CustomToolParseError(
                [
                    "The tool source code must only define a single function, optionally preceded by imports."
                ]
            )

        errors = [
            x
            for x in (
                "The tool function must not have positional-only arguments"
                if function_def.args.posonlyargs
                else None,
                "The tool function must not have *args"
                if function_def.args.vararg
                else None,
                "The tool function must not have **kwargs"
                if function_def.args.kwarg
                else None,
                "The tool function arguments must have type annotations"
                if not all(
                    arg.annotation
                    for arg in (*function_def.args.args, *function_def.args.kwonlyargs)
                )
                else None,
            )
            if x is not None
        ]

        if errors:
            raise CustomToolParseError(errors)

        fn_description, return_description, param_descriptions = _parse_docstring(
            ast.get_docstring(function_def) or ""
        )

        json_schema = {
            "$schema": "http://json-schema.org/draft-07/schema#",
            "type": "object",
            "title": function_def.name,
            "properties": {
                arg.arg: _type_to_json_schema(arg.annotation)
                | (
                    {"description": param_description}
                    if (param_description := param_descriptions.get(arg.arg))
                    else {}
                )
                for arg in (*function_def.args.args, *function_def.args.kwonlyargs)
                if arg.annotation
            },
            "required": [
                arg.arg
                for arg in (
                    *function_def.args.args[: -len(function_def.args.defaults) or None],
                    *(
                        arg
                        for arg, default in zip(
                            function_def.args.kwonlyargs, function_def.args.kw_defaults
                        )
                        if default is None
                    ),
                )
            ],
            "additionalProperties": False,
        }

        return_type = (
            ast.unparse(function_def.returns) if function_def.returns else None
        )
        return_full_description = " -- ".join(
            s for s in (return_type, return_description) if s
        )

        description = "\n\n".join(
            s
            for s in (
                fn_description,
                "Returns: " + return_full_description
                if return_full_description
                else None,
            )
            if s
        )

        return CustomTool(
            name=function_def.name,
            description=description,
            input_schema=json_schema,
        )

    @validate_call
    async def execute(
        self,
        executor_id: ExecutorId,
        tool_source_code: str,
        tool_input: dict[str, typing.Any],
    ) -> typing.Any:
        """
        Execute the given custom tool with the given input.

        The source code is expected to be valid according to the parse method.
        The input is expected to be valid according to the input schema produced by the parse method.
        """

        result = await self.code_executor.execute(
            executor_id=executor_id,
            source_code=f"""
import contextlib
import json

# Import all tool dependencies here -- to aid the dependency detection
{
    "\n".join(
        ast.unparse(node)
        for node in ast.parse(textwrap.dedent(tool_source_code)).body
        if isinstance(node, (ast.Import, ast.ImportFrom))
    )
}

with contextlib.redirect_stdout(None):
    inner_globals = {{}}
    exec(compile({repr(textwrap.dedent(tool_source_code))}, "<string>", "exec"), inner_globals)
    result = next(x for x in inner_globals.values() if getattr(x, '__module__', ...) is None)(**{repr(tool_input)})

print(json.dumps(result))
        """,
        )

        if result.exit_code != 0:
            raise CustomToolExecuteError(result.stderr)

        return json.loads(result.stdout)


def _type_to_json_schema(type_node: ast.AST) -> dict:
    if isinstance(type_node, ast.Subscript):
        type_node_name = ast.unparse(type_node.value)
        if type_node_name == "list":
            return {"type": "array", "items": _type_to_json_schema(type_node.slice)}
        elif type_node_name == "dict" and isinstance(type_node.slice, ast.Tuple):
            key_type_node, value_type_node = type_node.slice.elts
            if ast.unparse(key_type_node) != "str":
                raise ValueError(f"Unsupported type: {type_node}")
            return {
                "type": "object",
                "additionalProperties": _type_to_json_schema(value_type_node),
            }
        elif type_node_name == "Optional" or type_node_name == "typing.Optional":
            return {"anyOf": [{"type": "null"}, _type_to_json_schema(type_node.slice)]}
        elif (
            type_node_name == "Union" or type_node_name == "typing.Union"
        ) and isinstance(type_node.slice, ast.Tuple):
            return {"anyOf": [_type_to_json_schema(el) for el in type_node.slice.elts]}
        elif (
            type_node_name == "Tuple" or type_node_name == "typing.Tuple"
        ) and isinstance(type_node.slice, ast.Tuple):
            return {
                "type": "array",
                "minItems": len(type_node.slice.elts),
                "items": [_type_to_json_schema(el) for el in type_node.slice.elts],
                "additionalItems": False,
            }

    type_node_name = ast.unparse(type_node)
    if type_node_name == "int":
        return {"type": "integer"}
    elif type_node_name == "float":
        return {"type": "number"}
    elif type_node_name == "str":
        return {"type": "string"}
    elif type_node_name == "bool":
        return {"type": "boolean"}
    elif type_node_name == "Any" or type_node_name == "typing.Any":
        return {"type": "array"}
    else:
        raise ValueError(f"Unsupported type: {type_node_name}")


def _parse_docstring(docstring: str) -> typing.Tuple[str, str, dict[str, str]]:
    """
    Parse a docstring in the ReST format and return the function description, return description and a dictionary of parameter descriptions.

    Supported docstring directives are :param, :return.
    """
    clean_docstring = inspect.cleandoc(docstring)
    chunks = [
        chunk.strip()
        for chunk in re.split(r"(^|\n)\s*:", clean_docstring, flags=re.MULTILINE)
    ]
    fn_description = chunks[0]
    param_descriptions = {}
    return_description = ""
    for chunk in chunks[1:]:
        if match := re.match(
            r"param ([a-z_]+): ((?:.|\n)+)", chunk, flags=re.MULTILINE
        ):
            param_name, param_description = match.groups()
            param_descriptions[param_name] = param_description
        elif match := re.match(r"return: ((?:.|\n)+)", chunk, flags=re.MULTILINE):
            return_description = match.group(1)
    return fn_description, return_description, param_descriptions
