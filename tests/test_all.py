"""
test_all.py
===========
Dependency-free test suite (plain asserts, no pytest required) covering the
simulator, the identified model and the controller.

Run directly:      python tests/test_all.py
Also run as part of:  python run_all.py

The most important test here is `test_controller_against_foreign_plant`, which
drives the controller against a completely different plant that merely
satisfies the `WellSimulator` Protocol.  That is what makes the claim "an
official simulator can be swapped in with zero controller changes" verifiable
rather than just asserted in a README.
"""

from __future__ import annotations

import sys
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import numpy as np

from config import CONTROLLER, DATA_DIR, LIMITS, PLANT, TS_HOURS
from controller import ChokeMPC
from model import OUTPUTS, WellModel
from simulator_interface import WellSimulator as WellSimulatorProtocol
from well_simulator import WellSimulator

FAILURES = []


def check(cond, msg):
    if not cond:
        raise AssertionError(msg)


# ---------------------------------------------------------------- simulator
def test_simulator_satisfies_protocol():
    sim = WellSimulator()
    check(isinstance(sim, WellSimulatorProtocol),
          "WellSimulator does not satisfy the WellSimulator Protocol")


def test_reset_is_deterministic():
    a = WellSimulator(seed=7)
    b = WellSimulator(seed=7)
    for u in [10, 30, 55, 20]:
        for _ in range(3):
            check(np.allclose(a.step(u), b.step(u)),
                  "two simulators with the same seed diverged")
    a.reset()
    b.reset()
    check(np.allclose(a.step(42), b.step(42)), "reset() did not restore the RNG")


def test_shut_in_gives_no_flow():
    sim = WellSimulator(noise=False)
    sim.reset()
    for _ in range(10):
        Q, WHP, FLP, BHP = sim.step(0.0)
    check(abs(Q) < 1e-9, f"shut-in well still flowing at {Q}")
    check(abs(BHP - PLANT.p_res) < 1e-6, "shut-in BHP should equal reservoir pressure")


def test_flow_increases_monotonically_with_choke():
    sim = WellSimulator(noise=False)
    qs = [sim.steady_state(u)["Q"] for u in range(0, 101, 5)]
    for a, b in zip(qs, qs[1:]):
        check(b >= a - 1e-9, "steady-state Q is not monotonically increasing in u")


def test_pressures_move_the_right_way():
    """Opening the choke must raise Q and FLP, and lower WHP and BHP."""
    sim = WellSimulator(noise=False)
    lo, hi = sim.steady_state(30.0), sim.steady_state(60.0)
    check(hi["Q"] > lo["Q"], "opening the choke did not increase Q")
    check(hi["FLP"] > lo["FLP"], "opening the choke did not raise FLP")
    check(hi["WHP"] < lo["WHP"], "opening the choke did not lower WHP")
    check(hi["BHP"] < lo["BHP"], "opening the choke did not lower BHP")


def test_choke_input_is_clipped_and_finite():
    sim = WellSimulator()
    for u in [-50, -1, 0, 50, 100, 101, 1e6, float("inf")]:
        out = sim.step(u)
        check(all(np.isfinite(v) for v in out), f"non-finite output for u={u}")
        check(out[0] >= 0.0, f"negative flow for u={u}")


def test_no_nan_under_long_random_drive():
    rng = np.random.default_rng(0)
    sim = WellSimulator(seed=3)
    sim.reset()
    for _ in range(500):
        out = sim.step(rng.uniform(-10, 110))
        check(all(np.isfinite(v) for v in out), "NaN/inf appeared during random drive")


def test_first_order_lag_is_present():
    """A step change must NOT be reached instantly - there are real dynamics."""
    sim = WellSimulator(noise=False)
    sim.reset()
    ss = sim.steady_state(50.0)
    Q1, *_ = sim.step(50.0)
    check(Q1 < 0.95 * ss["Q"], "output reached steady state in a single step (no lag)")


# -------------------------------------------------------------------- model
def test_model_roundtrips_through_disk():
    m = WellModel.load(DATA_DIR / "fitted_model.json")
    for k in OUTPUTS:
        check(m.outputs[k].tau > 0, f"non-positive tau for {k}")
        check(len(m.outputs[k].u_knots) == len(m.outputs[k].y_knots),
              f"knot arrays disagree for {k}")


def test_model_prediction_shape_and_finiteness():
    m = WellModel.load(DATA_DIR / "fitted_model.json")
    y0 = {"Q": 100.0, "WHP": 500.0, "FLP": 220.0, "BHP": 2100.0}
    traj = m.predict(y0, [40.0] * 8)
    for k in OUTPUTS:
        check(len(traj[k]) == 8, f"trajectory length wrong for {k}")
        check(np.all(np.isfinite(traj[k])), f"non-finite prediction for {k}")
    check(np.all(traj["Q"] >= 0.0), "model predicted negative flow")


