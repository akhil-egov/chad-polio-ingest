# chad-polio-ingest

## Role
This repo is the **data extraction layer only**. It pulls from Elasticsearch and writes Excel files.  
It does NOT process, transform, or visualise data. It does NOT connect to the dashboard.

## Three-repo pipeline
```
[chad-polio-ingest]  →  Excel file  →  [chad-polio-transform (future)]  →  [chad-polio-dashboard]
```
For now: ingest writes Excel → dashboard reads it directly (transform step is manual).

## Data contract
`CONTRACT.md` in this repo defines the exact Excel schema both this repo and the dashboard depend on.  
**Never change column names or sheet names without updating CONTRACT.md first.**

## Architecture decisions (set by master window)
- Config-driven: campaign params live in `config/chad.json`, never hardcoded
- `base.py` is the only file that makes HTTP calls to Elasticsearch
- Entry point: `main.py` with `run(country, reports="all")` callable as function AND CLI
- `notebook.ipynb` at root is a thin wrapper that calls `main.py` — all logic lives in `.py` files
- Output: `output/chad_YYYYMMDD_HHMM.xlsx`, timestamped, never overwritten

## Elasticsearch
- URL: `https://elasticsearch-data.es-cluster:9200`
- Auth: Basic auth, `verify=False`
- Credentials via env vars: `ES_URL`, `ES_USER`, `ES_PASS`
- Local: load from `.env` file. Jupyter: set in kernel environment.

## Campaign config (Chad)
- Campaign ID: `CMP-2026-05-29-000091`
- Always filter every query: `Data.campaignNumber.keyword = CMP-2026-05-29-000091`
- Always use `.keyword` suffix on string fields in term/terms queries

## Indices
- `chad-project-task-index-v1` — vaccination tasks (~12,500+ records)
- `chad-project-beneficiary-index-v1` — registered beneficiaries (~62,000+)
- `chad-household-index-v1` — households (~18,700+)
- `chad-user-action-location-capture-index-v1` — stock + GPS actions

## Critical field rules
- Vaccination status: use `administrationStatus`, NOT `productName`
- Eligible children: `ageInMonths <= 59` AND `isHeadOfHousehold = false`
- GPS valid range: longitude 13–17, latitude 11–14 (filter out ~77° India coordinates)
- Inactive users: always build full user list from USER_FACILITY_MAP and left-join (they are missing from task index)

## Ten extractors to build (one file each in extractors/)
1. `coverage.py` — daily vaccinations by facility and day
2. `activity.py` — per-user task count by date + last sync time
3. `refusals.py` — refusal reason codes by facility
4. `enumeration.py` — households registered + eligible children + vaccinated children (**two-index query**: household + beneficiary index for enumeration fields, task index for vaccinated_children)
5. `stock.py` — vials issued / returned / used
6. `gps.py` — household and task lat/lng (GPS-valid only)
7. `microplan.py` — coverage % vs facility targets
8. `settlement.py` — URBAN/RURAL/SLUMS breakdown
9. `demographics.py` — age/gender of vaccinated children
10. `inactive_users.py` — users with no sync in last 24h (part of activity.py or separate)

## Dependencies (keep minimal)
- `requests` — ES HTTP calls
- `pandas` — data shaping
- `openpyxl` — Excel write
- `python-dotenv` — local .env loading
- No heavy libs (no numpy, no elasticsearch-py client)

## Do not
- Connect to the dashboard repo
- Process or aggregate data beyond what's needed for the Excel columns in CONTRACT.md
- Hardcode campaign IDs, index names, or credentials
