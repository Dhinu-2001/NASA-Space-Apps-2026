# Stage 7 — Core user interface

Status: implemented; the UI has no engine capability of its own. Stage 7 was approved by the project owner (Stage 8 deferred, Stage 9 authorised). Minimal, read-only (decision C2). Code: `web/src/`.
Screenshots from the real app against the real backend (Stage 9 final polish): [final_view.png](final_view.png), [final_compare.png](final_compare.png), [final_delay.png](final_delay.png), [final_about.png](final_about.png), [final_mobile.png](final_mobile.png) (500 px). Rehearsal evidence: [../stage9/DEMO_READINESS.md](../stage9/DEMO_READINESS.md).

## 1. Scope (C2) and the required workflow
One page, four tabs. Nothing beyond the C2 list: site, UTC time, Sun/Earth az/el, horizon profile, terrain-corrected visibility, sunlight and Earth timelines — plus the comparison, delay and data/assumptions views the Stage 7 task list names. No 3D, no animation, no editing of scientific data.

| Gate step | Where |
|---|---|
| 1. Select a landing location | **Site & time**: 2D map (click a site), catalogue dropdown, custom latitude/longitude |
| 2. Choose a date and time | window start, window length, "show positions at" (all UTC), observer height, assumed position uncertainty |
| 3. View Sun and Earth positions | panel 3: azimuth/elevation at the chosen time; panel 4: Sun and Earth paths over the window and their current positions on the horizon plot |
| 4. Understand terrain visibility | panel 4 horizon profile (terrain vs the bodies); panel 3 states: centre / any part / whole disc, headline VISIBLE or BLOCKED, geometric alongside |
| 5. Explore sunlight and communication windows | panel 5: timelines (terrain-corrected with boundary whiskers, geometric beneath), elevation-vs-horizon charts, metrics and event tables; click a timeline to move the time marker |
| 6. Compare another location or date | **Compare** (sites × dates, baseline choice) and **Delay simulator** |
| 7. Understand the differences | differences vs baseline in words with their bands, rankings with "clearly ahead / not distinguishable", "How to read this", **Data & assumptions** |

## 2. Rules from the decision log, and how the UI meets them
* **C4 — the frontend only displays.** Audit of `web/src` (grep): the only trigonometry is the pixel layout of the orientation map (`SiteMap.tsx`); the only date arithmetic converts UTC strings to chart-axis seconds and the `datetime-local` input to ISO form (`format.ts`, `ViewTab.tsx`). No astronomy, terrain or visibility logic exists in the UI: states, intervals, bands and metrics are read from the API. Every plotted point is a backend number; the elevation-vs-horizon chart draws the backend's two series and never decides which is higher.
* **Bands are always visible.** Every visible fraction, total, interval count, longest interval and event time is printed with its position band (`band a to b`), event rows give the earliest–latest window and its width, timelines draw the boundary whiskers (dashed = incomplete: some displaced runs lack the event), the elevation chart shades the horizon change under the position error, the Sun/Earth cards state "could change by up to X° for a ±N m position error" and whether the state is the same at all sampled positions, and comparison/delay differences print their band and whether they are distinguishable from zero. If a band was not computed the UI says "not computed"; it never silently shows the nominal alone.
* **Insufficient sites are shown honestly.** In Compare and Delay a site without terrain support is a dashed "Terrain data insufficient" row/box with the reason and **no figures, no chart bar, no rank, no placeholder**; it is listed under "Not compared". In the single-site view the visibility timelines and metrics are replaced by the same box, while the astronomy-only Sun/Earth directions and the horizon (with its lower-bound azimuths marked red) remain.
* **Capability status is surfaced everywhere.** A strip at the top lists every capability with its backend status (validated / implemented unvalidated / not implemented); each result panel carries the status tag of the capability it depends on (e.g. Compare shows "scenarios: implemented unvalidated"); the About tab explains the three statuses. Nothing is presented as more validated than the backend reports.
* **Assumptions are labelled** wherever they appear (2.0 m observer height, ±100 m position uncertainty, 14-day delay window), and the About tab lists the data sources (catalogue source links, DEM products with SHA-256, SPICE kernels with SHA-256), the metric definitions and the limitations.
* **Cut-off intervals** are flagged ("cut off", dashed outline on the timeline) in the single view, the comparison and the delay views.
* **Loading and error states.** Spinner with elapsed seconds and a hint after 4 s ("the first calculation for a site can take about a minute"); API errors show the message, code and field; "backend unavailable" shows how to start it; form input is validated before any request.
* **Responsive.** Two columns above 900 px, one below; wrapping tags; checked at 500 px (single column, no horizontal overflow). Light and dark themes follow the system setting.

## 3. Behaviour notes
* The default scenario (IM-2, 2027-01-15, 30 days, ±100 m) is computed on load; the first computation for a new site takes about a minute (terrain profiles at the site and 8 displaced positions), then it is cached.
* Deep links: `#view`, `#compare`, `#delay`, `#about`; add `?autorun=1` to run the Compare/Delay defaults on load. The About tab reads `GET /provenance` (full checksums, code commit, software).
* Visibility inputs are limited to the validated range (2025-01-01 to 2035-12-31) by the input `min`/`max` and by the backend.
* Not built (by decision): 3D lunar surface, animation, full time-scrubbing player (clicking the timeline moves the time marker), saved-scenario browser, export.

## 4. Tests (`web/src/App.test.tsx`, 16 tests)
Capability strip shows real statuses and panel tags; error state; the form's controls and client-side validation; the data/assumptions page; comparison rows show terrain-corrected next to geometric with bands; cut-off flagged; an insufficient site is a label with no numbers and absent from rankings; differences carry bands and "within position uncertainty"; delay chart draws band and geometric value; "not computed" instead of a confident number; timeline bars, dashed cut-off outlines and whiskers; the full view workflow with an insufficient site. The Compare and Delay components were additionally rendered against the real backend JSON (4 supported + 4 insufficient scenarios, real delay results) during development.

## 5. Limitations
* Visual verification: headless-browser screenshots of all four tabs with real data plus a 500 px Compare view (Stage 9 polish); browser console captured on every tab with no errors or warnings. Not tested across browsers.
* Small-screen charts scale down with the page (text gets small below ~500 px).
* Accessibility: tags and landmarks are in place and the map/timelines have text alternatives, but no formal audit was done.
