"""
01_reference_dataset_eda.py
============================
Exploratory analysis of the PROVIDED reference dataset
(`data/official_sample_dataset.csv`, the hackathon's
`Autonomous_Choke_Control_Simulated_Dataset.csv`).

Per the problem statement, this dataset is used for exactly one purpose:

    "The reference dataset is intended only to demonstrate simulator
     behavior. Students are expected to generate their own data using the
     simulator and develop their control-oriented models from these
     experiments."

So NOTHING in this project's model identification touches this file.  The
dynamic model in `03_identify_model.py` is fitted exclusively to our own
step-test experiments (`02_step_tests.py`), as instructed.  This script only:

    1. characterises the reference data (structure, steps, steady states)
    2. compares it against our physics-based stand-in simulator, honestly
       documenting where the two differ

Outputs
-------
    figures/reference_dataset.png       the provided data, as trends
    figures/reference_vs_standin.png    steady-state comparison
    data/reference_steady_states.csv    extracted steady-state operating points
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

from config import DATA_DIR, FIG_DIR
from well_simulator import WellSimulator
from plotting import (COLOR_Q, COLOR_WHP, COLOR_FLP, COLOR_BHP, COLOR_CHOKE,
                      style_axis, savefig)

REF_CSV = DATA_DIR / "official_sample_dataset.csv"


def load_reference() -> pd.DataFrame | None:
    if not REF_CSV.exists():
        print(f"  NOTE: {REF_CSV.name} not present - skipping reference EDA.")
        print("  (The rest of the pipeline does not depend on it.)")
        return None
    df = pd.read_csv(REF_CSV)
    df = df.rename(columns={
        "Time_hr": "time_h", "Choke_pct": "choke_pct", "OilRate_bbl_hr": "Q",
        "WHP_psi": "WHP", "FLP_psi": "FLP", "BHP_psi": "BHP",
    })
    return df


def steady_states(df: pd.DataFrame) -> pd.DataFrame:
    """Average the last few samples of each constant-choke hold."""
    df = df.copy()
    df["hold"] = (df["choke_pct"] != df["choke_pct"].shift()).cumsum()
    rows = []
    for _, seg in df.groupby("hold"):
        tail = seg.tail(5).mean(numeric_only=True)
        rows.append({"choke_pct": seg["choke_pct"].iloc[0], "n_samples": len(seg),
                     "Q": tail["Q"], "WHP": tail["WHP"],
                     "FLP": tail["FLP"], "BHP": tail["BHP"]})
    return pd.DataFrame(rows)


def plot_reference(df: pd.DataFrame) -> None:
    fig, axes = plt.subplots(5, 1, figsize=(11, 11), sharex=True)
    t = df["time_h"]
    axes[0].plot(t, df["choke_pct"], color=COLOR_CHOKE, lw=2, drawstyle="steps-post")
    style_axis(axes[0], title="Provided reference dataset - choke position", ylabel="Choke [%]")
    for ax, col, c, unit in [
        (axes[1], "Q", COLOR_Q, "bbl/hr"), (axes[2], "WHP", COLOR_WHP, "psi"),
        (axes[3], "FLP", COLOR_FLP, "psi"), (axes[4], "BHP", COLOR_BHP, "psi"),
    ]:
        ax.plot(t, df[col], color=c, lw=1.8)
        style_axis(ax, title=col, ylabel=f"{col} [{unit}]")
    axes[-1].set_xlabel("Time [h]")
    fig.suptitle("Reference dataset (illustrative only - NOT used for model identification)",
                 fontweight="bold")
    fig.tight_layout()
    savefig(fig, FIG_DIR / "reference_dataset.png")


def plot_comparison(ss: pd.DataFrame) -> None:
    """Overlay the reference steady states on our stand-in's own curves."""
    sim = WellSimulator(noise=False)
    u_grid = np.linspace(20, 75, 120)
    ours = pd.DataFrame([{"choke_pct": u, **sim.steady_state(u)} for u in u_grid])

    fig, axes = plt.subplots(1, 4, figsize=(15, 3.9))
    for ax, col, c, unit in [
        (axes[0], "Q", COLOR_Q, "bbl/hr"), (axes[1], "WHP", COLOR_WHP, "psi"),
        (axes[2], "FLP", COLOR_FLP, "psi"), (axes[3], "BHP", COLOR_BHP, "psi"),
    ]:
        ax.plot(ours["choke_pct"], ours[col], color=c, lw=2, label="our stand-in")
        ax.plot(ss["choke_pct"], ss[col], "o--", color="#111827", lw=1.4,
                ms=6, label="reference data")
        style_axis(ax, title=col, xlabel="Choke [%]", ylabel=f"{col} [{unit}]")
        ax.legend(fontsize=8)
    fig.suptitle("Steady-state behaviour: physics stand-in vs provided reference dataset",
                 fontweight="bold")
    fig.tight_layout()
    savefig(fig, FIG_DIR / "reference_vs_standin.png")


def main():
    df = load_reference()
    if df is None:
        return

    print(f"Reference dataset: {len(df)} rows, choke levels "
          f"{sorted(df['choke_pct'].unique().tolist())}")
    ss = steady_states(df)
    ss.to_csv(DATA_DIR / "reference_steady_states.csv", index=False)

    print("\nSteady-state operating points extracted from the reference data:")
    print(ss.round(1).to_string(index=False))

    # Characterise its gain, for comparison with our own step tests.
    ss_sorted = ss.sort_values("choke_pct")
    du = np.diff(ss_sorted["choke_pct"].values)
    dq = np.diff(ss_sorted["Q"].values)
    gains = dq / du
    print(f"\nReference dQ/du across its range: {np.round(gains, 2).tolist()} bbl/hr per %")
    print(f"  -> min {gains.min():.2f}, max {gains.max():.2f} "
          f"(ratio {gains.max() / gains.min():.1f}x)")

    sim = WellSimulator(noise=False)
    ours = [sim.steady_state(u)["Q"] for u in ss_sorted["choke_pct"]]
    og = np.diff(ours) / du
    print(f"Our stand-in over the same range:  {np.round(og, 2).tolist()} bbl/hr per %")
    print(f"  -> min {og.min():.2f}, max {og.max():.2f} (ratio {og.max() / og.min():.1f}x)")

    print("\nKEY DIFFERENCES (documented in the report, not corrected for):")
    print("  * the reference is close to LINEAR in choke; our physics stand-in is")
    print("    strongly nonlinear because of the choke orifice equation")
    print("  * the reference FLP FALLS as rate rises; a flowline with friction")
    print("    should see FLP RISE with throughput, as our stand-in does")
    print("  * absolute pressure levels differ (reference WHP ~217-270 psi,")
    print("    BHP ~2890-3130 psi)")
    print("\nNOTE: this dataset is used for ILLUSTRATION ONLY. The dynamic model is")
    print("identified exclusively from our own step tests, per the problem statement.")

    plot_reference(df)
    plot_comparison(ss)
    print(f"\n  wrote {FIG_DIR / 'reference_dataset.png'}")
    print(f"  wrote {FIG_DIR / 'reference_vs_standin.png'}")


if __name__ == "__main__":
    main()
