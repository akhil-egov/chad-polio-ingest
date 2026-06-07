# chad-polio-ingest

Data extraction pipeline for the WHO AFRO nOPV2 campaign dashboard — N'Djamena, Chad, June 2026.

Pulls structured data from Elasticsearch, shapes it with pandas, and writes a timestamped Excel file consumed by [`chad-polio-dashboard`](https://github.com/akhil-egov/chad-polio-dashboard).

---

## Pipeline overview

```
Elasticsearch (WHO AFRO)
        │
        ▼
  chad-polio-ingest          ← you are here
  (extractors/ + main.py)
        │
        ▼
  output/chad_YYYYMMDD_HHMM.xlsx
        │
        ▼
  chad-polio-dashboard
  (fetch_latest.py → data.json → Vercel)
```

---

## Quick start (local)

```bash
git clone https://github.com/akhil-egov/chad-polio-ingest
cd chad-polio-ingest
pip install -r requirements.txt
cp .env.example .env   # fill in ES_URL + ES_AUTH_HEADER
python main.py
```

Output lands in `output/chad_YYYYMMDD_HHMM.xlsx`.

---

## Environment variables (`.env`)

```
ES_URL=https://elasticsearch-data.es-cluster:9200
ES_AUTH_HEADER=Basic <base64-encoded credentials>
OUTPUT_DIR=output

JUPYTER_BASE=https://<host>/jupyter/user/<username>
JUPYTER_TOKEN=<jupyterhub_api_token>
JUPYTER_REMOTE_ROOT=<path/to/DST/relative/to/jupyter/home>
```

---

## Repository structure

```
extractors/
  base.py           — ESClient (only file that touches ES)
  coverage.py       — daily vaccinations by facility
  activity.py       — per-user task count + last sync
  refusals.py       — refusal reason codes by facility
  enumeration.py    — households + eligible children + vaccinated
  stock.py          — vial reconciliation (supply-side)
  stock_daily.py    — per-team per-day vial issuance
  gps.py            — household GPS + vaccination count + head-of-household
  gps_refusals.py   — refusal household dots
  gps_zerodose.py   — zero-dose children
  microplan.py      — coverage vs microplan target
  settlement.py     — URBAN/RURAL/SLUMS breakdown
  demographics.py   — age/gender of vaccinated children
  inactive_users.py — users not synced in 24h
config/
  chad.json         — campaign config (IDs, bounds, facility map)
deploy.py           — push any local file to remote Jupyter server
scheduler.py        — hourly background runner for Jupyter server
run_hourly.py       — wrapper called by scheduler
main.py             — entry point: run(country, reports="all")
CONTRACT.md         — Excel schema shared with dashboard repo
```

---

## Running specific reports

```bash
python main.py --reports gps,enumeration
python main.py --reports all             # default
```

---

## Deployment — remote Jupyter server

The pipeline runs on a **remote JupyterHub** server (no git, no crontab installed). Use the automation scripts to manage it.

### Deploy a file to the server
```bash
python3 deploy.py extractors/gps.py
python3 deploy.py extractors/gps.py extractors/enumeration.py   # multiple files
```
Uses the Jupyter contents API with `JUPYTER_TOKEN` from `.env`.

### Start the hourly scheduler (once, or after a server reboot)
```bash
# From chad-polio-dashboard/
python3 setup_cron.py
```
Starts `scheduler.py` as a background process on the server. Logs to `~/pipeline.log`.

### Full workflow for an extractor change
```bash
# 1. Edit locally
vim extractors/gps.py

# 2. Deploy to server
python3 deploy.py extractors/gps.py

# 3. Trigger an immediate run + download + push
cd ../chad-polio-dashboard
python3 run_pipeline.py
```

---

## Elasticsearch indices

| Index | Contents | Campaign-scoped? |
|-------|----------|-----------------|
| `chad-household-index-v1` | Households | Yes |
| `chad-project-task-index-v1` | Vaccination tasks | Yes |
| `chad-project-beneficiary-index-v1` | Registered beneficiaries | Yes |
| `chad-household-member-index-v1` | Membership + isHeadOfHousehold | **No** |
| `chad-individual-index-v1` | Names (flat structure) | **No** |
| `chad-user-action-location-capture-index-v1` | Stock + GPS actions | Yes |

Campaign ID: `CMP-2026-05-29-000091`

### ⚠️ Campaign filter gotcha
`ESClient(campaign_number=...)` in `main.py` injects `Data.campaignNumber.keyword` into every query. The member and individual indices have no such field — queries against them via the campaign-scoped client return **0 hits silently**. Always use `ESClient()` (no args) for those two indices.

### ⚠️ Individual index is flat
`chad-individual-index-v1` fields are at the **root level**, not nested under `Data.Individual`:
- Query: `clientReferenceId.keyword`
- Names: `name.givenName`, `name.familyName`

---

## Extractor pattern

All extractors are plain modules — no class inheritance:

```python
SHEET_NAME = "sheet_name"
COLUMNS    = {"col": dtype, ...}

def extract(es, config) -> pd.DataFrame: ...
def _empty() -> pd.DataFrame: ...
```

`config` comes from `config/chad.json`. Common keys: `config["indices"]["households"]`, `config["indices"]["tasks"]`, `config["gps_bounds"]`, `config["facility_prefix_map"]`.

---

## Data contract

`CONTRACT.md` defines the exact Excel schema. **Both repos treat it as ground truth.** Never rename a column or sheet without updating `CONTRACT.md` first.

---

## ESClient methods

```python
es.query(index, body)           # single POST _search, returns dict
es.scroll(index, body, size)    # generator, yields one hit at a time
```

`es.search()` does not exist. Always use `es.query()` or `es.scroll()`.
