# Copyright (c) 2016-2017 H. Turgut Uyar <uyar@tekir.org>
#
# pygenstub is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# pygenstub is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with pygenstub.  If not, see <http://www.gnu.org/licenses/>.

from __future__ import print_function, unicode_literals

from argparse import ArgumentParser
from bisect import bisect
from codecs import open
from collections import OrderedDict
from docutils.core import publish_doctree
from io import StringIO

import ast
import logging
import re
import sys

try:
    from textwrap import indent
except ImportError:     # PY2
    def indent(body, start):
        return body if start == '' else \
            '\n'.join([start + line for line in body.splitlines()]) + '\n'


BUILTIN_TYPES = {
    'int', 'float', 'bool', 'str', 'bytes', 'unicode',
    'tuple', 'list', 'set', 'dict', 'None'
}

SIGNATURE_FIELD = 'sig'
SIGNATURE_COMMENT = ' # sig: '

LINE_LENGTH_LIMIT = 79
INDENT_SIZE = 4
INDENT = ' ' * INDENT_SIZE
MULTILINE_STUB_INDENT_LEVEL = 2
MULTILINE_STUB_INDENT = INDENT * MULTILINE_STUB_INDENT_LEVEL

EDIT_WARNING = 'THIS FILE IS AUTOMATICALLY GENERATED, DO NOT EDIT MANUALLY.'

RE_NAMES = re.compile(r'\w+(?:\.\w+)*')


_logger = logging.getLogger(__name__)


def get_fields(node, fields_tag='field_list'):
    """Get field names and values of a node.

    :sig: (docutils.nodes.document, str) -> Mapping[str, str]
    :param node: Node to get the fields from.
    :param fields_tag: Tag of child node that contains the fields.
    :return: Field names and their values.
    """
    fields_nodes = [c for c in node.children if c.tagname == fields_tag]
    if len(fields_nodes) == 0:
        return {}
    assert len(fields_nodes) == 1, 'multiple nodes with tag ' + fields_tag
    fields_node = fields_nodes[0]
    fields = [{f.tagname: f.rawsource.strip() for f in n.children}
              for n in fields_node.children if n.tagname == 'field']
    return {f['field_name']: f['field_body'] for f in fields}


def get_signature(node):
    """Get the signature field from the docstring of a node.

    :sig: (Union[ast.FunctionDef, ast.ClassDef]) -> Optional[str]
    :param node: Node to get the signature for.
    :return: Value of signature field in node docstring.
    """
    docstring = ast.get_docstring(node)
    if docstring is None:
        return None
    doc = publish_doctree(docstring, settings_overrides={'report_level': 5})
    fields = get_fields(doc)
    return fields.get(SIGNATURE_FIELD)


def split_parameter_types(parameter_types):
    """Split a full parameter types declaration into individual types.

    :sig: (str) -> List[str]
    :param parameter_types: Parameter types declaration in the signature.
    :return: Types of parameters.
    """
    if parameter_types == '':
        return []

    # only consider the top level commas, ignore the ones in []
    commas = []
    bracket_depth = 0
    for i, char in enumerate(parameter_types):
        if (char == ',') and (bracket_depth == 0):
            commas.append(i)
        elif char == '[':
            bracket_depth += 1
        elif char == ']':
            bracket_depth -= 1

    types = []
    last_i = 0
    for i in commas:
        types.append(parameter_types[last_i:i].strip())
        last_i = i + 1
    else:
        types.append(parameter_types[last_i:].strip())
    return types


def parse_signature(signature):
    """Parse a signature to get its input and output parameter types.

    :sig: (str) -> Tuple[List[str], str]
    :param signature: Signature to parse.
    :return: Input parameter types and return type.
    """
    lhs, return_type = [s.strip() for s in signature.split(' -> ')]
    parameters_def = lhs[1:-1].strip()  # remove the () around parameter list
    parameter_types = split_parameter_types(parameters_def)
    _logger.debug('parameter types: %s', parameter_types)
    _logger.debug('return type: %s', return_type)
    return parameter_types, return_type


def get_parameter_declaration(name, type_, has_default=False):
    """Get the parameter declaration part of a stub.

    :sig: (str, str, Optional[bool]) -> str
    :param name: Name of parameter.
    :param type_: Type of parameter.
    :param has_default: Whether parameter has a default value or not.
    :return: Parameter declaration to be used in function stub.
    """
    if type_ == '':
        return name
    out = name + ': ' + type_
    if has_default:
        out += ' = ...'
    return out


