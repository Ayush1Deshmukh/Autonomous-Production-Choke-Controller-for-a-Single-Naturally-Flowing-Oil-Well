"""
06_robustness_study.py
=======================
Monte-Carlo robustness study.

Passing the safety audit on ONE random seed proves very little - it could be
luck.  This script re-runs all three scenarios across many independent sensor-
noise realisations and asserts that the operating envelope is respected in
EVERY run, reporting the worst-case margin actually observed.

It also answers the question a reviewer should ask about the safety margins:
"how much production are they costing you?"  The study reports the achieved
rate against the ground-truth maximum safe rate computed directly from the
plant's own steady-state curve.

Outputs
-------
    data/robustness_summary.json
    figures/robustness.png     (margin distributions + achieved-rate spread)
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

from config import DATA_DIR, FIG_DIR, LIMITS, CONTROLLER, SCENARIOS, TS_HOURS
from well_simulator import WellSimulator
from model import WellModel
from controller import ChokeMPC
from plotting import COLOR_WHP, COLOR_FLP, COLOR_BHP, COLOR_Q, style_axis, savefig

N_RUNS = 100          # independent noise realisations per scenario


def target_at(targets, t):
    val = targets[0][1]
    for start_h, v in targets:
        if t >= start_h:
            val = v
    return val


def run_once(key: str, model: WellModel, seed: int) -> dict:
    """One closed-loop run of a scenario with a given noise seed."""
    spec = SCENARIOS[key]
    sim = WellSimulator(seed=seed, noise=True)
    sim.reset()
    controller = ChokeMPC(model=model)

    u = spec["u_initial"]
    meas = {
        "Q": 0.0,
        "WHP": sim.history[-1]["WHP"],
        "FLP": sim.history[-1]["FLP"],
        "BHP": sim.history[-1]["BHP"],
    }

    rows = []
    for k in range(int(spec["duration_h"] / TS_HOURS)):
        t = k * TS_HOURS
        target = target_at(spec["targets"], t)
        u = controller.step(meas, u, target).u_selected
        Q, WHP, FLP, BHP = sim.step(u)
        meas = {"Q": Q, "WHP": WHP, "FLP": FLP, "BHP": BHP}
        rows.append({"t": t + TS_HOURS, "target": target, "u": u,
                     "Q": Q, "WHP": WHP, "FLP": FLP, "BHP": BHP})

    df = pd.DataFrame(rows)
    L = LIMITS
    # Signed distance to the nearest limit (negative == violated)
    margins = {
        "WHP": float(np.minimum(df["WHP"] - L.whp_min, L.whp_max - df["WHP"]).min()),
        "FLP": float(np.minimum(df["FLP"] - L.flp_min, L.flp_max - df["FLP"]).min()),
        "BHP": float(np.minimum(df["BHP"] - L.bhp_min, L.bhp_max - df["BHP"]).min()),
    }
    max_move = float(df["u"].diff().abs().max())
    tail = df.tail(20)

    return {
        "seed": seed,
        "margins": margins,
        "worst_margin": min(margins.values()),
        "violated": min(margins.values()) < 0,
        "max_move": max_move,
        "ramp_ok": max_move <= CONTROLLER.max_move + 1e-6,
        "final_Q": float(tail["Q"].mean()),
        "final_target": float(df["target"].iloc[-1]),
        "choke_std_tail": float(tail["u"].std()),
        "has_nan": bool(df.isna().any().any()),
    }


def main():
    model = WellModel.load(DATA_DIR / "fitted_model.json")

    # Ground truth: best steady rate that keeps every pressure inside limits.
    q_max_safe, u_max_safe = WellSimulator(noise=False).max_safe_rate(LIMITS)

    results = {}
    all_pass = True

    for key in ("A", "B", "C"):
        runs = [run_once(key, model, seed=1000 + i) for i in range(N_RUNS)]
        n_viol = sum(r["violated"] for r in runs)
        n_ramp_bad = sum(not r["ramp_ok"] for r in runs)
        n_nan = sum(r["has_nan"] for r in runs)
        worst = min(r["worst_margin"] for r in runs)
        finals = np.array([r["final_Q"] for r in runs])
        ok = (n_viol == 0) and (n_ramp_bad == 0) and (n_nan == 0)
        all_pass = all_pass and ok

        results[key] = {
            "name": SCENARIOS[key]["name"],
            "n_runs": N_RUNS,
            "violations": n_viol,
            "ramp_breaches": n_ramp_bad,
            "nan_runs": n_nan,
            "worst_margin_psi": worst,
            "final_Q_mean": float(finals.mean()),
            "final_Q_std": float(finals.std()),
            "final_Q_min": float(finals.min()),
            "final_Q_max": float(finals.max()),
            "target": runs[0]["final_target"],
            "choke_std_tail_mean": float(np.mean([r["choke_std_tail"] for r in runs])),
            "pass": ok,
            "_runs": runs,
        }
        print(
            f"[{key}] {N_RUNS} runs | violations={n_viol} ramp_breaches={n_ramp_bad} "
            f"nan={n_nan} | worst margin={worst:.1f} psi | "
            f"final Q={finals.mean():.1f}+/-{finals.std():.1f} bbl/hr -> "
            f"{'PASS' if ok else 'FAIL'}"
        )

    # Production cost of the safety margins, measured against ground truth.
    c = results["C"]
    give_away = q_max_safe - c["final_Q_mean"]
    print(
        f"\nGround-truth max safe rate: {q_max_safe:.1f} bbl/hr at u={u_max_safe:.1f} %"
        f"\nScenario C achieved:        {c['final_Q_mean']:.1f} bbl/hr"
        f"\nSafety margins cost:        {give_away:.1f} bbl/hr "
        f"({100 * give_away / q_max_safe:.1f} % of achievable rate)"
    )

    # ---------------- figure ----------------
    fig, axes = plt.subplots(1, 3, figsize=(13, 3.8))
    colors = {"WHP": COLOR_WHP, "FLP": COLOR_FLP, "BHP": COLOR_BHP}

    for ax, key in zip(axes[:2], ("A", "C")):
        runs = results[key]["_runs"]
        for var in ("WHP", "FLP", "BHP"):
            ax.hist([r["margins"][var] for r in runs], bins=18, alpha=0.65,
                    color=colors[var], label=var)
        ax.axvline(0, color="#dc2626", lw=1.8, ls="--", label="limit")
        style_axis(ax, title=f"Scenario {key}: worst margin per run",
                   xlabel="Distance to nearest limit [psi]", ylabel="runs")
        ax.legend(fontsize=7)

    ax = axes[2]
    for key, col in zip(("A", "B", "C"), (COLOR_Q, "#7c3aed", COLOR_BHP)):
        finals = [r["final_Q"] for r in results[key]["_runs"]]
        ax.hist(finals, bins=16, alpha=0.65, color=col, label=f"{key} (target {results[key]['target']:.0f})")
    ax.axvline(q_max_safe, color="#111827", lw=1.6, ls=":", label=f"max safe {q_max_safe:.0f}")
    style_axis(ax, title="Settled rate across 100 noise seeds",
               xlabel="Final oil rate [bbl/hr]", ylabel="runs")
    ax.legend(fontsize=7)

    fig.suptitle(f"Monte-Carlo robustness: {N_RUNS} seeds x 3 scenarios", fontweight="bold")
    fig.tight_layout()
    savefig(fig, FIG_DIR / "robustness.png")
    print(f"\n  wrote {FIG_DIR / 'robustness.png'}")

    for v in results.values():
        v.pop("_runs")
    results["_meta"] = {
        "n_runs_per_scenario": N_RUNS,
        "q_max_safe_ground_truth": q_max_safe,
        "u_max_safe_ground_truth": u_max_safe,
        "margin_cost_bblhr": give_away,
        "all_pass": all_pass,
    }
    (DATA_DIR / "robustness_summary.json").write_text(json.dumps(results, indent=2))
    print(f"  wrote {DATA_DIR / 'robustness_summary.json'}")

    print("\n" + "=" * 62)
    print(f"ROBUSTNESS ({3 * N_RUNS} closed-loop runs):", "PASS" if all_pass else "FAIL")
    print("=" * 62)
    if not all_pass:
        sys.exit(1)


if __name__ == "__main__":
    main()
