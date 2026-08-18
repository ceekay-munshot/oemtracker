# Auto OEM Trends — Audit Report

- Run: `2026-08-18T06:44:45.520408+00:00`
- Publish gate: ✅ clean — safe to commit
- LLM tally: 15 calls, ~$0.350 (65799+10156 tok)

## Store
- `Company(BSE/NSE)`: 127 records, 127 unique keys
- `FADA`: 69 records, 69 unique keys
- `Internal-DB(historical)`: 15915 records, 15915 unique keys
- `SIAM`: 56944 records, 56944 unique keys

## Flags
- **low_confidence**: 1
    - company_announcements: ATULAUTO 3w/Exports=585 conf=0.50
- **ticker_unresolved**: 5
    - company_announcements: Maruti Suzuki: no candidate symbol resolved on Muns
    - company_announcements: SML Isuzu: no candidate symbol resolved on Muns
    - company_announcements: Force Motors: no candidate symbol resolved on Muns
    - financials: SML Isuzu: no candidate symbol resolved on Muns
    - financials: Force Motors: no candidate symbol resolved on Muns
- **unmapped_oem**: 50
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
    - fada: FADA: 'MAHINDRA LAST MILE MOBILITY LTD' not in alias map (kept)
    - fada: FADA: 'MAHINDRA & MAHINDRA LIMITED (2)' not in alias map (kept)
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
    - …and 25 more

## Lane status
- `fada` (lane C): ok · records=69 flags=49
- `manual` (lane Manual): skipped — no source data available (fetch returned nothing) · records=0 flags=0
- `company_announcements` (lane A): ok · records=49 flags=5
- `concalls` (lane E): skipped — no source data available (fetch returned nothing) · records=0 flags=0
- `financials` (lane D): error — ServiceUnavailableException: An error occurred (ServiceUnavailableException) when calling the InvokeModel operation (reached max retries: 4): Bedrock is unable to process your request. · records=0 flags=2
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
