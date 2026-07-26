/*
 * controller.js
 * -------------
 * JS port of src/model.py (WellModel) and src/controller.py (ChokeMPC), used
 * by the dashboard's "Live / Custom Target" mode. Logic is a direct 1:1 port
 * of the Python: predict -> constraint-filter -> select, with the same
 * fallback and tie-breaking rules. The model coefficients are the exact
 * fitted values from data/fitted_model.json (embedded in data.js), not
 * re-fit in JS.
 */
(function (global) {
  "use strict";

  const OUTPUTS = ["Q", "WHP", "FLP", "BHP"];

  function interp(x, xp, fp) {
    if (x <= xp[0]) return fp[0];
    if (x >= xp[xp.length - 1]) return fp[fp.length - 1];
    for (let i = 1; i < xp.length; i++) {
      if (x <= xp[i]) {
        const t = (x - xp[i - 1]) / (xp[i] - xp[i - 1]);
        return fp[i - 1] + t * (fp[i] - fp[i - 1]);
      }
    }
    return fp[fp.length - 1];
  }

  class WellModel {
    constructor(modelJson, ts) {
      this.ts = ts;
      this.outputs = modelJson.outputs;
    }
    ySs(name, u) {
      const m = this.outputs[name];
      return interp(u, m.u_knots, m.y_knots);
    }
    alpha(name) {
      const m = this.outputs[name];
      return 1 - Math.exp(-this.ts / m.tau);
    }
    // Predict a trajectory given a starting measurement, a sequence of choke
    // moves (move-blocked), and an output disturbance/bias estimate.
    predict(y0, uSeq, disturbance) {
      const d = disturbance || { Q: 0, WHP: 0, FLP: 0, BHP: 0 };
      const y = Object.assign({}, y0);
      const traj = { Q: [], WHP: [], FLP: [], BHP: [] };
      for (const u of uSeq) {
        for (const k of OUTPUTS) {
          const target = this.ySs(k, u) + (d[k] || 0);
          y[k] += this.alpha(k) * (target - y[k]);
          traj[k].push(y[k]);
        }
      }
      traj.Q = traj.Q.map((v) => Math.max(v, 0));
      return traj;
    }
  }

  class ChokeMPC {
    constructor(model, limits, params) {
      this.model = model;
      this.limits = limits;
      this.p = params;
      this.disturbance = { Q: 0, WHP: 0, FLP: 0, BHP: 0 };
      this.lastPrediction = null;
    }

    _updateBias(measured) {
      if (!this.lastPrediction) return;
      const a = this.p.bias_filter_alpha;
      for (const k of OUTPUTS) {
        const err = measured[k] - this.lastPrediction[k];
        this.disturbance[k] = (1 - a) * this.disturbance[k] + a * err;
      }
    }

    _candidateGrid(uCurrent) {
      const lo = Math.max(this.p.u_min, uCurrent - this.p.max_move);
      const hi = Math.min(this.p.u_max, uCurrent + this.p.max_move);
      const n = Math.max(Math.round((hi - lo) / this.p.candidate_step) + 1, 1);
      const grid = [];
      for (let i = 0; i < n; i++) grid.push(lo + ((hi - lo) * i) / Math.max(n - 1, 1));
      if (!grid.some((v) => Math.abs(v - uCurrent) < 1e-9)) grid.push(uCurrent);
      grid.sort((a, b) => a - b);
      return grid;
    }

    _violation(traj) {
      const L = this.limits, m = this.p;
      const maxArr = (arr) => Math.max.apply(null, arr);
      const minArr = (arr) => Math.min.apply(null, arr);
      let v = 0;
      v += Math.max(0, (L.whp_min + m.margin_whp) - minArr(traj.WHP));
      v += Math.max(0, maxArr(traj.WHP) - (L.whp_max - m.margin_whp));
      v += Math.max(0, (L.flp_min + m.margin_flp) - minArr(traj.FLP));
      v += Math.max(0, maxArr(traj.FLP) - (L.flp_max - m.margin_flp));
      v += Math.max(0, (L.bhp_min + m.margin_bhp) - minArr(traj.BHP));
      v += Math.max(0, maxArr(traj.BHP) - (L.bhp_max - m.margin_bhp));
      return v;
    }

    _rejectReason(traj) {
      const L = this.limits, m = this.p;
      const checks = [
        ["BHP", Math.min.apply(null, traj.BHP), L.bhp_min + m.margin_bhp, "min"],
        ["BHP", Math.max.apply(null, traj.BHP), L.bhp_max - m.margin_bhp, "max"],
        ["WHP", Math.min.apply(null, traj.WHP), L.whp_min + m.margin_whp, "min"],
        ["WHP", Math.max.apply(null, traj.WHP), L.whp_max - m.margin_whp, "max"],
        ["FLP", Math.min.apply(null, traj.FLP), L.flp_min + m.margin_flp, "min"],
        ["FLP", Math.max.apply(null, traj.FLP), L.flp_max - m.margin_flp, "max"],
      ];
      for (const [name, val, bound, kind] of checks) {
        if (kind === "min" && val < bound) {
          const k = traj[name].indexOf(Math.min.apply(null, traj[name]));
          return `${name} ${val.toFixed(0)} < ${bound.toFixed(0)} at k+${k + 1}`;
        }
        if (kind === "max" && val > bound) {
          const k = traj[name].indexOf(Math.max.apply(null, traj[name]));
          return `${name} ${val.toFixed(0)} > ${bound.toFixed(0)} at k+${k + 1}`;
        }
      }
      return null;
    }

    step(measured, uCurrent, targetQ) {
      this._updateBias(measured);
      const grid = this._candidateGrid(uCurrent);
      const results = [];

      for (const u of grid) {
        const uSeq = new Array(this.p.horizon).fill(u);
        const traj = this.model.predict(measured, uSeq, this.disturbance);
        const viol = this._violation(traj);
        const feasible = viol <= 1e-9;
        const reason = feasible ? null : this._rejectReason(traj);
        const qEnd = traj.Q[traj.Q.length - 1];
        const du = u - uCurrent;
        const cost = Math.pow(qEnd - targetQ, 2) + this.p.move_penalty * du * du;
        results.push({ u, du, feasible, reason, qEnd, trajectory: traj, cost, violation: viol });
      }

      const feasibleResults = results.filter((r) => r.feasible);
      const allInfeasible = feasibleResults.length === 0;

      let chosen;
      if (!allInfeasible) {
        chosen = feasibleResults.reduce((best, r) => {
          const key = (x) => [Math.round(x.cost * 1e6), Math.round(Math.abs(x.du) * 1e6), x.u];
          const a = key(r), b = key(best);
          return a[0] !== b[0] ? (a[0] < b[0] ? r : best)
            : a[1] !== b[1] ? (a[1] < b[1] ? r : best)
            : (a[2] < b[2] ? r : best);
        });
      } else {
        chosen = results.reduce((best, r) => {
          const key = (x) => [Math.round(x.violation * 1e6), Math.round(Math.abs(x.du) * 1e6), x.u];
          const a = key(r), b = key(best);
          return a[0] !== b[0] ? (a[0] < b[0] ? r : best)
            : a[1] !== b[1] ? (a[1] < b[1] ? r : best)
            : (a[2] < b[2] ? r : best);
        });
      }

      this.lastPrediction = {
        Q: chosen.trajectory.Q[0], WHP: chosen.trajectory.WHP[0],
        FLP: chosen.trajectory.FLP[0], BHP: chosen.trajectory.BHP[0],
      };

      return {
        uSelected: chosen.u,
        uPrevious: uCurrent,
        targetQ,
        candidates: results,
        selected: chosen,
        allInfeasible,
        disturbance: Object.assign({}, this.disturbance),
      };
    }
  }

  global.WellModel = WellModel;
  global.ChokeMPC = ChokeMPC;
})(typeof window !== "undefined" ? window : globalThis);
