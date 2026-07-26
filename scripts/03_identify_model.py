"""
03_identify_model.py
=====================
Dynamic model identification from the IDENTIFICATION step-test data only
(`data/step_test_identification.csv`), then validation against the held-out
VALIDATION step-test data (`data/step_test_validation.csv`).

For each output y in {Q, WHP, FLP, BHP}:
    * steady-state knots y_ss(u) are read directly from the end-of-step values
      of the identification test (piecewise-linear steady-state curve)
    * a single first-order time constant tau_y is fitted by nonlinear least
      squares against the *shape* of every step's transient (normalised to
      0-1), pooled across all steps for robustness
    * dead time theta is fitted too (expected ~0 for this plant) for honesty

Outputs
-------
    data/fitted_model.json                 (the WellModel, used by the controller)
    data/model_gain_table.csv              (local gain vs operating point, for report)
    figures/model_validation.png            (predicted vs actual on held-out data)
    data/model_validation_metrics.json      (RMSE / NRMSE per output)
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import numpy as np
import pandas as pd
from scipy.optimize import least_squares
import matplotlib.pyplot as plt

from config import (DATA_DIR, FIG_DIR, STEP_HOLD_HOURS, STEP_SEQUENCE_ID,
                    STEP_SEQUENCE_VAL, TS_HOURS)
from model import WellModel, OutputModel, OUTPUTS
from plotting import COLOR_Q, COLOR_WHP, COLOR_FLP, COLOR_BHP, style_axis, savefig

COLORS = {"Q": COLOR_Q, "WHP": COLOR_WHP, "FLP": COLOR_FLP, "BHP": COLOR_BHP}


def extract_steady_state_knots(df: pd.DataFrame, sequence, hold_hours, y_col):
    """Steady-state value of `y_col` at the END of every held step."""
    u_knots, y_knots = [], []
    for i, u in enumerate(sequence):
        # last sample of this hold window (steady state, since hold >> tau)
        end_row = df[df["step_index"] == i].iloc[-1]
        u_knots.append(u)
        y_knots.append(end_row[y_col])
    # de-duplicate / sort by u for a well-posed interpolant
    order = np.argsort(u_knots)
    u_sorted = np.array(u_knots)[order]
    y_sorted = np.array(y_knots)[order]
    u_uniq, idx = np.unique(u_sorted, return_index=True)
    return u_uniq.tolist(), y_sorted[idx].tolist()


def fit_time_constant(df: pd.DataFrame, sequence, hold_hours, y_col, u_knots, y_knots):
    """
    Pool every step's transient (normalised to its own start/end) and fit one
    (tau, theta) pair by nonlinear least squares against the first-order
    step-response shape  y_norm(t) = 1 - exp(-(t-theta)/tau).
    """
    t_rel_all, y_norm_all, tau_per_step = [], [], []

    for i in range(1, len(sequence)):
        seg = df[df["step_index"] == i].reset_index(drop=True)
        y0 = df[df["step_index"] == i - 1].iloc[-1][y_col]
        y1 = seg.iloc[-1][y_col]
        if abs(y1 - y0) < 1e-6:
            continue
        t_rel = np.arange(len(seg)) * TS_HOURS
        y_norm = (seg[y_col].values - y0) / (y1 - y0)

        # quick per-step tau estimate (time to reach 63.2%) for diagnostics
        idx_63 = np.searchsorted(y_norm, 0.632)
        if 0 < idx_63 < len(t_rel):
            tau_per_step.append(float(t_rel[idx_63]))

        t_rel_all.append(t_rel)
        y_norm_all.append(y_norm)

    t_all = np.concatenate(t_rel_all)
    y_all = np.concatenate(y_norm_all)

    def resid(p):
        tau, theta = p
        tau = max(tau, 0.05)
        theta = max(theta, 0.0)
        pred = 1.0 - np.exp(-np.maximum(t_all - theta, 0.0) / tau)
        return pred - y_all

    res = least_squares(resid, x0=[1.0, 0.0], bounds=([0.05, 0.0], [10.0, 2.0]))
    tau_fit, theta_fit = res.x
    rmse = float(np.sqrt(np.mean(res.fun ** 2)))
    return float(tau_fit), float(theta_fit), rmse, tau_per_step


def identify(df_id: pd.DataFrame) -> WellModel:
    outputs = {}
    for y in OUTPUTS:
        u_knots, y_knots = extract_steady_state_knots(
            df_id, STEP_SEQUENCE_ID, STEP_HOLD_HOURS, y
        )
        tau, theta, rmse, tau_per_step = fit_time_constant(
            df_id, STEP_SEQUENCE_ID, STEP_HOLD_HOURS, y, u_knots, y_knots
        )
        outputs[y] = OutputModel(
            name=y, tau=tau, theta=theta, u_knots=u_knots, y_knots=y_knots,
            tau_per_step=tau_per_step, rmse_fit=rmse,
        )
        print(
            f"  {y:4s}: tau={tau:.2f} h  theta={theta:.2f} h  "
            f"fit RMSE(normalised)={rmse:.3f}   "
            f"per-step tau spread={np.round(tau_per_step, 2)}"
        )
    return WellModel(ts=TS_HOURS, outputs=outputs)


def validate(model: WellModel, df_val: pd.DataFrame, sequence, hold_hours):
    """Open-loop prediction from the model over the held-out validation test,
    starting from the true initial condition, applying the same choke sequence,
    and comparing to the measured (noise-free) plant trajectory."""
    y0 = {y: float(df_val.iloc[0][y]) for y in OUTPUTS}
    u_seq = df_val["choke_pct"].values[1:]   # skip the initial reset row
    pred = model.predict(y0, u_seq)

    actual = {y: df_val[y].values[1:] for y in OUTPUTS}
    t = df_val["time_h"].values[1:]

    metrics = {}
    fig, axes = plt.subplots(4, 1, figsize=(11, 10), sharex=True)
    for ax, y in zip(axes, OUTPUTS):
        rmse = float(np.sqrt(np.mean((pred[y] - actual[y]) ** 2)))
        span = max(actual[y].max() - actual[y].min(), 1e-6)
        nrmse = 100.0 * rmse / span
        metrics[y] = {"rmse": rmse, "nrmse_pct": nrmse}

        ax.plot(t, actual[y], color=COLORS[y], lw=2.0, label="Actual (plant)")
        ax.plot(t, pred[y], color="black", lw=1.4, ls="--", label="Predicted (model)")
        style_axis(ax, title=f"{y}: RMSE={rmse:.2f}, NRMSE={nrmse:.1f}%", ylabel=y)
        ax.legend(loc="best", fontsize=8)
    axes[-1].set_xlabel("Time [h]")
    fig.suptitle("Model Validation on Held-Out Step Test", fontweight="bold")
    fig.tight_layout()
    savefig(fig, FIG_DIR / "model_validation.png")
    return metrics


def main():
    df_id = pd.read_csv(DATA_DIR / "step_test_identification.csv")
    df_val = pd.read_csv(DATA_DIR / "step_test_validation.csv")

    print("Identifying model from identification step test...")
    model = identify(df_id)
    model.save(DATA_DIR / "fitted_model.json")
    print(f"  wrote {DATA_DIR / 'fitted_model.json'}")

    print("\nValidating against held-out step test...")
    metrics = validate(model, df_val, STEP_SEQUENCE_VAL, STEP_HOLD_HOURS)
    for y, m in metrics.items():
        print(f"  {y:4s}: RMSE={m['rmse']:.2f}   NRMSE={m['nrmse_pct']:.1f}%")
    (DATA_DIR / "model_validation_metrics.json").write_text(json.dumps(metrics, indent=2))

    gain_table = model.gain_table([10, 20, 30, 40, 50, 60, 70, 80, 90])
    pd.DataFrame(gain_table).to_csv(DATA_DIR / "model_gain_table.csv", index=False)
    print(f"\n  wrote {DATA_DIR / 'model_gain_table.csv'}")
    print(f"  wrote {FIG_DIR / 'model_validation.png'}")


if __name__ == "__main__":
    main()
