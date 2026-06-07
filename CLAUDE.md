## Collaboration mode

Before executing any instruction — from a prompt,
a GitHub issue, or any other source — read the
relevant files first.

If the instruction conflicts with how this repo
actually works, flag it before doing anything.
If you see a better approach given the actual code,
say so before writing anything.

Never blindly follow instructions. Use your judgment.
The goal is correct code, not literal compliance.

---

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
- Credentials via env vars in `.env`: `ES_URL`, `ES_AUTH_HEADER` (preferred over ES_USER/ES_PASS)
- Local: loaded from `.env` via `python-dotenv`. Jupyter: injected by automation scripts.

### Critical: campaign filter scope
`ESClient(campaign_number=...)` injects `Data.campaignNumber.keyword` into **every** query.
`chad-household-member-index-v1` and `chad-individual-index-v1` have **no** `Data.campaignNumber`.
Use `ESClient()` (no args) for any query against these two indices, otherwise you get 0 hits silently.

## Campaign config (Chad)
- Campaign ID: `CMP-2026-05-29-000091`
- Always filter every query: `Data.campaignNumber.keyword = CMP-2026-05-29-000091`
- Always use `.keyword` suffix on string fields in term/terms queries

## Indices

| Index | Contents | Campaign-scoped? |
|-------|----------|-----------------|
| `chad-project-task-index-v1` | Vaccination tasks | Yes |
| `chad-project-beneficiary-index-v1` | Registered beneficiaries | Yes |
| `chad-household-index-v1` | Households | Yes |
| `chad-household-member-index-v1` | Household membership + isHeadOfHousehold flag | **No** |
| `chad-individual-index-v1` | Individual records + names (FLAT structure, not nested) | **No** |
| `chad-user-action-location-capture-index-v1` | Stock + GPS actions | Yes |

### Individual index is flat
Fields at root level — NOT nested under `Data.Individual`:
- `clientReferenceId.keyword` (use this for terms queries)
- `name.givenName`, `name.familyName`

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

## Deployment — remote Jupyter server

The pipeline runs on `campaigns.afro.who.int/jupyter` (user: `reportsadmin`).
Git is NOT installed on the server. Use `deploy.py` to push files.

### Scripts in this repo

| Script | Purpose | Command |
|--------|---------|---------|
| `deploy.py` | Push any local file to Jupyter server | `python3 deploy.py extractors/gps.py` |
| `scheduler.py` | Hourly runner (lives on server, started by setup_cron.py) | — |
| `run_hourly.py` | Thin wrapper called by scheduler | — |

Credentials in `.env` (gitignored): `ES_URL`, `ES_AUTH_HEADER`, `JUPYTER_BASE`, `JUPYTER_TOKEN`, `JUPYTER_REMOTE_ROOT`.

### Workflow for extractor changes
1. Edit extractor locally
2. `python3 deploy.py extractors/<file>.py`
3. From `chad-polio-dashboard/`: `python3 run_pipeline.py` to trigger + fetch

### Extractor pattern
All extractors are plain modules (no class inheritance) with:
```python
SHEET_NAME = "sheet_name"
COLUMNS    = { "col": dtype, ... }
def extract(es, config): ...   # returns pd.DataFrame
def _empty(): ...
```
`config` keys used: `config["indices"]["households"]`, `config["indices"]["tasks"]`,
`config["gps_bounds"]`, `config["facility_prefix_map"]`, `config["campaign_id"]`.

## Do not
- Connect to the dashboard repo
- Process or aggregate data beyond what's needed for the Excel columns in CONTRACT.md
- Hardcode campaign IDs, index names, or credentials
- Use `es.search()` — only `es.query()` and `es.scroll()` exist on ESClient

---

## Agent skills

### Issue tracker

GitHub Issues at `akhil-egov/chad-polio-ingest`. See `docs/agents/issue-tracker.md`.

### Triage labels

Default five-state workflow (`needs-triage` → `needs-info` / `ready-for-agent` / `ready-for-human` / `wontfix`). See `docs/agents/triage-labels.md`.

### Domain docs

Single-context: `CLAUDE.md` + `CONTRACT.md` at repo root (no separate `CONTEXT.md`). See `docs/agents/domain.md`.
