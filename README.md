# Auto OEM Trends Tracker

A **static, trend-first analytics dashboard** for the Indian automobile industry — an
equity-research "OEM Trends Tracker" covering production, sales, market share and EV, by OEM
and by vehicle category. Every screen leads with a time-series; KPI cards and prose are kept to
a minimum. The whole thing is static (HTML + CSS + vanilla ES modules + ECharts) and is designed
to be deployed as static assets (e.g. Cloudflare). **The browser never parses `.xlsx`** — all of
the spreadsheet wrangling happens once, at build time, in a Python pipeline that emits clean JSON.

---

## What's in the box

```
index.html                     App shell (header, tabs, filter bar, footer, loading veil)
dashboard/
  css/main.css                 Design system (institutional light theme, tokens)
  js/
    app.js                     Boot, header tabs, global filter bar, dataset routing
    state.js                   Filter state (single source of truth) mirrored to the URL hash
    data.js                    Manifest + dataset loading (works offline, no server needed)
    compute.js                 Derived metrics: YoY %, market share, share-delta (pp), rebase-100
    charts.js                  ECharts option factories (the shared chart look)
    trendcard.js               The one reusable "TrendCard" every tab composes
    format.js                  Number/period formatting (Lakh / Crore, FY labels)
    xlsx.js                    Dependency-free .xlsx writer (every table exports to Excel)
    ui.js                      Small DOM helpers + UI atoms
    tabs/                      One module per tab (overview, sales, share, ev, prodmix, segmix, datatab)
    vendor/echarts.min.js      ECharts 5.5.0, vendored locally so charts work offline
data/                          Normalized JSON emitted by the pipeline + manifest (+ .js loaders)
scripts/build.py               The openpyxl parser: xlsx -> JSON (idempotent, commented)
raw/                           The two source workbooks (pipeline inputs)
```

The seven tabs — **Overview · Sales Trends · Market Share · EV Tracker · Production·Sales·Exports ·
Segment Mix · Data** — all reuse a single `TrendCard` component (chart + mini-toggles + optional
sortable table + Excel export + source tag + provisional note + calm empty state).

---

## Running the data pipeline

The pipeline reads the workbooks in `raw/` and (re)writes `data/`. It only needs `openpyxl`.

```bash
pip install openpyxl
python3 scripts/build.py
```

Re-running is **idempotent** — it deterministically overwrites `data/`. `build.py` is also the
seed for future automation, so it is structure-driven (it locates header rows / group headers
rather than trusting fixed column positions) and heavily commented.

For each `(category, source)` it writes a compact `data/<category>__<source>.json` (plus a
`.js` loader twin — see below) and a small `data/manifest.json` catalogue (categories, sources,
entities, coverage, latest/provisional periods, attribution).

---

## Viewing the dashboard

The dashboard is 100% static — no server-side code, no API, no build step for the front-end.

- **Deployed (Cloudflare / any static host):** just serve the folder. It works as-is.
- **Locally:** serve the folder over HTTP and open it, e.g.

  ```bash
  python3 -m http.server 8099
  # then open http://127.0.0.1:8099/index.html
  ```

  A tiny static server is used because browsers apply cross-origin rules to **ES modules** on
  the `file://` protocol. The **data** itself is loaded via `<script>` injection (JSONP-style
  `data/*.js` twins of the JSON), so no `fetch()`/CORS is involved for data — that part works
  even from `file://`. The JSON files remain the canonical artifacts (and the automation seed);
  the `.js` twins simply register the same payload on a global for zero-dependency loading.

---

## Data model & principles

### Sources (kept strictly separate)

| Source        | Workbook                                  | Coverage                          | Notes |
| ------------- | ----------------------------------------- | --------------------------------- | ----- |
| **SIAM**      | `Monthly_SIAM_Industry_Data_Jun26.xlsx`   | Monthly, Apr-1992 → 2026          | Industry-wide; 4 metrics (Production / Domestic / Exports / Total); PV, 2W, 3W, M&HCV, LCV |
| **Internal DB** | `Auto_Database_Summary__Spark.xlsx`     | Monthly from Apr-2012 (CV quarterly) | OEM-granular; EV splits; 2W, PV, 3W, CV, Tractors |

**One source per table/chart — never blended.** SIAM numbers and internal-DB numbers use
different definitions, so they live on separate cards/tabs and every card carries its source tag.

### Derived metrics (recomputed, not trusted from the file)

- **Frequencies** roll up on the **Indian fiscal year (Apr–Mar)**: Quarterly = 3-month sums
  (Q1 = Apr–Jun … Q4 = Jan–Mar), Yearly = 12-month sums, **FY labelled by its ending year**
  (FY26 = Apr-2025 → Mar-2026). Only complete periods are final; the in-progress quarter/FY is
  shown but flagged **partial + provisional**.
- **Value mode:** Absolute and **YoY %** (same period one fiscal year prior). Plus an **Index-100**
  rebase for clean relative-growth comparison.
- **Market share** is **recomputed in the browser** from the raw numbers within a single source
  (share sums to 100% across reporting OEMs); the workbook's pre-computed share blocks are
  ignored. The Market Share tab also shows each OEM's **YoY change in share in percentage points**.
- **EV** (internal DB): EV penetration (EV ÷ segment), EV-vs-ICE, and EV-maker share trends.

### Data-quality guardrails

- **Never fabricate / interpolate.** Missing periods render as a gap in the line / a blank cell.
- **Trailing `0`/blank from a non-reporting OEM is treated as missing** (not a crash to zero) and
  is excluded from market-share denominators for that period. Leading zeros (before an OEM enters)
  are likewise treated as missing.
- **Defunct / all-zero OEMs are hidden by default** (an "active OEMs only" default, with a
  "show all / include defunct" escape hatch). Defaults are the top-N active OEMs by
  trailing-12-month volume.
- **The latest 1–2 periods are marked provisional** (subject to revision / late reporting).

---

## Notes

- The global filter bar (Category · Source · Metric · Frequency · Value mode · OEMs · Range)
  drives every tab, and the selection is persisted in the URL hash so views are shareable.
- Fonts are Inter + JetBrains Mono (Google Fonts) with system fallbacks, so the UI stays readable
  even if the font CDN is unavailable.
- Deployment/hosting is intentionally out of scope for this repo.
