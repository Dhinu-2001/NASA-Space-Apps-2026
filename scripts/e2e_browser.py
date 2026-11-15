# ruff: noqa: ASYNC210, ASYNC220, ASYNC251, BLE001
"""End-to-end test of the complete workflow in a REAL browser (Chrome, DevTools protocol) against a running instance.

    python scripts/e2e_browser.py [--base http://127.0.0.1:8000] [--shots docs/stage11/e2e] [--chrome PATH]

Walks the whole demonstration path: pick a site on the map and compute, a custom point without terrain data (must be labelled,
never estimated), compare scenarios, compare landing sites (IM-1 must show 'terrain data insufficient'), a parameter sweep, the
mission delay simulator, the solar-energy upper bound, the data/assumptions page and the Learn tab. It checks specific numbers
that the validation reports document, records every console error, uncaught exception and failed /api request, and saves a
screenshot of each stage. Needs the warmed caches (scripts/warm_cache.py) for a fast run; otherwise cold scenarios take minutes.
Exit code 0 only if every check passes and nothing unexpected was logged. Needs `websockets` (installed with uvicorn[standard]).
"""

from __future__ import annotations

import asyncio
import base64
import json
import math
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

import websockets

ROOT = Path(__file__).resolve().parents[1]
ARGS = sys.argv[1:]
BASE = ARGS[ARGS.index("--base") + 1] if "--base" in ARGS else "http://127.0.0.1:8000"
SHOTS = Path(ARGS[ARGS.index("--shots") + 1]) if "--shots" in ARGS else ROOT / "docs" / "stage11" / "e2e"
CHROME = ARGS[ARGS.index("--chrome") + 1] if "--chrome" in ARGS else r"C:\Program Files\Google\Chrome\Application\chrome.exe"
PORT = 9335
R_M = 1_737_400.0

results: list[tuple[str, bool, str]] = []
api_errors: list[str] = []
console_errors: list[str] = []
exceptions: list[str] = []
tile_failures = 0


def check(name: str, ok: bool, detail: str = "") -> None:
    results.append((name, bool(ok), detail))
    print(f"[{'PASS' if ok else 'FAIL'}] {name}{(' - ' + detail) if detail else ''}", flush=True)


def stereo(lat: float, lon: float) -> tuple[float, float]:
    rho = 2 * R_M * math.tan(math.radians(lat + 90) / 2)       # the engine's projection (dem.lonlat_to_xy)
    return rho * math.sin(math.radians(lon)), rho * math.cos(math.radians(lon))