class StubNode(object):
    """A node in a stub tree.

    :sig: (Optional['StubNode']) -> None
    :param parent: Parent node of the node.
    """

    def __init__(self, parent=None):
        self.parent = parent        # sig: Optional[StubNode]
        self.children = []          # sig: List[StubNode]
        if parent is not None:
            parent.add_child(self)

    def add_child(self, node):
        """Add a child node to this node.

        :sig: ('StubNode') -> None
        :param node: Child to add.
        """
        self.children.append(node)

    def get_code(self):
        """Get the prototype code for this node.

        :sig: () -> str
        """
        out = StringIO()
        for child in self.children:
            out.write(child.get_code())
        return out.getvalue()


class ClassStubNode(StubNode):
    """A node representing a class in a stub tree."""

    def __init__(self, parent, name, signature):
        super(ClassStubNode, self).__init__(parent)
        self.name = name
        self.signature = signature

    def get_code(self):
        body = super(ClassStubNode, self).get_code()
        return 'class %(name)s:\n%(body)s' % {
            'name': self.name,
            'body': indent(body, INDENT)
        }


class FunctionStubNode(StubNode):
    """A node representing a function in a stub tree."""

    def __init__(self, parent, name, signature, ast_node):
        super(FunctionStubNode, self).__init__(parent)
        self.name = name
        self.signature = signature
        self.ast_node = ast_node

    def get_code(self):
        parameter_types, return_type = parse_signature(self.signature)
        parameters = [arg.arg if hasattr(arg, 'arg') else arg.id
                      for arg in self.ast_node.args.args]
        if (len(parameters) > 0) and (parameters[0] == 'self'):
            parameter_types.insert(0, '')
        assert len(parameter_types) == len(parameters)

        parameter_locations = [(a.lineno, a.col_offset)
                               for a in self.ast_node.args.args]
        parameter_defaults = {bisect(parameter_locations, (d.lineno, d.col_offset)) - 1
                                   for d in self.ast_node.args.defaults}

        parameter_stubs = [
            get_parameter_declaration(n, t, i in parameter_defaults)
            for i, (n, t) in enumerate(zip(parameters, parameter_types))]
        prototype = 'def %(name)s(%(params)s) -> %(rtype)s: ...\n' % {
            'name': self.ast_node.name,
            'params': ', '.join(parameter_stubs),
            'rtype': return_type
        }
        if len(prototype) > LINE_LENGTH_LIMIT:
            prototype = 'def %(name)s(\n%(indent)s%(params)s\n) -> %(rtype)s: ...\n' % {
                'name': self.ast_node.name,
                'indent': MULTILINE_STUB_INDENT,
                'params': (',\n' + MULTILINE_STUB_INDENT).join(
                    parameter_stubs),
                'rtype': return_type
            }
        return prototype


class VariableStubNode(StubNode):
    def __init__(self, parent, name, type_):
        super(VariableStubNode, self).__init__(parent)
        self.name = name
        self.type_ = type_

    def get_code(self):
        return self.name + ' = ...' + ' # type: ' + self.type_ + '\n'


