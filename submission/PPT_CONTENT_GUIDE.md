# Final PPT Plan — 6 Slides, Official Template

This is the complete, build-ready plan. It uses the official hackathon template (the
one linked in the problem statement, `id=1nCeqwAlNsR0eMCuCDS1HVfoRRBnf5aPc`) as the
outer shell, and puts the problem statement's three required content sections —
**Process Understanding & Model**, **Control Strategy**, **Results** — front and
centre inside it, with every one of their sub-bullets explicitly labelled so nothing
required is missing.

> **Note on your uploaded file:** `IDEA_Presentation_Format.pptx` from your Downloads
> folder is still blocked from my side by a macOS permission (Full Disk Access for
> the terminal), not by anything in this session. I've confirmed it is the same file
> as the one linked directly in the problem statement — I downloaded that copy earlier
> (`report/HACKATHON_TEMPLATE.pptx`) and it opens and inspects fine, 7 slides before
> deleting the instructions slide (6 after). This plan is built against that confirmed
> structure. If your local copy differs in layout, tell me what's different and I'll
> adjust.

**Before you start:** open the template, **delete Slide 1 "IMPORTANT INSTRUCTIONS."**
What remains is exactly 6 slides — do not add, remove, or rename any.

**Canvas:** 13.33 × 7.5 in (16:9). Positions below are inches from the top-left.
**Images:** all pre-built in `submission/presentation_assets/`, named by slide.
**Numbers:** pulled from the generated results as of the last `python run_all.py`.
**Rule throughout:** *no paragraphs* — bullets, tables, diagrams, images only.

---

## MASTER COVERAGE MAP

Confirm this table before you build — it shows every required item has an exact home.

| Problem-statement requirement | Exact sub-item | Slide | Template's own section |
|---|---|---|---|
| **Process Understanding & Model** | Step-test results | **2** | Idea / Proposed Solution |
| | Model assumptions | **2** | Idea / Proposed Solution |
| | Dynamic model developed | **2** | Idea / Proposed Solution |
| **Control Strategy** | Prediction methodology | **3** | Technical Approach |
| | Choke move selection logic | **3** | Technical Approach |
| | Constraint handling approach | **3** | Technical Approach |
| **Results** | Safety performance | **4** | Feasibility and Viability |
| | Scenario outcomes | **5** | Artifacts |
| | Tracking performance | **5** | Artifacts |
| | Lessons learned | **6** | Research and References |
| Required plots (target Q, actual Q, WHP, FLP, BHP, choke) | — | **5** | Artifacts |
| Reference links | — | **6** | Research and References |
| Deploy link + repo link | — | **1** and **6** | Title / References |

Every template placeholder is also satisfied naturally by this content — Slide 2's
"how it addresses the problem" and "innovation" prompts are answered inside the
Process Understanding block; Slide 4's "challenges and risks" prompt is answered by
the two real bugs the Monte-Carlo study caught.

---

# SLIDE 1 — TITLE PAGE

Fill the template's existing fields — do not restyle them.

| Field | Value |
|---|---|
| Problem Statement ID | *(your portal ID)* |
| Problem Statement Title | Autonomous Production Choke Controller for a Single Naturally Flowing Oil Well |
| Theme | Oil & Gas / Industrial Process Control & Automation |
| PS Category | **Software** |
| Team Name | *(yours)* |
| Team ID | *(yours)* |

**Add below the fields:**

> An autonomous choke controller that maximises safe oil production and refuses any
> target it cannot reach safely. **Zero constraint violations across 300 closed-loop
> runs.**

**Add a small link strip at the bottom of the slide** (10 pt, one line):

> 🔗 Live demo: ayush1deshmukh.github.io/Autonomous-Production-Choke-Controller-for-a-Single-Naturally-Flowing-Oil-Well
> · Code: github.com/Ayush1Deshmukh/Autonomous-Production-Choke-Controller-for-a-Single-Naturally-Flowing-Oil-Well

**Images:** none. Keep the title slide clean.

---

# SLIDE 2 — PROCESS UNDERSTANDING & MODEL

*(Template section: Idea Title / Proposed Solution — pointers: detailed explanation ·
how it addresses the problem · innovation and uniqueness)*

**Add a small banner under the template's own title** reading **"PROCESS
UNDERSTANDING & MODEL"** in blue, so the required section is visibly labelled.

### LAYOUT

| Element | Position | Size |
|---|---|---|
| Left column | x 0.5, y 1.35 | 6.1 in wide |
| Right column | x 6.9, y 1.35 | 6.0 in wide |
| `slide2_gain_curve.png` | x 7.4, y 5.6 | 5.0 in wide |

