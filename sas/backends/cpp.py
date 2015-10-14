from clang.cindex import TranslationUnit
from clang.cindex import CursorKind
from .utils import get_cursors, get_root_cursors
from ..wrappers import *
from ..config import Config
from re import match
from rply import Token


def find_candidates(config, ast):
    """ Find patterns in 'filename' matching 'ast'
    """

    tu = TranslationUnit.from_source(config.filename, ["-std=c++11"])
    for cursor in resolve_ast(tu, ast, config):
        start, end = cursor.extent.start, cursor.extent.end
        yield ((start.line, start.column),
               (end.line, end.column))


def has_required_children(tu, cursor, children, config):
    if not children:
        return True
    for child in children:
        try:
            next(resolve_ast(tu, child, config, cursor))
        except StopIteration:
            break
    else:
        return True
    return False


def resolve_ast(tu, ast, config, root=None):
    """ Yields cursors matching the pattern in 'ast'
    """
    def inner_resolve():
        if isinstance(ast, Function):
            for cursor in resolve_function(tu, ast, config, root):
                yield cursor
        elif isinstance(ast, Variable):
            for cursor in resolve_variable(tu, ast, config, root):
                yield cursor
        elif isinstance(ast, Class):
            for cursor in resolve_class(tu, ast, config, root):
                yield cursor
        elif isinstance(ast, Search):
            for cursor in resolve_basic_search(tu, ast, config, root):
                yield cursor
    for result in inner_resolve():
        if has_required_children(tu, result, ast.contents, config):
            yield result


def matches_by_kinds(cursor, variable, kinds):
    return cursor.kind in kinds and \
        match(variable.type, cursor.type.spelling) and \
        match(variable.name, cursor.spelling)


def matches_function_parameters(cursor, function):
    cursor_parameters = list(cursor.get_arguments())
    ellipses_active = False
    for parameter in function.parameters:
        if isinstance(parameter, Token):
            ellipses_active = True
            continue
        if len(cursor_parameters) == 0:
            return False

        if not matches_by_kinds(cursor_parameters[0],
                                parameter,
                                (CursorKind.PARM_DECL,)):
            if not ellipses_active:
                return False
            else:
                cursor_parameters = cursor_parameters[1:]
        else:
            cursor_parameters = cursor_parameters[1:]
            ellipses_active = False
    if len(cursor_parameters) and not ellipses_active:
        return False
    return True


def resolve_qualifiers(tu, qualifiers, config, root):
    if qualifiers is None:
        for cursor in get_root_cursors(tu, filename=config.filename, root=root):
            yield cursor
    elif len(qualifiers) == 0:
        for cursor in get_cursors(tu, filename=config.filename, root=root):
            yield cursor
    else:
        def valid_qualifier_cursor(cursor):
            return cursor.kind in (CursorKind.CLASS_DECL,
                                   CursorKind.STRUCT_DECL,
                                   CursorKind.NAMESPACE)

        def recurse_qualifiers(cursor, qualifiers):
            if len(qualifiers) == 0:
                for child in cursor.get_children():
                    yield child
            else:
                for child in cursor.get_children():
                    if not match(qualifiers[0], child.spelling) or \
                       not valid_qualifier_cursor(child):
                        continue
                    for inner in recurse_qualifiers(child, qualifiers[1:]):
                        yield inner
        for cursor in get_root_cursors(tu, qualifiers[0], config.filename, root):
            if not valid_qualifier_cursor(cursor):
                continue
            for inner in recurse_qualifiers(cursor, qualifiers[1:]):
                yield inner


def resolve_function(tu, function, config, root):
    allowed_kinds = []
    if config.mode & Config.MATCH_MODE.DECLARATION:
        allowed_kinds += [CursorKind.FUNCTION_DECL,
                          CursorKind.CXX_METHOD,
                          CursorKind.FUNCTION_TEMPLATE,
                          CursorKind.CONSTRUCTOR,
                          CursorKind.DESTRUCTOR]
    if config.mode & Config.MATCH_MODE.EXPRESSION:
        allowed_kinds += [CursorKind.CALL_EXPR]

    for cursor in resolve_qualifiers(tu, function.qualifiers, config, root):
        if cursor.kind in allowed_kinds and \
           match(function.name, cursor.spelling) and \
           match(function.return_type, cursor.result_type.spelling) and \
           matches_function_parameters(cursor, function):
            yield cursor


def resolve_variable(tu, variable, config, root):
    allowed_kinds = []
    if config.mode & Config.MATCH_MODE.DECLARATION:
        allowed_kinds += [CursorKind.VAR_DECL]
    if config.mode & Config.MATCH_MODE.EXPRESSION:
        allowed_kinds += [CursorKind.DECL_REF_EXPR,
                          CursorKind.MEMBER_REF_EXPR]
    for cursor in resolve_qualifiers(tu, variable.qualifiers, config, root):
        if match(variable.name, cursor.spelling) and \
           matches_by_kinds(cursor, variable, allowed_kinds):
            yield cursor


def resolve_class(tu, class_t, config, root):
    allowed_kinds = []
    if config.mode & Config.MATCH_MODE.DECLARATION:
        allowed_kinds += [CursorKind.CLASS_DECL,
                          CursorKind.STRUCT_DECL,
                          CursorKind.CLASS_TEMPLATE,
                          CursorKind.CLASS_TEMPLATE_PARTIAL_SPECIALIZATION]
    if config.mode & Config.MATCH_MODE.EXPRESSION:
        allowed_kinds += []
    for cursor in resolve_qualifiers(tu, class_t.qualifiers, config, root):
        if match(class_t.name, cursor.spelling) and \
           cursor.kind in allowed_kinds:
            yield cursor


def resolve_basic_search(tu, search, config, root):
    for cursor in resolve_qualifiers(tu, search.qualifiers, config, root):
        if match(search.search, cursor.spelling):
            yield cursor
