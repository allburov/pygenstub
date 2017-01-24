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


BUILTIN_TYPES = {
    'int', 'float', 'bool', 'str', 'bytes', 'unicode',
    'tuple', 'list', 'set', 'dict', 'None'
}

SIGNATURE_FIELD = 'sig'
LINE_LENGTH_LIMIT = 79
INDENT_SIZE = 8
MULTILINE_INDENT = ' ' * INDENT_SIZE

EDIT_WARNING = 'THIS FILE IS AUTOMATICALLY GENERATED, DO NOT EDIT MANUALLY.'


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
    assert len(fields_nodes) == 1
    fields_node = fields_nodes[0]
    fields = [{f.tagname: f.rawsource.strip() for f in n.children}
              for n in fields_node.children if n.tagname == 'field']
    return {f['field_name']: f['field_body'] for f in fields}


def get_parameter_types(parameter_defs):
    """Get the types of all parameters.

    :sig: (str) -> List[str]
    :param parameter_defs: Parameter definitions in signature.
    :return: Types of parameters.
    """
    if parameter_defs == '':
        return []

    # only consider the top level commas, ignore the ones in []
    commas = []
    bracket_depth = 0
    for i, c in enumerate(parameter_defs):
        if (c == ',') and (bracket_depth == 0):
            commas.append(i)
        elif c == '[':
            bracket_depth += 1
        elif c == ']':
            bracket_depth -= 1

    types = []
    last_i = 0
    for i in commas:
        types.append(parameter_defs[last_i:i].strip())
        last_i = i + 1
    else:
        types.append(parameter_defs[last_i:].strip())
    return types


def get_parameter_stub(name, type_, default=None):
    """Get the parameter definition part of a stub.

    :sig: (str, str, Optional[Union[ast.NameConstant, ast.Str, ast.Tuple]]) -> str
    :param name: Name of parameter.
    :param type_: Type of parameter.
    :param default: Default value of the parameter.
    :return: Parameter definition to be used in function stub.
    """
    out = name + ': ' + type_
    if default is not None:
        raw_value = getattr(default, default._fields[0])
        if isinstance(default, ast.Str):
            value = "'" + raw_value + "'"
        elif isinstance(default, ast.Tuple):
            value = tuple(raw_value)
        else:
            value = raw_value
        out += ' = ' + str(value)
    return out


def get_prototype(node):
    """Get the prototype for a function.

    :sig: (ast.FunctionDef) -> Optional[Tuple[str, Set[str]]]
    :param node: Function node to get the prototype for.
    :return: Prototype and required type names.
    """
    docstring = ast.get_docstring(node)
    if docstring is None:
        return None

    doctree = publish_doctree(docstring, settings_overrides={'report_level': 5})
    fields = get_fields(doctree)
    signature = fields.get(SIGNATURE_FIELD)
    if signature is None:
        return None

    _logger.debug('parsing signature for %s', node.name)
    lhs, return_type = [s.strip() for s in signature.split(' -> ')]
    parameter_defs = lhs[1:-1].strip()  # remove the () around parameter list

    parameter_types = get_parameter_types(parameter_defs)
    _logger.debug('parameter types: %s', parameter_types)
    _logger.debug('return type: %s', return_type)

    parameters = [arg.arg if hasattr(arg, 'arg') else arg.id
                  for arg in node.args.args]
    assert len(parameter_types) == len(parameters)

    parameter_locations = [(a.lineno, a.col_offset) for a in node.args.args]
    parameter_defaults = {bisect(parameter_locations, (d.lineno, d.col_offset)): d
                          for d in node.args.defaults}

    parameter_stubs = [get_parameter_stub(n, t, parameter_defaults.get(i + 1))
                       for i, (n, t) in enumerate(zip(parameters, parameter_types))]
    prototype = 'def %(name)s(%(params)s) -> %(rtype)s: ...\n' % {
        'name': node.name,
        'params': ', '.join(parameter_stubs),
        'rtype': return_type
    }
    if len(prototype) > LINE_LENGTH_LIMIT:
        prototype = 'def %(name)s(\n%(indent)s%(params)s\n) -> %(rtype)s: ...\n' % {
            'name': node.name,
            'indent': MULTILINE_INDENT,
            'params': (',\n' + MULTILINE_INDENT).join(parameter_stubs),
            'rtype': return_type
        }

    required_types = {n for n in re.findall(r'\w+(?:\.\w+)*', signature)
                      if n not in BUILTIN_TYPES}

    _logger.debug('requires %s', required_types)
    _logger.debug('prototype: %s', prototype)
    return prototype, required_types


def get_stub(code):
    """Get the stub declarations for a source code.

    :sig: (str) -> str
    :param code: Source code to generate the stub for.
    :return: Stub declarations for the source code.
    """
    tree = ast.parse(code)

    signatures = list(filter(
        lambda x: x is not None,
        [get_prototype(node) for node in tree.body if isinstance(node, ast.FunctionDef)]
    ))

    if len(signatures) == 0:
        return ''

    prototypes, required_types = zip(*signatures)
    needed_types = {t for r in required_types for t in r}

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

    stub = StringIO()
    started = False

    if len(typing_types) > 0:
        stub.write('from typing import ' + ', '.join(sorted(typing_types)) + '\n')
        started = True

    if len(imported_types) > 0:
        if started:
            stub.write('\n')
        # preserve the import order in the source file
        for name in imported_names:
            if name in imported_types:
                stub.write(
                    'from %(module)s import %(name)s\n' % {
                        'module': imported_names[name],
                        'name': name
                    }
                )
        started = True

    if len(dotted_types) > 0:
        if started:
            stub.write('\n')
        imported_modules = {'.'.join(n.split('.')[:-1]) for n in dotted_types}
        for module in sorted(imported_modules):
            stub.write('import ' + module + '\n')
        started = True

    if started:
        stub.write('\n\n')
    stub.write('\n\n'.join(prototypes))

    return stub.getvalue()


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
    if len(stub) > 0:
        with open(destination, mode='w', encoding='utf-8') as f_out:
            f_out.write('# ' + EDIT_WARNING + '\n\n')
            f_out.write(stub)


if __name__ == '__main__':
    main()