def test_model_extrapolation_is_clamped():
    m = WellModel.load(DATA_DIR / "fitted_model.json")
    lo = float(m.outputs["Q"].y_ss(-40))
    hi = float(m.outputs["Q"].y_ss(400))
    check(np.isfinite(lo) and np.isfinite(hi), "extrapolation produced non-finite values")
    check(m.outputs["Q"].is_extrapolating(400), "is_extrapolating failed to flag 400 %")


def test_model_tracks_plant_steady_state():
    """The identified steady-state curve must match the plant closely - this is
    what every constraint prediction rests on.

    Accuracy is required where it changes decisions, not uniformly:

      * u >= 55 %  - BHP is below 1960 psi here and closing on its 1900 psi
                     limit, so this is the band where a prediction error can
                     actually cause a violation.  Held to < 4 psi, well inside
                     the 15 psi safety margin.
      * 35-95 %    - normal operating band, BHP still 100+ psi clear.
      * full range - the curve is very steep and strongly convex below ~30 %,
                     but BHP there is 500+ psi clear of any limit, so a looser
                     bound is the honest requirement.
    """
    m = WellModel.load(DATA_DIR / "fitted_model.json")
    sim = WellSimulator(noise=False)

    def worst_over(lo, hi):
        return max(
            abs(float(m.outputs["BHP"].y_ss(u)) - sim.steady_state(u)["BHP"])
            for u in np.arange(lo, hi, 0.5)
        )

    constrained = worst_over(55, 95)
    check(constrained < 4.0,
          f"model/plant BHP error in the constrained band too large: {constrained:.1f} psi")
    operating = worst_over(35, 95)
    check(operating < 8.0,
          f"model/plant BHP error in the operating band too large: {operating:.1f} psi")
    overall = worst_over(15, 100)
    check(overall < 20.0,
          f"model/plant BHP error over the full range too large: {overall:.1f} psi")


# --------------------------------------------------------------- controller
def _fresh_controller():
    return ChokeMPC(model=WellModel.load(DATA_DIR / "fitted_model.json"))


def test_controller_respects_ramp_limit():
    c = _fresh_controller()
    meas = {"Q": 100.0, "WHP": 500.0, "FLP": 220.0, "BHP": 2100.0}
    for u_now in [0.0, 12.5, 50.0, 97.0, 100.0]:
        for target in [0.0, 50.0, 200.0, 1e4]:
            d = c.step(meas, u_now, target)
            check(abs(d.u_selected - u_now) <= CONTROLLER.max_move + 1e-9,
                  f"ramp limit breached: {u_now} -> {d.u_selected}")
            check(0.0 <= d.u_selected <= 100.0,
                  f"choke out of range: {d.u_selected}")


def test_controller_never_selects_a_predicted_violation():
    """If any candidate is feasible, the selected one must be feasible."""
    c = _fresh_controller()
    for bhp in [2900.0, 2200.0, 1960.0, 1930.0]:
        meas = {"Q": 120.0, "WHP": 480.0, "FLP": 235.0, "BHP": bhp}
        d = c.step(meas, 55.0, 250.0)
        chosen = d.candidates[d.selected_index]
        if any(x.feasible for x in d.candidates):
            check(chosen.feasible,
                  f"selected an infeasible candidate at BHP={bhp} despite safe options")


def test_controller_output_is_always_valid_even_when_all_infeasible():
    """Deep inside a violation every candidate is unsafe; the controller must
    still return a usable number and must not lurch."""
    c = _fresh_controller()
    meas = {"Q": 200.0, "WHP": 300.0, "FLP": 275.0, "BHP": 1500.0}
    d = c.step(meas, 80.0, 250.0)
    check(np.isfinite(d.u_selected), "fallback produced a non-finite choke position")
    check(0.0 <= d.u_selected <= 100.0, "fallback produced an out-of-range choke position")
    check(abs(d.u_selected - 80.0) <= CONTROLLER.max_move + 1e-9,
          "fallback breached the ramp limit")


def test_controller_is_deterministic():
    a, b = _fresh_controller(), _fresh_controller()
    meas = {"Q": 90.0, "WHP": 600.0, "FLP": 215.0, "BHP": 2250.0}
    for _ in range(5):
        ua = a.step(meas, 40.0, 150.0).u_selected
        ub = b.step(meas, 40.0, 150.0).u_selected
        check(ua == ub, "controller is not deterministic")


