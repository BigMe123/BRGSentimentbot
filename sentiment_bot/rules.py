"""Rule engine using YAML playbooks."""

from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path
from typing import List

try:  # pragma: no cover - optional dependency
    import yaml  # type: ignore
except Exception:  # pragma: no cover
    yaml = None  # type: ignore

from .config import settings
from .analyzer import Snapshot


@dataclass
class Rule:
    when: str
    then: str


def load_rules(path: str | None = None) -> List[Rule]:
    rules_path = Path(path or settings.RULES_PATH)
    if not rules_path.exists():
        return []
    text = rules_path.read_text()
    if yaml:
        data = yaml.safe_load(text) or []
    else:
        data = []
        for block in text.strip().split("- "):
            block = block.strip()
            if not block:
                continue
            rule = {}
            for line in block.splitlines():
                if ":" in line:
                    k, v = line.split(":", 1)
                    rule[k.strip()] = v.strip()
            if rule:
                data.append(rule)
    return [Rule(**r) for r in data]


def _safe_eval(expr: str, snapshot: Snapshot) -> bool:
    """Evaluate ``expr`` against ``snapshot`` using a whitelisted AST."""

    tree = ast.parse(expr, mode="eval")

    allowed_nodes = (
        ast.Expression,
        ast.BoolOp,
        ast.Compare,
        ast.Attribute,
        ast.Name,
        ast.Load,
        ast.And,
        ast.Or,
        ast.Gt,
        ast.GtE,
        ast.Lt,
        ast.LtE,
        ast.Eq,
        ast.NotEq,
        ast.Constant,
    )

    class Evaluator(ast.NodeVisitor):
        def visit(self, node: ast.AST):  # type: ignore[override]
            if not isinstance(node, allowed_nodes):
                raise ValueError(f"disallowed node {type(node).__name__}")
            return super().visit(node)

        def visit_Expression(self, node: ast.Expression):  # pragma: no cover - trivial
            return self.visit(node.body)

        def visit_Name(self, node: ast.Name):
            if node.id != "snapshot":
                raise ValueError("unknown name")
            return snapshot

        def visit_Attribute(self, node: ast.Attribute):
            value = self.visit(node.value)
            if value is not snapshot:
                raise ValueError("attribute access not allowed")
            if node.attr.startswith("_"):
                raise ValueError("private attribute access not allowed")
            return getattr(value, node.attr)

        def visit_Constant(self, node: ast.Constant):  # pragma: no cover - trivial
            return node.value

        def visit_BoolOp(self, node: ast.BoolOp):
            values = [self.visit(v) for v in node.values]
            if isinstance(node.op, ast.And):
                return all(values)
            if isinstance(node.op, ast.Or):
                return any(values)
            raise ValueError("unsupported boolean operator")

        def visit_Compare(self, node: ast.Compare):
            left = self.visit(node.left)
            for op, comparator in zip(node.ops, node.comparators):
                right = self.visit(comparator)
                if isinstance(op, ast.Gt):
                    result = left > right
                elif isinstance(op, ast.GtE):
                    result = left >= right
                elif isinstance(op, ast.Lt):
                    result = left < right
                elif isinstance(op, ast.LtE):
                    result = left <= right
                elif isinstance(op, ast.Eq):
                    result = left == right
                elif isinstance(op, ast.NotEq):
                    result = left != right
                else:  # pragma: no cover - defensive
                    raise ValueError("unsupported comparison")
                if not result:
                    return False
                left = right
            return True

    evaluator = Evaluator()
    return bool(evaluator.visit(tree))


def apply_rules(snapshot: Snapshot, rules: List[Rule] | None = None) -> List[str]:
    """Return alert messages for ``snapshot``."""

    rules = rules or load_rules()
    alerts: list[str] = []
    for rule in rules:
        try:
            if _safe_eval(rule.when, snapshot):
                alerts.append(rule.then)
        except Exception:
            continue
    return alerts