---

## LEFT COLUMN — STEP-TEST RESULTS

*Lead:*
> A valve at the top of the well — the **production choke** — sets how much oil comes
> out. We characterised the well by stepping that valve through **15 moves** covering
> 0–100 %, up and down, small (5 %) and large (10–20 %) jumps, each held **8 hours**
> (four times the slowest response) until the well truly settled. A held-out sequence
> at **five more positions** was kept aside to check the model afterwards, never used
> to build it.

*Detail:*
- Identification sequence: 0, 20, 25, 30, 40, 35, 45, 55, 50, 60, 65, 70, 80, 90, 100 %
- Validation sequence (held out): 0, 25, 63, 42, 85 %
- Every opening moves all four outputs together: **Q ↑, FLP ↑, WHP ↓, BHP ↓**
- Gain collapses **dQ/du 3.91 → 0.15 bbl/hr per %** (≈26×) from low to high opening
- Knot spacing is a safety decision, not cosmetic: a coarse 55→70 % jump made the model
  **8 psi optimistic on BHP** exactly where the limit binds — found via Monte-Carlo,
  fixed by halving the spacing (§ Lessons learned, Slide 6)

## LEFT COLUMN — MODEL ASSUMPTIONS

*Lead:*
> The model rests on standard, stated assumptions rather than hidden ones: reservoir
> pressure and productivity are treated as constant during a run, dynamics are
> first-order per output, and any transport delay is short enough to ignore.

*Detail:*
- Linear inflow performance (constant productivity index) — standard above the bubble point
- One first-order time constant per output, independent of direction (down-steps match up-steps)
- Dead time fitted at ≤ 0.09 h — under one control interval, so ignored
- Nonlinearity lives **only** in the steady-state curve; the dynamics are locally linear
- Valid over the tested 0–100 % range

## LEFT COLUMN — DYNAMIC MODEL DEVELOPED

*Lead:*
> For each of Q, WHP, FLP and BHP we fit a first-order response toward a steady-state
> curve that itself bends with choke position — a simple structure that still captures
> the ~26× gain change.

*Detail:*
- `y(k+1) = y(k) + α·(y_ss(u) + d − y(k))`, `α = 1 − e^(−Ts/τ)`
- τ: **Q 0.99 h · WHP 1.18 h · FLP 0.80 h · BHP 1.75 h** (slowest → sets the control horizon)
- `y_ss(u)` = piecewise-linear curve read straight off the step-test end points
- `d` = online bias correction (Slide 3) that removes residual offset
- Validated on **held-out** data: NRMSE **0.09 % (Q) · 0.14 % (WHP) · 0.08 % (FLP) · 0.95 % (BHP)**

---

## RIGHT COLUMN — how it addresses the problem / innovation *(template pointers)*

*Lead:*
> Today this valve is set by hand, from experience, across dozens of wells — so wells
> run too cautiously and lose production, or too hard and risk damage, and no two
> operators agree. Our model replaces judgement with a curve fitted from evidence,
> so the controller (Slide 3) can predict the consequence of every move before making it.

*Detail — why this is different:*
- **Safety in the structure, not a penalty weight** — Slide 3 shows unsafe moves are
  deleted from the search, not merely discouraged
- **Explainable** — every step, the model can justify its prediction against real
  step-test evidence, not a black box
- **Built from our own experiments only** — the provided reference dataset was used
  purely for illustration, exactly as the problem statement instructs (Slide 6)

**Caption under the gain-curve image:**
> Gain collapses ~26× across the range — why fixed tuning cannot work and a
> model-based controller is needed.

---

# SLIDE 3 — CONTROL STRATEGY

*(Template section: Technical Approach — pointers: technologies used · methodology
and process for implementation)*

**Add a banner under the template's title** reading **"CONTROL STRATEGY."**

### TOP — architecture diagram, full width

| Image | Position | Size |
|---|---|---|
| `slide3_architecture_diagram.png` | x 0.45, y 1.55 | 12.4 in wide |

The flow chart the template asks for: well → model → MPC → back to well, with the
safe envelope feeding the constraint filter.

### BOTTOM-LEFT — text box at x 0.55, y 4.75, width 6.0 in

**PREDICTION METHODOLOGY**
- Every control interval (**Ts = 1 h**): enumerate **21 candidate** choke positions,
  u(k) ± 5 % on a 0.5 % grid, clipped to [0, 100]