class SignatureCollector(ast.NodeVisitor):
    """A collector that scans a source code and gathers signature data.

    :sig: (str) -> None
    :param code: Source code to traverse.
    """

    def __init__(self, code):
        self.code_lines = code.splitlines()     # sig: Sequence[str]

        self.tree = ast.parse(code)             # sig: ast.AST
        self.stub_tree = StubNode()             # sig: StubNode

        self.imported_names = OrderedDict()     # sig: OrderedDict
        self.defined_types = set()              # sig: Set[str]
        self.required_types = set()             # sig: Set[str]

        self.units = [self.stub_tree]           # sig: List[StubNode]

    def traverse(self):
        """Recursively visit all nodes of the tree and gather signature data.

        :sig: () -> None
        """
        self.visit(self.tree)

    def visit_ImportFrom(self, node):
        for name in node.names:
            self.imported_names[name.name] = node.module

    def visit_ClassDef(self, node):
        self.defined_types.add(node.name)
        signature = get_signature(node)
        if signature is not None:
            requires = {n for n in RE_NAMES.findall(signature) if n not in BUILTIN_TYPES}
            self.required_types |= requires

        parent = self.units[-1]
        stub_node = ClassStubNode(parent, node.name, signature=signature)

        self.units.append(stub_node)
        self.generic_visit(node)
        del self.units[-1]

    def visit_FunctionDef(self, node):
        signature = get_signature(node)

        if signature is None:
            parent = self.units[-1]
            if isinstance(parent, ClassStubNode) and (node.name == '__init__'):
                signature = parent.signature

        if signature is not None:
            requires = {n for n in RE_NAMES.findall(signature) if n not in BUILTIN_TYPES}
            self.required_types |= requires

            parent = self.units[-1]
            stub_node = FunctionStubNode(parent, node.name, signature, node)

            self.units.append(stub_node)
            self.generic_visit(node)
            del self.units[-1]

    def visit_Assign(self, node):
        parent = self.units[-1]
        code_line = self.code_lines[node.lineno - 1]
        if SIGNATURE_COMMENT in code_line:
            _, type_ = code_line.split(SIGNATURE_COMMENT)
            for var in node.targets:
                if isinstance(var, ast.Name):
                    stub_node = VariableStubNode(parent, var.id, type_.strip())
                if isinstance(var, ast.Attribute) and (var.value.id == 'self'):
                    stub_node = VariableStubNode(parent, var.attr, type_.strip())

    def get_stub(self):
        needed_types = self.required_types

        needed_types -= self.defined_types
        _logger.debug('defined types: %s', self.defined_types)

        imported_types = {n for n in self.imported_names if n in needed_types}
        needed_types -= imported_types
        _logger.debug('imported names: %s', self.imported_names)
        _logger.debug('used imported types: %s', imported_types)

        dotted_types = {n for n in needed_types if '.' in n}
        needed_types -= dotted_types
        _logger.debug('dotted types: %s', dotted_types)

        try:
            typing_module = __import__('typing')
            typing_types = {n for n in needed_types if hasattr(typing_module, n)}
            _logger.debug('types from typing module: %s', typing_types)
        except ImportError:
            _logger.debug('typing module not installed')
            typing_types = set()
        needed_types -= typing_types

        if len(needed_types) > 0:
            print('Unknown types: ' + ', '.join(needed_types), file=sys.stderr)
            sys.exit(1)

        out = StringIO()
        started = False

        if len(typing_types) > 0:
            out.write(
                'from typing import ' + ', '.join(sorted(typing_types)) + '\n')
            started = True

        if len(imported_types) > 0:
            if started:
                out.write('\n')
            # preserve the import order in the source file
            for name in self.imported_names:
                if name in imported_types:
                    out.write(
                        'from %(module)s import %(name)s\n' % {
                            'module': self.imported_names[name],
                            'name': name
                        }
                    )
            started = True

        if len(dotted_types) > 0:
            if started:
                out.write('\n')
            imported_modules = {'.'.join(n.split('.')[:-1]) for n in
                                dotted_types}
            for module in sorted(imported_modules):
                out.write('import ' + module + '\n')
            started = True

        if started:
            out.write('\n\n')
        out.write(self.stub_tree.get_code())
        return out.getvalue()


def get_stub(code):
    """Get the stub declarations for a source code.

    :sig: (str) -> str
    :param code: Source code to generate the stub for.
    :return: Stub code for the source.
    """
    collector = SignatureCollector(code)
    collector.traverse()
    return collector.get_stub()


def main():
    """Entry point of the command-line utility.

    :sig: () -> None
    """
    parser = ArgumentParser()
    parser.add_argument('source', help='source file')
    parser.add_argument('--debug', action='store_true', help='enable debug messages')
    arguments = parser.parse_args()

    log_level = logging.DEBUG if arguments.debug else logging.INFO
    logging.basicConfig(level=log_level)

    with open(arguments.source, mode='r', encoding='utf-8') as f_in:
        code = f_in.read()

    stub = get_stub(code)

    destination = arguments.source + 'i'
    if stub != '':
        with open(destination, mode='w', encoding='utf-8') as f_out:
            f_out.write('# ' + EDIT_WARNING + '\n\n')
            f_out.write(stub)


if __name__ == '__main__':
    main()
