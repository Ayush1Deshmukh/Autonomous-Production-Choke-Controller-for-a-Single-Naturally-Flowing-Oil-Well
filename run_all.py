"""
run_all.py
==========
Single entry point that reproduces every deliverable end-to-end:

    1. Generate the illustrative reference dataset
    2. Run open-loop step tests (identification + validation)
    3. Identify the dynamic model and validate it
    4. Run the brute-force MPC controller on Scenarios A, B, C
    5. Export the data bundle consumed by the interactive dashboard

Exits non-zero if any scenario fails its constraint-safety audit.

Usage:
    python run_all.py
"""

from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PY = sys.executable

STEPS = [
    ("Reference-dataset EDA (illustrative only)", "scripts/01_reference_dataset_eda.py"),
    ("Running open-loop step tests", "scripts/02_step_tests.py"),
    ("Identifying and validating the dynamic model", "scripts/03_identify_model.py"),
    ("Running Scenarios A/B/C with the brute-force MPC", "scripts/04_run_scenarios.py"),
    ("Exporting dashboard data bundle", "scripts/05_export_dashboard_data.py"),
    ("Monte-Carlo robustness study (300 closed-loop runs)", "scripts/06_robustness_study.py"),
    ("Capturing dashboard screenshots (optional)", "scripts/07_capture_dashboard.py"),
    ("Running the test suite", "tests/test_all.py"),
    ("Building the submission deck (optional)", "scripts/09_build_presentation.py"),
    ("Assembling presentation assets", "scripts/10_build_ppt_assets.py"),
]


def main():
    print("=" * 70)
    print("AUTONOMOUS PRODUCTION CHOKE CONTROLLER — full pipeline")
    print("=" * 70)

    for label, script in STEPS:
        print(f"\n>>> {label}  [{script}]")
        t0 = time.time()
        result = subprocess.run([PY, str(ROOT / script)], cwd=str(ROOT))
        dt = time.time() - t0
        if result.returncode != 0:
            print(f"\n*** FAILED at: {script} (exit {result.returncode}, {dt:.1f}s) ***")
            sys.exit(result.returncode)
        print(f"    done in {dt:.1f}s")

    print("\n" + "=" * 70)
    print("ALL STEPS COMPLETE.")
    print("  Figures  -> figures/")
    print("  Data     -> data/")
    print("  Dashboard-> dashboard/index.html  (open directly in a browser)")
    print("  Report   -> report/ENGINEERING_REPORT.md")
    print("=" * 70)


if __name__ == "__main__":
    main()
