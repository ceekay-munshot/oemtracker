# Auto OEM Trends Tracker

A **static, trend-first analytics dashboard** for the Indian automobile industry — an
equity-research "OEM Trends Tracker" covering production, sales, market share and EV, by OEM
and by vehicle category — now backed by a **hands-off monthly data-automation pipeline**.

The dashboard is 100% static (HTML + CSS + vanilla ES modules + ECharts) and reads normalized
JSON from `/data`. **The browser never parses `.xlsx`.** Historically that JSON was built once
from two Excel workbooks; now the same JSON is **refreshed automatically every month from live
sources** (SIAM, company disclosures, FADA, screener financials, concalls) — no one hand-edits
a spreadsheet again. The dashboard front-end is unchanged: it consumes the exact same JSON
contract.

---

## Two halves of the repo

| Half | What it is | Touch it? |
| ---- | ---------- | --------- |
| **Dashboard** (`index.html`, `dashboard/`) | The static front-end. Reads `data/*.js` + `data/manifest.js`. | Unchanged — do not edit for data work. |
| **Automation** (`lib/`, `sources/`, `scripts/`, `config/`, `.github/`) | Fetches live data → a canonical store → derives the dashboard JSON. | This is the data layer. |

---

## How the automation works (the short version)

```
live sources ──adapters──► canonical STORE (append-only) ──build──► data/*.json  ──► dashboard
 SIAM · Company · FADA        data/store/*.jsonl            lib/build.py   (same contract)
 Financials · Concalls        (immutable history)
```

1. **Seed once** — `scripts/seed_history.py` parses the two workbooks into the append-only
   store (`data/store/`), preserving the full **1992→2026** history.
2. **Every month** — `run.py` runs each source adapter (isolated), appends new records to the
   store, audits, and rebuilds `data/*.json` from the store.
3. **Publish gate** — a clean run commits `data/` (Cloudflare deploys on push); a run with any
   hard data-integrity flag opens a **Pull Request** with the audit report instead — a bad file
   never silently reaches the live dashboard.

Everything is **append-only** (past months are immutable; a revision is a new row, latest
wins), **idempotent** (re-running a month appends nothing), and **one-source-per-table** (SIAM
wholesale, FADA retail and company disclosures never blend in a single series).

The store round-trip is verified: `seed_history.py` → `lib/build.py` reproduces the committed
dashboard JSON **byte-for-byte** (`scripts/verify_identity.py`), so history is provably lossless
and the dashboard renders identically.

---

## GitHub Secrets to add

Add these under **Settings → Secrets and variables → Actions**. Any missing/expired secret makes
just that lane log `skipped — no/invalid credential` and the run continues (a `401` from Muns
means an expired `MUNS_TOKEN`, surfaced in plain English).

| Secret | Used by | Required? |
| ------ | ------- | --------- |
| `MUNS_TOKEN` | Company announcements, financials, concalls (Bearer for `devde.muns.io` **and** `fastapi.muns.io`) | Needed for lanes A, D, E |
| `FIRECRAWL_API_KEY` | Web scraping (SIAM/FADA press pages) | One scraper needed for lanes B, C |
| `SCRAPEDO_API_KEY` | Web scraping fallback | Alternative to Firecrawl |
| `MISTRAL_API_KEY` | OCR for PDFs | Needed for any PDF lane |
| `BEDROCK_API_KEY` | Claude on Bedrock (extraction) — **or** the three AWS vars below | Needed for extraction |
| `AWS_ACCESS_KEY_ID` + `AWS_SECRET_ACCESS_KEY` + `AWS_REGION` | Claude on Bedrock (alternative to `BEDROCK_API_KEY`) | Alternative to `BEDROCK_API_KEY` |
| `BEDROCK_CLAUDE_MODEL_ID` | The Bedrock Claude model / inference-profile id | Needed for extraction |
| `SIAM_USERNAME` + `SIAM_PASSWORD` | **Optional** — only if SIAM per-OEM detail is member-only (Playwright login path) | Optional |

