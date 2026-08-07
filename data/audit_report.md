# Auto OEM Trends — Audit Report

- Run: `2026-08-07T08:40:39.653227+00:00`
- Publish gate: ✅ clean — safe to commit
- LLM tally: 19 calls, ~$0.994 (235020+19273 tok)

## Store
- `Company(BSE/NSE)`: 118 records, 118 unique keys
- `Internal-DB(historical)`: 15915 records, 15915 unique keys
- `SIAM`: 56944 records, 56944 unique keys

## Flags
- **extract_failed**: 1
    - fada: LLM extraction failed: extraction failed after 3 attempts: 'rows' is a required property
- **low_confidence**: 3
    - company_announcements: ASHOKLEY mhcv/Exports=1220 conf=0.50
    - company_announcements: ASHOKLEY lcv/Exports=390 conf=0.50
    - company_announcements: ATULAUTO 3w/Exports=585 conf=0.50
- **ticker_unresolved**: 4
    - company_announcements: SML Isuzu: no candidate symbol resolved on Muns
    - company_announcements: Force Motors: no candidate symbol resolved on Muns
    - financials: SML Isuzu: no candidate symbol resolved on Muns
    - financials: Force Motors: no candidate symbol resolved on Muns

## Lane status
- `fada` (lane C): ok · records=0 flags=1
- `manual` (lane Manual): skipped — no source data available (fetch returned nothing) · records=0 flags=0
- `company_announcements` (lane A): ok · records=95 flags=5
- `concalls` (lane E): skipped — no source data available (fetch returned nothing) · records=0 flags=0
- `financials` (lane D): ok · records=0 flags=2
- `siam` (lane B): skipped — no source data available (fetch returned nothing) · records=0 flags=0

## Idempotency
- no duplicate natural keys — store is idempotent

## Arithmetic
- new data arithmetic consistent

## YoY / MoM sanity
- 0 implausible MoM/YoY swings flagged (0 hard / 0 flash-review)

## Cross-source divergence (informational)
- no material company-vs-SIAM divergence in new data

## Market share (recomputed from SIAM totals)
- no new SIAM totals to recompute share from
