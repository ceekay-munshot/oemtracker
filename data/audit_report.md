# Auto OEM Trends — Audit Report

- Run: `2026-11-18T15:15:56.429793+00:00`
- Publish gate: ✅ clean — safe to commit
- LLM tally: 15 calls, ~$0.722 (195101+9145 tok)

## Store
- `Company(BSE/NSE)`: 186 records, 186 unique keys
- `FADA`: 138 records, 138 unique keys
- `Internal-DB(historical)`: 15915 records, 15915 unique keys
- `SIAM`: 56944 records, 56944 unique keys

## Flags
- **extract_failed**: 1
    - fada: OCR unavailable or empty
- **ticker_unresolved**: 17
    - company_announcements: Maruti Suzuki: no candidate symbol resolved on Muns
    - company_announcements: Tata Motors PV: no candidate symbol resolved on Muns
    - company_announcements: Tata Motors CV: no candidate symbol resolved on Muns
    - company_announcements: Mahindra & Mahindra: no candidate symbol resolved on Muns
    - company_announcements: Hyundai Motor India: no candidate symbol resolved on Muns
    - company_announcements: Bajaj Auto: no candidate symbol resolved on Muns
    - company_announcements: Hero MotoCorp: no candidate symbol resolved on Muns
    - company_announcements: TVS Motor: no candidate symbol resolved on Muns
    - company_announcements: Eicher Motors: no candidate symbol resolved on Muns
    - company_announcements: Ashok Leyland: no candidate symbol resolved on Muns
    - company_announcements: Escorts Kubota: no candidate symbol resolved on Muns
    - company_announcements: SML Isuzu: no candidate symbol resolved on Muns
    - company_announcements: Force Motors: no candidate symbol resolved on Muns
    - company_announcements: Atul Auto: no candidate symbol resolved on Muns
    - company_announcements: Olectra Greentech: no candidate symbol resolved on Muns
    - financials: SML Isuzu: no candidate symbol resolved on Muns
    - financials: Force Motors: no candidate symbol resolved on Muns

## Lane status
- `fada` (lane C): ok · records=0 flags=1
- `manual` (lane Manual): skipped — no source data available (fetch returned nothing) · records=0 flags=0
- `company_announcements` (lane A): ok · records=0 flags=15
- `concalls` (lane E): skipped — no source data available (fetch returned nothing) · records=0 flags=0
- `financials` (lane D): ok · records=0 flags=2
- `siam` (lane B): skipped — no source data available (fetch returned nothing) · records=0 flags=0

## Idempotency
- no duplicate natural keys — store is idempotent

## New data
- no new live records this run — last good data intact
