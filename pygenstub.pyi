# THIS FILE IS AUTOMATICALLY GENERATED, DO NOT EDIT MANUALLY.

from typing import List, Mapping, Optional, Sequence, Set, Tuple, Union

from collections import OrderedDict

import ast
import docutils.nodes


SIGNATURE_FIELD = ...    # type: str
SIGNATURE_COMMENT = ...  # type: str

def get_fields(
        node: docutils.nodes.document,
        fields_tag: Optional[str] = ...
) -> Mapping[str, str]: ...

def get_signature(
        node: Union[ast.FunctionDef, ast.ClassDef]
) -> Optional[str]: ...

def split_parameter_types(parameters_def: str) -> List[str]: ...

def parse_signature(signature: str) -> Tuple[List[str], str, Set[str]]: ...

class StubNode:
    variables = ...  # type: List[VariableNode]
    children = ...   # type: List[Union[FunctionNode, ClassNode]]
    parent = ...     # type: Optional[StubNode]

    def __init__(self) -> None: ...

    def add_variable(self, node: VariableNode) -> None: ...

    def add_child(self, node: Union[FunctionNode, ClassNode]) -> None: ...

    def get_code(self, **kwargs) -> str: ...

class VariableNode(StubNode):
    name = ...   # type: str
    type_ = ...  # type: str

    def __init__(self, name: str, type_: str) -> None: ...

    def get_code(self, align: Optional[int] = ...) -> str: ...

class FunctionNode(StubNode):
    name = ...  # type: str

    def __init__(
            self,
            name: str,
            parameters: Sequence[str],
            parameter_types: Sequence[str],
            parameter_defaults: Set[int],
            return_type: str
    ) -> None: ...

class ClassNode(StubNode):
    name = ...       # type: str
    bases = ...      # type: Sequence[str]
    signature = ...  # type: Optional[str]

    def __init__(
            self,
            name: str,
            bases: Sequence[str],
            signature: Optional[str] = ...
    ) -> None: ...

    def get_code(self) -> str: ...

class SignatureCollector(ast.NodeVisitor):
    tree = ...            # type: ast.AST
    stub_tree = ...       # type: StubNode
    imported_names = ...  # type: OrderedDict
    defined_types = ...   # type: Set[str]
    required_types = ...  # type: Set[str]
    parents = ...         # type: List[StubNode]
    code = ...            # type: Sequence[str]

    def __init__(self, code: str) -> None: ...

    def traverse(self) -> None: ...

    def get_stub(self) -> str: ...

def get_stub(code: str) -> str: ...

def main() -> None: ...
