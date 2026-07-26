"""
04_run_scenarios.py
====================
Runs the three required demonstration scenarios (A: Startup to Target,
B: Target Tracking, C: Infeasible Target) closed-loop, using the fitted
`WellModel` inside the brute-force `ChokeMPC` controller acting on the noisy
`WellSimulator` plant.

For each scenario this script produces:
    data/scenario_{X}_log.csv          - full time series log
    data/scenario_{X}_decisions.json   - per-step MPC reasoning (for the dashboard)
    figures/scenario_{X}.png           - 6-panel results figure
and prints an explicit PASS/FAIL constraint-safety audit.  `run_all.py`
propagates a non-zero exit code if any scenario fails its audit.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

from config import DATA_DIR, FIG_DIR, LIMITS, CONTROLLER, SEED, SCENARIOS, TS_HOURS
from well_simulator import WellSimulator
from model import WellModel, OUTPUTS
from controller import ChokeMPC
from plotting import (
    COLOR_CHOKE, COLOR_Q, COLOR_TARGET, COLOR_WHP, COLOR_FLP, COLOR_BHP,
    style_axis, shade_safe_band, ramp_envelope, savefig,
)


def target_at(targets, t):
    """Piecewise-constant target schedule: targets = [(start_h, value), ...]."""
    val = targets[0][1]
    for start_h, v in targets:
        if t >= start_h:
            val = v
    return val


def run_scenario(key: str, model: WellModel) -> tuple[pd.DataFrame, list, dict]:
    spec = SCENARIOS[key]
    # NOTE: use a fixed, explicit per-scenario offset rather than hash(key).
    # Python randomises string hashing per process (PYTHONHASHSEED), so
    # hash(key) would silently give a different noise realisation on every
    # run and the "reproducible with a fixed seed" guarantee would be false.
    seed_offset = {"A": 1, "B": 2, "C": 3}[key]
    sim = WellSimulator(seed=SEED + seed_offset, noise=True)
    sim.reset()
    controller = ChokeMPC(model=model)

    u = spec["u_initial"]
    rows = []
    decisions = []

    # Prime the plant to the initial choke position's own dynamics naturally
    # by simply starting the loop; step 0 uses the reset (shut-in) measurement.
    meas = {"Q": 0.0, "WHP": sim.history[-1]["WHP"], "FLP": sim.history[-1]["FLP"],
            "BHP": sim.history[-1]["BHP"]}

    n_steps = int(spec["duration_h"] / TS_HOURS)
    for k in range(n_steps):
        t = k * TS_HOURS
        target = target_at(spec["targets"], t)

        decision = controller.step(meas, u, target)
        u = decision.u_selected

        Q, WHP, FLP, BHP = sim.step(u)
        meas = {"Q": Q, "WHP": WHP, "FLP": FLP, "BHP": BHP}

        n_feas = sum(c.feasible for c in decision.candidates)
        rows.append(
            {
                "time_h": t + TS_HOURS,
                "target_Q": target,
                "choke_pct": u,
                "Q": Q, "WHP": WHP, "FLP": FLP, "BHP": BHP,
                # Informational only - monitored as part of a complete
                # production operating envelope, but NOT active constraints in
                # this challenge and never used by the controller.
                "WHT": sim.history[-1]["WHT"],
                "AP": sim.history[-1]["AP"],
                "n_candidates": len(decision.candidates),
                "n_feasible": n_feas,
                "all_infeasible": decision.all_infeasible,
            }
        )

        chosen = decision.candidates[decision.selected_index]
        decisions.append(
            {
                "t": t,
                "u_prev": decision.u_previous,
                "u_selected": decision.u_selected,
                "target_Q": target,
                "all_infeasible": decision.all_infeasible,
                "selected_index": decision.selected_index,
                "candidates": [
                    {
                        "u": round(c.u, 2),
                        "du": round(c.du, 2),
                        "feasible": c.feasible,
                        "reason": c.reject_reason,
                        "q_end": round(c.predicted_Q_end, 1),
                        "cost": round(c.cost, 2),
                    }
                    for c in decision.candidates
                ],
                "selected_trajectory": {
                    k2: [round(float(v), 1) for v in chosen.predicted_trajectory[k2]]
                    for k2 in OUTPUTS
                },
            }
        )

    df = pd.DataFrame(rows)
    return df, decisions, spec


def audit(df: pd.DataFrame, key: str) -> bool:
    """Explicit PASS/FAIL constraint-safety check against the TRUE hard limits
    (not the controller's internal safety-margin limits)."""
    L = LIMITS
    checks = {
        "WHP": (df["WHP"] >= L.whp_min).all() and (df["WHP"] <= L.whp_max).all(),
        "FLP": (df["FLP"] >= L.flp_min).all() and (df["FLP"] <= L.flp_max).all(),
        "BHP": (df["BHP"] >= L.bhp_min).all() and (df["BHP"] <= L.bhp_max).all(),
        "ramp": (df["choke_pct"].diff().abs().dropna() <= CONTROLLER.max_move + 1e-6).all(),
        "u_range": (df["choke_pct"] >= 0).all() and (df["choke_pct"] <= 100).all(),
        "no_nan": not df.isna().any().any(),
    }
    passed = all(checks.values())
    marks = " ".join(f"{k} {'OK' if v else 'FAIL'}" for k, v in checks.items())
    print(f"[Scenario {key}] {marks} -> {'PASS' if passed else 'FAIL'}")
    return passed


def plot_scenario(df: pd.DataFrame, spec: dict, key: str, path: Path) -> None:
    fig, axes = plt.subplots(7, 1, figsize=(11, 17.5), sharex=True)
    t = df["time_h"]
    L = LIMITS

    axes[0].plot(t, df["target_Q"], color=COLOR_TARGET, lw=1.6, ls="--", label="Target")
    axes[0].plot(t, df["Q"], color=COLOR_Q, lw=2.0, label="Actual")
    style_axis(axes[0], title=f"{spec['name']}: Oil Flow Rate", ylabel="Q [bbl/hr]")
    axes[0].legend(loc="best", fontsize=8)

    axes[1].plot(t, df["WHP"], color=COLOR_WHP, lw=1.8)
    shade_safe_band(axes[1], L.whp_min, L.whp_max, CONTROLLER.margin_whp, CONTROLLER.margin_whp)
    style_axis(axes[1], title="Wellhead Pressure", ylabel="WHP [psi]")

    axes[2].plot(t, df["FLP"], color=COLOR_FLP, lw=1.8)
    shade_safe_band(axes[2], L.flp_min, L.flp_max, CONTROLLER.margin_flp, CONTROLLER.margin_flp)
    style_axis(axes[2], title="Flowline Pressure", ylabel="FLP [psi]")

    axes[3].plot(t, df["BHP"], color=COLOR_BHP, lw=1.8)
    shade_safe_band(axes[3], L.bhp_min, L.bhp_max, CONTROLLER.margin_bhp, CONTROLLER.margin_bhp)
    style_axis(axes[3], title="Bottom Hole Pressure", ylabel="BHP [psi]")

    axes[4].plot(t, df["choke_pct"], color=COLOR_CHOKE, lw=2.0, drawstyle="steps-post")
    axes[4].set_ylim(-5, 105)
    style_axis(axes[4], title="Choke Position (5%/step ramp limit)", ylabel="Choke [%]")

    axes[5].plot(t, df["n_feasible"], color="#7c3aed", lw=1.6)
    axes[5].axhline(0, color="#dc2626", lw=1, ls=":")
    style_axis(axes[5], title="Feasible Candidates per Step (of 21)",
               ylabel="# feasible")

    # Informational variables (WHT, AP): monitored as part of a complete
    # operating envelope per the problem statement, but not active constraints
    # and never used by the controller.
    ax6 = axes[6]
    ax6.plot(t, df["WHT"], color="#c2410c", lw=1.6, label="WHT [degF]")
    ax6.set_ylabel("WHT [degF]")
    ax6b = ax6.twinx()
    ax6b.plot(t, df["AP"], color="#0891b2", lw=1.4, ls="--", label="AP [psi]")
    ax6b.set_ylabel("AP [psi]")
    lines = ax6.get_lines() + ax6b.get_lines()
    ax6.legend(lines, [l.get_label() for l in lines], loc="best", fontsize=8)
    style_axis(ax6, title="Informational only - not active constraints (WHT, AP)",
               xlabel="Time [h]")

    fig.tight_layout()
    savefig(fig, path)
    print(f"  wrote {path}")


def plot_compact_summary(logs: dict) -> None:
    """A single landscape figure with all three scenarios side by side.

    The per-scenario 7-panel figures are portrait and far too tall to embed in
    a slide; this is the wide, at-a-glance version for the deck and the report
    summary.  Rows: oil rate vs target, BHP against its limit, choke position.
    """
    fig, axes = plt.subplots(3, 3, figsize=(15, 7.2), sharex="col")
    L = LIMITS
    for col, key in enumerate(("A", "B", "C")):
        df = logs[key]
        t = df["time_h"]
        spec = SCENARIOS[key]

        ax = axes[0][col]
        ax.plot(t, df["target_Q"], color=COLOR_TARGET, lw=1.6, ls="--", label="Target")
        ax.plot(t, df["Q"], color=COLOR_Q, lw=2.0, label="Actual")
        style_axis(ax, title=spec["name"], ylabel="Q [bbl/hr]" if col == 0 else None)
        ax.legend(loc="lower right", fontsize=7)

        ax = axes[1][col]
        ax.plot(t, df["BHP"], color=COLOR_BHP, lw=1.8)
        shade_safe_band(ax, L.bhp_min, L.bhp_max, CONTROLLER.margin_bhp, CONTROLLER.margin_bhp)
        ax.set_ylim(L.bhp_min - 60, max(df["BHP"].max() + 60, L.bhp_min + 200))
        style_axis(ax, title=f"BHP  (min {df['BHP'].min():.0f} psi, limit {L.bhp_min:.0f})",
                   ylabel="BHP [psi]" if col == 0 else None)

        ax = axes[2][col]
        ax.plot(t, df["choke_pct"], color=COLOR_CHOKE, lw=2.0, drawstyle="steps-post")
        ax.set_ylim(-5, 105)
        style_axis(ax, title="Choke position", xlabel="Time [h]",
                   ylabel="Choke [%]" if col == 0 else None)

    fig.suptitle("Scenario results - target tracking and constraint compliance",
                 fontweight="bold")
    fig.tight_layout()
    savefig(fig, FIG_DIR / "scenarios_compact.png")
    print(f"  wrote {FIG_DIR / 'scenarios_compact.png'}")


def main():
    model = WellModel.load(DATA_DIR / "fitted_model.json")

    all_pass = True
    summary = {}
    logs = {}
    for key in ("A", "B", "C"):
        print(f"\nRunning {SCENARIOS[key]['name']} ...")
        df, decisions, spec = run_scenario(key, model)

        df.to_csv(DATA_DIR / f"scenario_{key}_log.csv", index=False)
        (DATA_DIR / f"scenario_{key}_decisions.json").write_text(json.dumps(decisions))

        logs[key] = df
        ok = audit(df, key)
        all_pass = all_pass and ok

        plot_scenario(df, spec, key, FIG_DIR / f"scenario_{key}.png")

        summary[key] = {
            "name": spec["name"],
            "pass": ok,
            # A single last sample carries a full dose of sensor noise, so the
            # settled mean over the final 20 intervals is the honest number to
            # quote for tracking performance.
            "final_Q": float(df["Q"].iloc[-1]),
            "settled_Q": float(df["Q"].tail(20).mean()),
            "settled_Q_std": float(df["Q"].tail(20).std()),
            "final_target": float(df["target_Q"].iloc[-1]),
            "final_choke": float(df["choke_pct"].iloc[-1]),
            "min_whp": float(df["WHP"].min()), "max_whp": float(df["WHP"].max()),
            "min_flp": float(df["FLP"].min()), "max_flp": float(df["FLP"].max()),
            "min_bhp": float(df["BHP"].min()), "max_bhp": float(df["BHP"].max()),
        }

    plot_compact_summary(logs)

    (DATA_DIR / "scenario_summary.json").write_text(json.dumps(summary, indent=2))
    print("\n" + "=" * 60)
    print("ALL SCENARIOS:", "PASS" if all_pass else "FAIL")
    print("=" * 60)

    if not all_pass:
        sys.exit(1)


if __name__ == "__main__":
    main()
