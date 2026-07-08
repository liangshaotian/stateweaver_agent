from __future__ import annotations

import ast
import operator as op

from .skill_spec import SkillResult


OPS = {
    ast.Add: op.add, ast.Sub: op.sub, ast.Mult: op.mul, ast.Div: op.truediv,
    ast.Pow: op.pow, ast.USub: op.neg, ast.Mod: op.mod,
}


def _eval(node):
    if isinstance(node, ast.Num):
        return node.n
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return node.value
    if isinstance(node, ast.BinOp) and type(node.op) in OPS:
        return OPS[type(node.op)](_eval(node.left), _eval(node.right))
    if isinstance(node, ast.UnaryOp) and type(node.op) in OPS:
        return OPS[type(node.op)](_eval(node.operand))
    raise ValueError(f"Unsupported expression: {ast.dump(node)}")


def calculator(expression: str) -> SkillResult:
    try:
        value = _eval(ast.parse(expression, mode="eval").body)
        return SkillResult("ok", {"expression": expression, "value": value})
    except Exception as exc:
        return SkillResult("error", error=str(exc))
