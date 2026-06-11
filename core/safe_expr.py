"""
Evaluador seguro de expresiones para la primitiva `raw_expr`.

Reemplaza a `eval()` con un walker AST que sólo acepta:
- literales numéricos
- nombres en una whitelist (variables de grilla + constantes)
- operadores aritméticos / comparaciones / booleanos / unarios
- llamadas a funciones en una whitelist (sin atributos, sin subscript, sin lambdas)

Bloquea: acceso a atributos, subscripts, comprehensions, lambdas, asignaciones,
nombres dunder, expresiones excesivamente largas o profundas.
"""

from __future__ import annotations

import ast
from typing import Any, Mapping

MAX_EXPR_LEN = 500
MAX_AST_DEPTH = 25

_ALLOWED_BINOPS = (
    ast.Add, ast.Sub, ast.Mult, ast.Div, ast.FloorDiv,
    ast.Mod, ast.Pow,
)
_ALLOWED_UNARYOPS = (ast.UAdd, ast.USub, ast.Not)
_ALLOWED_BOOLOPS = (ast.And, ast.Or)
_ALLOWED_CMPOPS = (
    ast.Eq, ast.NotEq, ast.Lt, ast.LtE, ast.Gt, ast.GtE,
)


class UnsafeExpressionError(ValueError):
    pass


def _depth(node: ast.AST, d: int = 0) -> int:
    if d > MAX_AST_DEPTH:
        raise UnsafeExpressionError(f"expresión demasiado profunda (>{MAX_AST_DEPTH})")
    return max((_depth(c, d + 1) for c in ast.iter_child_nodes(node)), default=d)


def _validate(node: ast.AST, allowed_names: set[str], allowed_funcs: set[str]) -> None:
    if isinstance(node, ast.Expression):
        _validate(node.body, allowed_names, allowed_funcs)
        return
    if isinstance(node, ast.Constant):
        if not isinstance(node.value, (int, float, bool)):
            raise UnsafeExpressionError(f"constante no permitida: {type(node.value).__name__}")
        return
    if isinstance(node, ast.Name):
        if node.id.startswith("_"):
            raise UnsafeExpressionError(f"nombre con guion bajo prohibido: {node.id}")
        if node.id not in allowed_names and node.id not in allowed_funcs:
            raise UnsafeExpressionError(f"nombre no permitido: {node.id}")
        return
    if isinstance(node, ast.BinOp):
        if not isinstance(node.op, _ALLOWED_BINOPS):
            raise UnsafeExpressionError(f"operador binario no permitido: {type(node.op).__name__}")
        _validate(node.left, allowed_names, allowed_funcs)
        _validate(node.right, allowed_names, allowed_funcs)
        return
    if isinstance(node, ast.UnaryOp):
        if not isinstance(node.op, _ALLOWED_UNARYOPS):
            raise UnsafeExpressionError(f"operador unario no permitido: {type(node.op).__name__}")
        _validate(node.operand, allowed_names, allowed_funcs)
        return
    if isinstance(node, ast.BoolOp):
        if not isinstance(node.op, _ALLOWED_BOOLOPS):
            raise UnsafeExpressionError(f"operador bool no permitido: {type(node.op).__name__}")
        for v in node.values:
            _validate(v, allowed_names, allowed_funcs)
        return
    if isinstance(node, ast.Compare):
        if not all(isinstance(op, _ALLOWED_CMPOPS) for op in node.ops):
            raise UnsafeExpressionError("comparador no permitido")
        _validate(node.left, allowed_names, allowed_funcs)
        for c in node.comparators:
            _validate(c, allowed_names, allowed_funcs)
        return
    if isinstance(node, ast.Call):
        if not isinstance(node.func, ast.Name):
            raise UnsafeExpressionError("solo se permiten llamadas a funciones de la whitelist")
        if node.func.id not in allowed_funcs:
            raise UnsafeExpressionError(f"función no permitida: {node.func.id}")
        if node.keywords:
            raise UnsafeExpressionError("argumentos por palabra clave no permitidos")
        for a in node.args:
            _validate(a, allowed_names, allowed_funcs)
        return
    if isinstance(node, ast.IfExp):
        _validate(node.test, allowed_names, allowed_funcs)
        _validate(node.body, allowed_names, allowed_funcs)
        _validate(node.orelse, allowed_names, allowed_funcs)
        return
    raise UnsafeExpressionError(f"nodo AST no permitido: {type(node).__name__}")


def safe_eval(
    expr: str,
    variables: Mapping[str, Any],
    functions: Mapping[str, Any],
) -> Any:
    """Evalúa una expresión validada contra la whitelist de nombres y funciones."""
    if not isinstance(expr, str):
        raise UnsafeExpressionError("expr debe ser str")
    if len(expr) > MAX_EXPR_LEN:
        raise UnsafeExpressionError(f"expresión demasiado larga (>{MAX_EXPR_LEN} chars)")
    try:
        tree = ast.parse(expr, mode="eval")
    except SyntaxError as e:
        raise UnsafeExpressionError(f"sintaxis inválida: {e}") from e
    _depth(tree)
    allowed_names = set(variables.keys())
    allowed_funcs = set(functions.keys())
    _validate(tree, allowed_names, allowed_funcs)
    ns = {**variables, **functions}
    return eval(compile(tree, "<safe_expr>", "eval"), {"__builtins__": {}}, ns)
