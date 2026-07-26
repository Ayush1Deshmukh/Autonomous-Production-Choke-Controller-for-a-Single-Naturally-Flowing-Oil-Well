# Complete 6-Slide PPT Build Guide

Everything needed to build the submission deck: exact text to paste, exact images to
place, exact positions, and verified references.

**Before you start:** open the provided template, **delete the "IMPORTANT INSTRUCTIONS"
slide**. What remains is exactly 6 slides. Do not add or remove any others, and do not
change the section headings.

**Canvas:** 13.33 in × 7.5 in (16:9). All positions below are in inches from the top-left.
**Images:** all in `submission/presentation_assets/`, named by the slide they belong to.
**Numbers:** every figure below comes from the generated results as of the last
`python run_all.py`. If you re-run, re-check them.

**Rule to obey throughout:** *no paragraphs.* Bullets, tables, diagrams and pictures only.

---

# SLIDE 1 — TITLE PAGE

Fill the template's existing fields. Do not restyle them.

| Field | Value |
|---|---|
| Problem Statement ID | *(your portal ID)* |
| Problem Statement Title | Autonomous Production Choke Controller for a Single Naturally Flowing Oil Well |
| Theme | Oil & Gas / Industrial Process Control & Automation |
| PS Category | **Software** |
| Team Name | *(yours)* |
| Team ID | *(yours)* |

**Add one line below the fields** (this is the hook — it is the first thing judged):

> An autonomous choke controller that maximises safe oil production and refuses any
> target it cannot reach safely. **Zero constraint violations across 300 closed-loop runs.**

**Images:** none. Leave the title slide clean.

---

# SLIDE 2 — IDEA TITLE / PROPOSED SOLUTION

Template pointers to answer: *detailed explanation · how it addresses the problem · innovation and uniqueness*

**Pattern used on this slide:** every block is written twice.

1. **The lead paragraph** — plain English a non-specialist follows immediately, but with
   the key terms introduced in passing (*production choke*, *BHP*) and the headline
   numbers included, so the block is complete on its own.
2. **The bullets underneath** — the full technical detail, equations and figures.

Set the lead in *italic* and the bullets in normal weight so the two layers read as
distinct. A judge who reads only the italic text should still get the whole idea, with
numbers.

### LAYOUT

| Element | Position | Size |
|---|---|---|
| Left column text | x 0.5, y 1.25 | 6.1 in wide |
| Right column text | x 6.9, y 1.25 | 6.0 in wide |
| `slide2_gain_curve.png` | x 7.4, y 5.55 | 5.0 in wide (small, bottom-right) |

---

## LEFT COLUMN

### THE PROBLEM

*Lead (italic):*
> A valve at the top of an oil well — the **production choke** — decides how much oil comes
> out. Open it wider and flow rate **Q** rises, but pressure inside the well falls: at the
> wellhead (**WHP**) and, critically, at the bottom of the well (**BHP**). Let BHP drop below
> **1900 psi** and the well is outside its safe range. That one limit caps this well at
> **165 bbl/hr**. Today an operator picks the setting by hand across dozens of wells, so wells
> run either too cautiously, losing part of that 165, or too hard and risk damage.

*Detail:*
- One manipulated variable: choke opening **u**, 0–100 %. Four coupled outputs: **Q, WHP, FLP, BHP**
- Opening the choke: **Q ↑, FLP ↑, WHP ↓, BHP ↓** — production and safety pull in opposite directions
- Envelope: **WHP ≥ 320 · FLP ≤ 260 · BHP ≥ 1900 psi**; ramp limit **|Δu| ≤ 5 %/hour**
- Strongly nonlinear: gain **dQ/du falls 3.91 → 0.15 bbl/hr per %** (≈26×) → **fixed tuning cannot work**
- Manual control is also unverifiable: no operator can prove a setting is safe across every future hour

### THE SOLUTION

*Lead (italic):*
> Software that sets the valve automatically, once an hour (**Ts = 1 h**). Before moving, it
> lists every setting it is allowed to reach — the choke may shift only **±5 % per hour**, giving
> **21 options** — and predicts what each would do to flow and to all three pressures over the
> next **10 hours**. Any option that would push WHP, FLP or BHP outside the safe range is thrown
> away. From what survives it picks the one landing closest to the production target. If none
> can reach it safely, it settles at the highest safe rate — **162.7 bbl/hr** against a true
> ceiling of **165.0** — and holds there.

