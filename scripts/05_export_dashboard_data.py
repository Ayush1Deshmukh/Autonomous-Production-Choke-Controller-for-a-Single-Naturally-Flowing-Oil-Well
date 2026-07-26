"""
05_export_dashboard_data.py
=============================
Bundles everything the dashboard needs (scenario logs, per-step MPC
reasoning, limits, controller config) into a single `dashboard/data.js` file
that defines `window.DASHBOARD_DATA`.

A plain <script src="data.js"> tag (not `fetch`) is used by the dashboard so
that it works when the HTML file is simply double-clicked and opened from
disk, with no local server and no network access required.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pandas as pd

from dataclasses import asdict

from config import DATA_DIR, DASH_DIR, LIMITS, CONTROLLER, SCENARIOS, PLANT, TS_HOURS


def main():
    fitted_model = json.loads((DATA_DIR / "fitted_model.json").read_text())

    bundle = {
        "limits": LIMITS.as_dict(),
        "controller": {
            "ts": CONTROLLER.ts,
            "u_min": CONTROLLER.u_min,
            "u_max": CONTROLLER.u_max,
            "max_move": CONTROLLER.max_move,
            "horizon": CONTROLLER.horizon,
            "candidate_step": CONTROLLER.candidate_step,
            "move_penalty": CONTROLLER.move_penalty,
            "margin_whp": CONTROLLER.margin_whp,
            "margin_flp": CONTROLLER.margin_flp,
            "margin_bhp": CONTROLLER.margin_bhp,
            "bias_filter_alpha": CONTROLLER.bias_filter_alpha,
        },
        "plant": asdict(PLANT),
        "ts_hours": TS_HOURS,
        "model": fitted_model,
        "scenarios": {},
    }

    for key in ("A", "B", "C"):
        df = pd.read_csv(DATA_DIR / f"scenario_{key}_log.csv")
        decisions = json.loads((DATA_DIR / f"scenario_{key}_decisions.json").read_text())

        bundle["scenarios"][key] = {
            "name": SCENARIOS[key]["name"],
            "description": SCENARIOS[key]["description"],
            "u_initial": SCENARIOS[key]["u_initial"],
            "log": df.round(2).to_dict(orient="records"),
            "decisions": decisions,
        }

    out = DASH_DIR / "data.js"
    out.write_text("window.DASHBOARD_DATA = " + json.dumps(bundle) + ";\n")
    print(f"wrote {out}  ({out.stat().st_size/1024:.0f} KB)")


if __name__ == "__main__":
    main()
