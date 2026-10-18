"""Safe evaluation of free-form arithmetic expressions.

Expressions are parsed with the :mod:`ast` module and walked against an
explicit allowlist of node types. Anything else -- names, calls, attributes,
subscripts, comprehensions, literals other than numbers -- is rejected before
it can execute, so a hostile expression cannot reach the interpreter.

Example
-------
>>> evaluate("2 + 3 * 4")
14
"""

from __future__ import annotations

import ast
import operator

#: Longest expression accepted. Bounds nesting depth and input size.
MAX_EXPRESSION_LENGTH = 200

#: Largest exponent magnitude accepted for ``**``. Without this, ``2**999999999``
#: is a single ``Pow`` node that would consume all available memory.
MAX_EXPONENT = 1000

_BINARY_OPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
}

_UNARY_OPS = {
    ast.USub: operator.neg,
    ast.UAdd: operator.pos,
}


class ExpressionError(ValueError):
    """Raised when an expression is malformed, unsupported, or unsafe."""


def _check_length(expression: str) -> None:
    if not expression.strip():
        raise ExpressionError("expression is empty")
    if len(expression) > MAX_EXPRESSION_LENGTH:
        raise ExpressionError(
            f"expression is too long (limit {MAX_EXPRESSION_LENGTH} characters)"
        )


def _parse(expression: str) -> ast.Expression:
    try:
        tree = ast.parse(expression, mode="eval")
    except SyntaxError as exc:
        raise ExpressionError(f"could not parse expression: {exc.msg}") from exc
    except ValueError as exc:  # e.g. embedded null byte
        raise ExpressionError(f"could not parse expression: {exc}") from exc
    return tree


def _check_exponent(exponent: int | float) -> None:
    if exponent > MAX_EXPONENT:
        raise ExpressionError(f"exponent is too large (limit {MAX_EXPONENT})")
    if exponent < -MAX_EXPONENT:
        raise ExpressionError(f"exponent is too small (limit -{MAX_EXPONENT})")


def _evaluate_node(node: ast.AST) -> int | float:
    if isinstance(node, ast.Expression):
        return _evaluate_node(node.body)

    if isinstance(node, ast.Constant):
        value = node.value
        # bool is a subclass of int, so it has to be excluded explicitly.
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ExpressionError(f"unsupported literal: {value!r}")
        return value

    if isinstance(node, ast.BinOp):
        func = _BINARY_OPS.get(type(node.op))
        if func is None:
            raise ExpressionError(f"unsupported operator: {type(node.op).__name__}")

        left = _evaluate_node(node.left)
        right = _evaluate_node(node.right)

        if isinstance(node.op, ast.Pow):
            _check_exponent(right)

        try:
            return func(left, right)
        except ZeroDivisionError:
            raise ExpressionError("division by zero") from None
        except OverflowError:
            raise ExpressionError("result is too large to compute") from None

    if isinstance(node, ast.UnaryOp):
        func = _UNARY_OPS.get(type(node.op))
        if func is None:
            raise ExpressionError(f"unsupported operator: {type(node.op).__name__}")
        return func(_evaluate_node(node.operand))

    raise ExpressionError(f"unsupported syntax: {type(node).__name__}")


def evaluate(expression: str) -> int | float:
    """Return the value of ``expression``.

    Raises :class:`ExpressionError` if the input is malformed, unsupported, or
    too expensive to compute.
    """
    _check_length(expression)
    return _evaluate_node(_parse(expression))


def format_result(value: int | float) -> str:
    """Render a result for display and storage.

    ``str`` keeps floats tidy (``3.5``) while preserving the full precision of
    large integers, which a ``REAL`` column would silently round.
    """
    return str(value)
