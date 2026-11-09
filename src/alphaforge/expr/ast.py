"""Expression AST and canonical serialisation."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable

# infix operators and their precedence (higher binds tighter)
INFIX = {
    "add": ("+", 1),
    "sub": ("-", 1),
    "mul": ("*", 2),
    "div": ("/", 2),
    "pow": ("^", 3),
}
UNARY = {"neg": "-"}


@dataclass(frozen=True)
class Node:
    kind: str                          # field | const | op
    name: str = ""
    value: float = 0.0
    args: tuple["Node", ...] = ()

    # -- constructors ------------------------------------------------------
    @staticmethod
    def field(name: str) -> "Node":
        return Node("field", name=name.lower())

    @staticmethod
    def const(value: float) -> "Node":
        return Node("const", value=float(value))

    @staticmethod
    def op(name: str, *args: "Node") -> "Node":
        return Node("op", name=name, args=tuple(args))

    # -- properties --------------------------------------------------------
    @property
    def is_leaf(self) -> bool:
        return self.kind in ("field", "const")

    def children(self) -> tuple["Node", ...]:
        return self.args

    def size(self) -> int:
        return 1 + sum(a.size() for a in self.args)

    def depth(self) -> int:
        return 1 if not self.args else 1 + max(a.depth() for a in self.args)

    def fields(self) -> set[str]:
        if self.kind == "field":
            return {self.name}
        out: set[str] = set()
        for a in self.args:
            out |= a.fields()
        return out

    def operators(self) -> list[str]:
        out = [self.name] if self.kind == "op" else []
        for a in self.args:
            out.extend(a.operators())
        return out

    # -- serialisation -----------------------------------------------------
    def to_string(self, parent_prec: int = 0) -> str:
        if self.kind == "field":
            return self.name
        if self.kind == "const":
            v = self.value
            if float(v).is_integer():
                return str(int(v))
            return f"{v:.6g}"
        if self.name in UNARY:
            inner = self.args[0].to_string(3)
            return f"-{inner}"
        if self.name in INFIX:
            symbol, prec = INFIX[self.name]
            if self.name == "pow":
                inner = f"{self.args[0].to_string(prec)}^{self.args[1].to_string(prec - 1)}"
            else:
                inner = f"{self.args[0].to_string(prec)} {symbol} {self.args[1].to_string(prec + 1)}"
            return f"({inner})" if prec < parent_prec else inner
        return f"{self.name}({', '.join(a.to_string() for a in self.args)})"

    def __str__(self) -> str:
        return self.to_string()


def node_from_string(text: str) -> Node:
    from alphaforge.expr.parser import parse

    return parse(text)


def walk(node: Node) -> Iterable[Node]:
    yield node
    for a in node.args:
        yield from walk(a)