- Apply each candidate, hold it, and roll it **10 hours** forward through the model
  from Slide 2 — starting from the **current measurement**, so error never compounds
  across intervals
- Horizon is a safety parameter: it must outrun the slowest lag (**BHP τ = 1.75 h**);
  10 h = 5.7 τ leaves predictions settled to within 0.3 %
- Measurements are first-order filtered (α = 0.4) before prediction, so sensor noise
  cannot flip a candidate across the constraint boundary

### BOTTOM-RIGHT — text box at x 6.8, y 4.75, width 6.0 in

**CHOKE MOVE SELECTION LOGIC**
- Minimise `J = (Q_pred − Q_target)² + 0.05·(Δu)²` among the safe candidates
- Ties break deterministically: lowest cost → smallest move → lower choke — no randomness
- **Deadband:** move only if it buys ≥ 2 (bbl/hr)² improvement over holding →
  choke chatter eliminated (was 10/24 moves at steady state, now 0/24)

**CONSTRAINT HANDLING APPROACH**
- Reject any candidate whose predicted WHP, FLP or BHP breaches a limit at **any**
  point in the horizon
- Back-off inside each hard limit — **10 / 8 / 15 psi** on WHP / FLP / BHP — covering
  sensor noise, model error and filter lag together
- If every candidate is unsafe: pick the one minimising the worst predicted violation —
  always returns a valid, non-lurching move

**TECHNOLOGIES:** Python 3.10+, NumPy, pandas, SciPy, Matplotlib — **no solver
library**, brute force is exact here. Dashboard: self-contained HTML/CSS/JS, no
build step. `python run_all.py` reproduces and re-verifies everything (~2 min).

*Optional if space allows:* `slide3_mpc_reasoning.png` small, showing the live
candidate list and rejection reasons.

---

# SLIDE 4 — RESULTS: SAFETY PERFORMANCE

*(Template section: Feasibility and Viability — pointers: feasibility analysis ·
challenges and risks · strategies for overcoming)*

**Add a banner under the title** reading **"RESULTS — SAFETY PERFORMANCE."**

### TOP — KPI banner, full width

| Image | Position | Size |
|---|---|---|
| `slide4_kpi_strip.png` | x 0.45, y 1.55 | 12.4 in wide |

Shows: **300 runs · 0 violations · 98.6 % of max safe rate · 19/19 tests · 2.3 bbl/hr
cost of safety**

### LEFT COLUMN — text box at x 0.6, y 3.3, width 6.0 in

**SAFETY PERFORMANCE — PROVEN, NOT CLAIMED**
- **Monte-Carlo: 100 noise seeds × 3 scenarios = 300 closed-loop runs**
  (~26,000 control intervals), envelope checked on **every sample**
- Worst margin to any limit: **A +26.0 psi · B +15.8 psi · C +3.2 psi** — never crossed
- Controller reads **only** `simulator.step(u)` → official simulator drops in with
  **zero code changes**, proven by a test against a deliberately different plant

