"""
plotting.py
===========
Shared "house style" for every figure in the project, so step-test plots,
model-validation plots and scenario plots all look like they belong to one
polished submission.
"""

from __future__ import annotations

import matplotlib

matplotlib.use("Agg")   # headless, no display needed for report generation
import matplotlib.pyplot as plt
import numpy as np

# --------------------------------------------------------------------------
# Palette
# --------------------------------------------------------------------------
COLOR_CHOKE = "#6b7280"     # slate grey
COLOR_Q = "#2563eb"         # blue
COLOR_TARGET = "#111827"    # near-black, dashed
COLOR_WHP = "#059669"       # green
COLOR_FLP = "#d97706"       # amber
COLOR_BHP = "#dc2626"       # red
COLOR_SAFE = "#22c55e"
COLOR_LIMIT = "#dc2626"
COLOR_BAND = "#22c55e"

plt.rcParams.update(
    {
        "figure.facecolor": "white",
        "axes.facecolor": "white",
        "axes.edgecolor": "#374151",
        "axes.labelcolor": "#111827",
        "axes.titlesize": 12,
        "axes.titleweight": "bold",
        "axes.grid": True,
        "grid.color": "#e5e7eb",
        "grid.linewidth": 0.8,
        "font.size": 10,
        "font.family": "DejaVu Sans",
        "legend.frameon": False,
        "xtick.color": "#374151",
        "ytick.color": "#374151",
        "figure.dpi": 130,
        "savefig.dpi": 150,
        "savefig.bbox": "tight",
    }
)


def style_axis(ax, title=None, ylabel=None, xlabel=None):
    if title:
        ax.set_title(title, loc="left")
    if ylabel:
        ax.set_ylabel(ylabel)
    if xlabel:
        ax.set_xlabel(xlabel)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    return ax


def shade_safe_band(ax, lo, hi, margin_lo=None, margin_hi=None, label="Safe band"):
    """Green safe band between hard limits, with limit lines drawn on top."""
    ax.axhspan(lo, hi, color=COLOR_BAND, alpha=0.08, zorder=0, label=label)
    ax.axhline(lo, color=COLOR_LIMIT, lw=1.3, ls="--", zorder=1)
    ax.axhline(hi, color=COLOR_LIMIT, lw=1.3, ls="--", zorder=1)
    if margin_lo is not None:
        ax.axhline(lo + margin_lo, color="#f59e0b", lw=0.9, ls=":", zorder=1)
    if margin_hi is not None:
        ax.axhline(hi - margin_hi, color="#f59e0b", lw=0.9, ls=":", zorder=1)


def ramp_envelope(ax, t, u0, max_move, ts):
    """Draw the feasible ramp-rate cone from the initial choke position."""
    steps = (np.asarray(t) - t[0]) / ts
    hi = np.clip(u0 + max_move * steps, 0, 100)
    lo = np.clip(u0 - max_move * steps, 0, 100)
    ax.fill_between(t, lo, hi, color=COLOR_CHOKE, alpha=0.08, zorder=0,
                     label="Ramp envelope")


def savefig(fig, path):
    fig.savefig(path)
    plt.close(fig)
