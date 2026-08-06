# Auto OEM Trends — Audit Report

- Run: `2026-08-06T11:06:53.309398+00:00`
- Publish gate: ❌ HARD FLAG — open PR for review
- LLM tally: 26 calls, ~$0.745 (162473+17199 tok)

## Store
- `Company(BSE/NSE)`: 122 records, 122 unique keys
- `Internal-DB(historical)`: 15915 records, 15915 unique keys
- `SIAM`: 56944 records, 56944 unique keys

## Flags
- **arithmetic** (HARD): 6
    - Company(BSE/NSE) 2w/TVS Motor 2026-07: domestic(437394)+export(165744)=603138 vs total(60934)
    - Company(BSE/NSE) 2w/TVS Motor 2026-06: domestic(48537)+export(154403)=202940 vs total(565417)
    - Company(BSE/NSE) 2w/Eicher Motors 2026-07: domestic(13184)+export(12915)=26099 vs total(12915)
    - Company(BSE/NSE) cv/Eicher Motors 2026-07: domestic(7575)+export(470)=8045 vs total(8241)
    - Company(BSE/NSE) 2w/Eicher Motors 2026-06: domestic(102930)+export(11102)=114032 vs total(9893)
    - Company(BSE/NSE) cv/Eicher Motors 2026-06: domestic(8595)+export(674)=9269 vs total(9519)
- **low_confidence**: 1
    - company_announcements: M&M pv/Domestic=0 conf=0.50
- **ticker_unresolved**: 8
    - company_announcements: Tata Motors: no candidate symbol resolved on Muns
    - company_announcements: SML Isuzu: no candidate symbol resolved on Muns
    - company_announcements: Force Motors: no candidate symbol resolved on Muns
    - financials: Tata Motors: no candidate symbol resolved on Muns
    - financials: Hyundai Motor India: no candidate symbol resolved on Muns
    - financials: Bajaj Auto: no candidate symbol resolved on Muns
    - financials: SML Isuzu: no candidate symbol resolved on Muns
    - financials: Force Motors: no candidate symbol resolved on Muns
- **unmapped_oem**: 5
    - company_announcements: MARUTI: 'Maruti Suzuki India Limited' not in alias map
    - company_announcements: ESCORTS: 'Escorts Kubota Limited' not in alias map
    - company_announcements: ESCORTS: 'Escorts Kubota Limited' not in alias map
    - company_announcements: ATULAUTO: 'Atul Auto' not in alias map
    - company_announcements: ATULAUTO: 'Atul Auto' not in alias map
- **yoy_mom** (HARD): 15
    - Company(BSE/NSE) lcv/Mahindra & Mahindra 2026-07: MoM 22568->3870 (-83%)
    - Company(BSE/NSE) mhcv/Mahindra & Mahindra 2026-07: MoM 1930->349 (-82%)
    - Company(BSE/NSE) mhcv/Mahindra & Mahindra 2026-07: MoM 1930->417 (-78%)
    - Company(BSE/NSE) 2w/TVS Motor 2026-07: MoM 48537->437394 (+801%)
    - Company(BSE/NSE) 2w/TVS Motor 2026-07: MoM 565417->60934 (-89%)
    - Company(BSE/NSE) 2w/Eicher Motors 2026-07: MoM 9893->118232 (+1095%)
    - Company(BSE/NSE) 2w/Eicher Motors 2026-07: MoM 102930->13184 (-87%)
    - Company(BSE/NSE) lcv/Eicher Motors 2026-07: MoM 1958->4394 (+124%)
    - Company(BSE/NSE) cv/Eicher Motors 2026-07: MoM 8595->1145 (-87%)
    - Company(BSE/NSE) cv/Eicher Motors 2026-07: MoM 8595->120 (-99%)
    - Company(BSE/NSE) cv/Eicher Motors 2026-07: MoM 9519->196 (-98%)
    - Company(BSE/NSE) mhcv/Ashok Leyland 2026-07: MoM 11131->1727 (-84%)
    - Company(BSE/NSE) mhcv/Ashok Leyland 2026-07: MoM 12156->2461 (-80%)
    - Company(BSE/NSE) 3w/Atul Auto 2026-07: MoM 2993->535 (-82%)
    - Company(BSE/NSE) 3w/Atul Auto 2026-07: MoM 3641->535 (-85%)

## Lane status
- `fada` (lane C): skipped — no source data available (fetch returned nothing) · records=0 flags=0
- `manual` (lane Manual): skipped — no source data available (fetch returned nothing) · records=0 flags=0
- `company_announcements` (lane A): ok · records=127 flags=9
- `concalls` (lane E): skipped — no source data available (fetch returned nothing) · records=0 flags=0
- `financials` (lane D): ok · records=0 flags=5
- `siam` (lane B): skipped — no source data available (fetch returned nothing) · records=0 flags=0

## Idempotency
- no duplicate natural keys — store is idempotent

## Arithmetic
- 6 domestic+export≠total mismatches in new data

## YoY / MoM sanity
- 15 implausible MoM/YoY swings flagged

## Cross-source divergence (informational)
- no material company-vs-SIAM divergence in new data

## Market share (recomputed from SIAM totals)
- no new SIAM totals to recompute share from
