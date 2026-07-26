# Autonomous Production Choke Controller

A brute-force MPC controller for a single naturally flowing oil well's
production choke, built for the Honeywell hackathon challenge
*"Autonomous Production Choke Controller for a Single Naturally Flowing Oil Well."*

**🔗 Live dashboard:** https://ayush1deshmukh.github.io/Autonomous-Production-Choke-Controller-for-a-Single-Naturally-Flowing-Oil-Well/
**💻 Repository:** https://github.com/Ayush1Deshmukh/Autonomous-Production-Choke-Controller-for-a-Single-Naturally-Flowing-Oil-Well

> **No official simulator file was provided** despite the problem statement
> indicating one would be. `src/well_simulator.py` is a physics-based
> stand-in built from the process description, exposing the exact interface
> named in the problem statement (`Q, WHP, FLP, BHP = simulator.step(u)`), so
> the official simulator can be substituted with **zero controller changes**.
> Details in `report/ENGINEERING_REPORT.md`, §0.

## Run and verify everything with one command

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python run_all.py
```

This regenerates every deliverable from scratch and verifies it:

1. step-test experiments + plots
2. dynamic model identification + held-out validation
3. all three demonstration scenarios, each with an explicit PASS/FAIL
   constraint-safety audit printed to the console
4. the dashboard data bundle
5. a **Monte-Carlo robustness study** — 300 closed-loop runs (100 noise
   seeds × 3 scenarios) asserting the operating envelope is never breached
6. a **19-test suite** covering simulator physics, model accuracy and
   controller safety

Total runtime ~2 minutes, and it exits non-zero if anything fails. Everything
is reproducible from a fixed seed.

Headline results: **0 constraint violations in 300 runs**, targets tracked to
within 1 %, and the infeasible target correctly capped at **98.6 % of the
true maximum safe rate**.

## See the live dashboard (the centerpiece demo)

```bash
open dashboard/index.html
```

No server, no build step, no dependencies — it's a static page. Pick
Scenario A/B/C to replay the exact runs from `run_all.py`, or click
**"Live / Custom"** to drive the well interactively: drag the target
slider at any time and watch the controller (running fully in-browser, a
verified 1:1 port of the Python plant + model + controller — see
`dashboard/parity_check.py`) re-plan every step.

What's on screen:

- **Trends** for Q, WHP, FLP, BHP and choke, each with the safe operating
  envelope shaded, hard limits dashed in red, the controller's internal
  safety margins dotted in amber, and the MPC's 10-hour predicted trajectory
  ghosted ahead of "now"
- **Well schematic** — animated flow through reservoir → tubing → wellhead →
  choke → flowline → separator, with a choke aperture that opens and closes
  with the control action and live pressure callouts that turn amber as they
  approach a limit
- **Operating envelope bars** showing exactly where each pressure sits inside
  its allowed range
- **MPC reasoning panel** — a plain-English verdict for the current move, plus
  every candidate choke position considered, colour-coded safe/rejected/
  selected, with the exact predicted violation for each rejected one
  (e.g. *"BHP 1912 < 1915 at k+10"*)

Light and dark themes (toggle in the header, follows your OS by default),
fully responsive down to phone width, and keyboard shortcuts: `Space`
play/pause, `R` reset, `1`/`2`/`3` scenarios, `L` live mode.

## Deploying it

The dashboard is fully static, so it hosts anywhere. Fastest route to a public link
for judges: drag the `dashboard/` folder onto https://app.netlify.com/drop.
GitHub Pages, Vercel, Cloudflare Pages and Docker options are in
[DEPLOYMENT.md](DEPLOYMENT.md).

## What's in here

```
src/well_simulator.py      physics-based plant stand-in (see note above)
src/simulator_interface.py the contract the controller relies on
src/config.py               every tunable number in the project, in one place
src/model.py                 identified dynamic model (gain-scheduled first-order)
src/controller.py            the brute-force MPC
src/plotting.py              shared figure style

scripts/01_reference_dataset_eda.py     EDA on the PROVIDED reference data (NOT used for ID)
scripts/02_step_tests.py                open-loop step-test experiments + plots
scripts/03_identify_model.py            fits + validates the dynamic model
scripts/04_run_scenarios.py             runs Scenarios A/B/C + safety audit
scripts/05_export_dashboard_data.py     bundles everything for the dashboard
scripts/06_robustness_study.py          Monte-Carlo: 300 closed-loop runs
scripts/07_capture_dashboard.py         real dashboard screenshots (optional)
scripts/08_export_report_pdf.py         renders the report to PDF (optional)
scripts/09_build_presentation.py        builds the 6-slide deck from the official template
tests/test_all.py                       19 tests, no pytest needed

dashboard/                  self-contained interactive HTML/JS dashboard
report/ENGINEERING_REPORT.md   Process Understanding & Model / Control Strategy / Results
data/, figures/              generated outputs (regenerated by run_all.py)
```

## Requirements

Python 3.10+, `numpy`, `pandas`, `scipy`, `matplotlib` (see
`requirements.txt`). No GPU, no internet access, no external services
required. Node.js is optional, used only to run `dashboard/parity_check.py`.

Optional, only for `scripts/08_export_report_pdf.py` (renders the
engineering report to `submission/ENGINEERING_REPORT.pdf`; not needed to
reproduce any of the core technical deliverables):

```bash
pip install reportlab markdown
```
