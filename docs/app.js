/*
 * app.js
 * ------
 * Dashboard application logic:
 *   - scenario replay (A/B/C) from the precomputed Python pipeline logs
 *   - a live/custom-target mode driven by the JS ports in plant.js / controller.js
 *   - canvas trend charts with the safe operating envelope drawn in
 *   - an animated well schematic carrying live values
 *   - operating-envelope margin bars
 *   - the MPC "reasoning" panel: every candidate move considered this step,
 *     which were rejected and why, and which was selected
 */
(function () {
  "use strict";

  const D = window.DASHBOARD_DATA;
  const L = D.limits;
  const CTRL = D.controller;

  const $ = (s) => document.querySelector(s);
  const scenarioBtns = document.querySelectorAll(".scenario-btn[data-scenario]");
  const liveBtn = $("#btn-live");
  const playBtn = $("#btn-play");
  const resetBtn = $("#btn-reset");
  const speedSel = $("#speed");
  const scrubber = $("#scrubber");
  const scrubLabel = $("#scrub-label");
  const customPanel = $("#custom-panel");
  const targetSlider = $("#target-slider");
  const targetVal = $("#target-val");
  const scenarioDesc = $("#scenario-desc");
  const runState = $("#run-state");
  const runStateText = $("#run-state-text");
  const mpcStepEl = $("#mpc-step");
  const verdictEl = $("#verdict");
  const candidateStrip = $("#candidate-strip");
  const rejectList = $("#reject-list");
  const stripLo = $("#strip-lo");
  const stripHi = $("#strip-hi");
  const envelopeEl = $("#envelope");
  const flowTag = $("#flow-tag");

  const chips = {
    time: $("#chip-time"), q: $("#chip-q"), err: $("#chip-err"),
    choke: $("#chip-choke"), margin: $("#chip-margin"), feas: $("#chip-feas"),
  };
  const canvases = {
    Q: $("#chart-q"), WHP: $("#chart-whp"), FLP: $("#chart-flp"),
    BHP: $("#chart-bhp"), choke: $("#chart-choke"),
  };
  const sch = {
    q: $("#sch-q"), whp: $("#sch-whp"), flp: $("#sch-flp"),
    bhp: $("#sch-bhp"), choke: $("#sch-choke"),
    chokeFill: $("#choke-fill"), flowAnim: $("#flowanim"),
  };

  const PRESSURES = [
    { key: "WHP", label: "WHP", min: L.whp_min, max: L.whp_max, margin: CTRL.margin_whp },
    { key: "FLP", label: "FLP", min: L.flp_min, max: L.flp_max, margin: CTRL.margin_flp },
    { key: "BHP", label: "BHP", min: L.bhp_min, max: L.bhp_max, margin: CTRL.margin_bhp },
  ];

  const cssVar = (n) => getComputedStyle(document.documentElement).getPropertyValue(n).trim();

  // ---- theme: explicit choice wins, otherwise follow the OS ----------------
  const themeBtn = $("#theme-btn");
  function systemDark() {
    return window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches;
  }
  function isDark() {
    const t = document.documentElement.getAttribute("data-theme");
    if (t === "dark") return true;
    if (t === "light") return false;
    return systemDark();
  }
  function applyTheme(t) {
    if (t) document.documentElement.setAttribute("data-theme", t);
    else document.documentElement.removeAttribute("data-theme");
    try { t ? localStorage.setItem("choke-theme", t) : localStorage.removeItem("choke-theme"); } catch (e) {}
    // canvases are painted, not styled — repaint them on every theme change
    requestAnimationFrame(() => requestAnimationFrame(render));
  }
  (function initTheme() {
    let saved = null;
    try { saved = localStorage.getItem("choke-theme"); } catch (e) {}
    if (saved === "dark" || saved === "light") document.documentElement.setAttribute("data-theme", saved);
  })();
  // Theme flip. Where supported, reveal the new theme as a circle expanding
  // out of the toggle button itself; otherwise just cross-fade via CSS.
  themeBtn.addEventListener("click", () => {
    const next = isDark() ? "light" : "dark";
    const reduced = window.matchMedia &&
      window.matchMedia("(prefers-reduced-motion: reduce)").matches;

    if (!document.startViewTransition || reduced) { applyTheme(next); return; }

    const r = themeBtn.getBoundingClientRect();
    const cx = r.left + r.width / 2, cy = r.top + r.height / 2;
    const radius = Math.hypot(
      Math.max(cx, window.innerWidth - cx),
      Math.max(cy, window.innerHeight - cy)
    );
    const vt = document.startViewTransition(() => applyTheme(next));
    vt.ready.then(() => {
      document.documentElement.animate(
        { clipPath: [`circle(0px at ${cx}px ${cy}px)`, `circle(${radius}px at ${cx}px ${cy}px)`] },
        { duration: 620, easing: "cubic-bezier(.22,1,.36,1)",
          pseudoElement: "::view-transition-new(root)" }
      );
    }).catch(() => {});
  });

  // Replay the staggered entrance animation (on load and on scenario switch)
  function replayEntrance() {
    const els = document.querySelectorAll(".card, .chip");
    els.forEach((el) => el.classList.remove("enter"));
    void document.body.offsetWidth;               // force reflow so it re-runs
    els.forEach((el) => el.classList.add("enter"));
  }

  // ==================================================================
  // Canvas chart renderer (no external chart library)
  // ==================================================================
  function fitCanvas(canvas, cssHeight) {
    const dpr = window.devicePixelRatio || 1;
    const w = Math.max(canvas.parentElement.clientWidth - 28, 120);
    canvas.style.width = w + "px";
    canvas.style.height = cssHeight + "px";
    canvas.width = Math.round(w * dpr);
    canvas.height = Math.round(cssHeight * dpr);
    const ctx = canvas.getContext("2d");
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    return { ctx, w, h: cssHeight };
  }

  function niceRange(vals, padFrac) {
    const clean = vals.filter((v) => v != null && isFinite(v));
    let lo = Math.min.apply(null, clean);
    let hi = Math.max.apply(null, clean);
    if (!isFinite(lo) || !isFinite(hi)) { lo = 0; hi = 1; }
    if (hi - lo < 1e-6) { hi += 1; lo -= 1; }
    const pad = (hi - lo) * padFrac;
    return [lo - pad, hi + pad];
  }

  function drawChart(canvas, opts) {
    const { ctx, w, h } = fitCanvas(canvas, opts.height || 148);
    ctx.clearRect(0, 0, w, h);
    const padL = 48, padR = 58, padT = 10, padB = 20;
    const plotW = w - padL - padR, plotH = h - padT - padB;
    const n = opts.t.length;
    if (n < 1 || plotW <= 0) return;

    const gridColor = cssVar("--line-soft") || "#eef1f5";
    const inkDim = cssVar("--ink-dim") || "#64748b";
    const panel = cssVar("--panel") || "#fff";

    const xMax = Math.max(opts.xDomainMax || opts.t[n - 1], opts.t[n - 1], 1e-6);
    const X = (tv) => padL + (tv / xMax) * plotW;

    let all = [];
    opts.series.forEach((s) => { all = all.concat(s.data); });
    if (opts.ghost) all = all.concat(opts.ghost.data);
    if (opts.safeBand) all.push(opts.safeBand.lo, opts.safeBand.hi);
    if (opts.yMin != null) all.push(opts.yMin);
    if (opts.yMax != null) all.push(opts.yMax);
    const [yLo, yHi] = niceRange(all, 0.14);
    const Y = (v) => padT + plotH - ((v - yLo) / (yHi - yLo)) * plotH;

    // ---- safe band + limit lines ----
    if (opts.safeBand) {
      const b = opts.safeBand;
      const yTop = Math.max(Y(b.hi), padT), yBot = Math.min(Y(b.lo), padT + plotH);
      ctx.fillStyle = isDark() ? "rgba(34,197,94,.10)" : "rgba(34,197,94,.09)";
      ctx.fillRect(padL, yTop, plotW, Math.max(yBot - yTop, 0));
      ctx.setLineDash([2, 3]); ctx.lineWidth = 1; ctx.strokeStyle = "#d97706";
      [b.lo + b.marginLo, b.hi - b.marginHi].forEach((v) => {
        if (v > yLo && v < yHi) {
          ctx.beginPath(); ctx.moveTo(padL, Y(v)); ctx.lineTo(padL + plotW, Y(v)); ctx.stroke();
        }
      });
      ctx.setLineDash([5, 4]); ctx.lineWidth = 1.3; ctx.strokeStyle = "#dc2626";
      [b.lo, b.hi].forEach((v) => {
        if (v > yLo && v < yHi) {
          ctx.beginPath(); ctx.moveTo(padL, Y(v)); ctx.lineTo(padL + plotW, Y(v)); ctx.stroke();
        }
      });
      ctx.setLineDash([]);
    }

    // ---- gridlines + axis labels ----
    ctx.font = "10px -apple-system, system-ui, sans-serif";
    ctx.fillStyle = inkDim; ctx.strokeStyle = gridColor; ctx.lineWidth = 1;
    for (let i = 0; i <= 4; i++) {
      const v = yLo + (i / 4) * (yHi - yLo), yy = Y(v);
      ctx.beginPath(); ctx.moveTo(padL, yy); ctx.lineTo(padL + plotW, yy); ctx.stroke();
      ctx.textAlign = "right";
      ctx.fillText(Math.abs(v) >= 100 ? v.toFixed(0) : v.toFixed(1), padL - 6, yy + 3);
    }
    ctx.textAlign = "center";
    for (let i = 0; i <= 5; i++) {
      const tv = (xMax * i) / 5;
      ctx.fillText(tv.toFixed(0) + "h", X(tv), h - 5);
    }
    ctx.textAlign = "left";

    // ---- series (with gradient area fill for the primary series) ----
    opts.series.forEach((s, si) => {
      if (s.fill) {
        const grad = ctx.createLinearGradient(0, padT, 0, padT + plotH);
        grad.addColorStop(0, s.color + "33");
        grad.addColorStop(1, s.color + "05");
        ctx.fillStyle = grad;
        ctx.beginPath();
        ctx.moveTo(X(opts.t[0]), padT + plotH);
        for (let i = 0; i < n; i++) ctx.lineTo(X(opts.t[i]), Y(s.data[i]));
        ctx.lineTo(X(opts.t[n - 1]), padT + plotH);
        ctx.closePath(); ctx.fill();
      }
      ctx.strokeStyle = s.color;
      ctx.lineWidth = s.width || 2;
      ctx.lineJoin = "round"; ctx.lineCap = "round";
      ctx.setLineDash(s.dash || []);
      ctx.beginPath();
      for (let i = 0; i < n; i++) {
        const px = X(opts.t[i]), py = Y(s.data[i]);
        if (i === 0) ctx.moveTo(px, py); else ctx.lineTo(px, py);
      }
      ctx.stroke();
      ctx.setLineDash([]);
    });

    // ---- predicted-horizon ghost ----
    if (opts.ghost && opts.ghost.data.length > 1) {
      const g = opts.ghost;
      ctx.strokeStyle = isDark() ? "#94a3b8" : "#94a3b8";
      ctx.lineWidth = 1.5; ctx.setLineDash([2, 3]);
      ctx.beginPath();
      ctx.moveTo(X(g.t[0]), Y(g.data[0]));
      for (let i = 1; i < g.data.length; i++) ctx.lineTo(X(g.t[i]), Y(g.data[i]));
      ctx.stroke(); ctx.setLineDash([]);
      ctx.fillStyle = "#94a3b8";
      for (let i = 1; i < g.data.length; i++) {
        ctx.beginPath(); ctx.arc(X(g.t[i]), Y(g.data[i]), 1.9, 0, 7); ctx.fill();
      }
    }

    // ---- current-value marker + right-edge pill ----
    const main = opts.series[opts.series.length - 1];
    const lastV = main.data[n - 1];
    const px = X(opts.t[n - 1]), py = Y(lastV);
    ctx.fillStyle = main.color;
    ctx.beginPath(); ctx.arc(px, py, 3.4, 0, 7); ctx.fill();
    ctx.strokeStyle = panel; ctx.lineWidth = 1.6; ctx.stroke();

    const txt = (Math.abs(lastV) >= 100 ? lastV.toFixed(0) : lastV.toFixed(1)) +
      (opts.unit ? " " + opts.unit : "");
    ctx.font = "600 10.5px -apple-system, system-ui, sans-serif";
    const tw = ctx.measureText(txt).width;
    const bx = Math.min(px + 8, w - tw - 12), by = Math.max(Math.min(py, h - 22), padT + 2);
    ctx.fillStyle = main.color;
    const r = 4, bw = tw + 10, bh = 16;
    ctx.beginPath();
    ctx.moveTo(bx + r, by - 8); ctx.arcTo(bx + bw, by - 8, bx + bw, by - 8 + bh, r);
    ctx.arcTo(bx + bw, by - 8 + bh, bx, by - 8 + bh, r);
    ctx.arcTo(bx, by - 8 + bh, bx, by - 8, r); ctx.arcTo(bx, by - 8, bx + bw, by - 8, r);
    ctx.closePath(); ctx.fill();
    ctx.fillStyle = "#fff"; ctx.textAlign = "left";
    ctx.fillText(txt, bx + 5, by + 3.5);
  }

  // ==================================================================
  // Player
  // ==================================================================
  const Player = {
    mode: null, playing: false, idx: 0, speed: "5", timer: null,
    t: [], targetQ: [], Q: [], WHP: [], FLP: [], BHP: [], choke: [],
    decisions: [], liveController: null, livePlant: null, liveU: 0, maxLen: 0,

    loadScenario(key) {
      this.stop();
      this.mode = key;
      const sc = D.scenarios[key];
      scenarioDesc.textContent = sc.description;
      this.t = sc.log.map((r) => r.time_h);
      this.targetQ = sc.log.map((r) => r.target_Q);
      this.Q = sc.log.map((r) => r.Q);
      this.WHP = sc.log.map((r) => r.WHP);
      this.FLP = sc.log.map((r) => r.FLP);
      this.BHP = sc.log.map((r) => r.BHP);
      this.choke = sc.log.map((r) => r.choke_pct);
      this.decisions = sc.decisions;
      this.maxLen = this.t.length;
      this.idx = 1;
      scrubber.max = this.maxLen - 1;
      scrubber.value = 0;
      customPanel.classList.remove("show");
      setActive(key);
      setRunState("ready", "Ready");
      render();
      replayEntrance();
    },

    loadLive() {
      this.stop();
      this.mode = "live";
      scenarioDesc.textContent =
        "Live mode — the plant, the identified model and the brute-force MPC all run in your browser. " +
        "Drag the target slider at any time and watch the controller re-plan, respecting the same " +
        "operating envelope and ±5 %/step ramp limit.";
      const model = new WellModel(D.model, D.ts_hours);
      this.liveController = new ChokeMPC(model, L, CTRL);
      this.livePlant = new WellPlant(D.plant, D.ts_hours, 777, true);
      const first = this.livePlant.reset();
      this.liveU = 0;
      this.t = [0]; this.targetQ = [Number(targetSlider.value)];
      this.Q = [first.Q]; this.WHP = [first.WHP]; this.FLP = [first.FLP]; this.BHP = [first.BHP];
      this.choke = [0];
      this.decisions = [];
      this.idx = 1; this.maxLen = 1;
      scrubber.max = 0; scrubber.value = 0;
      customPanel.classList.add("show");
      setActive(null);
      setRunState("ready", "Ready");
      render();
      replayEntrance();
    },

    stepLive() {
      const j = this.t.length - 1;
      const measured = { Q: this.Q[j], WHP: this.WHP[j], FLP: this.FLP[j], BHP: this.BHP[j] };
      const target = Number(targetSlider.value);
      const decision = this.liveController.step(measured, this.liveU, target);
      this.liveU = decision.uSelected;
      const meas = this.livePlant.step(this.liveU);
      const tNow = this.t[j] + D.ts_hours;
      this.t.push(tNow); this.targetQ.push(target);
      this.Q.push(meas.Q); this.WHP.push(meas.WHP);
      this.FLP.push(meas.FLP); this.BHP.push(meas.BHP);
      this.choke.push(this.liveU);
      this.decisions.push({
        t: tNow - D.ts_hours, u_prev: decision.uPrevious, u_selected: decision.uSelected,
        target_Q: target, all_infeasible: decision.allInfeasible,
        selected_index: decision.candidates.indexOf(decision.selected),
        candidates: decision.candidates.map((c) => ({
          u: c.u, du: c.du, feasible: c.feasible, reason: c.reason, q_end: c.qEnd, cost: c.cost,
        })),
        selected_trajectory: decision.selected.trajectory,
      });
      this.idx = this.t.length; this.maxLen = this.t.length;
      scrubber.max = this.maxLen - 1; scrubber.value = this.maxLen - 1;
    },

    stop() {
      this.playing = false;
      if (this.timer) { clearInterval(this.timer); this.timer = null; }
      playBtn.textContent = "▶";
      playBtn.classList.remove("is-playing");
      if (this.mode && this.idx >= this.maxLen && this.mode !== "live") setRunState("done", "Complete");
      else setRunState("ready", "Paused");
    },

    play() {
      if (this.mode === null) return;
      if (this.mode !== "live" && this.idx >= this.maxLen) { this.idx = 1; }
      this.playing = true;
      playBtn.textContent = "⏸";
      playBtn.classList.add("is-playing");
      setRunState("running", this.mode === "live" ? "Live" : "Running");

      if (this.speed === "instant" && this.mode !== "live") {
        this.idx = this.maxLen;
        scrubber.value = this.maxLen - 1;
        render(); this.stop(); return;
      }
      const ms = this.speed === "instant" ? 30 : 440 / Number(this.speed);
      this.timer = setInterval(() => {
        if (!this.playing) return;
        if (this.mode === "live") {
          this.stepLive();
        } else {
          if (this.idx >= this.maxLen) { this.stop(); render(); return; }
          this.idx += 1;
          scrubber.value = this.idx - 1;
        }
        render();
      }, ms);
    },

    resetRun() {
      this.stop();
      if (this.mode === "live") this.loadLive();
      else this.loadScenario(this.mode || "A");
    },
  };

  function setActive(key) {
    scenarioBtns.forEach((b) => b.classList.toggle("active", b.dataset.scenario === key));
    liveBtn.classList.toggle("active", key === null);
  }
  function setRunState(cls, text) {
    runState.className = "status-pill " + cls;
    runStateText.textContent = text;
  }

  // ==================================================================
  // Schematic
  // ==================================================================
  let flowPhase = 0, lastFrame = 0;
  function animateFlow(ts) {
    const dt = lastFrame ? (ts - lastFrame) : 16;
    lastFrame = ts;
    const i = Math.max(Player.idx - 1, 0);
    const q = Player.Q[i] || 0;
    flowPhase -= (q / 165) * dt * 0.045;   // dash speed proportional to rate
    if (sch.flowAnim) sch.flowAnim.style.strokeDashoffset = flowPhase.toFixed(2);
    requestAnimationFrame(animateFlow);
  }

  function pressureClass(v, lim) {
    if (v < lim.min || v > lim.max) return "bad";
    if (v < lim.min + lim.margin * 2.5 || v > lim.max - lim.margin * 2.5) return "warn";
    return "";
  }

  function renderSchematic(i) {
    const q = Player.Q[i], u = Player.choke[i];
    const vals = { WHP: Player.WHP[i], FLP: Player.FLP[i], BHP: Player.BHP[i] };
    sch.q.textContent = q.toFixed(1) + " bbl/hr";
    sch.choke.textContent = u.toFixed(1) + " %";
    PRESSURES.forEach((p) => {
      const el = sch[p.key.toLowerCase()];
      el.textContent = vals[p.key].toFixed(0) + " psi";
      el.setAttribute("class", "val-lbl " + pressureClass(vals[p.key], p));
    });
    // choke aperture: opening grows from the centre of the bowtie
    const wOpen = 1 + (u / 100) * 19;
    sch.chokeFill.setAttribute("width", wOpen.toFixed(2));
    sch.chokeFill.setAttribute("x", (150 - wOpen / 2).toFixed(2));
    flowTag.textContent = q > 1 ? "flowing · " + q.toFixed(0) + " bbl/hr" : "shut-in";
  }

  // ==================================================================
  // Operating-envelope bars
  // ==================================================================
  function renderEnvelope(i) {
    const vals = { WHP: Player.WHP[i], FLP: Player.FLP[i], BHP: Player.BHP[i] };
    envelopeEl.innerHTML = PRESSURES.map((p) => {
      const v = vals[p.key];
      const frac = Math.min(Math.max((v - p.min) / (p.max - p.min), 0), 1);
      const cls = pressureClass(v, p);
      const marginLo = v - p.min, marginHi = p.max - v;
      const nearest = Math.min(marginLo, marginHi);
      return `
        <div class="env-row">
          <div class="env-head">
            <span>${p.label} <span style="opacity:.7">· ${nearest.toFixed(0)} psi to limit</span></span>
            <b class="${cls === "bad" ? "txt-red" : cls === "warn" ? "txt-amber" : ""}">${v.toFixed(0)} psi</b>
          </div>
          <div class="env-track">
            <div class="env-marker ${cls}" style="left:calc(${(frac * 100).toFixed(2)}% - 1.5px)"></div>
          </div>
          <div class="env-scale"><span>${p.min.toFixed(0)}</span><span>${p.max.toFixed(0)}</span></div>
        </div>`;
    }).join("");
  }

  // ==================================================================
  // KPI chips
  // ==================================================================
  // Animate a value change only when it is slow enough to read — at 5x/instant
  // playback a pop on every step would just be strobing.
  function animatedUpdates() {
    return !Player.playing || Player.speed === "1";
  }

  function setChip(el, value, sub, extraClass) {
    const v = el.querySelector(".value");
    const changed = v.dataset.raw !== value;
    v.dataset.raw = value;
    v.innerHTML = value;
    v.className = "value " + (extraClass || "");
    if (changed && animatedUpdates()) {
      v.classList.add("changed");
      setTimeout(() => v.classList.remove("changed"), 240);
    }
    el.querySelector(".sub").innerHTML = sub || "";
  }

  function renderChips(i) {
    const t = Player.t[i], q = Player.Q[i], tq = Player.targetQ[i], u = Player.choke[i];
    setChip(chips.time, t.toFixed(0) + '<span class="u">h</span>',
      Player.mode === "live" ? "live run" : "of " + Player.t[Player.maxLen - 1].toFixed(0) + " h");
    setChip(chips.q, q.toFixed(1) + '<span class="u">bbl/hr</span>', "target " + tq.toFixed(0));

    const err = q - tq;
    const errCls = Math.abs(err) <= 3 ? "txt-green" : Math.abs(err) <= 15 ? "txt-amber" : "txt-red";
    setChip(chips.err, (err >= 0 ? "+" : "") + err.toFixed(1) + '<span class="u">bbl/hr</span>',
      Math.abs(err) <= 3 ? "on target" : "tracking", errCls);

    const prevU = i > 0 ? Player.choke[i - 1] : u;
    const du = u - prevU;
    setChip(chips.choke, u.toFixed(1) + '<span class="u">%</span>',
      "Δ " + (du >= 0 ? "+" : "") + du.toFixed(1) + " %/step");

    const margins = PRESSURES.map((p) => ({
      name: p.label, m: Math.min(Player[p.key][i] - p.min, p.max - Player[p.key][i]), p,
    }));
    margins.sort((a, b) => a.m - b.m);
    const worst = margins[0];
    const col = worst.m < 0 ? "red" : worst.m < worst.p.margin * 2.5 ? "amber" : "green";
    setChip(chips.margin,
      `<span class="dot ${col}"></span>${worst.m.toFixed(0)}<span class="u">psi</span>`,
      worst.name + " is closest");

    const dec = currentDecision(i);
    if (dec) {
      const nF = dec.candidates.filter((c) => c.feasible).length;
      const cls = dec.all_infeasible ? "txt-red" : nF < dec.candidates.length ? "txt-amber" : "";
      setChip(chips.feas, nF + " / " + dec.candidates.length,
        dec.all_infeasible ? "fallback engaged" : nF < dec.candidates.length
          ? "envelope active" : "unconstrained", cls);
    }
  }

  // ==================================================================
  // Reasoning panel
  // ==================================================================
  function currentDecision(i) {
    if (!Player.decisions.length) return null;
    return Player.decisions[Math.min(i, Player.decisions.length - 1)];
  }

  function explain(dec, i) {
    const q = Player.Q[i], tq = Player.targetQ[i];
    const err = q - tq;
    const feas = dec.candidates.filter((c) => c.feasible);
    const rejected = dec.candidates.filter((c) => !c.feasible);
    const maxFeasU = feas.length ? Math.max.apply(null, feas.map((c) => c.u)) : null;
    const cappedAbove = rejected.some((c) => maxFeasU != null && c.u > maxFeasU);

    if (dec.all_infeasible) {
      return {
        cls: "capped",
        html: `<b>All ${dec.candidates.length} candidate moves are predicted unsafe.</b> The controller
               fell back to the least-bad move (smallest predicted violation) and is backing off.`,
      };
    }
    if (cappedAbove && err < -5) {
      const reason = rejected[0] ? rejected[0].reason.split(" ")[0] : "a pressure limit";
      return {
        cls: "capped",
        html: `Target is <b>${tq.toFixed(0)} bbl/hr</b> but opening further is blocked by
               <b>${reason}</b>. The controller is holding at the <b>maximum safe rate</b>
               (${q.toFixed(1)} bbl/hr) rather than chasing an unreachable target.`,
      };
    }
    if (Math.abs(err) <= 3) {
      return {
        cls: "ontarget",
        html: `<b>On target.</b> Predicted flow sits within ${Math.abs(err).toFixed(1)} bbl/hr of the
               ${tq.toFixed(0)} bbl/hr setpoint, so the controller is making only fine trim moves.`,
      };
    }
    const dir = dec.u_selected > dec.u_prev ? "Opening" : dec.u_selected < dec.u_prev ? "Closing" : "Holding";
    return {
      cls: "",
      html: `<b>${dir} the choke</b> ${dir === "Holding" ? "" :
        "by " + Math.abs(dec.u_selected - dec.u_prev).toFixed(1) + " %"} to move flow
             ${err < 0 ? "up toward" : "down toward"} the ${tq.toFixed(0)} bbl/hr target,
             within the ±${CTRL.max_move} %/step ramp limit.`,
    };
  }

  function renderReasoning(i) {
    const dec = currentDecision(i);
    if (!dec) {
      candidateStrip.innerHTML = ""; rejectList.innerHTML = "";
      mpcStepEl.innerHTML = ""; verdictEl.innerHTML = "";
      stripLo.textContent = "—"; stripHi.textContent = "—";
      return;
    }

    const v = explain(dec, i);
    const verdictChanged = verdictEl.dataset.raw !== v.html;
    verdictEl.dataset.raw = v.html;
    verdictEl.className = "verdict " + v.cls;
    verdictEl.innerHTML = v.html;
    if (verdictChanged && animatedUpdates()) {
      verdictEl.classList.add("flash");
      setTimeout(() => verdictEl.classList.remove("flash"), 320);
    }

    const lo = dec.candidates[0].u, hi = dec.candidates[dec.candidates.length - 1].u;
    stripLo.textContent = lo.toFixed(1) + " %";
    stripHi.textContent = hi.toFixed(1) + " %";

    mpcStepEl.innerHTML =
      `t = <b>${dec.t.toFixed(0)} h</b> · choke <b>${dec.u_prev.toFixed(1)} %</b> → ` +
      `<b>${dec.u_selected.toFixed(1)} %</b> · target <b>${dec.target_Q.toFixed(0)} bbl/hr</b> · ` +
      `horizon <b>${CTRL.horizon} h</b>`;

    candidateStrip.classList.toggle("no-anim", !animatedUpdates());
    candidateStrip.innerHTML = dec.candidates.map((c, ci) => {
      const cls = "cand " + (c.feasible ? "feasible" : "infeasible") +
        (ci === dec.selected_index ? " selected" : "");
      const tip = c.feasible
        ? `u=${c.u.toFixed(1)}% (Δ${c.du >= 0 ? "+" : ""}${c.du.toFixed(1)}) · predicted Q=${c.q_end.toFixed(1)} bbl/hr`
        : `u=${c.u.toFixed(1)}% (Δ${c.du >= 0 ? "+" : ""}${c.du.toFixed(1)}) · REJECTED — ${c.reason}`;
      return `<div class="${cls}" style="animation-delay:${(ci * 7)}ms" ` +
             `data-tip="${tip.replace(/"/g, "&quot;")}"></div>`;
    }).join("");

    const rejected = dec.candidates.filter((c) => !c.feasible);
    rejectList.innerHTML = rejected.length
      ? rejected.map((c, ri) =>
          `<div class="row" style="animation-delay:${ri * 22}ms">` +
          `<span>u = ${c.u.toFixed(1)} % (Δ${c.du >= 0 ? "+" : ""}${c.du.toFixed(1)})</span>` +
          `<b>${c.reason}</b></div>`
        ).join("")
      : `<div class="row none">All ${dec.candidates.length} candidates were inside the envelope at this step.</div>`;
  }

  // ==================================================================
  // Master render
  // ==================================================================
  function render() {
    if (!Player.t.length) return;
    const i = Math.min(Math.max(Player.idx - 1, 0), Player.t.length - 1);
    const tSlice = Player.t.slice(0, i + 1);
    const xMax = Player.t[Player.maxLen - 1];
    const dec = currentDecision(i);

    const ghostFor = (key) => {
      if (!dec || !dec.selected_trajectory || !dec.selected_trajectory[key]) return null;
      const traj = dec.selected_trajectory[key];
      const t0 = Player.t[i];
      return {
        t: [t0].concat(traj.map((_, k) => t0 + D.ts_hours * (k + 1))),
        data: [Player[key][i]].concat(traj),
      };
    };

    drawChart(canvases.Q, {
      t: tSlice, xDomainMax: xMax, unit: "bbl/hr", height: 156,
      series: [
        { data: Player.targetQ.slice(0, i + 1), color: "#94a3b8", dash: [5, 4], width: 1.5 },
        { data: Player.Q.slice(0, i + 1), color: "#2563eb", width: 2.3, fill: true },
      ],
      ghost: ghostFor("Q"),
    });
    drawChart(canvases.WHP, {
      t: tSlice, xDomainMax: xMax, unit: "psi",
      series: [{ data: Player.WHP.slice(0, i + 1), color: "#059669", width: 2, fill: true }],
      safeBand: { lo: L.whp_min, hi: L.whp_max, marginLo: CTRL.margin_whp, marginHi: CTRL.margin_whp },
      ghost: ghostFor("WHP"),
    });
    drawChart(canvases.FLP, {
      t: tSlice, xDomainMax: xMax, unit: "psi",
      series: [{ data: Player.FLP.slice(0, i + 1), color: "#d97706", width: 2, fill: true }],
      safeBand: { lo: L.flp_min, hi: L.flp_max, marginLo: CTRL.margin_flp, marginHi: CTRL.margin_flp },
      ghost: ghostFor("FLP"),
    });
    drawChart(canvases.BHP, {
      t: tSlice, xDomainMax: xMax, unit: "psi",
      series: [{ data: Player.BHP.slice(0, i + 1), color: "#dc2626", width: 2, fill: true }],
      safeBand: { lo: L.bhp_min, hi: L.bhp_max, marginLo: CTRL.margin_bhp, marginHi: CTRL.margin_bhp },
      ghost: ghostFor("BHP"),
    });
    drawChart(canvases.choke, {
      t: tSlice, xDomainMax: xMax, unit: "%",
      series: [{ data: Player.choke.slice(0, i + 1), color: "#64748b", width: 2.2, fill: true }],
      yMin: 0, yMax: 100,
    });

    scrubLabel.textContent = `${Player.t[i].toFixed(0)} / ${xMax.toFixed(0)} h`;
    renderChips(i);
    renderSchematic(i);
    renderEnvelope(i);
    renderReasoning(i);
  }

  // ==================================================================
  // Controls
  // ==================================================================
  scenarioBtns.forEach((b) => b.addEventListener("click", () => Player.loadScenario(b.dataset.scenario)));
  liveBtn.addEventListener("click", () => Player.loadLive());
  playBtn.addEventListener("click", () => (Player.playing ? Player.stop() : Player.play()));
  resetBtn.addEventListener("click", () => Player.resetRun());
  speedSel.addEventListener("change", () => {
    Player.speed = speedSel.value;
    if (Player.playing) { Player.stop(); Player.play(); }
  });
  scrubber.addEventListener("input", () => {
    if (Player.mode === "live") return;
    Player.stop();
    Player.idx = Number(scrubber.value) + 1;
    render();
  });
  targetSlider.addEventListener("input", () => {
    targetVal.textContent = Number(targetSlider.value).toFixed(0) + " bbl/hr";
  });

  document.addEventListener("keydown", (e) => {
    if (e.target.tagName === "INPUT" || e.target.tagName === "SELECT") return;
    if (e.code === "Space") { e.preventDefault(); Player.playing ? Player.stop() : Player.play(); }
    else if (e.key === "r" || e.key === "R") Player.resetRun();
    else if (e.key === "1") Player.loadScenario("A");
    else if (e.key === "2") Player.loadScenario("B");
    else if (e.key === "3") Player.loadScenario("C");
    else if (e.key === "l" || e.key === "L") Player.loadLive();
  });

  let resizeTimer = null;
  window.addEventListener("resize", () => {
    clearTimeout(resizeTimer);
    resizeTimer = setTimeout(render, 90);
  });
  if (window.matchMedia) {
    const mq = window.matchMedia("(prefers-color-scheme: dark)");
    if (mq.addEventListener) mq.addEventListener("change", render);
  }

  // ==================================================================
  // Init
  // ==================================================================
  Player.speed = speedSel.value;
  targetVal.textContent = Number(targetSlider.value).toFixed(0) + " bbl/hr";
  Player.loadScenario("A");
  requestAnimationFrame(animateFlow);
})();
