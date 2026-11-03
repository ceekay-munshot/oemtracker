# Auto OEM Trends — Audit Report

- Run: `2026-11-03T13:46:29.844873+00:00`
- Publish gate: ✅ clean — safe to commit
- LLM tally: 15 calls, ~$0.670 (177106+9230 tok)

## Store
- `Company(BSE/NSE)`: 186 records, 186 unique keys
- `FADA`: 138 records, 138 unique keys
- `Internal-DB(historical)`: 15915 records, 15915 unique keys
- `SIAM`: 56944 records, 56944 unique keys

## Flags
- **extract_failed**: 1
    - fada: OCR unavailable or empty
- **ticker_unresolved**: 4
    - company_announcements: SML Isuzu: no candidate symbol resolved on Muns
    - company_announcements: Force Motors: no candidate symbol resolved on Muns
    - financials: SML Isuzu: no candidate symbol resolved on Muns
    - financials: Force Motors: no candidate symbol resolved on Muns

## Lane status
- `fada` (lane C): ok · records=0 flags=1
- `manual` (lane Manual): skipped — no source data available (fetch returned nothing) · records=0 flags=0
- `company_announcements` (lane A): ok · records=0 flags=2
- `concalls` (lane E): skipped — no source data available (fetch returned nothing) · records=0 flags=0
- `financials` (lane D): ok · records=0 flags=2
- `siam` (lane B): skipped — no source data available (fetch returned nothing) · records=0 flags=0

## Idempotency
- no duplicate natural keys — store is idempotent

## New data
- no new live records this run — last good data intact
