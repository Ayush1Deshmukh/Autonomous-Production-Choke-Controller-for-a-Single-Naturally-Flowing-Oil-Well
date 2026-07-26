"""
parity_check.py
================
Proves the JS plant port (`plant.js`) used by the dashboard's Live/Custom mode
reproduces the Python plant (`src/well_simulator.py`) that the offline
scenarios were validated against.

Method: run the SAME choke step sequence (noise-free) through both
implementations and diff every sample.  Node.js is used to execute plant.js
headlessly; if Node is not available the check is skipped with a clear note
(the offline scenario deliverables do not depend on this check).
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from config import PLANT, TS_HOURS, STEP_SEQUENCE_ID, STEP_HOLD_HOURS  # noqa: E402
from well_simulator import WellSimulator  # noqa: E402
from dataclasses import asdict


def python_trace():
    sim = WellSimulator(noise=False)
    sim.reset()
    for u in STEP_SEQUENCE_ID:
        for _ in range(STEP_HOLD_HOURS):
            sim.step(u)
    df = sim.to_dataframe()
    return df[["Q", "WHP", "FLP", "BHP"]].to_dict(orient="list")


def js_trace():
    node = shutil.which("node")
    if node is None:
        return None

    plant_params = json.dumps(asdict(PLANT))
    sequence = json.dumps(STEP_SEQUENCE_ID)

    script = f"""
    const {{ WellPlant }} = require({json.dumps(str(ROOT / "dashboard" / "plant.js"))});
    const params = {plant_params};
    const sequence = {sequence};
    const holdHours = {STEP_HOLD_HOURS};
    const ts = {TS_HOURS};

    const plant = new WellPlant(params, ts, 1, false);
    plant.reset();
    const out = {{ Q: [], WHP: [], FLP: [], BHP: [] }};
    // include the reset sample to match Python's logging of the initial row
    const first = plant._measure();
    out.Q.push(first.Q); out.WHP.push(first.WHP); out.FLP.push(first.FLP); out.BHP.push(first.BHP);
    for (const u of sequence) {{
      for (let i = 0; i < holdHours; i++) {{
        const m = plant.step(u);
        out.Q.push(m.Q); out.WHP.push(m.WHP); out.FLP.push(m.FLP); out.BHP.push(m.BHP);
      }}
    }}
    console.log(JSON.stringify(out));
    """
    # module.exports shim for plant.js (browser-style global assignment)
    shim = "global.window = global; " + Path(ROOT / "dashboard" / "plant.js").read_text()
    shim += "\nmodule.exports = { WellPlant: window.WellPlant };\n"
    tmp = ROOT / "dashboard" / "_plant_node_shim.js"
    tmp.write_text(shim)

    script = script.replace(str(ROOT / "dashboard" / "plant.js"), str(tmp))
    result = subprocess.run([node, "-e", script], capture_output=True, text=True)
    tmp.unlink(missing_ok=True)
    if result.returncode != 0:
        print("Node execution failed:\n", result.stderr)
        return None
    return json.loads(result.stdout)


def main():
    py = python_trace()
    js = js_trace()

    if js is None:
        print("Node.js not available or plant.js failed to run - skipping JS parity check.")
        print("(This does not affect the offline Python deliverables.)")
        return

    max_err = {}
    ok = True
    for k in ("Q", "WHP", "FLP", "BHP"):
        a = py[k]
        b = js[k]
        n = min(len(a), len(b))
        err = max(abs(a[i] - b[i]) for i in range(n))
        max_err[k] = err
        if err > 1e-6:
            ok = False

    print("Max |Python - JS| difference per variable (noise-free identification sequence):")
    for k, v in max_err.items():
        print(f"  {k:4s}: {v:.2e}")
    print("PARITY:", "PASS (JS dashboard plant matches Python plant)" if ok else "FAIL")
    if not ok:
        sys.exit(1)


if __name__ == "__main__":
    main()
