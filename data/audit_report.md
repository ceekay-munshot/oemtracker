# Auto OEM Trends — Audit Report

- Run: `2026-08-06T13:09:03.839723+00:00`
- Publish gate: ✅ clean — safe to commit
- LLM tally: 26 calls, ~$0.682 (167228+12032 tok)

## Store
- `Company(BSE/NSE)`: 54 records, 54 unique keys
- `Internal-DB(historical)`: 15915 records, 15915 unique keys
- `SIAM`: 56944 records, 56944 unique keys

## Flags
- **low_confidence**: 1
    - company_announcements: ATULAUTO 3w/Exports=648 conf=0.50
- **ticker_unresolved**: 7
    - company_announcements: Tata Motors: no candidate symbol resolved on Muns
    - company_announcements: SML Isuzu: no candidate symbol resolved on Muns
    - company_announcements: Force Motors: no candidate symbol resolved on Muns
    - financials: Maruti Suzuki: no candidate symbol resolved on Muns
    - financials: Tata Motors: no candidate symbol resolved on Muns
    - financials: SML Isuzu: no candidate symbol resolved on Muns
    - financials: Force Motors: no candidate symbol resolved on Muns

## Lane status
- `fada` (lane C): skipped — no source data available (fetch returned nothing) · records=0 flags=0
- `manual` (lane Manual): skipped — no source data available (fetch returned nothing) · records=0 flags=0
- `company_announcements` (lane A): ok · records=54 flags=4
- `concalls` (lane E): skipped — no source data available (fetch returned nothing) · records=0 flags=0
- `financials` (lane D): ok · records=0 flags=4
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
