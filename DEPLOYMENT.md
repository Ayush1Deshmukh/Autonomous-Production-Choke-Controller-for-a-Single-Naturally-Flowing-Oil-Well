# Deployment Guide

What actually gets deployed here is **the dashboard** — a fully static page
(`dashboard/`, 780 KB total) with no build step, no backend and no network calls.
The Python side is a batch pipeline, not a service, so it is *run*, not *hosted*.

Verified before writing this guide: the dashboard uses only relative paths and
loads correctly when served from a sub-directory, which is what GitHub Pages does
(`https://user.github.io/repo/`). All five assets returned HTTP 200 and the page
rendered with no console errors.

Pick one of the options below. **Option A is the one to use for a hackathon** —
it gives judges a clickable link.

---

## 0. One-time preparation

```bash
cd ~/Development/gird
python run_all.py          # regenerates data/, figures/ and dashboard/data.js
```

This matters: `dashboard/data.js` is a generated file holding the scenario logs and
the fitted model. **If you deploy without it, the dashboard will be blank.** It is
committed on purpose (see `.gitignore`) so a fresh clone works immediately.

Quick sanity check before you push:

```bash
ls -la dashboard/data.js     # should be ~690 KB, not 0
```

---

## Option A — GitHub Pages (free, public link, recommended)

**Result:** `https://<your-username>.github.io/<repo-name>/`

### A1. Create the repository

```bash
cd ~/Development/gird
git init
git add .
git commit -m "Autonomous production choke controller"
git branch -M main
```

Create an empty repo on GitHub (no README, no .gitignore — you already have both), then:

```bash
git remote add origin https://github.com/<your-username>/<repo-name>.git
git push -u origin main
```

`.venv/` is ignored, so you are pushing about **19 MB**, mostly figures. That is fine.

### A2. Put the dashboard where Pages can find it

GitHub Pages serves from the repo root or from `/docs`. The simplest reliable route
is a `docs/` copy:

```bash
mkdir -p docs
cp dashboard/index.html dashboard/style.css dashboard/app.js \
   dashboard/plant.js dashboard/controller.js dashboard/data.js docs/
git add docs && git commit -m "Publish dashboard to docs/" && git push
```

Do **not** copy `dashboard/parity_check.py` — it is a dev script, not part of the page.

### A3. Turn Pages on

On GitHub: **Settings → Pages → Build and deployment**
- Source: **Deploy from a branch**
- Branch: **main**, folder: **/docs**
- Save

Wait 1–2 minutes, then open `https://<your-username>.github.io/<repo-name>/`.

### A4. Keeping it updated

Any time you re-run the pipeline:

```bash
python run_all.py
cp dashboard/data.js docs/data.js
git add docs data figures && git commit -m "Refresh results" && git push
```

> **Cache note:** the asset URLs carry a version query (`app.js?v=9`). If you edit
> `app.js` or `style.css`, bump that number in `index.html` (and in your `docs/` copy),
> otherwise returning visitors get the cached old file.

---

## Option B — Netlify Drop (fastest, ~30 seconds, no git)

1. Go to **https://app.netlify.com/drop**
2. Drag the **`dashboard/` folder** onto the page
3. You get a live URL immediately, e.g. `https://random-name-123.netlify.app`
4. Optional: *Site settings → Change site name* to something readable

Good when you want a link during judging without touching git. The URL is temporary
unless you claim the site to a free account.

---

## Option C — Vercel

```bash
npm install -g vercel
cd ~/Development/gird/dashboard
vercel --prod
```

Accept the defaults. When it asks for a build command, leave it **empty** — this is a
static site with nothing to build. Output directory: `.` (current folder).

---

## Option D — Cloudflare Pages

Connect the GitHub repo, then set:

| Setting | Value |
|---|---|
| Framework preset | **None** |
| Build command | *(leave empty)* |
| Build output directory | `dashboard` |

No build step, so deploys take a few seconds.

---

## Option E — Offline / judges run it themselves

This is what the submitted zip is for, and it needs no hosting at all.

**Just the dashboard** — unzip and double-click `dashboard/index.html`. It works from
`file://` with no server.

> One caveat: some browsers block `localStorage` on `file://`, so the light/dark toggle
> will not remember your choice between reloads. Everything else works. Serving over
> HTTP (below) fixes it.

**The full pipeline:**

```bash
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python run_all.py
```

Runs in about 2 minutes and re-verifies everything: scenarios, the 300-run
Monte-Carlo study and the 19 tests. Exits non-zero if anything fails.

**Serve locally over HTTP:**

```bash
python -m http.server 8000 --directory dashboard
```

Then open `http://localhost:8000`.

---

## Option F — Docker (only if you need a reproducible pipeline environment)

Not required for the demo, but useful if someone wants the exact environment.

`Dockerfile`:

```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
RUN python run_all.py
EXPOSE 8000
CMD ["python", "-m", "http.server", "8000", "--directory", "dashboard"]
```

```bash
docker build -t choke-controller .
docker run -p 8000:8000 choke-controller
```

The build runs the full pipeline, so the image fails to build if any scenario,
robustness check or test fails. That is deliberate — a broken build is better than a
container that silently serves stale results.

---

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| Dashboard loads but is blank / no charts | `data.js` missing or empty | Run `python run_all.py`, confirm `dashboard/data.js` is ~690 KB, redeploy |
| Styling missing, page looks like plain text | `style.css` not copied to the deploy folder | Copy all 6 files: `index.html`, `style.css`, `app.js`, `plant.js`, `controller.js`, `data.js` |
| Old version still showing after a push | Browser cached the versioned assets | Bump `?v=` in `index.html`, or hard-reload (Cmd/Ctrl + Shift + R) |
| 404 on GitHub Pages | Pages source folder wrong, or still building | Settings → Pages → confirm branch `main` + folder `/docs`; wait 2 min |
| Theme toggle does not persist | Opened via `file://` | Serve over HTTP instead |
| `python run_all.py` fails on a clean machine | Dependencies not installed | Activate the venv, `pip install -r requirements.txt` |
| Deck build step skipped | `python-pptx` not installed | `pip install -r requirements-optional.txt` — optional, core pipeline is unaffected |

---

## What to hand to judges

| Item | Where |
|---|---|
| Live dashboard | your Pages / Netlify URL |
| Code + data + figures | `submission/Autonomous_Choke_Controller_Submission.zip` |
| Engineering report | `submission/ENGINEERING_REPORT.pdf` |
| Presentation | your PDF export (portal accepts PDF only) |

**Add the live URL to the title slide and to the README.** A judge who can click a link
and immediately drive the controller is worth more than any screenshot.