Secrets are **only** read from the environment — never hardcoded, never printed (tokens are
redacted in all logs).

---

## Running it

```bash
pip install -r requirements.txt

# One-time: backfill the full history from the two workbooks into the store.
python scripts/seed_history.py

# Monthly (what CI runs): fetch live data → store → audit → rebuild data/.
python run.py                     # all lanes
python run.py --only siam,fada    # a subset
python run.py --no-build          # store/audit only

# Rebuild dashboard JSON from the store without fetching (deterministic):
python lib/build.py

# Prove the store reproduces the committed dashboard JSON:
python scripts/verify_identity.py <reference_dir>   # e.g. a clean checkout's data/

# Hermetic invariant checks (no secrets/network needed):
python scripts/selftest.py
```

`scripts/build.py` (workbook → JSON) is retained for backward compatibility and produces
byte-identical output; the production path is `run.py` → `lib/build.py` (store → JSON).

### Dropping a manual file (e.g. ACMA half-yearly)

Drop a PDF into `data/intake/` named `<source>__<label>.pdf` and it is auto-parsed on the next
run, then moved to `data/raw/manual/`:

```
data/intake/acma__h1fy26.pdf        # → parsed, stored, archived
data/intake/siam__jun26.pdf         # prefix routes it to the SIAM source
```

Recognised prefixes: `acma`, `siam`, `fada`, `company` (anything else → source `Manual`).

---

## Source lanes (each stays in its own lane)

| Lane | Source | Store source id | Role |
| ---- | ------ | --------------- | ---- |
| **A — Flash** | Listed-OEM monthly sales (BSE/NSE via Muns Corporate Announcements) | `Company(BSE/NSE)` | Fast per-OEM sales, provisional until SIAM confirms |
| **B — Backbone** | SIAM monthly | `SIAM` | **Primary** for core trend & market-share tables |
| **C — Retail** | FADA monthly | `FADA` | Retail registrations (separate from wholesale) |
| **D — Financials** | Screener via Muns | `Muns-Financials` | Revenue/margin/valuation overlay |
| **E — Commentary** | Concalls via Muns | `Concalls` | Qualitative guidance / EV outlook |
| **Manual** | `data/intake/` drop | (by prefix) | Low-frequency top-ups (e.g. ACMA) |
| *(seed)* | The two workbooks | `SIAM`, `Internal-DB(historical)` | The backfilled 1992→2026 history |

**Wave behaviour:** company (flash) announcements land first, FADA mid-month, SIAM weeks later.
When SIAM confirms a month, the earlier flash rows are flipped `provisional:false` via a
revision bump — history is never overwritten.

New lanes (Company/FADA/financials/concalls) are derived into **sidecar overlays** under
`data/out/` (e.g. `company_flash.json`, `fada_retail.json`, `financials.json`, `concalls.json`).
These are kept **out of** the dashboard's core source contract (`data/<cat>__siam|internal.json`)
so the existing UI is untouched, but are available for future front-end work.

---

## The canonical store

`data/store/` is the single source of truth: one **immutable record per figure** in long
format, git-committable JSONL partitioned by source.

- **Natural (upsert) key:** `(source, category, segment, oem, metric, frequency, period)`.
- **Append-only:** a changed value or a provisional→confirmed flip is a **new** record with
  `revision + 1`; the build takes the highest revision per key ("latest wins"). Nothing is lost.
- **Idempotent:** re-running a month whose values already match appends nothing.
- Records are stored lean (fields equal to their default are omitted; integral values as ints).
  An explicit period axis (`_axis.json`) guarantees the build's period grid is exact even when a
  month is sparse.

Where a seeded series has no sustainable live feed (some internal-DB granular/EV splits) the
history is kept and marked `Internal-DB(historical)` (not live-updated); each dashboard table is
continued from the lane that *can* be sustained (SIAM backbone + company disclosures).

---

## The extraction brain (OCR + Claude)