*Detail:*
- **Enumerate** — u(k) ± 5 % on a 0.5 % grid, clipped to [0, 100] → **21 candidates**
- **Predict** — roll each **10 steps** through a model identified from our own step tests
  (τ: Q 0.99 h · WHP 1.18 h · FLP 0.80 h · **BHP 1.75 h**; horizon = **5.7 × τ_BHP**)
- **Filter** — reject if predicted WHP/FLP/BHP breaches a limit at **any** step in the horizon
- **Select** — minimise `J = (Q_pred − Q_target)² + 0.05·(Δu)²`
- **Hold** — move only if it buys ≥ **2 (bbl/hr)²** improvement → **zero valve chatter** once settled
- Validated model: NRMSE **0.09 %** (Q), **0.95 %** (BHP) on held-out step data

---

## RIGHT COLUMN

### HOW IT ADDRESSES THE PROBLEM

*Lead (italic):*
> It replaces a judgement call with arithmetic anyone can check. An unsafe move is deleted
> from the list *before* the choice is made, so it cannot be selected at any price — unlike
> controllers that merely penalise violations. And because it re-plans every hour from live
> measurements, it can sit right beside the limit without crossing it: in the infeasible-target
> case BHP settles at **1906 psi** against a **1900 psi** limit, while producing **98.6 %** of what
> the well can safely give. Across **300 runs** it never crossed once.

*In mathematical terms:*
- Feasible set: **F(k) = { u : ĝ(u, j) ≤ 0 for all j = 1…10 }**, ĝ = predicted limit breach
- Chosen move: **u\*(k) = argmin J(u) s.t. u ∈ F(k)** — a violation is *infeasible*, not merely expensive
- Back-off inside each limit: **10 / 8 / 15 psi** (WHP / FLP / BHP), covering sensor noise + model error + filter lag
- Tracking: **A 121.0 ± 0.6** (target 120) · **B 150.8 ± 0.8** (target 150) · **C 162.7 ± 0.9** (target 200, capped)
- Safety: **0 violations / 300 runs**, worst margin **+3.2 psi**; cost of that safety **2.3 bbl/hr (1.4 %)**

### INNOVATION AND UNIQUENESS

*Lead (italic):*
> Three things. **Safety is structural** — unsafe candidates are removed from the search rather
> than penalised, so there is no weighting to tune and no breach a large production error can
> buy. **It explains itself** — every hour it can list all **21** candidates and the exact reason
> each was rejected (*"BHP 1912 < 1915 psi at k+10"*), which is what an operator needs before
> trusting it. **It knows when to stop** — an unreachable **200 bbl/hr** target does not make it
> push or oscillate; it parks at **162.7** and stays still.

*In mathematical terms:*
- **Constraint-as-structure:** classic MPC uses `J = e² + ρ·max(0, g)²`, so a big enough error can still buy a breach. We delete those candidates — **no ρ to tune, no breach purchasable at any price**
- **Explainability:** all 21 candidates + reject reason logged every step. A black-box optimiser or neural policy cannot produce this
- **Infeasible target needs no special case:** F(k) is bounded above, so the minimiser sits on **∂F** and stays — the cap is *emergent*, not coded
- **Plant-agnostic:** calls only `step(u)` / `reset()`; a test runs it unchanged on a completely different well
- **No solver library** — exhaustive search over 21 candidates is exact, runs in **milliseconds**, deployable on an edge gateway

---

**Caption under the gain-curve image (9 pt italic grey):**
> Gain collapses ~26× across the range — the reason fixed tuning fails and a predictive
> model-based controller is needed.

**If the slide overflows:** trim the *Detail* bullets to three per block. Keep every italic
lead intact — those carry both the idea and the headline numbers, and they are what lands
in the first ten seconds.

---

# SLIDE 3 — TECHNICAL APPROACH

Template pointers: *technologies used · methodology and process for implementation (flow charts / images / working prototype)*

### TOP — architecture diagram, full width

| Image | Position | Size |
|---|---|---|
| `slide3_architecture_diagram.png` | x 0.45, y 1.15 | 12.4 in wide |

