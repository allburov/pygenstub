# THIS FILE IS AUTOMATICALLY GENERATED, DO NOT EDIT MANUALLY.

from typing import List, Mapping, Optional, Sequence, Set, Tuple, Union

import ast
import docutils.nodes


class Namespace:
    scope = ...       # type: str
    name = ...        # type: str
    level = ...       # type: int
    docstring = ...   # type: Optional[str]
    components = ...  # type: List
    variables = ...   # type: List[Tuple[str, str]]

    def __init__(self, scope: str, name: str, level: int) -> None: ...

    def get_stub(self) -> str: ...


def get_fields(
        node: docutils.nodes.document,
        fields_tag: str = ...
) -> Mapping[str, str]: ...


def get_signature(
        node: Union[ast.FunctionDef, ast.ClassDef]
) -> Optional[str]: ...


def split_parameter_types(parameter_types: str) -> List[str]: ...


def get_parameter_declaration(
        name: str,
        type_: str,
        has_default: Optional[bool] = ...
) -> str: ...


def get_prototype(node: ast.FunctionDef) -> Tuple[str, Set[str]]: ...


def _traverse_namespace(
        namespace: Namespace,
        nodes: List[ast.AST],
        required_types: Set[str],
        defined_types: Set[str],
        code_lines: Sequence[str]
) -> None: ...


def get_stub(code: str) -> str: ...


def main() -> None: ...
