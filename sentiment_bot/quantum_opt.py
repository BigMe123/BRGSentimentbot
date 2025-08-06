"""QAOA-inspired portfolio optimisation using Qiskit Aer."""
from __future__ import annotations

from typing import Sequence

import numpy as np
from qiskit import QuantumCircuit
from qiskit.circuit import Parameter
from qiskit_aer import AerSimulator
from qiskit.algorithms.optimizers import COBYLA


def optimize_portfolio(weights_init: Sequence[float]) -> np.ndarray:
    """Return new weights optimised by a tiny quantum-inspired routine."""

    n = len(weights_init)
    params = [Parameter(f"theta_{i}") for i in range(n)]
    qc = QuantumCircuit(n)
    for i, p in enumerate(params):
        qc.ry(p, i)
    simulator = AerSimulator(method="statevector")
    optimizer = COBYLA(maxiter=50)

    def objective(x: np.ndarray) -> float:
        bind = qc.bind_parameters({p: v for p, v in zip(params, x)})
        result = simulator.run(bind).result()
        state = result.get_statevector()
        probs = np.abs(state) ** 2
        cost = 0.0
        for i, w in enumerate(weights_init):
            mask = 1 << (n - i - 1)
            prob_one = probs.reshape(-1)[
                [j for j in range(len(probs)) if j & mask]
            ].sum()
            cost -= w * prob_one
        return cost

    res = optimizer.minimize(objective, np.array(weights_init, dtype=float))
    return res.x