This is the flow chart the template asks for: well → model → MPC → back to well, with the
safe envelope feeding the constraint filter.

### BOTTOM-LEFT — text box at x 0.6, y 4.5, width 5.9 in

**TECHNOLOGIES**
- **Python 3.10+** · NumPy · pandas · SciPy · Matplotlib
- **No optimisation or solver library** — brute-force search is exact here
- **HTML / CSS / JavaScript** dashboard — self-contained, no build step, no server
- One command reproduces and re-verifies everything: `python run_all.py` (~2 min)

### BOTTOM-RIGHT — text box at x 6.8, y 4.5, width 6.0 in

**METHODOLOGY — 5 STEPS**
1. **Step tests** — 15 choke steps, up and down, 5–20 %, each held 8 h to true steady state
2. **Model ID** — first-order lag per output + piecewise-linear steady-state curve `y_ss(u)`
3. **Predict** — roll all 21 candidates 10 h forward from the *current measurement*
4. **Filter** — reject any candidate breaching a limit at **any** point in the horizon
5. **Select** — minimise `(Q_pred − Q_target)² + 0.05·(Δu)²`, with a deadband to stop valve chatter

**KEY NUMBERS**
- τ: Q 0.99 h · WHP 1.18 h · FLP 0.80 h · **BHP 1.75 h** (slowest → sets the 10 h horizon)
- Validated on **held-out** steps: NRMSE **0.09 %** (Q), **0.95 %** (BHP)

*Optional if space allows:* `slide3_model_validation.png` or `slide3_mpc_reasoning.png` small in a corner.

---

# SLIDE 4 — FEASIBILITY AND VIABILITY

Template pointers: *feasibility analysis · potential challenges and risks · strategies for overcoming*

### TOP — KPI banner, full width

| Image | Position | Size |
|---|---|---|
| `slide4_kpi_strip.png` | x 0.45, y 1.15 | 12.4 in wide (thin banner, ~1.5 in tall) |

Shows: **300 runs · 0 violations · 98.6 % of max safe rate · 19/19 tests · 2.3 bbl/hr cost of safety**

### LEFT COLUMN — text box at x 0.6, y 2.9, width 6.0 in

**FEASIBILITY — PROVEN, NOT CLAIMED**
- **Monte-Carlo: 100 noise seeds × 3 scenarios = 300 closed-loop runs** (~26,000 control intervals)
- Envelope checked on **every sample of every run**
- Worst margin to any limit: **A +26.0 psi · B +15.8 psi · C +3.2 psi** — never crossed
- Runs in ~2 min on a laptop. No GPU, no internet, no solver
- Controller reads **only** `simulator.step(u)` → official simulator drops in with **zero code changes**, proven by a test against a deliberately different plant

**CHALLENGES FOUND — AND FIXED**
- **Horizon shorter than the slowest lag.** A 5 h horizon saw only ~94 % of BHP's fall, so the controller parked somewhere that kept sinking *after* the horizon ended → **11 of 100 runs breached**. Fixed by extending to 10 h ≈ 5.7 τ
- **Coarse step-test knots.** Linear interpolation across a *convex* curve over-estimated BHP by **8 psi** — optimistic in exactly the unsafe direction. Fixed with 5 % knot spacing through the operating band
- **Both passed single-run testing.** Only the Monte-Carlo exposed them

**RISK STRATEGY**
- Margins sized for **noise + model error + filter lag**, not noise alone, then re-verified over 300 runs
- **Cost of safety quantified, not hidden:** 2.3 bbl/hr (1.4 %) below the theoretical maximum
- Automated PASS/FAIL audit in the pipeline; non-zero exit if any check fails

### RIGHT COLUMN — image

| Image | Position | Size |
|---|---|---|
| `slide4_robustness.png` | x 6.9, y 3.0 | 6.0 in wide |

**Caption (9 pt, grey):**
> Distance to the nearest limit across 100 seeds per scenario. Every run stays on the safe
> side of zero, including Scenario C which deliberately operates hard against the BHP limit.

---

# SLIDE 5 — ARTIFACTS

Template pointers: *copy of the code embedded · snaps of the solution proposal · dashboard snaps*

### TOP-LEFT — results table at x 0.55, y 1.25, width 6.4 in