PDFs → **Mistral OCR** → **Claude on Bedrock** which is forced to return **schema-valid JSON**
(a tool whose `input_schema` is the target schema; invalid output is retried with the validation
error). Every figure carries a **confidence** and the source line it was read from; figures
below the confidence threshold are **flagged for review, never written** (never fabricate). OCR
and LLM results are **cached by input sha256** — an unchanged filing is never re-processed or
re-charged. A per-run token/$ tally and call cap keep cost bounded.

---

## Audit / QA gate

After each run, `lib/audit.py` writes `data/audit_report.md` and decides the publish gate:

- **Idempotency/dedup** — no duplicate natural keys.
- **Arithmetic** — domestic+export≈total; segment sums≈total.
- **YoY/MoM sanity** — implausible swings (major OEM MoM > ±60% or YoY > ±100%) flagged.
- **Cross-source sanity** — company-disclosed vs SIAM totals for the same month (reported;
  lanes stay separate regardless).
- **Market share** — recomputed from SIAM totals; must sum to ~100% per category.
- **Unmapped OEMs & low-confidence** — listed explicitly.

A **hard** flag (data-integrity risk) blocks a direct commit and opens a **PR** for human review.

---

## The workflow

`.github/workflows/update-auto.yml` runs:

```
schedule: '0 6 3,18 * *'   # 3rd: new-month company announcements; 18th: SIAM/FADA + revisions
workflow_dispatch: {}       # on demand
push (main): sources/**, lib/**, scripts/**, .github/workflows/update-auto.yml   # rebuild on code change
```

Steps: checkout → Python 3.11 (pip cache) → `pip install -r requirements.txt` → `python run.py`
with all secrets injected as env → **clean** run commits `data/` (Cloudflare deploys); **flagged**
run opens a PR (`peter-evans/create-pull-request`) with `data/audit_report.md` in the body.
Requires `permissions: contents: write, pull-requests: write`.

---

## Repo layout

```
config/    tickers.yaml, oem_aliases.yaml, sources.yaml
lib/       pipeline_core.py (shared math), store.py, build.py, model.py,
           muns.py, fetch.py, ocr.py, extract.py, normalize.py,
           audit.py, http_util.py, logging_util.py, cache.py, config.py
sources/   base.py, muns_announcements.py, siam.py, fada.py,
           muns_financials.py, muns_concalls.py, manual_intake.py
scripts/   run.py, seed_history.py, build.py (legacy), verify_identity.py, selftest.py
run.py     repo-root entry point (delegates to scripts/run.py)
data/      store/ (canonical, committed)   raw/ (fetched artifacts, gitignored)
           cache/ (ocr+llm, gitignored)    out/ (derived overlays)
           intake/ (manual drop)           *.json + *.js (dashboard contract)  audit_report.md
raw/       the two seed workbooks (pipeline inputs)
.github/workflows/update-auto.yml
```

> **Note on directory layout:** the dashboard reads `data/*.json` + `data/manifest.js` directly,
> so the derived dashboard JSON stays at the `data/` root (not `data/out/`) to keep the existing
> front-end contract intact. `data/out/` holds the newer sidecar overlays only.

---

## Dashboard (unchanged) — how it reads the data

The seven tabs — **Overview · Sales Trends · Market Share · EV Tracker · Production·Sales·Exports ·
Segment Mix · Data** — all reuse a single `TrendCard` component. The global filter bar
(Category · Source · Metric · Frequency · Value mode · OEMs · Range) drives every tab and is
mirrored to the URL hash. Data is loaded via `<script>` injection (JSONP-style `data/*.js`
twins of the JSON) so it works from `file://` with no server.

Derived metrics are recomputed in the browser (YoY %, market share, index-100 rebase);
frequencies roll up on the Indian fiscal year (Apr–Mar, FY labelled by ending year). Serve the
folder over any static host, or locally:

```bash
python3 -m http.server 8099   # then open http://127.0.0.1:8099/index.html
```
