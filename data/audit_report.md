# Auto OEM Trends — Audit Report

- Run: `2026-10-18T10:33:13.184413+00:00`
- Publish gate: ✅ clean — safe to commit
- LLM tally: 11 calls, ~$0.532 (140776+7307 tok)

## Store
- `Company(BSE/NSE)`: 186 records, 186 unique keys
- `FADA`: 138 records, 138 unique keys
- `Internal-DB(historical)`: 15915 records, 15915 unique keys
- `SIAM`: 56944 records, 56944 unique keys

## Flags
- **extract_failed**: 17
    - fada: OCR unavailable or empty
    - company_announcements: MARUTI: OCR unavailable or empty
    - company_announcements: MARUTI: OCR unavailable or empty
    - company_announcements: TMPV: OCR unavailable or empty
    - company_announcements: TMPV: OCR unavailable or empty
    - company_announcements: TMCV: OCR unavailable or empty
    - company_announcements: M&M: OCR unavailable or empty
    - company_announcements: M&M: OCR unavailable or empty
    - company_announcements: M&M: OCR unavailable or empty
    - company_announcements: HYUNDAI: OCR unavailable or empty
    - company_announcements: BAJAJ-AUTO: OCR unavailable or empty
    - company_announcements: TVSMOTOR: OCR unavailable or empty
    - company_announcements: EICHERMOT: OCR unavailable or empty
    - company_announcements: EICHERMOT: OCR unavailable or empty
    - company_announcements: ASHOKLEY: OCR unavailable or empty
    - company_announcements: ESCORTS: OCR unavailable or empty
    - company_announcements: ATULAUTO: OCR unavailable or empty
- **ticker_unresolved**: 8
    - company_announcements: SML Isuzu: no candidate symbol resolved on Muns
    - company_announcements: Force Motors: no candidate symbol resolved on Muns
    - financials: SML Isuzu: no candidate symbol resolved on Muns
    - financials: Force Motors: no candidate symbol resolved on Muns
    - financials: Atul Auto: no candidate symbol resolved on Muns
    - financials: Olectra Greentech: no candidate symbol resolved on Muns
    - financials: Ola Electric: no candidate symbol resolved on Muns
    - financials: Ather Energy: no candidate symbol resolved on Muns

## Lane status
- `fada` (lane C): ok · records=0 flags=1
- `manual` (lane Manual): skipped — no source data available (fetch returned nothing) · records=0 flags=0
- `company_announcements` (lane A): ok · records=0 flags=18
- `concalls` (lane E): skipped — no source data available (fetch returned nothing) · records=0 flags=0
- `financials` (lane D): ok · records=0 flags=6
- `siam` (lane B): skipped — no source data available (fetch returned nothing) · records=0 flags=0

## Idempotency
- no duplicate natural keys — store is idempotent

## New data
- no new live records this run — last good data intact
