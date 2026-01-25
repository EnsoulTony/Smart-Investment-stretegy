"""Shared guardrails helpers for tests."""

from __future__ import annotations

import ast
import io
import tokenize
from typing import Iterable


def _docstring_line_spans(tree: ast.AST) -> set[int]:
    spans: set[int] = set()

    def record(node: ast.AST) -> None:
        body = getattr(node, "body", [])
        if not body:
            return
        first = body[0]
        if isinstance(first, ast.Expr) and isinstance(getattr(first, "value", None), ast.Constant):
            value = first.value
            if isinstance(value.value, str) and hasattr(first, "lineno") and hasattr(first, "end_lineno"):
                for line_no in range(first.lineno, first.end_lineno + 1):
                    spans.add(line_no)

    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            record(node)

    return spans


def strip_comments_and_docstrings(text: str) -> str:
    """Return source with comments and docstrings removed.

    Keeps string literals in code (so connection strings remain detectable).
    """
    try:
        tree = ast.parse(text)
        docstring_lines = _docstring_line_spans(tree)
    except SyntaxError:
        docstring_lines = set()

    out = []
    tokens = tokenize.generate_tokens(io.StringIO(text).readline)
    for token in tokens:
        tok_type, tok_str, (srow, _), _, _ = token
        if tok_type == tokenize.COMMENT:
            continue
        if tok_type == tokenize.STRING and srow in docstring_lines:
            continue
        out.append(tok_str)

    return "".join(out)


def iter_lines(text: str) -> Iterable[tuple[int, str]]:
    for idx, line in enumerate(text.splitlines(), 1):
        yield idx, line
