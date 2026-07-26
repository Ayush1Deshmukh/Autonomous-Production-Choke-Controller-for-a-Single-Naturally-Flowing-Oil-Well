"""
07_capture_dashboard.py
========================
Captures real screenshots of the interactive dashboard for use in the
presentation deck and the report.

Uses Playwright + Chromium against a local static server so the shots are of
the genuine running page (not a mock-up). Skips gracefully if Playwright is
not installed - no other deliverable depends on it.

Outputs
-------
    figures/dashboard/dash_scenarioC_light.png
    figures/dashboard/dash_scenarioC_dark.png
    figures/dashboard/dash_reasoning.png
"""

from __future__ import annotations

import subprocess
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "figures" / "dashboard"
PORT = 8731  # dedicated port so it never collides with the dev preview server


def serve():
    return subprocess.Popen(
        [sys.executable, "-m", "http.server", str(PORT), "--directory", str(ROOT / "dashboard")],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )


def main():
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("  Playwright not installed - skipping dashboard capture.")
        print("  (pip install playwright && playwright install chromium)")
        return

    OUT.mkdir(parents=True, exist_ok=True)
    srv = serve()
    time.sleep(1.5)
    url = f"http://localhost:{PORT}/index.html"

    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch()

            def shot(name, theme, setup_js, full=False, clip=None):
                page = browser.new_page(viewport={"width": 1600, "height": 1000},
                                        device_scale_factor=2,
                                        color_scheme=theme)
                page.goto(url, wait_until="networkidle")
                # Headless Chromium composites `backdrop-filter` layers in a way
                # that blanks out <canvas> children in screenshots (the canvas
                # pixels are genuinely there - verified via getImageData - but
                # they do not make it into the captured frame). Disabling the
                # filter only for the capture gives a faithful shot of the
                # charts; the live page is unaffected.
                page.add_style_tag(content=(
                    "*{backdrop-filter:none!important;"
                    "-webkit-backdrop-filter:none!important}"
                    # The rejected-candidate list scrolls on the live page; for a
                    # still image let it expand so no row is sliced in half.
                    ".reject-list{max-height:none!important;overflow:visible!important}"
                ))
                page.evaluate(
                    "t => { document.documentElement.dataset.theme = t; }", theme
                )
                page.evaluate(setup_js)
                page.wait_for_timeout(1400)
                path = OUT / name
                if clip:
                    page.locator(clip).screenshot(path=str(path))
                else:
                    page.screenshot(path=str(path), full_page=full)
                print(f"  wrote {path.relative_to(ROOT)}")
                page.close()

            run_c = """() => {
                document.querySelector('[data-scenario="C"]').click();
                const s = document.querySelector('#speed');
                s.value = 'instant'; s.dispatchEvent(new Event('change'));
                document.querySelector('#btn-play').click();
            }"""

            shot("dash_scenarioC_light.png", "light", run_c)
            shot("dash_scenarioC_dark.png", "dark", run_c)
            shot("dash_reasoning.png", "light", run_c, clip=".reasoning")
            browser.close()
    finally:
        srv.terminate()


if __name__ == "__main__":
    main()