def test_controller_holds_still_at_target():
    """The deadband must stop the choke chattering once the target is met."""
    model = WellModel.load(DATA_DIR / "fitted_model.json")
    sim = WellSimulator(seed=11, noise=True)
    sim.reset()
    c = ChokeMPC(model=model)
    u = 0.0
    meas = {"Q": 0.0, "WHP": sim.history[-1]["WHP"],
            "FLP": sim.history[-1]["FLP"], "BHP": sim.history[-1]["BHP"]}
    us = []
    for _ in range(60):
        u = c.step(meas, u, 120.0).u_selected
        Q, W, F, B = sim.step(u)
        meas = {"Q": Q, "WHP": W, "FLP": F, "BHP": B}
        us.append(u)
    tail = np.array(us[-20:])
    check(tail.std() < 0.25, f"choke still chattering at target: std={tail.std():.3f} %")
    check(abs(np.mean(tail) - us[-1]) < 0.5, "choke not settled")


class _ForeignPlant:
    """A deliberately DIFFERENT well that satisfies the same Protocol:
    different pressures, different gains, different dynamics, different units
    of nonlinearity.  The controller has never seen it and has no access to
    its internals - it only calls step()/reset()."""

    def __init__(self):
        self.reset()

    def reset(self):
        self.q, self.whp, self.flp, self.bhp = 0.0, 1200.0, 150.0, 2600.0
        return self.q, self.whp, self.flp, self.bhp

    def step(self, u):
        u = float(np.clip(u, 0, 100))
        q_ss = 190.0 * (u / 100.0) ** 0.75          # different characteristic
        bhp_ss = 2600.0 - 5.2 * q_ss
        whp_ss = bhp_ss - 1100.0 - 0.004 * q_ss ** 2
        flp_ss = 150.0 + 0.55 * q_ss
        a = 0.45                                     # different time constant
        self.q += a * (q_ss - self.q)
        self.whp += a * (whp_ss - self.whp)
        self.flp += a * (flp_ss - self.flp)
        self.bhp += a * (bhp_ss - self.bhp)
        return self.q, self.whp, self.flp, self.bhp


def test_controller_against_foreign_plant():
    """Swap-in proof: the controller runs, stays inside the ramp limit and
    produces finite, in-range moves on a plant it was never tuned for."""
    plant = _ForeignPlant()
    check(isinstance(plant, WellSimulatorProtocol),
          "the foreign plant does not satisfy the Protocol")
    c = _fresh_controller()
    Q, WHP, FLP, BHP = plant.reset()
    u = 0.0
    for _ in range(80):
        prev = u
        u = c.step({"Q": Q, "WHP": WHP, "FLP": FLP, "BHP": BHP}, u, 120.0).u_selected
        check(abs(u - prev) <= CONTROLLER.max_move + 1e-9, "ramp limit breached on foreign plant")
        check(0.0 <= u <= 100.0, "choke out of range on foreign plant")
        Q, WHP, FLP, BHP = plant.step(u)
        check(all(np.isfinite(v) for v in (Q, WHP, FLP, BHP)), "foreign plant produced NaN")


# ------------------------------------------------------------- scenario logs
def test_scenario_logs_respect_every_limit():
    import pandas as pd
    for key in ("A", "B", "C"):
        path = DATA_DIR / f"scenario_{key}_log.csv"
        if not path.exists():
            continue
        df = pd.read_csv(path)
        check(not df.isna().any().any(), f"NaN in scenario {key} log")
        check(df["WHP"].between(LIMITS.whp_min, LIMITS.whp_max).all(), f"WHP breach in {key}")
        check(df["FLP"].between(LIMITS.flp_min, LIMITS.flp_max).all(), f"FLP breach in {key}")
        check(df["BHP"].between(LIMITS.bhp_min, LIMITS.bhp_max).all(), f"BHP breach in {key}")
        check((df["choke_pct"].diff().abs().dropna() <= CONTROLLER.max_move + 1e-6).all(),
              f"ramp breach in {key}")


def main():
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    print(f"Running {len(tests)} tests\n" + "-" * 58)
    passed = 0
    for t in tests:
        try:
            t()
            print(f"  PASS  {t.__name__}")
            passed += 1
        except Exception as e:
            FAILURES.append((t.__name__, e))
            print(f"  FAIL  {t.__name__}: {e}")
            if not isinstance(e, AssertionError):
                traceback.print_exc()
    print("-" * 58)
    print(f"{passed}/{len(tests)} passed")
    if FAILURES:
        sys.exit(1)


if __name__ == "__main__":
    main()
