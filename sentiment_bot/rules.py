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
    """Evaluate expression against ``snapshot`` in a safe namespace."""

    tree = ast.parse(expr, mode="eval")
    allowed = {"snapshot": snapshot}
    code = compile(tree, "<rules>", "eval")
    return bool(eval(code, {"__builtins__": {}}, allowed))


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
