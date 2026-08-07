# Auto OEM Trends — Audit Report

- Run: `2026-08-07T09:41:40.110606+00:00`
- Publish gate: ✅ clean — safe to commit
- LLM tally: 16 calls, ~$0.777 (198509+12131 tok)

## Store
- `Company(BSE/NSE)`: 118 records, 118 unique keys
- `FADA`: 67 records, 67 unique keys
- `Internal-DB(historical)`: 15915 records, 15915 unique keys
- `SIAM`: 56944 records, 56944 unique keys

## Flags
- **low_confidence**: 3
    - company_announcements: ASHOKLEY mhcv/Exports=1220 conf=0.50
    - company_announcements: ASHOKLEY lcv/Exports=390 conf=0.50
    - company_announcements: ATULAUTO 3w/Exports=585 conf=0.50
- **ticker_unresolved**: 4
    - company_announcements: SML Isuzu: no candidate symbol resolved on Muns
    - company_announcements: Force Motors: no candidate symbol resolved on Muns
    - financials: SML Isuzu: no candidate symbol resolved on Muns
    - financials: Force Motors: no candidate symbol resolved on Muns
- **unmapped_oem**: 47
    - fada: FADA: 'HONDA MOTORCYCLE AND SCOOTER INDIA (P) LTD' not in alias map (kept)
    - fada: FADA: 'SUZUKI MOTORCYCLE INDIA PVT LTD' not in alias map (kept)
    - fada: FADA: 'INDIA YAMAHA MOTOR PVT LTD' not in alias map (kept)
    - fada: FADA: 'ATHER ENERGY LTD' not in alias map (kept)
    - fada: FADA: 'OLA ELECTRIC TECHNOLOGIES PVT LTD' not in alias map (kept)
    - fada: FADA: 'GREAVES ELECTRIC MOBILITY LTD' not in alias map (kept)
    - fada: FADA: 'RIVER MOBILITY PVT LTD' not in alias map (kept)
    - fada: FADA: 'BGAUSS AUTO PRIVATE LIMITED' not in alias map (kept)
    - fada: FADA: 'CLASSIC LEGENDS PVT LTD' not in alias map (kept)
    - fada: FADA: 'PIAGGIO VEHICLES PVT LTD' not in alias map (kept)
    - fada: FADA: 'Others Including EV' not in alias map (kept)
    - fada: FADA: 'MAHINDRA & MAHINDRA LIMITED' not in alias map (kept)
    - fada: FADA: 'PIAGGIO VEHICLES PVT LTD' not in alias map (kept)
    - fada: FADA: 'YC ELECTRIC VEHICLE' not in alias map (kept)
    - fada: FADA: 'DILLI ELECTRIC AUTO PVT LTD' not in alias map (kept)
    - fada: FADA: 'SAERA ELECTRIC AUTO PVT LTD' not in alias map (kept)
    - fada: FADA: 'MINI METRO EV L.L.P' not in alias map (kept)
    - fada: FADA: 'Others including EV' not in alias map (kept)
    - fada: FADA: 'MAHINDRA & MAHINDRA LIMITED' not in alias map (kept)
    - fada: FADA: 'VE COMMERCIAL VEHICLES LTD' not in alias map (kept)
    - fada: FADA: 'FORCE MOTORS LIMITED' not in alias map (kept)
    - fada: FADA: 'SML MAHINDRA LTD' not in alias map (kept)
    - fada: FADA: 'DAIMLER INDIA COMMERCIAL VEHICLES PVT. LTD' not in alias map (kept)
    - fada: FADA: 'Others' not in alias map (kept)
    - fada: FADA: 'MAHINDRA & MAHINDRA LIMITED' not in alias map (kept)
    - …and 22 more

## Lane status
- `fada` (lane C): ok · records=67 flags=47
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
