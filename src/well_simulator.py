"""
well_simulator.py
=================

Physics-informed simulator of a SINGLE NATURALLY FLOWING OIL WELL with one
production choke.

>>> IMPORTANT NOTE ON PROVENANCE <<<
The hackathon problem statement says a simulator "will be provided".  No
simulator file was made available to us, so this module is a physics-based
STAND-IN built directly from the process description in the problem statement
(reservoir -> bottom hole -> tubing -> wellhead -> choke -> flowline ->
manifold -> separator).

It exposes exactly the interface named in the problem statement:

    Q, WHP, FLP, BHP = simulator.step(choke_position)

and nothing else is used by the controller (see `simulator_interface.py`), so
the official simulator can be substituted with no controller changes.

--------------------------------------------------------------------------
MODEL
--------------------------------------------------------------------------
At every control interval the *steady-state* operating point implied by the
commanded choke opening is solved from four simultaneous relations, and each
measured variable is then moved towards it through a first-order lag.

1. Reservoir inflow performance (linear IPR)
       BHP = P_res - Q / PI
   Drawdown grows linearly with rate; more flow means less bottom hole
   pressure.  A linear IPR (constant productivity index) is the standard
   first-order description above the bubble point and is explicitly adequate
   for this scope.

2. Production tubing hydraulics
       WHP = BHP - dP_static - k_fric * Q^2
   The static head (fluid column) is constant for a fixed fluid gradient; the
   friction term is turbulent and therefore grows with the square of rate.

3. Production choke (orifice / valve equation)
       Q = Cv * f(u) * sqrt(WHP - FLP),      f(u) = (u/100)^1.5
   The single most important relation in the model: flow through the choke
   depends on BOTH the opening AND the pressure drop across the valve.  Q is
   *not* a direct function of choke position alone.  Opening the choke
   increases Q, which increases drawdown, which lowers WHP, which reduces the
   available dP - a self-limiting negative feedback that is exactly what makes
   the process nonlinear and interesting to control.

4. Flowline backpressure
       FLP = FLP_base + k_flowline * Q
   A separator/manifold baseline plus a mild rise with throughput.

Because (1)-(4) are coupled, the steady state is found by solving the scalar
residual

       g(Q) = Cv*f(u)*sqrt(max(WHP(Q) - FLP(Q), 0)) - Q = 0

which is strictly decreasing in Q (raising Q lowers WHP and raises FLP, so it
lowers the right-hand side while raising the left).  A monotone residual means
a bracketed bisection/Brent solve is guaranteed to converge - there is no way
for the simulator to produce a NaN.

5. Dynamics and measurement
   Every output is passed through a first-order lag with its own time constant
   (BHP slowest, flowline fastest), then corrupted with small Gaussian sensor
   noise.  This makes the plant genuinely dynamic, so the controller has to
   *predict* rather than merely invert a static curve.

--------------------------------------------------------------------------
ASSUMPTIONS (per the problem statement)
--------------------------------------------------------------------------
    * single naturally flowing well, single production choke, no artificial
      lift, no gas lift / ESP optimisation
    * no facility-network interaction, constant reservoir properties,
      constant GOR and water cut
    * isothermal hydraulics (WHT is reported but is informational only)
    * the choke responds to the commanded position within one control interval
      (actuator dynamics are fast relative to Ts = 1 h)

All parameters live in `config.PlantParams` and are easy to retune.
"""

from __future__ import annotations

from typing import Dict, List, Tuple

import numpy as np
import pandas as pd

try:                                    # works both as a package and a script
    from .config import PLANT, SEED, TS_HOURS, PlantParams
except ImportError:                     # pragma: no cover
    from config import PLANT, SEED, TS_HOURS, PlantParams