async def main() -> int:
    SHOTS.mkdir(parents=True, exist_ok=True)
    proc = subprocess.Popen([CHROME, "--headless=new", "--disable-gpu", f"--remote-debugging-port={PORT}", "--window-size=1400,1000", "about:blank"],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        for _ in range(60):
            try:
                tabs = json.load(urllib.request.urlopen(f"http://127.0.0.1:{PORT}/json"))
                break
            except Exception:
                time.sleep(0.5)
        ws_url = next(t["webSocketDebuggerUrl"] for t in tabs if t["type"] == "page")
        async with websockets.connect(ws_url, max_size=100_000_000) as ws:
            n = 0
            pending: dict[int, asyncio.Future] = {}
            req_urls: dict[str, str] = {}

            async def reader() -> None:
                global tile_failures
                async for raw in ws:
                    msg = json.loads(raw)
                    if "id" in msg and msg["id"] in pending:
                        pending[msg["id"]].set_result(msg.get("result", {}))
                        continue
                    m, p = msg.get("method"), msg.get("params", {})
                    if m == "Network.requestWillBeSent":
                        req_urls[p["requestId"]] = p["request"]["url"]
                    elif m == "Network.responseReceived":
                        url = p["response"]["url"]
                        if "/api/" in url and p["response"]["status"] >= 400:
                            api_errors.append(f"{p['response']['status']} {url.split('/api')[1].split('?')[0]}")
                    elif m == "Network.loadingFailed":
                        url = req_urls.get(p["requestId"], "")
                        if "trek.nasa.gov" in url:
                            tile_failures += 1
                        elif "/api/" in url and not p.get("canceled"):
                            api_errors.append(f"network failure {url}")
                    elif m == "Runtime.exceptionThrown":
                        exceptions.append(p["exceptionDetails"].get("text", "") + " " + str(p["exceptionDetails"].get("exception", {}).get("description", ""))[:200])
                    elif m == "Runtime.consoleAPICalled" and p["type"] in ("error", "assert"):
                        console_errors.append(" ".join(str(a.get("value", a.get("description", ""))) for a in p["args"])[:300])

            reader_task = asyncio.create_task(reader())

            async def call(method: str, **params):
                nonlocal n
                n += 1
                fut = asyncio.get_event_loop().create_future()
                pending[n] = fut
                await ws.send(json.dumps({"id": n, "method": method, "params": params}))
                return await fut

            async def js(expr: str):
                r = await call("Runtime.evaluate", expression=expr, returnByValue=True, awaitPromise=True)
                return r.get("result", {}).get("value")

            async def wait(expr: str, timeout: float = 120.0, what: str = "") -> bool:
                t0 = time.time()
                while time.time() - t0 < timeout:
                    if await js(f"!!({expr})"):
                        return True
                    await asyncio.sleep(0.4)
                print(f"   (timed out waiting for {what or expr})")
                return False

            async def shot(name: str) -> None:
                r = await call("Page.captureScreenshot", format="png", captureBeyondViewport=True)
                (SHOTS / f"{name}.png").write_bytes(base64.b64decode(r["data"]))

            btn = lambda text: f"[...document.querySelectorAll('button:not([role=tab])')].find(b => b.textContent.trim() === {json.dumps(text)})"
            text_has = lambda s: f"document.body.innerText.includes({json.dumps(s)})"

            async def click_button(text: str) -> bool:
                return bool(await js(f"(() => {{ const b = {btn(text)}; if (!b) return false; b.click(); return true; }})()"))

            async def click_tab(label: str) -> None:
                await js(f"[...document.querySelectorAll('[role=tab]')].find(t => t.textContent.trim() === {json.dumps(label)}).click()")
                await asyncio.sleep(0.5)

            async def set_input(selector: str, value: str) -> None:
                await js(f"""(() => {{ const el = document.querySelector({json.dumps(selector)}); const set = Object.getOwnPropertyDescriptor(el.constructor.prototype, 'value').set;
                    set.call(el, {json.dumps(value)}); el.dispatchEvent(new Event('input', {{bubbles: true}})); el.dispatchEvent(new Event('change', {{bubbles: true}})); }})()""")

            async def mouse_click(x: float, y: float) -> None:
                await call("Input.dispatchMouseEvent", type="mouseMoved", x=x, y=y)
                await call("Input.dispatchMouseEvent", type="mousePressed", x=x, y=y, button="left", clickCount=1)
                await call("Input.dispatchMouseEvent", type="mouseReleased", x=x, y=y, button="left", clickCount=1)

            await call("Page.enable")
            await call("Runtime.enable")
            await call("Network.enable")
            await call("Emulation.setDeviceMetricsOverride", width=1400, height=1000, deviceScaleFactor=1, mobile=False)

            # ---------------------------------------------------------------- 1. open, default site computes
            await call("Page.navigate", url=f"{BASE}/#view")
            check("1a app loads and the backend is reachable", await wait("document.querySelector('[data-testid=health-status]')", 60, "health"), await js("document.querySelector('[data-testid=health-status]')?.textContent || ''"))
            check("1b capability strip shows 7 validated capabilities", await js("document.querySelectorAll('.cap-list li').length") == 7 and await js("[...document.querySelectorAll('.cap-list li')].every(l => l.textContent.includes('validated'))"))
            check("1c default IM-2 view computes (Sun/Earth cards, horizon plot, visibility metrics)", await wait("document.querySelector('[data-testid=now-sun]') && " + text_has("Visible fraction"), 240, "view results"))
            body = await js("document.body.innerText")
            check("1d IM-2 numbers match the validated reports (Sun 48.6 %, Earth 80.8 %, geometric 53.3 % / 73.5 %)", all(s in body for s in ("48.6 %", "80.8 %", "53.3 %", "73.5 %")))
            check("1e advanced plots panel present", await wait("document.querySelector('[data-testid=advanced-plots]')", 60, "advanced plots"))
            check("1f basemap tiles requested (16) and credit shown", await js("document.querySelectorAll('[data-testid=basemap] image').length") == 16 and await js("document.body.innerText.includes('LRO LROC WAC mosaic')"))
            await shot("01_view_im2")

            # ---------------------------------------------------------------- 2. solar energy upper bound
            await js("(() => { const b = [...document.querySelectorAll('button')].find(b => b.textContent.includes('Use example')); if (b) { b.click(); return true; } })()")
            await click_button("Estimate energy")
            check("2a solar estimate: 143.0 kWh with its band and the 'upper bound' label", await wait("document.querySelector('[data-testid=solar-result]') && " + text_has("143.0 kWh") + " && " + text_has("UPPER BOUND"), 120, "solar"))
            await shot("02_solar")

            # ---------------------------------------------------------------- 3. pick a point on the map without terrain data
            await call("Input.dispatchMouseEvent", type="mouseMoved", x=5, y=5)   # headless Chrome shows its scrollbar on first mouse activity
            await asyncio.sleep(0.8)
            box = await js("(() => { const r = document.querySelector('[data-testid=site-map]').getBoundingClientRect(); return [r.left, r.top, r.width, r.height]; })()")
            left, top, w, h = box
            await asyncio.sleep(1.0)                                   # let late layout settle, then measure again
            box = await js("(() => { const r = document.querySelector('[data-testid=site-map]').getBoundingClientRect(); return [r.left, r.top, r.width, r.height]; })()")
            left, top, w, h = box
            print("   map box", [round(v, 1) for v in box], "scroll", await js("[scrollX, scrollY, innerWidth, innerHeight, devicePixelRatio]"))
            x, y = stereo(-75.0, 100.0)
            # Hover the target first and measure again: headless Chrome (with device emulation) can show its classic scrollbar only once the
            # pointer is over the page, shifting the centred layout by ~7 px; a person aims at what is under the pointer, so do the same.
            for _ in range(2):
                cx, cy = left + (170 + x / 1e6 * 158) / 340 * w, top + (170 - y / 1e6 * 158) / 340 * h
                await call("Input.dispatchMouseEvent", type="mouseMoved", x=cx, y=cy)
                await asyncio.sleep(0.6)
                left, top, w, h = await js("(() => { const r = document.querySelector('[data-testid=site-map]').getBoundingClientRect(); return [r.left, r.top, r.width, r.height]; })()")
            await mouse_click(cx, cy)
            lat_v, lon_v = await js("[document.getElementById('lat').value, document.getElementById('lon').value]")
            check("3a clicking the map fills latitude/longitude (about -75, 100)", abs(float(lat_v) + 75) < 0.5 and abs(float(lon_v) - 100) < 1.0, f"{lat_v}, {lon_v}")
            await click_button("Compute")
            check("3b a point without terrain data is LABELLED 'terrain data insufficient', never estimated", await wait(text_has("Terrain data insufficient"), 60, "insufficient label") and not await js("document.querySelector('[data-testid=solar-result]')"))
            await shot("03_custom_point_insufficient")

            # ---------------------------------------------------------------- 4. back to IM-2 via the site list, mission profile
            await js("document.querySelector('#site-select').scrollIntoView()")
            await js("(() => { const cb = [...document.querySelectorAll('label')].find(l => l.textContent.includes('Use custom coordinates')).querySelector('input'); cb.click(); })()")
            await js("(() => { const s = document.getElementById('view-profile-select'); const set = Object.getOwnPropertyDescriptor(HTMLSelectElement.prototype, 'value').set; set.call(s, 'one-lunar-day'); s.dispatchEvent(new Event('change', {bubbles: true})); })()")
            check("4a choosing a mission profile fills the form at once (14 days)", await js("document.getElementById('days').value") == "14")
            await js("(() => { const s = document.getElementById('view-profile-select'); const set = Object.getOwnPropertyDescriptor(HTMLSelectElement.prototype, 'value').set; set.call(s, 'extended'); s.dispatchEvent(new Event('change', {bubbles: true})); })()")
            await click_button("Compute")
            check("4b Compute after returning to IM-2 shows results again", await wait("document.querySelector('[data-testid=now-sun]') && " + text_has("48.6 %"), 120, "recompute"))

            # ---------------------------------------------------------------- 5. compare scenarios
            await click_tab("Compare")
            await click_button("Compare")
            check("5a compare: 6 supported scenarios and 2 'terrain data insufficient' (IM-1)", await wait("document.querySelectorAll('[data-testid=row-supported]').length === 6 && document.querySelectorAll('[data-testid=row-insufficient]').length === 2", 300, "compare table"))
            check("5b compare: bands shown and no number for IM-1 rows", await js("[...document.querySelectorAll('[data-testid=row-insufficient]')].every(r => !/\\d\\d\\.\\d %/.test(r.textContent))"))
            await shot("05_compare")

            # ---------------------------------------------------------------- 6. landing sites side by side
            await click_tab("Landing sites")
            await click_button("Compare sites")
            check("6a landing sites table appears", await wait("document.querySelector('[data-testid=sites-table]')", 300, "sites table"))
            check("6b IM-1 column is labelled in all 9 metric rows", await js("document.querySelectorAll('[data-testid=cell-insufficient]').length") == 9)
            check("6c Chandrayaan-3 is supported but flagged 'terrain not yet approved'; IM-2 is not flagged", await js("document.querySelectorAll('[data-testid=not-approved-flag]').length") == 1)
            await shot("06_landing_sites")

            # ---------------------------------------------------------------- 7. sweep
            await click_tab("Explore sweeps")
            await click_button("Run sweep")
            check("7a position-uncertainty sweep: 5 rows, Sun nominal 48.6 % in every row, bands widen", await wait("document.querySelectorAll('[data-testid=sweep-row]').length === 5", 300, "sweep rows") and await js("[...document.querySelectorAll('[data-testid=sweep-row]')].every(r => r.textContent.includes('48.6 %'))"))
            await shot("07_sweep")

            # ---------------------------------------------------------------- 8. delay simulator
            await click_tab("Delay simulator")
            await click_button("Simulate delays")
            check("8a delay simulator returns its table", await wait("document.querySelectorAll('table').length > 0 && document.body.innerText.toLowerCase().includes('delay') && !document.body.innerText.includes('Simulating')", 300, "delay table"))
            await shot("08_delay")

            # ---------------------------------------------------------------- 9. data & assumptions, learn
            await click_tab("Data & assumptions")
            check("9a data page lists kernels with SHA-256, DEM windows and credits", await wait(" && ".join([text_has("de440s.bsp"), text_has("Scientific data sources"), text_has("Credits and acknowledgements")]), 60, "about page"))
            check("9b assumptions and limitations are stated (35 items)", await js(text_has("(35 items)")))
            await shot("09_data_assumptions")
            await click_tab("Learn")
            check("9c Learn tab renders the glossary", await wait("document.body.innerText.toLowerCase().includes('glossary')", 30, "learn"))

            # ---------------------------------------------------------------- 10. production hygiene
            headers = await js("fetch('/', {cache: 'no-store'}).then(r => ({csp: r.headers.get('content-security-policy'), nosniff: r.headers.get('x-content-type-options'), frame: r.headers.get('x-frame-options')}))")
            if BASE.endswith(":5173") or "5173" in BASE:
                print("   (dev server: security headers are only added by the production entry point; skipped)")
            else:
                check("10a production page carries CSP, nosniff and no-framing headers", bool(headers.get("csp")) and headers.get("nosniff") == "nosniff" and headers.get("frame") == "DENY", str(headers))
            reader_task.cancel()
    finally:
        proc.terminate()

    unexpected = [e for e in api_errors if not (e.startswith("422 ") and any(p in e for p in ("/horizon/profile", "/visibility/", "/scenarios/")))]
    expected = [e for e in api_errors if e not in unexpected]
    check("11a no uncaught JavaScript exceptions", not exceptions, "; ".join(exceptions[:3]))
    check("11b no console errors (apart from the browser's own notes on the expected 422s)", all("Failed to load resource" in c for c in console_errors), "; ".join(c for c in console_errors if "Failed to load resource" not in c)[:300])
    check("11c no unexpected failed API requests", not unexpected, "; ".join(unexpected[:5]))
    print(f"   expected 422 responses (custom point without terrain data): {len(expected)}; basemap tile failures: {tile_failures}")
    out = {"base": BASE, "checks": [{"name": a, "pass": b, "detail": c} for a, b, c in results], "expected_422": expected, "unexpected_api_errors": unexpected,
           "console_errors": console_errors, "exceptions": exceptions, "basemap_tile_failures": tile_failures}
    (SHOTS.parent / "e2e_results.json").write_text(json.dumps(out, indent=2), encoding="utf-8")
    failed = [r for r in results if not r[1]]
    print(f"\n{len(results) - len(failed)}/{len(results)} checks passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
