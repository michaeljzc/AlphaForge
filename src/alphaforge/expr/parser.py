"""Recursive-descent parser for the AlphaForge factor DSL.

Grammar::

    expr    := ternary
    ternary := or_expr ('?' expr ':' expr)?
    or_expr := and_expr ('||' and_expr)*
    and_expr:= comparison ('&&' comparison)*
    comp    := additive (('>' | '<' | '>=' | '<=' | '==' | '!=') additive)*
    additive:= term (('+' | '-') term)*
    term    := unary (('*' | '/') unary)*
    unary   := ('+' | '-') unary | power
    power   := atom ('^' unary)?
    atom    := NUMBER | FIELD | FUNC '(' [expr (',' expr)*] ')' | '(' expr ')'

Field names may optionally be prefixed with ``$`` (Qlib style).  Function
names are validated against :mod:`alphaforge.expr.ops`.
"""

from __future__ import annotations

import re

from alphaforge.expr.ast import Node

_TOKEN = re.compile(
    r"""
    (?P<space>\s+)
  | (?P<number>(?:\d+\.\d*|\.\d+|\d+)(?:[eE][-+]?\d+)?)
  | (?P<ident>\$?[A-Za-z_][A-Za-z0-9_]*)
  | (?P<op>\*\*|<=|>=|==|!=|\|\||&&|[<>?:\-+*/^(),])
    """,
    re.VERBOSE,
)


class ParseError(ValueError):
    pass


def tokenize(text: str) -> list[tuple[str, str]]:
    tokens: list[tuple[str, str]] = []
    pos = 0
    while pos < len(text):
        m = _TOKEN.match(text, pos)
        if not m:
            raise ParseError(f"非法字符 {text[pos]!r} (位置 {pos})")
        pos = m.end()
        kind = m.lastgroup
        if kind == "space":
            continue
        value = m.group()
        if kind == "op" and value == "**":
            value = "^"
        tokens.append((kind, value))
    tokens.append(("eof", ""))
    return tokens


class _Parser:
    def __init__(self, text: str):
        self.text = text
        self.tokens = tokenize(text)
        self.i = 0

    def peek(self) -> tuple[str, str]:
        return self.tokens[self.i]

    def take(self, value: str | None = None) -> tuple[str, str]:
        token = self.tokens[self.i]
        if value is not None and token[1] != value:
            raise ParseError(f"期望 {value!r}，得到 {token[1]!r} (位置 {self.i})")
        self.i += 1
        return token

    def parse(self) -> Node:
        node = self.expr()
        if self.peek()[0] != "eof":
            raise ParseError(f"多余的记号 {self.peek()[1]!r}")
        return node

    def expr(self) -> Node:
        return self.ternary()

    def ternary(self) -> Node:
        node = self.or_expr()
        if self.peek()[1] == "?":
            self.take("?")
            yes = self.expr()
            self.take(":")
            no = self.expr()
            return Node.op("where", node, yes, no)
        return node

    def or_expr(self) -> Node:
        node = self.and_expr()
        while self.peek()[1] == "||":
            self.take("||")
            node = Node.op("or", node, self.and_expr())
        return node

    def and_expr(self) -> Node:
        node = self.comparison()
        while self.peek()[1] == "&&":
            self.take("&&")
            node = Node.op("and", node, self.comparison())
        return node

    def comparison(self) -> Node:
        node = self.additive()
        while self.peek()[1] in (">", "<", ">=", "<=", "==", "!="):
            op = self.take()[1]
            rhs = self.additive()
            name = {">": "gt", "<": "lt", ">=": "ge", "<=": "le",
                    "==": "eq", "!=": "ne"}[op]
            node = Node.op(name, node, rhs)
        return node

    def additive(self) -> Node:
        node = self.term()
        while self.peek()[1] in ("+", "-"):
            op = self.take()[1]
            rhs = self.term()
            node = Node.op("add" if op == "+" else "sub", node, rhs)
        return node

    def term(self) -> Node:
        node = self.unary()
        while self.peek()[1] in ("*", "/"):
            op = self.take()[1]
            rhs = self.unary()
            node = Node.op("mul" if op == "*" else "div", node, rhs)
        return node

    def unary(self) -> Node:
        if self.peek()[1] == "-":
            self.take()
            return Node.op("neg", self.unary())
        if self.peek()[1] == "+":
            self.take()
            return self.unary()
        return self.power()

    def power(self) -> Node:
        node = self.atom()
        if self.peek()[1] == "^":
            self.take()
            rhs = self.unary()
            return Node.op("pow", node, rhs)
        return node

    def atom(self) -> Node:
        kind, value = self.peek()
        if kind == "number":
            self.take()
            return Node.const(float(value))
        if kind == "ident":
            self.take()
            name = value.lstrip("$").lower()
            if self.peek()[1] == "(":
                self.take("(")
                args: list[Node] = []
                if self.peek()[1] != ")":
                    args.append(self.expr())
                    while self.peek()[1] == ",":
                        self.take(",")
                        args.append(self.expr())
                self.take(")")
                from alphaforge.expr.ops import OPS

                if name not in OPS:
                    raise ParseError(f"未知算子 {name!r}")
                arity = OPS[name].arity
                allowed = (arity,) if isinstance(arity, int) else tuple(arity)
                if len(args) not in allowed:
                    raise ParseError(
                        f"算子 {name} 需要 {allowed} 个参数，实际 {len(args)} 个"
                    )
                return Node.op(name, *args)
            return Node.field(name)
        if value == "(":
            self.take("(")
            node = self.expr()
            self.take(")")
            return node
        raise ParseError(f"意外的记号 {value!r}")


def parse(text: str) -> Node:
    text = text.strip()
    if not text:
        raise ParseError("表达式为空")
    return _Parser(text).parse()
