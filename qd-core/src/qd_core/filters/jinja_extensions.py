"""QD v1 compatible Jinja control-flow extensions."""

import time
from collections.abc import Iterator

from jinja2 import nodes
from jinja2.ext import Extension
from jinja2.lexer import Token
from jinja2.runtime import Context
from jinja2.utils import pass_context

DEFAULT_MAX_WHILE_ITERATIONS = 10_000
DEFAULT_MAX_WHILE_SECONDS = 900.0
MAX_WHILE_ITERATIONS = DEFAULT_MAX_WHILE_ITERATIONS
MAX_WHILE_SECONDS = DEFAULT_MAX_WHILE_SECONDS

_LOOP_ALIASES = {
    "loop_length": "length",
    "loop_index": "index",
    "loop_index0": "index0",
    "loop_revindex": "revindex",
    "loop_revindex0": "revindex0",
    "loop_first": "first",
    "loop_last": "last",
    "loop_depth": "depth",
    "loop_depth0": "depth0",
}


@pass_context
def qd_while_guard(context: Context) -> str:
    max_iterations = int(context.environment.globals["_qd_while_loop_limit"])
    max_seconds = float(context.environment.globals["_qd_while_loop_timeout"])
    if MAX_WHILE_ITERATIONS != DEFAULT_MAX_WHILE_ITERATIONS:
        max_iterations = MAX_WHILE_ITERATIONS
    if MAX_WHILE_SECONDS != DEFAULT_MAX_WHILE_SECONDS:
        max_seconds = MAX_WHILE_SECONDS
    state = context.vars.setdefault(
        "__qd_while_state",
        {"started_at": time.monotonic(), "iterations": 0},
    )
    state["iterations"] += 1
    if state["iterations"] > max_iterations:
        raise RuntimeError(f"while loop exceeded {max_iterations} iterations")
    if time.monotonic() - state["started_at"] > max_seconds:
        raise RuntimeError(f"while loop exceeded {max_seconds:g} seconds")
    return ""


class QDCompatibilityExtension(Extension):
    """Add original-QD while tags and loop variable aliases."""

    tags = {"while"}

    def filter_stream(self, stream: Iterator[Token]) -> Iterator[Token]:
        for token in stream:
            attribute = _LOOP_ALIASES.get(token.value) if token.type == "name" else None
            if attribute is None:
                yield token
                continue
            yield Token(token.lineno, "name", "loop")
            yield Token(token.lineno, "dot", ".")
            yield Token(token.lineno, "name", attribute)

    def parse(self, parser):
        lineno = next(parser.stream).lineno
        condition = parser.parse_expression()
        body = parser.parse_statements(("name:endwhile",), drop_needle=True)

        stop_when_false = nodes.If(nodes.Not(condition), [nodes.Break()], [], [])
        guard = nodes.ExprStmt(
            nodes.Call(nodes.Name("_qd_while_guard", "load"), [], [], None, None)
        )
        loop = nodes.For(
            nodes.Name("_qd_while_index", "store"),
            nodes.Call(
                nodes.Name("_qd_while_range", "load"),
                [],
                [],
                None,
                None,
            ),
            [stop_when_false, guard, *body],
            [],
            None,
            False,
        )
        return loop.set_lineno(lineno)
