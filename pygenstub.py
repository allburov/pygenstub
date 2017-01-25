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
from textwrap import indent

import ast
import logging
import re
import sys


BUILTIN_TYPES = {
    'int', 'float', 'bool', 'str', 'bytes', 'unicode',
    'tuple', 'list', 'set', 'dict', 'None'
}

SIGNATURE_FIELD = 'sig'

LINE_LENGTH_LIMIT = 79
INDENT_SIZE = 4
INDENT = ' ' * INDENT_SIZE
MULTILINE_STUB_INDENT_LEVEL = 2
MULTILINE_STUB_INDENT = INDENT * MULTILINE_STUB_INDENT_LEVEL

EDIT_WARNING = 'THIS FILE IS AUTOMATICALLY GENERATED, DO NOT EDIT MANUALLY.'


_logger = logging.getLogger(__name__)


class Namespace(object):
    """A unit that can contain names, e.g. a module, a class, ...

    :sig: (str, str, int) -> None
    :param scope: Scope of namespace.
    :param name: Name of namespace.
    :param level: Level of namespace, used for indentation.
    """

    def __init__(self, scope, name, level):
        self.scope = scope
        self.name = name
        self.level = level
        self.docstring = None
        self.components = []

    def get_stub(self):
        """Get the stub code for this namespace.

        :sig: () -> str
        :return: Stub code for this namespace.
        """
        blank_lines = '\n\n' if self.scope == 'module' else '\n'
        body = blank_lines.join([c.get_stub() if isinstance(c, Namespace) else c
                                 for c in self.components])
        if self.scope == 'class':
            body = 'class %(name)s:\n%(body)s' % {
                'name': self.name,
                'body': indent(body, INDENT)
            }
            return indent(body, INDENT * (self.level - 1))
        else:
            return indent(body, INDENT * self.level)


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
    assert len(fields_nodes) == 1
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
    docstring = node.docstring if hasattr(node, 'docstring') else ast.get_docstring(node)
    if docstring is None:
        return None
    doctree = publish_doctree(docstring, settings_overrides={'report_level': 5})
    fields = get_fields(doctree)
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


def get_prototype(node):
    """Get the prototype for a function or a method.

    :sig: (ast.FunctionDef) -> Tuple[str, Set[str]]
    :param node: Function or method node to get the prototype for.
    :return: Prototype and required type names.
    """
    signature = get_signature(node)
    if signature is None:
        return '', set()

    _logger.debug('parsing signature for %s', node.name)
    lhs, return_type = [s.strip() for s in signature.split(' -> ')]
    parameter_defs = lhs[1:-1].strip()  # remove the () around parameter list

    parameter_types = split_parameter_types(parameter_defs)
    _logger.debug('parameter types: %s', parameter_types)
    _logger.debug('return type: %s', return_type)

    parameters = [arg.arg if hasattr(arg, 'arg') else arg.id
                  for arg in node.args.args]
    if (len(parameters) > 0) and (parameters[0] == 'self'):
        # TODO: better way to handle this rather than checking the name 'self'?
        parameter_types.insert(0, '')
    assert len(parameter_types) == len(parameters)

    parameter_locations = [(a.lineno, a.col_offset) for a in node.args.args]
    parameter_defaults = {bisect(parameter_locations, (d.lineno, d.col_offset)) - 1
                          for d in node.args.defaults}

    parameter_stubs = [get_parameter_declaration(n, t, i in parameter_defaults)
                       for i, (n, t) in enumerate(zip(parameters, parameter_types))]
    prototype = 'def %(name)s(%(params)s) -> %(rtype)s: ...\n' % {
        'name': node.name,
        'params': ', '.join(parameter_stubs),
        'rtype': return_type
    }
    if len(prototype) > LINE_LENGTH_LIMIT:
        prototype = 'def %(name)s(\n%(indent)s%(params)s\n) -> %(rtype)s: ...\n' % {
            'name': node.name,
            'indent': MULTILINE_STUB_INDENT,
            'params': (',\n' + MULTILINE_STUB_INDENT).join(parameter_stubs),
            'rtype': return_type
        }

    required_types = {n for n in re.findall(r'\w+(?:\.\w+)*', signature)
                      if n not in BUILTIN_TYPES}

    _logger.debug('requires %s', required_types)
    _logger.debug('prototype: %s', prototype)
    return prototype, required_types


def _traverse_namespace(namespace, root, required_types, defined_types):
    """Recursively traverse and collect the prototypes under a node.

    The prototypes are accumulated in the ``components`` attribute
    of the namespace. Any types required by the annotations will be accumulated
    in the ``required_types`` parameter and all types/classes defined
    in the module will be accumulated in the ``defined_types`` parameter.

    :sig: (Namespace, Any, Set[str], Set[str]) -> None
    :param namespace: Namespace collecting the prototypes.
    :param root: Root node to collect the prototypes from.
    :param required_types: All types required by type annotations.
    :param defined_types: All types defined in the module.
    """
    for node in root:
        if isinstance(node, ast.FunctionDef):
            prototype, requires = get_prototype(node)
            if (prototype == '') and (node.name == '__init__'):
                node.docstring = namespace.docstring
                prototype, requires = get_prototype(node)
            if prototype != '':
                namespace.components.append(prototype)
                required_types |= requires
        if isinstance(node, ast.ClassDef):
            subnamespace = Namespace('class', node.name, namespace.level + 1)
            defined_types.add(node.name)
            subnamespace.docstring = ast.get_docstring(node)
            _traverse_namespace(subnamespace, node.body, required_types, defined_types)
            if len(subnamespace.components) > 0:
               namespace.components.append(subnamespace)


def get_stub(code):
    """Get the stub declarations for a source code.

    :sig: (str) -> str
    :param code: Source code to generate the stub for.
    :return: Stub declarations for the source code.
    """
    tree = ast.parse(code)

    namespace = Namespace('module', '', level=0)
    needed_types = set()
    defined_types = set()
    _traverse_namespace(namespace, tree.body, needed_types, defined_types)

    if len(namespace.components) == 0:
        return ''

    needed_types -= defined_types
    _logger.debug('defined types: %s', defined_types)

    imported_names = OrderedDict(
        [(name.name, node.module)
         for node in tree.body if isinstance(node, ast.ImportFrom)
         for name in node.names]
    )
    _logger.debug('imported names: %s', imported_names)

    imported_types = {n for n in imported_names if n in needed_types}
    needed_types -= imported_types
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
        print('Following types could not be found: ' + ', '.join(needed_types),
              file=sys.stderr)
        sys.exit(1)

    out = StringIO()
    started = False

    if len(typing_types) > 0:
        out.write('from typing import ' + ', '.join(sorted(typing_types)) + '\n')
        started = True

    if len(imported_types) > 0:
        if started:
            out.write('\n')
        # preserve the import order in the source file
        for name in imported_names:
            if name in imported_types:
                out.write(
                    'from %(module)s import %(name)s\n' % {
                        'module': imported_names[name],
                        'name': name
                    }
                )
        started = True

    if len(dotted_types) > 0:
        if started:
            out.write('\n')
        imported_modules = {'.'.join(n.split('.')[:-1]) for n in dotted_types}
        for module in sorted(imported_modules):
            out.write('import ' + module + '\n')
        started = True

    if started:
        out.write('\n\n')
    out.write(namespace.get_stub())

    return out.getvalue()


def main():
    """Entry point of the command-line utility.

    :sig: () -> None
    """
    parser = ArgumentParser()
    parser.add_argument('source', help='source file to generate the stub for')
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
