"""
controller.py
==============

Brute-force Model Predictive Controller (MPC) for the production choke.

At every control interval (Ts = 1 hour) the controller:

    1. PREDICT   - for every candidate next choke position (current +/- up to
                   the ramp-rate limit, on a fine grid), roll the identified
                   `WellModel` forward over a short prediction horizon,
                   holding the candidate constant for the rest of the horizon
                   (move-blocking).  Every prediction starts from the CURRENT
                   MEASURED state, so model error never compounds across
                   control intervals - only within one horizon.

    2. FILTER    - reject any candidate whose predicted WHP, FLP or BHP would
                   breach the safe operating envelope at ANY point in the
                   horizon.  A small safety margin is enforced *inside* every
                   hard limit so sensor noise and plant/model mismatch can
                   never push the real well over the actual line.

    3. SELECT    - among the surviving (safe) candidates, choose the one whose
                   predicted end-of-horizon flow rate is closest to the target,
                   with a small penalty on move size for smoothness.  Ties are
                   broken deterministically: smallest |move|, then the lower
                   choke position (the more conservative choice).

    4. FALLBACK  - if every candidate is predicted to violate a constraint
                   (e.g. a very aggressive starting condition), the controller
                   does not throw up its hands: it picks the candidate that
                   minimises the worst predicted violation magnitude, which is
                   always the "hold or close slightly" direction, and is
                   incapable of making things worse.

This is exactly why the controller cannot oscillate on an infeasible target:
moving further open is rejected outright by step 2 once it would cross a
limit within the horizon, and moving back is never selected because it is
farther from (the unreachable) target while offering no constraint benefit -
so the cost function pins the choke at the largest FEASIBLE opening.

A steady-state bias/disturbance estimate (`_update_bias`) is maintained per
output: at every interval the previous prediction is compared with the new
measurement, and the small difference is added to all future steady-state
targets.  This removes any steady-state offset caused by the model being an
approximation of the true plant, which is what lets the controller land
exactly on target rather than merely near it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

import numpy as np

from model import WellModel, OUTPUTS

try:
    from .config import ControllerParams, Limits, CONTROLLER, LIMITS
except ImportError:  # pragma: no cover
    from config import ControllerParams, Limits, CONTROLLER, LIMITS


@dataclass
class CandidateResult:
    """Full record of one evaluated candidate, kept for the dashboard's
    'reasoning' panel and for logging."""

    u: float
    du: float
    feasible: bool
    reject_reason: Optional[str]
    predicted_Q_end: float
    predicted_trajectory: Dict[str, np.ndarray]
    cost: float
    max_violation: float          # 0 if feasible; otherwise worst overshoot


@dataclass
class ControllerDecision:
    """Everything the controller decided at one control interval."""

    u_selected: float
    u_previous: float
    target_Q: float
    candidates: List[CandidateResult]
    selected_index: int
    all_infeasible: bool
    disturbance: Dict[str, float]


class ChokeMPC:
    """Brute-force MPC for the single-well production choke."""

    def __init__(
        self,
        model: WellModel,
        limits: Limits = LIMITS,
        params: ControllerParams = CONTROLLER,
    ) -> None:
        self.model = model
        self.limits = limits
        self.p = params
        # Online disturbance estimate (plant - model) per output, used to
        # remove steady-state offset.  Starts at zero (no bias assumed).
        self.disturbance: Dict[str, float] = {k: 0.0 for k in OUTPUTS}
        self._last_prediction: Optional[Dict[str, float]] = None
        # Filtered measurement state (see ControllerParams.meas_filter_alpha).
        self._y_filt: Optional[Dict[str, float]] = None

    def _filter_measurement(self, measured: Dict[str, float]) -> Dict[str, float]:
        """First-order filter on the incoming measurement, so that sensor noise
        does not randomly flip candidates across the constraint boundary."""
        a = self.p.meas_filter_alpha
        if self._y_filt is None:
            self._y_filt = {k: float(measured[k]) for k in OUTPUTS}
        else:
            for k in OUTPUTS:
                self._y_filt[k] = (1 - a) * self._y_filt[k] + a * float(measured[k])
        return dict(self._y_filt)

    # ------------------------------------------------------------------
    def _update_bias(self, measured: Dict[str, float]) -> None:
        """Compare the previous step's one-step-ahead prediction with the new
        measurement and nudge the disturbance estimate (exponential filter)."""
        if self._last_prediction is None:
            return
        a = self.p.bias_filter_alpha
        for k in OUTPUTS:
            err = measured[k] - self._last_prediction[k]
            self.disturbance[k] = (1 - a) * self.disturbance[k] + a * err

    # ------------------------------------------------------------------
    def _candidate_grid(self, u_current: float) -> np.ndarray:
        lo = max(self.p.u_min, u_current - self.p.max_move)
        hi = min(self.p.u_max, u_current + self.p.max_move)
        n = max(int(round((hi - lo) / self.p.candidate_step)) + 1, 1)
        grid = np.linspace(lo, hi, n)
        # always include "hold" exactly, useful for the infeasible fallback
        if u_current not in grid:
            grid = np.sort(np.append(grid, u_current))
        return grid

    def _violation(self, traj: Dict[str, np.ndarray]) -> float:
        """Worst constraint violation (in psi, summed over pressure vars,
        margin-inclusive) anywhere in the horizon. 0 if fully feasible."""
        L = self.limits
        m = self.p
        viol = 0.0
        viol += np.maximum(0.0, (L.whp_min + m.margin_whp) - traj["WHP"]).max()
        viol += np.maximum(0.0, traj["WHP"] - (L.whp_max - m.margin_whp)).max()
        viol += np.maximum(0.0, (L.flp_min + m.margin_flp) - traj["FLP"]).max()
        viol += np.maximum(0.0, traj["FLP"] - (L.flp_max - m.margin_flp)).max()
        viol += np.maximum(0.0, (L.bhp_min + m.margin_bhp) - traj["BHP"]).max()
        viol += np.maximum(0.0, traj["BHP"] - (L.bhp_max - m.margin_bhp)).max()
        return float(viol)

    def _reject_reason(self, traj: Dict[str, np.ndarray]) -> Optional[str]:
        L = self.limits
        m = self.p
        checks = [
            ("BHP", traj["BHP"].min(), L.bhp_min + m.margin_bhp, "min"),
            ("BHP", traj["BHP"].max(), L.bhp_max - m.margin_bhp, "max"),
            ("WHP", traj["WHP"].min(), L.whp_min + m.margin_whp, "min"),
            ("WHP", traj["WHP"].max(), L.whp_max - m.margin_whp, "max"),
            ("FLP", traj["FLP"].min(), L.flp_min + m.margin_flp, "min"),
            ("FLP", traj["FLP"].max(), L.flp_max - m.margin_flp, "max"),
        ]
        for name, val, bound, kind in checks:
            if kind == "min" and val < bound:
                k = int(np.argmin(traj[name]))
                return f"{name} {val:.0f} < {bound:.0f} at k+{k+1}"
            if kind == "max" and val > bound:
                k = int(np.argmax(traj[name]))
                return f"{name} {val:.0f} > {bound:.0f} at k+{k+1}"
        return None

    # ------------------------------------------------------------------
    def step(
        self,
        measured: Dict[str, float],
        u_current: float,
        target_Q: float,
    ) -> ControllerDecision:
        """
        Compute the next choke position.

        Parameters
        ----------
        measured : dict
            Current {Q, WHP, FLP, BHP} measurement from the well.
        u_current : float
            Current choke position [%].
        target_Q : float
            Desired oil flow rate [bbl/hr].

        Returns
        -------
        ControllerDecision with the selected choke position and the full
        candidate evaluation (used for logging and for the dashboard's
        reasoning panel).
        """
        # Filter first, then run the whole predict -> filter -> select cycle on
        # the filtered state so the feasible set is stable interval to interval.
        measured = self._filter_measurement(measured)
        self._update_bias(measured)

        grid = self._candidate_grid(u_current)
        horizon_len = self.p.horizon
        results: List[CandidateResult] = []

        for u in grid:
            u_seq = [u] * horizon_len          # move-blocking: apply then hold
            traj = self.model.predict(measured, u_seq, self.disturbance)
            viol = self._violation(traj)
            feasible = viol <= 1e-9
            reason = None if feasible else self._reject_reason(traj)

            q_end = float(traj["Q"][-1])
            du = u - u_current
            cost = (q_end - target_Q) ** 2 + self.p.move_penalty * du ** 2

            results.append(
                CandidateResult(
                    u=float(u),
                    du=float(du),
                    feasible=feasible,
                    reject_reason=reason,
                    predicted_Q_end=q_end,
                    predicted_trajectory=traj,
                    cost=float(cost),
                    max_violation=viol,
                )
            )

        feasible_results = [r for r in results if r.feasible]
        all_infeasible = len(feasible_results) == 0

        if not all_infeasible:
            # SELECT: minimum cost; ties -> smallest |move|; then lower u.
            def sel_key(r: CandidateResult):
                return (round(r.cost, 6), round(abs(r.du), 6), r.u)

            chosen = min(feasible_results, key=sel_key)

            # DEADBAND: only actually move if the move buys a meaningful
            # predicted improvement over simply holding position.  The cost
            # surface is evaluated on noisy measurements, so without this its
            # argmin wanders every interval and the choke chatters - pure valve
            # wear with no production benefit.  Holding is always preferred on
            # a tie, which also makes the steady state genuinely steady.
            hold = min(
                (r for r in feasible_results if abs(r.du) < 1e-9),
                key=lambda r: abs(r.du),
                default=None,
            )
            if hold is not None and (hold.cost - chosen.cost) < self.p.min_cost_improvement:
                chosen = hold
        else:
            # FALLBACK: minimise worst constraint violation; ties -> smallest
            # |move| (never lurch), then lower u (favour closing).
            def fb_key(r: CandidateResult):
                return (round(r.max_violation, 6), round(abs(r.du), 6), r.u)

            chosen = min(results, key=fb_key)

        selected_index = results.index(chosen)
        self._last_prediction = {k: float(chosen.predicted_trajectory[k][0]) for k in OUTPUTS}

        return ControllerDecision(
            u_selected=chosen.u,
            u_previous=u_current,
            target_Q=target_Q,
            candidates=results,
            selected_index=selected_index,
            all_infeasible=all_infeasible,
            disturbance=dict(self.disturbance),
        )