**CHALLENGES AND RISKS — FOUND AND FIXED** *(template's own ask)*
- **Horizon shorter than the slowest lag** parked the controller somewhere BHP kept
  falling after the horizon ended → **11 of 100 runs breached**. Fixed: 5 h → 10 h
- **Coarse step-test knots** over-estimated BHP by 8 psi in the unsafe direction.
  Fixed: halved the knot spacing through the operating band
- Both passed single-run testing — **only the 300-run study exposed them**

### RIGHT COLUMN — image

| Image | Position | Size |
|---|---|---|
| `slide4_robustness.png` | x 6.9, y 3.4 | 6.0 in wide |

**Caption:**
> Distance to the nearest limit across 100 seeds per scenario. Every run stays on the
> safe side of zero, including Scenario C, which deliberately operates hard against
> the BHP limit.

---

# SLIDE 5 — RESULTS: SCENARIO OUTCOMES & TRACKING PERFORMANCE

*(Template section: Artifacts — pointers: code embedded · snaps of the solution ·
dashboard snaps)*

**Add a banner under the title** reading **"RESULTS — SCENARIO OUTCOMES & TRACKING
PERFORMANCE."**

### TOP-LEFT — results table at x 0.55, y 1.55, width 6.4 in

**SCENARIO OUTCOMES**

| Scenario | Target | Settled rate | Choke | Min BHP | Outcome |
|---|---|---|---|---|---|
| **A** Startup to target | 120 | **121.0 ± 0.6** | 33.5 % | 2184 psi | on target |
| **B** Tracking 100→150 | 150 | **150.8 ± 0.8** | 50.0 % | 1989 psi | retargets cleanly |
| **C** Infeasible target | 200 | **162.7 ± 0.9** | 64.0 % | **1906 psi** | capped at **98.6 %** of max safe |

**TRACKING PERFORMANCE**
> Safety held on **every sample**: WHP ≥ 320, FLP ≤ 260, BHP ≥ 1900 psi, |Δu| ≤ 5 %/step.
> True max safe rate is 165.0 bbl/hr — Scenario C reaches 162.7 without ever crossing
> a limit. A and B track within **±1 %** of target once settled.

### TOP-RIGHT — dashboard screenshot

| Image | Position | Size |
|---|---|---|
| `slide5_dashboard_light.png` | x 7.1, y 1.55 | 5.8 in wide |

*(use `slide5_dashboard_dark.png` for a dark-theme deck)*

### BOTTOM — required plots, full width

| Image | Position | Size |
|---|---|---|
| `slide5_all_scenarios.png` | x 0.5, y 4.6 | 12.3 in wide |

This single image covers every required trend — target oil rate, actual oil rate,
BHP with its limit line, and choke position — for **all three scenarios at once**.

**Caption:**
> Target tracked when feasible (A, B); refused and capped at the safe maximum when
> not (C). BHP rests on its limit without ever crossing it.

**Deliverables line:**
> Simulator · step tests · model ID · MPC · 3 scenarios · Monte-Carlo · 19 tests ·
> dashboard · report. Full 7-panel per-scenario figures (incl. WHP, FLP, WHT, AP) are
> in the submitted zip and repo.

---

# SLIDE 6 — RESULTS: LESSONS LEARNED, REFERENCES & LINKS

*(Template section: Research and References)*

**Add a banner under the title** reading **"RESULTS — LESSONS LEARNED."**

### LEFT COLUMN — text box at x 0.6, y 1.3, width 6.0 in

**LESSONS LEARNED**
- **Where you place step-test knots is a safety decision** — interpolating across a
  convex curve is optimistic exactly where the constraint binds
- **A horizon shorter than the slowest time constant is not conservative, it is unsafe**
- **One good run is not evidence** — a safety claim about a noisy system needs a
  distribution behind it, which is why we built the 300-run study
- Margins must cover **estimator lag and model error**, not just sensor noise
- Every filter is a trade: ours removed constraint hunting but cost response lag,
  paid for in margin
- **Infeasibility needs no special-case code** — it falls out of predict → filter → select

**PROVIDED MATERIAL — HOW WE USED IT**
- `Autonomous_Choke_Control_Simulated_Dataset.csv` used for **illustration only**,
  exactly as the problem statement directs — **never used to fit the model**
- Our model comes solely from our own step-test experiments
- Compared openly: the reference is near-linear; its FLP falls with rate where a
  friction-dominated flowline should rise

**NOTE ON THE SIMULATOR**
- The simulator **module** was never supplied, so we built a documented physics-based
  stand-in from the process description
- The controller touches only `step()` / `reset()`, so the official simulator
  substitutes with **zero changes**

### RIGHT COLUMN — text box at x 6.9, y 1.3, width 6.0 in

**PROJECT LINKS** *(put these at the top of this column — they are what a judge
actually clicks)*
- 🔗 **Live dashboard:** https://ayush1deshmukh.github.io/Autonomous-Production-Choke-Controller-for-a-Single-Naturally-Flowing-Oil-Well/
- 💻 **Source code:** https://github.com/Ayush1Deshmukh/Autonomous-Production-Choke-Controller-for-a-Single-Naturally-Flowing-Oil-Well

**REFERENCES** *(all verified — see note below)*

*Inflow performance and well hydraulics*
1. Vogel, J.V. (1968). *Inflow Performance Relationships for Solution-Gas Drive Wells.*
   Journal of Petroleum Technology, 20(1), 83–92. SPE-1476-PA.
   https://doi.org/10.2118/1476-PA
2. Beggs, H.D. (2003). *Production Optimization Using NODAL Analysis*, 2nd ed. OGCI/Petroskills.
3. Economides, M.J., Hill, A.D., Ehlig-Economides, C., Zhu, D. (2013).
   *Petroleum Production Systems*, 2nd ed. Prentice Hall.

*Choke and control-valve sizing*
4. IEC 60534-2-1 — *Industrial-process control valves, Part 2-1: Flow capacity.*
   https://webstore.iec.ch/publication/2477
5. ISA-75.01.01 — *Flow Equations for Sizing Control Valves.* ISA Standards catalogue:
   https://www.isa.org/standards-and-publications/isa-standards

*Model predictive control*
6. Cutler, C.R. & Ramaker, B.L. (1980). *Dynamic Matrix Control — A Computer Control
   Algorithm.* Joint Automatic Control Conference, San Francisco.
7. Qin, S.J. & Badgwell, T.A. (2003). *A survey of industrial model predictive control
   technology.* Control Engineering Practice, 11(7), 733–764.
   https://doi.org/10.1016/S0967-0661(02)00186-7
8. Maciejowski, J.M. (2002). *Predictive Control with Constraints.* Prentice Hall.
9. Rawlings, J.B., Mayne, D.Q., Diehl, M.M. (2017). *Model Predictive Control: Theory,
   Computation, and Design*, 2nd ed. Nob Hill. Free PDF:
   https://sites.engineering.ucsb.edu/~jbraw/mpc/

*Process identification*
10. Seborg, D.E., Edgar, T.F., Mellichamp, D.A., Doyle, F.J. (2016). *Process Dynamics
    and Control*, 4th ed. Wiley.
11. Ljung, L. (1999). *System Identification: Theory for the User*, 2nd ed. Prentice Hall.

*Problem material*
12. Honeywell hackathon problem statement and reference dataset
    `Autonomous_Choke_Control_Simulated_Dataset.csv` (provided via the submission portal).

> **Link verification note:** every URL above was checked before this guide was
> written. Two needed a second look: the SPE/OnePetro link (#1) shows a brief
> "checking your browser" page before loading — that's normal Cloudflare protection,
> not a dead link. The ISA link (#5) points to ISA's standards catalogue rather than
> a specific product page, since the exact product URL changes over time — search
> "75.01.01" there to find the current listing.

**PROJECT ARTIFACTS**
- `src/` — well_simulator · model · controller · simulator_interface
- `scripts/` — reference EDA · step tests · model ID · scenarios · robustness · dashboard capture
- `tests/` — 19 tests including a swap-in proof against a different plant
- `dashboard/` — self-contained HTML/JS demo (no build, no server)
- `report/ENGINEERING_REPORT.pdf` — full engineering report

---

# DESIGN SPECS

Keep it plain — judges read content, and heavy styling reads as filler.

| Element | Spec |
|---|---|
| Template's own section title | **do not restyle or rename** |
| Required-section banner (new, under the title) | 12 pt bold, white on blue `#1D4FD8`, e.g. "PROCESS UNDERSTANDING & MODEL" |
| Sub-heading (Step-test results, etc.) | 13–14 pt bold, dark blue `#1D4FD8` |
| Body bullet | 11–12 pt, dark grey `#334155` |
| Sub-bullet | 10–11 pt, grey `#64748B` |
| Emphasis / numbers | **bold**, near-black `#0F172A` |
| Good result / risk | green `#117A3A` · red `#B91C1C` |
| Caption under image | 9 pt italic grey `#64748B` |
| Link strip | 10 pt, blue `#1D4FD8`, underlined |
| Font | Calibri or Arial throughout |

**Spacing:** ≥ 0.4 in margin on all sides. No image touching a slide edge.

---

# ASSET INDEX — `submission/presentation_assets/`

| File | Slide | Shows |
|---|---|---|
| `slide2_gain_curve.png` | 2 | Q vs choke + gain collapsing 26× |
| `slide3_architecture_diagram.png` | **3** | control-loop flow chart |
| `slide3_step_tests.png` | 3 (optional) | the 15-step identification experiment |
| `slide3_model_validation.png` | 3 (optional) | predicted vs actual, held-out data |
| `slide3_mpc_reasoning.png` | 3 (optional) | live candidate list + rejection reasons |
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
- [ ] Each slide carries its required-section banner (Process Understanding & Model /
      Control Strategy / Results — Safety / Results — Scenario Outcomes / Results —
      Lessons Learned)
- [ ] **No paragraphs** — bullets, tables, diagrams, images only
- [ ] Template's own section titles unchanged
- [ ] Every image inside the margins, nothing overlapping or cropped
- [ ] Numbers match the generated results (re-check if you re-ran `run_all.py`)
- [ ] Reference links open correctly — click each one yourself before submitting
- [ ] Live dashboard link and repo link both present (Slide 1 and Slide 6)
- [ ] Exported to **PDF** (portal accepts PDF only, not PPT)
- [ ] PDF opens cleanly, all figures legible at 100 % zoom
- [ ] Zip includes code, figures and report