| Scenario | Target | Settled rate | Choke | Min BHP | Outcome |
|---|---|---|---|---|---|
| **A** Startup to target | 120 | **121.0 ± 0.6** | 33.5 % | 2184 psi | on target |
| **B** Tracking 100→150 | 150 | **150.8 ± 0.8** | 50.0 % | 1989 psi | retargets cleanly |
| **C** Infeasible target | 200 | **162.7 ± 0.9** | 64.0 % | **1906 psi** | capped at **98.6 %** of max safe |

**One line under the table:**
> Safety held on **every sample**: WHP ≥ 320, FLP ≤ 260, BHP ≥ 1900 psi, |Δu| ≤ 5 %/step.
> True max safe rate is 165.0 bbl/hr — Scenario C reaches 162.7 without ever crossing a limit.

### TOP-RIGHT — dashboard screenshot

| Image | Position | Size |
|---|---|---|
| `slide5_dashboard_light.png` | x 7.1, y 1.25 | 5.8 in wide |

*(Use `slide5_dashboard_dark.png` if your deck theme is dark.)*

### BOTTOM — all three scenarios, full width

| Image | Position | Size |
|---|---|---|
| `slide5_all_scenarios.png` | x 0.5, y 4.35 | 12.3 in wide |

This single image satisfies the problem statement's required trends — target rate, actual
rate, BHP with limit lines, and choke position — for **all three scenarios at once**.

**Caption (9 pt, grey):**
> Target tracked when feasible (A, B); refused and capped at the safe maximum when not (C).
> BHP rests on its limit without ever crossing it.

**Add one line listing deliverables:**
> Simulator · step tests · model ID · MPC · 3 scenarios · Monte-Carlo · 19 tests · dashboard · report.
> Full 7-panel per-scenario figures (incl. WHP, FLP, WHT, AP) are in the submitted zip.

---

# SLIDE 6 — RESEARCH AND REFERENCES

### LEFT COLUMN — text box at x 0.6, y 1.3, width 6.0 in

**LESSONS LEARNED**
- **Where you place step-test knots is a safety decision** — interpolating across a convex curve is optimistic exactly where the constraint binds
- **A horizon shorter than the slowest time constant is not conservative, it is unsafe**
- **One good run is not evidence** — a safety claim about a noisy system needs a distribution behind it
- Margins must cover **estimator lag and model error**, not just sensor noise
- Every filter is a trade: ours removed constraint hunting but cost response lag, paid for in margin
- **Infeasibility needs no special-case code** — it falls out of predict → filter → select

**PROVIDED MATERIAL — HOW WE USED IT**
- `Autonomous_Choke_Control_Simulated_Dataset.csv` used for **illustration only**, exactly as the problem statement directs. **Never used to fit the model**
- Our model comes solely from our own step-test experiments
- We compared the two openly: the reference is near-linear, and its FLP *falls* with rate where a friction-dominated flowline should rise

**NOTE ON THE SIMULATOR**
- The simulator **module** was never supplied, so we built a documented physics-based stand-in from the process description
- The controller touches only `step()` / `reset()`, so the official simulator substitutes with **zero changes**

### RIGHT COLUMN — text box at x 6.9, y 1.3, width 6.0 in

**REFERENCES**

*Inflow performance and well hydraulics*
1. Vogel, J.V. (1968). *Inflow Performance Relationships for Solution-Gas Drive Wells.* Journal of Petroleum Technology, 20(1), 83–92. SPE-1476-PA. https://doi.org/10.2118/1476-PA
2. Beggs, H.D. (2003). *Production Optimization Using NODAL Analysis*, 2nd ed. OGCI/Petroskills.
3. Economides, M.J., Hill, A.D., Ehlig-Economides, C., Zhu, D. (2013). *Petroleum Production Systems*, 2nd ed. Prentice Hall.

*Choke and control-valve sizing*
4. IEC 60534-2-1 — *Industrial-process control valves, Part 2-1: Flow capacity — Sizing equations for fluid flow under installed conditions.* https://webstore.iec.ch/publication/2477
5. ISA-75.01.01 — *Flow Equations for Sizing Control Valves.* https://www.isa.org/products/isa-75-01-01-2012-60534-2-1-mod-industrial-pr

