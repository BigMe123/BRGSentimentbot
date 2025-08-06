"""Differential privacy utilities using Diffprivlib."""

from __future__ import annotations

from functools import wraps
from typing import Any, Callable

from diffprivlib.accountant import BudgetAccountant


def dp_mechanism(epsilon: float, delta: float):
    """Decorator to track a simple privacy budget using ``diffprivlib``."""

    accountant = BudgetAccountant()

    def decorator(fn: Callable[..., Any]) -> Callable[..., Any]:
        @wraps(fn)
        def wrapped(*args: Any, **kwargs: Any) -> Any:
            result = fn(*args, **kwargs)
            accountant.spend(1.0, delta)
            eps, delt = accountant.total()
            if eps > epsilon or delt > delta:
                raise RuntimeError("Privacy budget exceeded")
            wrapped.epsilon = eps
            wrapped.delta = delt
            return result

        return wrapped

    return decorator
