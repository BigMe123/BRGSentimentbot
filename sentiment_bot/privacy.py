"""Differential privacy utilities using Opacus."""
from __future__ import annotations

from functools import wraps
from typing import Any, Callable


def dp_mechanism(epsilon: float, delta: float):
    """Decorator to track a simple privacy budget."""

    from opacus.accountants import RDPAccountant

    def decorator(fn: Callable[..., Any]) -> Callable[..., Any]:
        accountant = RDPAccountant()

        @wraps(fn)
        def wrapped(*args: Any, **kwargs: Any) -> Any:
            result = fn(*args, **kwargs)
            accountant.step(noise_multiplier=1.1, sample_rate=1.0)
            eps, delt = accountant.get_privacy_spent(delta)
            if eps > epsilon:
                raise RuntimeError("Privacy budget exceeded")
            wrapped.epsilon = eps
            wrapped.delta = delt
            return result

        return wrapped

    return decorator