*Model predictive control*
6. Cutler, C.R. & Ramaker, B.L. (1980). *Dynamic Matrix Control — A Computer Control Algorithm.* Joint Automatic Control Conference, San Francisco.
7. Qin, S.J. & Badgwell, T.A. (2003). *A survey of industrial model predictive control technology.* Control Engineering Practice, 11(7), 733–764. https://doi.org/10.1016/S0967-0661(02)00186-7
8. Maciejowski, J.M. (2002). *Predictive Control with Constraints.* Prentice Hall.
9. Rawlings, J.B., Mayne, D.Q., Diehl, M.M. (2017). *Model Predictive Control: Theory, Computation, and Design*, 2nd ed. Nob Hill. Free PDF: https://sites.engineering.ucsb.edu/~jbraw/mpc/

*Process identification*
10. Seborg, D.E., Edgar, T.F., Mellichamp, D.A., Doyle, F.J. (2016). *Process Dynamics and Control*, 4th ed. Wiley. — step testing and FOPDT identification
11. Ljung, L. (1999). *System Identification: Theory for the User*, 2nd ed. Prentice Hall.

*Problem material*
12. Honeywell hackathon problem statement and reference dataset `Autonomous_Choke_Control_Simulated_Dataset.csv` (provided via the submission portal).

**PROJECT ARTIFACTS**
- `src/` — well_simulator · model · controller · simulator_interface
- `scripts/` — reference EDA · step tests · model ID · scenarios · robustness · dashboard capture
- `tests/` — 19 tests including a swap-in proof against a different plant
- `dashboard/` — self-contained HTML/JS demo (no build, no server)
- `report/ENGINEERING_REPORT.pdf` — full engineering report

---

# DESIGN SPECS

Keep it plain. Judges read content, and heavy styling reads as filler.

| Element | Spec |
|---|---|
| Section heading | Template's own placeholder — **do not restyle or rename** |
| Sub-heading | 13–14 pt bold, dark blue `#1D4FD8` |
| Body bullet | 11–12 pt, dark grey `#334155` |
| Sub-bullet | 10–11 pt, grey `#64748B` |
| Emphasis / numbers | **bold**, near-black `#0F172A` |
| Good result | green `#117A3A` · Risk/limit: red `#B91C1C` |
| Caption under image | 9 pt italic grey `#64748B` |
| Font | Calibri or Arial throughout |

**Spacing:** leave ≥ 0.4 in margin on all sides. Do not let any image touch a slide edge.

---

# ASSET INDEX — `submission/presentation_assets/`

| File | Slide | Shows |
|---|---|---|
| `slide2_gain_curve.png` | 2 | Q vs choke + gain collapsing 26× |
| `slide3_architecture_diagram.png` | **3** | control-loop flow chart |
| `slide3_step_tests.png` | 3 (optional) | the 15-step identification experiment |
| `slide3_model_validation.png` | 3 (optional) | predicted vs actual, held-out data |
| `slide3_mpc_reasoning.png` | 3 or 4 (optional) | live candidate list + rejection reasons |
| `slide4_kpi_strip.png` | **4** | 5 headline KPIs as a banner |
| `slide4_robustness.png` | **4** | margin distributions over 300 runs |
| `slide5_all_scenarios.png` | **5** | all 3 scenarios: Q, BHP, choke |
| `slide5_dashboard_light.png` / `_dark.png` | **5** | dashboard screenshot |
| `slide6_reference_vs_standin.png` | 6 (optional) | provided reference data vs our stand-in |
| `slide6_reference_dataset.png` | 6 (optional) | the provided reference dataset plotted |
| `appendix_scenario_A/B/C_full.png` | not on a slide | full 7-panel per scenario, for the zip |

---

# PRE-SUBMISSION CHECKLIST

- [ ] Deleted the template's "IMPORTANT INSTRUCTIONS" slide
- [ ] Exactly **6 slides** including the title
- [ ] **No paragraphs** — bullets, tables, diagrams, images only
- [ ] Template section headings unchanged
- [ ] Every image inside the margins, nothing overlapping or cropped
- [ ] Numbers match the generated results (re-check if you re-ran `run_all.py`)
- [ ] Reference links open correctly — **verify each one before submitting**
- [ ] Exported to **PDF** (portal accepts PDF only, not PPT)
- [ ] PDF opens cleanly and all figures are legible at 100 % zoom
- [ ] Zip includes code, figures and report
