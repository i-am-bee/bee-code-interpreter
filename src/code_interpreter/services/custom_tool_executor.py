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
import typing
import inspect
import re
import json
import textwrap
import pydantic
import pydantic.json_schema
from code_interpreter.services.kubernetes_code_executor import KubernetesCodeExecutor


@dataclass
class CustomTool:
    name: str
    description: str
    input_schema: dict[str, typing.Any]


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

        Function arguments will be converted to JSONSchema by Pydantic, so everything that can be (de)serialized through Pydantic can be used.
        However, the imports that can be used in types are currently limited to `typing`, `pathlib` and `datetime` for safety reasons.
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

        namespace = _build_namespace(imports)

        json_schema = {
            "$schema": "http://json-schema.org/draft-07/schema#",
            "type": "object",
            "title": function_def.name,
            "properties": {
                arg.arg: _type_to_json_schema(arg.annotation, namespace)
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

    @pydantic.validate_call
    async def execute(
        self,
        tool_source_code: str,
        tool_input_json: str,
    ) -> typing.Any:
        """
        Execute the given custom tool with the given input.

        The source code is expected to be valid according to the parse method.
        The input is expected to be valid according to the input schema produced by the parse method.
        """

        clean_tool_source_code = textwrap.dedent(tool_source_code)
        *imports, function_def = ast.parse(clean_tool_source_code).body

        result = await self.code_executor.execute(
            source_code=f"""
# Import all tool dependencies here -- to aid the dependency detection
{"\n".join(ast.unparse(node) for node in imports if isinstance(node, (ast.Import, ast.ImportFrom)))}

import pydantic
import contextlib
import json

with contextlib.redirect_stdout(None):
    inner_globals = {{}}
    exec(compile({repr(clean_tool_source_code)}, "<string>", "exec"), inner_globals)
    result = pydantic.TypeAdapter(inner_globals[{repr(function_def.name)}]).validate_json({repr(tool_input_json)})

print(json.dumps(result))
        """,
        )

        if result.exit_code != 0:
            raise CustomToolExecuteError(result.stderr)

        return json.loads(result.stdout)


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


def _build_namespace(
    imports: list[ast.AST],
    allowed_modules: set[str] = {"typing", "pathlib", "datetime"},
) -> dict[str, typing.Any]:
    namespace = {
        "str": str,
        "int": int,
        "float": float,
        "bool": bool,
        "list": list,
        "dict": dict,
        "set": set,
        "tuple": tuple,
    }

    for node in imports:
        if isinstance(node, ast.Import):
            for name in node.names:
                if name.name in allowed_modules:
                    namespace[name.asname or name.name] = __import__(name.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module in allowed_modules:
                module = __import__(node.module, fromlist=[n.name for n in node.names])
                for name in node.names:
                    namespace[name.asname or name.name] = getattr(module, name.name)

    return namespace


def _type_to_json_schema(type_ast: ast.AST, namespace: dict) -> dict:
    type_str = ast.unparse(type_ast)
    if not _is_safe_type_ast(type_ast):
        raise CustomToolParseError([f"Invalid type annotation `{type_str}`"])
    try:
        return pydantic.TypeAdapter(eval(type_str, namespace)).json_schema(
            schema_generator=_GenerateJsonSchema
        )
    except Exception as e:
        raise CustomToolParseError([f"Error when parsing type `{type_str}`: {e}"])


class _GenerateJsonSchema(pydantic.json_schema.GenerateJsonSchema):
    schema_dialect = "http://json-schema.org/draft-07/schema#"

    def tuple_schema(self, schema):
        # Use draft-07 syntax for tuples
        schema = super().tuple_schema(schema)
        if "prefixItems" in schema:
            schema["items"] = schema.pop("prefixItems")
            schema.pop("maxItems")
            schema["additionalItems"] = False
        return schema


def _is_safe_type_ast(node: ast.AST) -> bool:
    match node:
        case ast.Name():
            return True
        case ast.Attribute():
            return _is_safe_type_ast(node.value)
        case ast.Subscript():
            return _is_safe_type_ast(node.value) and _is_safe_type_ast(node.slice)
        case ast.Tuple() | ast.List():
            return all(_is_safe_type_ast(elt) for elt in node.elts)
        case ast.Constant():
            return isinstance(node.value, (str, int, float, bool, type(None)))
        case ast.BinOp():
            return (
                isinstance(node.op, ast.BitOr)
                and _is_safe_type_ast(node.left)
                and _is_safe_type_ast(node.right)
            )
        case _:
            return False
