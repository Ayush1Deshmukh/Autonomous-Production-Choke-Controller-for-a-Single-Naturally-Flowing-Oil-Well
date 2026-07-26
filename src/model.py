"""
model.py
========

The CONTROL-ORIENTED dynamic model of the well, identified from open-loop
step tests (see `scripts/03_identify_model.py`).

Model form
----------
For each output y in {Q, WHP, FLP, BHP}:

    y(k+1) = y(k) + a_y * ( y_ss(u(k)) + d_y  -  y(k) ),     a_y = 1 - e^(-Ts/tau_y)

i.e. a **first-order lag towards an identified steady-state characteristic**,
plus a constant output disturbance d_y estimated online.

Why this form
-------------
* The step tests show the process is strongly NONLINEAR: the steady-state gain
  dQ/du is ~3.6 bbl/hr per % near 20 % opening but only ~0.15 at 90 %.  A
  single fixed-gain linear model would badly mispredict at one end of the
  range or the other.
* Splitting the model into "where does it end up" (the steady-state curve
  y_ss(u), read directly off the step-test end points) and "how fast does it
  get there" (one time constant per output) keeps it completely explainable -
  every number in the model is something an engineer can point at on a plot -
  while capturing the nonlinearity exactly where it matters.
* It reduces exactly to a classical first-order-plus-gain model on any small
  interval: locally, y_ss(u) is a straight line of slope K(u), so the model is
  y(k+1) = y(k) + a*(K*du + y0 - y(k)).  The per-region gains K(u) are
  reported in the engineering report.
* Dead time was fitted and came out at ~0 steps (the plant has no transport
  delay), so theta is carried in the model but is zero here.

Assumptions and limitations
---------------------------
* Steady-state curve is piecewise linear between the identified step end
  points; between knots the true curve is slightly convex, which is the main
  source of prediction error (quantified in the validation report).
* One time constant per output, assumed independent of operating point and of
  step direction.  The step tests support this (spread of fitted tau across
  steps is small - see the report).
* No dead time, no interaction beyond what is implicit in the shared
  dependence on u, and no reservoir depletion over the horizon.
* Valid over 0-100 % choke, the range the step tests covered.  Extrapolation
  beyond the knots is clamped (flat), which is flagged by `is_extrapolating`.
* The model is only ever used over a 5-step prediction horizon, where these
  approximations are small; the online disturbance estimate d_y removes any
  residual steady-state offset.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Sequence

import numpy as np

OUTPUTS = ("Q", "WHP", "FLP", "BHP")


@dataclass
class OutputModel:
    """Identified model of one measured output."""

    name: str
    tau: float                    # first-order time constant [h]
    theta: float                  # dead time [h] (0 for this plant)
    u_knots: List[float]          # choke openings at which steady state is known
    y_knots: List[float]          # corresponding steady-state values
    tau_per_step: List[float] = field(default_factory=list)   # diagnostics
    rmse_fit: float = 0.0

    # -- steady-state characteristic -----------------------------------
    def y_ss(self, u: float | np.ndarray) -> float | np.ndarray:
        """Identified steady-state value of this output at choke opening u."""
        return np.interp(u, self.u_knots, self.y_knots)

    def gain(self, u: float, du: float = 1.0) -> float:
        """Local steady-state gain dy/du [output units per % choke]."""
        return float((self.y_ss(u + du / 2) - self.y_ss(u - du / 2)) / du)

    def alpha(self, ts: float) -> float:
        """Discrete lag coefficient for a control interval of `ts` hours."""
        return float(1.0 - np.exp(-ts / self.tau))

    def is_extrapolating(self, u: float) -> bool:
        return u < min(self.u_knots) - 1e-9 or u > max(self.u_knots) + 1e-9

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "tau": self.tau,
            "theta": self.theta,
            "u_knots": list(map(float, self.u_knots)),
            "y_knots": list(map(float, self.y_knots)),
            "tau_per_step": list(map(float, self.tau_per_step)),
            "rmse_fit": float(self.rmse_fit),
        }

    @staticmethod
    def from_dict(d: dict) -> "OutputModel":
        return OutputModel(
            name=d["name"],
            tau=d["tau"],
            theta=d["theta"],
            u_knots=d["u_knots"],
            y_knots=d["y_knots"],
            tau_per_step=d.get("tau_per_step", []),
            rmse_fit=d.get("rmse_fit", 0.0),
        )


@dataclass
class WellModel:
    """The full four-output identified model used by the MPC."""

    ts: float
    outputs: Dict[str, OutputModel]

    # ------------------------------------------------------------------
    # Prediction
    # ------------------------------------------------------------------
    def predict(
        self,
        y0: Dict[str, float],
        u_sequence: Sequence[float],
        disturbance: Dict[str, float] | None = None,
    ) -> Dict[str, np.ndarray]:
        """
        Roll the model forward.

        Parameters
        ----------
        y0 : dict
            Current measured values {Q, WHP, FLP, BHP} - the prediction always
            starts from the real plant measurement, so errors cannot accumulate
            across control intervals.
        u_sequence : sequence of float
            Choke opening applied at each step of the horizon.
        disturbance : dict, optional
            Constant output disturbance d_y added to the steady-state target,
            estimated online from the one-step prediction error.  This is what
            removes steady-state offset caused by plant/model mismatch.

        Returns
        -------
        dict of arrays, each of length len(u_sequence), giving the predicted
        trajectory of each output (the value at the END of each step).
        """
        d = disturbance or {k: 0.0 for k in OUTPUTS}
        y = {k: float(y0[k]) for k in OUTPUTS}
        traj = {k: np.empty(len(u_sequence)) for k in OUTPUTS}

        for i, u in enumerate(u_sequence):
            for k in OUTPUTS:
                m = self.outputs[k]
                target = float(m.y_ss(u)) + d.get(k, 0.0)
                y[k] += m.alpha(self.ts) * (target - y[k])
                traj[k][i] = y[k]
        # A naturally flowing well cannot produce a negative rate.
        traj["Q"] = np.maximum(traj["Q"], 0.0)
        return traj

    def predict_one(
        self,
        y0: Dict[str, float],
        u: float,
        disturbance: Dict[str, float] | None = None,
    ) -> Dict[str, float]:
        """One-step-ahead prediction (used by the disturbance estimator)."""
        traj = self.predict(y0, [u], disturbance)
        return {k: float(v[0]) for k, v in traj.items()}

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------
    def save(self, path: str | Path) -> None:
        payload = {
            "ts": self.ts,
            "outputs": {k: m.to_dict() for k, m in self.outputs.items()},
        }
        Path(path).write_text(json.dumps(payload, indent=2))

    @staticmethod
    def load(path: str | Path) -> "WellModel":
        payload = json.loads(Path(path).read_text())
        return WellModel(
            ts=payload["ts"],
            outputs={
                k: OutputModel.from_dict(v) for k, v in payload["outputs"].items()
            },
        )

    # ------------------------------------------------------------------
    # Reporting helper
    # ------------------------------------------------------------------
    def gain_table(self, u_points: Sequence[float]) -> "list[dict]":
        """Local steady-state gains at several operating points, for the report."""
        rows = []
        for u in u_points:
            row = {"choke_pct": u}
            for k in OUTPUTS:
                row[f"K_{k}"] = self.outputs[k].gain(u, du=2.0)
            rows.append(row)
        return rows
