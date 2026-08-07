# Auto OEM Trends — Audit Report

- Run: `2026-08-07T05:39:23.675817+00:00`
- Publish gate: ✅ clean — safe to commit
- LLM tally: 29 calls, ~$0.937 (232789+15885 tok)

## Store
- `Company(BSE/NSE)`: 98 records, 98 unique keys
- `Internal-DB(historical)`: 15915 records, 15915 unique keys
- `SIAM`: 56944 records, 56944 unique keys

## Flags
- **extract_failed**: 1
    - company_announcements: OLAELEC: OCR unavailable or empty
- **low_confidence**: 3
    - company_announcements: ASHOKLEY mhcv/Exports=1220 conf=0.50
    - company_announcements: ASHOKLEY lcv/Exports=390 conf=0.50
    - company_announcements: ATULAUTO 3w/Exports=585 conf=0.50
- **ticker_unresolved**: 4
    - company_announcements: SML Isuzu: no candidate symbol resolved on Muns
    - company_announcements: Force Motors: no candidate symbol resolved on Muns
    - financials: SML Isuzu: no candidate symbol resolved on Muns
    - financials: Force Motors: no candidate symbol resolved on Muns
- **unmapped_oem**: 3
    - company_announcements: Tata Motors PV: 'Tata Motors Passenger Vehicles Limited' not in alias map (kept, not dropped)
    - company_announcements: Tata Motors CV: 'Tata Motors CV' not in alias map (kept, not dropped)
    - company_announcements: Hyundai Motor India: 'Hyundai Motor India Limited' not in alias map (kept, not dropped)

## Lane status
- `fada` (lane C): error — ValidationException: An error occurred (ValidationException) when calling the InvokeModel operation: messages.2: `tool_use` ids were found without `tool_result` blocks immediately after: toolu_bdrk_01WfJyXCLoTuipZaGyYrqMRa. Each `tool_use` block must have a corresponding `tool_result` block in the next message. · records=0 flags=0
- `manual` (lane Manual): skipped — no source data available (fetch returned nothing) · records=0 flags=0
- `company_announcements` (lane A): ok · records=95 flags=9
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
