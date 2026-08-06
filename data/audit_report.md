# Auto OEM Trends — Audit Report

- Run: `2026-08-06T09:10:08.971394+00:00`
- Publish gate: ✅ clean — safe to commit
- LLM tally: 0 calls, ~$0.000 (0+0 tok)

## Store
- `Internal-DB(historical)`: 15915 records, 15915 unique keys
- `SIAM`: 56944 records, 56944 unique keys

## Flags
- none

## Lane status
- `fada` (lane C): skipped — no source data available (fetch returned nothing) · records=0 flags=0
- `manual` (lane Manual): skipped — no source data available (fetch returned nothing) · records=0 flags=0
- `company_announcements` (lane A): error — HttpError: HTTP 404 from https://devde.muns.io/filings/corp/announcements/TATAMOTORS: {"statusCode":404,"timestamp":"2026-08-06T09:11:49.127Z","path":"/filings/corp/announcements/TATAMOTORS?fromDate=20260622&toDate=20260806","requestId":"e908996d-2a9b-4a1b-94e7-d1d6113eed0f","sessionId":"69c19441-deda-4f2c-9e5f-3f778c6956cd","message":{"message":"Stock not found: \"TATAMOTORS\". Plea …[+84 chars] · records=0 flags=0
- `concalls` (lane E): skipped — no source data available (fetch returned nothing) · records=0 flags=0
- `financials` (lane D): error — HttpError: HTTP 404 from https://devde.muns.io/filings/financial_tables/markdown/TATAMOTORS: {"statusCode":404,"timestamp":"2026-08-06T09:14:19.178Z","path":"/filings/financial_tables/markdown/TATAMOTORS?form=consolidated","requestId":"3ea17483-95a5-472e-a373-ccb7e3580cdd","sessionId":"1797f633-e08d-44a4-b252-5c4ff7190227","message":{"message":"Stock not found: \"TATAMOTORS\". Please verify …[+75 chars] · records=0 flags=0
- `siam` (lane B): skipped — no source data available (fetch returned nothing) · records=0 flags=0

## Idempotency
- no duplicate natural keys — store is idempotent

## New data
- no new live records this run — last good data intact
