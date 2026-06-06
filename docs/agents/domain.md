# Domain Docs — chad-polio-ingest

## Layout: single-context

One `CLAUDE.md` at the repo root. No `CONTEXT.md` yet (extraction pipeline — domain language lives in `CONTRACT.md` and `CLAUDE.md`).

## Consumer rules

- **Ground truth for schema**: `CONTRACT.md` — defines every sheet name, column name, and type. Never change output column names without updating CONTRACT.md first.
- **Ground truth for ES structure**: `CLAUDE.md` — field paths, index names, campaign ID, GPS bounds. Never hardcode these; read from `config/chad.json`.
- **Before any new extractor**: check `CONTRACT.md` for the target sheet spec. Check `CLAUDE.md` for the correct index and field paths.
- **ES calls**: only `base.py` makes HTTP calls. Use `es.query()` for paginated queries, `es.scroll()` for large result sets. Never call `es.search()` directly.
- **Credentials**: always via env vars (`ES_URL`, `ES_USER`, `ES_PASS`). Never hardcode. Load from `.env` locally; kernel env on Jupyter.

## Key domain concepts

- **Campaign ID**: `CMP-2026-05-29-000091` — every query must filter on this
- **Eligible child**: `ageInMonths <= 59` AND `isHeadOfHousehold = false`
- **Vaccinated**: `administrationStatus = ADMINISTRATION_SUCCESS` (NOT `productName`)
- **GPS valid range**: lat 11–14, lng 13–17 — filter all GPS queries to remove ~77° India artefacts
- **Inactive user**: no sync in last `config["inactive_threshold_hours"]` hours

## Related repo

`akhil-egov/chad-polio-dashboard` consumes the Excel output. `CONTRACT.md` in this repo is the shared schema.