class WellSimulator:
    """
    A single naturally flowing oil well with one production choke.

    Parameters
    ----------
    params : PlantParams, optional
        Physics parameters (defaults to `config.PLANT`).
    seed : int, optional
        Seed for the sensor-noise RNG; fixed by default for reproducibility.
    noise : bool, optional
        Set False for a noise-free plant (used by the step-test analysis to
        show the underlying dynamics cleanly, and by unit tests).
    ts : float, optional
        Control interval in hours (default 1.0).

    Examples
    --------
    >>> sim = WellSimulator()
    >>> Q, WHP, FLP, BHP = sim.step(30.0)
    """

    def __init__(
        self,
        params: PlantParams = PLANT,
        seed: int = SEED,
        noise: bool = True,
        ts: float = TS_HOURS,
    ) -> None:
        self.p = params
        self.ts = ts
        self.noise_on = noise
        self._seed = seed
        self.reset()

    # ------------------------------------------------------------------
    # Steady-state physics
    # ------------------------------------------------------------------
    def _bhp_of_q(self, q: float) -> float:
        """Linear IPR: bottom hole pressure falls as rate rises."""
        return self.p.p_res - q / self.p.pi_index

    def _whp_of_q(self, q: float) -> float:
        """Tubing: static head is constant, friction grows with Q^2."""
        dp_static = self.p.tvd_ft * self.p.grad_psi_per_ft
        return self._bhp_of_q(q) - dp_static - self.p.k_fric * q * q

    def _flp_of_q(self, q: float) -> float:
        """Flowline: baseline separator backpressure plus friction with rate."""
        return self.p.flp_base + self.p.k_flowline * q

    def _choke_char(self, u: float) -> float:
        """Valve characteristic f(u), 0 at shut, 1 at fully open."""
        u = float(np.clip(u, 0.0, 100.0))
        return (u / 100.0) ** self.p.choke_exp

    def _residual(self, q: float, u: float) -> float:
        """g(Q) = choke-passing flow at this Q  -  Q.   Strictly decreasing."""
        dp = self._whp_of_q(q) - self._flp_of_q(q)
        dp = max(dp, 0.0)
        return self.p.cv * self._choke_char(u) * np.sqrt(dp) - q

    def steady_state(self, u: float) -> Dict[str, float]:
        """
        Solve the coupled steady state for a given choke opening.

        Returns the noise-free equilibrium {Q, WHP, FLP, BHP, WHT, AP}.
        Uses bisection on the monotone residual g(Q); guaranteed to converge,
        so no NaN can ever leave this function.
        """
        u = float(np.clip(u, 0.0, 100.0))

        if self._choke_char(u) <= 0.0:      # fully shut -> no flow at all
            q = 0.0
        else:
            # Upper bracket: the rate at which the choke differential pressure
            # collapses to zero (no more driving force).  g(q_hi) = -q_hi < 0.
            lo, hi = 0.0, self._q_at_zero_dp()
            if self._residual(lo, u) <= 0.0:
                q = 0.0
            else:
                for _ in range(200):        # bisection: ~1e-13 relative in 200
                    mid = 0.5 * (lo + hi)
                    if self._residual(mid, u) > 0.0:
                        lo = mid
                    else:
                        hi = mid
                q = 0.5 * (lo + hi)

        return {
            "Q": q,
            "WHP": self._whp_of_q(q),
            "FLP": self._flp_of_q(q),
            "BHP": self._bhp_of_q(q),
            "WHT": self.p.wht_base + self.p.wht_gain * q,
            "AP": self.p.annulus_pressure,
        }

    def _q_at_zero_dp(self) -> float:
        """
        Largest physically meaningful rate: the Q at which WHP - FLP = 0.
        Solves  a*Q^2 + b*Q - c = 0  from the tubing/IPR/flowline relations.
        """
        a = self.p.k_fric
        b = 1.0 / self.p.pi_index + self.p.k_flowline
        c = (
            self.p.p_res
            - self.p.tvd_ft * self.p.grad_psi_per_ft
            - self.p.flp_base
        )
        if c <= 0.0:                         # well cannot flow at all
            return 0.0
        return (-b + np.sqrt(b * b + 4.0 * a * c)) / (2.0 * a)

    # ------------------------------------------------------------------
    # Dynamics
    # ------------------------------------------------------------------
    def _lag(self, current: float, target: float, tau: float) -> float:
        """Exact discretisation of a first-order lag over one interval."""
        alpha = 1.0 - np.exp(-self.ts / tau)
        return current + alpha * (target - current)

    # ------------------------------------------------------------------
    # Public API  (this is the entire contract the controller relies on)
    # ------------------------------------------------------------------
    def step(self, choke_position: float) -> Tuple[float, float, float, float]:
        """
        Advance the well by one control interval.

        Parameters
        ----------
        choke_position : float
            Commanded choke opening [%], clipped internally to 0-100.

        Returns
        -------
        (Q, WHP, FLP, BHP) : noisy measurements after this interval.
        """
        u = float(np.clip(choke_position, 0.0, 100.0))
        ss = self.steady_state(u)

        # First-order lag on every state.
        self._x["Q"] = self._lag(self._x["Q"], ss["Q"], self.p.tau_q)
        self._x["WHP"] = self._lag(self._x["WHP"], ss["WHP"], self.p.tau_whp)
        self._x["FLP"] = self._lag(self._x["FLP"], ss["FLP"], self.p.tau_flp)
        self._x["BHP"] = self._lag(self._x["BHP"], ss["BHP"], self.p.tau_bhp)
        self._x["WHT"] = self._lag(self._x["WHT"], ss["WHT"], self.p.tau_wht)
        self._x["AP"] = ss["AP"]

        self.t += self.ts
        self.u = u

        meas = self._measure()
        self._log(meas)
        return meas["Q"], meas["WHP"], meas["FLP"], meas["BHP"]

    def _measure(self) -> Dict[str, float]:
        """Apply sensor noise and physical floors to the internal state."""
        n = self._rng.normal
        p = self.p
        if self.noise_on:
            m = {
                "Q": self._x["Q"] + n(0.0, p.noise_q),
                "WHP": self._x["WHP"] + n(0.0, p.noise_whp),
                "FLP": self._x["FLP"] + n(0.0, p.noise_flp),
                "BHP": self._x["BHP"] + n(0.0, p.noise_bhp),
                "WHT": self._x["WHT"] + n(0.0, p.noise_wht),
                "AP": self._x["AP"] + n(0.0, p.noise_ap),
            }
        else:
            m = dict(self._x)
        m["Q"] = max(m["Q"], 0.0)            # a naturally flowing well cannot backflow
        return m

    def reset(self) -> Tuple[float, float, float, float]:
        """
        Return the well to shut-in conditions (choke closed, no flow, pressures
        equalised to reservoir) and clear the history log.
        """
        self._rng = np.random.default_rng(self._seed)
        ss = self.steady_state(0.0)
        self._x = dict(ss)
        self.t = 0.0
        self.u = 0.0
        self.history: List[Dict[str, float]] = []
        meas = self._measure()
        self._log(meas)
        return meas["Q"], meas["WHP"], meas["FLP"], meas["BHP"]

    # ------------------------------------------------------------------
    # History logging
    # ------------------------------------------------------------------
    def _log(self, meas: Dict[str, float]) -> None:
        self.history.append(
            {
                "time_h": self.t,
                "choke_pct": self.u,
                "Q": meas["Q"],
                "WHP": meas["WHP"],
                "FLP": meas["FLP"],
                "BHP": meas["BHP"],
                "WHT": meas["WHT"],
                "AP": meas["AP"],
                # Noise-free internal state, for analysis only.  The controller
                # never reads these columns.
                "Q_true": self._x["Q"],
                "WHP_true": self._x["WHP"],
                "FLP_true": self._x["FLP"],
                "BHP_true": self._x["BHP"],
            }
        )

    def to_dataframe(self) -> pd.DataFrame:
        """Full run history as a tidy DataFrame."""
        return pd.DataFrame(self.history)

    # ------------------------------------------------------------------
    # Analysis helpers (NOT used by the controller)
    # ------------------------------------------------------------------
    def steady_state_curve(self, u_grid=None) -> pd.DataFrame:
        """Noise-free steady-state operating curve, for plots and analysis."""
        if u_grid is None:
            u_grid = np.linspace(0.0, 100.0, 201)
        rows = [{"choke_pct": u, **self.steady_state(u)} for u in u_grid]
        return pd.DataFrame(rows)

    def max_safe_rate(self, limits, resolution: float = 0.01) -> Tuple[float, float]:
        """
        Ground-truth maximum steady-state rate that keeps every pressure inside
        `limits`, and the choke opening that achieves it.

        `resolution` is the choke-position step in percent (default 0.01 %).

        Used ONLY to check the controller's answer in Scenario C - the
        controller itself never calls this.
        """
        best_q, best_u = 0.0, 0.0
        for u in np.arange(0.0, 100.0 + resolution, resolution):
            ss = self.steady_state(u)
            ok = (
                limits.whp_min <= ss["WHP"] <= limits.whp_max
                and limits.flp_min <= ss["FLP"] <= limits.flp_max
                and limits.bhp_min <= ss["BHP"] <= limits.bhp_max
            )
            if ok and ss["Q"] > best_q:
                best_q, best_u = ss["Q"], u
        return best_q, best_u


if __name__ == "__main__":  # quick smoke test / sanity print
    from config import LIMITS

    sim = WellSimulator(noise=False)
    print(f"{'u [%]':>7} {'Q [bbl/hr]':>11} {'WHP':>8} {'FLP':>8} {'BHP':>8}")
    for u in [0, 10, 20, 30, 40, 50, 60, 70, 80, 90, 100]:
        ss = sim.steady_state(u)
        print(
            f"{u:7.0f} {ss['Q']:11.1f} {ss['WHP']:8.1f} "
            f"{ss['FLP']:8.1f} {ss['BHP']:8.1f}"
        )
    q_max, u_max = sim.max_safe_rate(LIMITS)
    print(f"\nMaximum SAFE steady-state rate: {q_max:.1f} bbl/hr at u = {u_max:.1f} %")
