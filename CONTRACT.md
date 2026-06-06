# Data Contract — Chad Polio Pipeline

This file is the handshake between `chad-polio-ingest` (extraction) and `chad-polio-dashboard` (visualisation).  
**Both repos must treat this as ground truth. Change here first, then update both repos.**

## Architectural decisions log

| # | Decision | Rationale |
|---|----------|-----------|
| 1 | `facility_id` = 2-letter prefix from `config/chad.json` (e.g. `AB`, `AT`, `BO1`) | ES only stores names, not IDs. Prefixes are already canonical in field data. |
| 2 | `stock` sheet is supply-side only — no `doses_per_vial`, no `doses_administered` | Actual doses are in task index and will differ from formula. Reconciliation is a future view. |
| 3 | `enumeration.vaccinated_children` requires two-index query (beneficiary + task index) | Documented in CLAUDE.md. Implementation detail, not a schema change. |

---

## Output file

`output/chad_YYYYMMDD_HHMM.xlsx`  
Timestamped. Never overwrite. Latest file = source of truth for dashboard.

---

## Sheets

### `coverage`
Daily vaccination by facility and day.

| Column | Type | Notes |
|--------|------|-------|
| `facility_name` | string | Health facility name |
| `facility_id` | string | 2-letter prefix from config (e.g. `AB`, `AT`, `BO1`) |
| `date` | YYYY-MM-DD | Vaccination date |
| `vaccinated` | int | Children vaccinated that day |
| `target` | int | Facility total target (from microplan) |
| `cumulative_vaccinated` | int | Running total to date |
| `pct_complete` | float | cumulative / target * 100 |

---

### `activity`
Per-user activity and sync status.

| Column | Type | Notes |
|--------|------|-------|
| `user_id` | string | |
| `user_name` | string | |
| `facility_name` | string | |
| `facility_id` | string | |
| `date` | YYYY-MM-DD | |
| `task_count` | int | Tasks completed that day |
| `last_sync` | ISO datetime | Most recent sync timestamp |
| `is_inactive` | bool | True if no sync in last 24h |

---

### `refusals`
Refusal reason codes by facility.

| Column | Type | Notes |
|--------|------|-------|
| `facility_name` | string | |
| `facility_id` | string | |
| `reason_code` | string | Raw code from ES |
| `reason_label` | string | Human-readable label |
| `count` | int | |

---

### `enumeration`
Household registration and eligible children. **Two-index query** — beneficiary index + task index.

| Column | Type | Notes |
|--------|------|-------|
| `facility_name` | string | |
| `facility_id` | string | 2-letter prefix from config |
| `households_registered` | int | From household index |
| `eligible_children` | int | age ≤ 59 months, not head of household — from beneficiary index |
| `vaccinated_children` | int | From task index (administrationStatus = success) |
| `pct_complete` | float | vaccinated_children / eligible_children * 100 |

---

### `stock`
Vial reconciliation by facility. **Supply-side only** — no dose estimates.

| Column | Type | Notes |
|--------|------|-------|
| `facility_name` | string | |
| `facility_id` | string | 2-letter prefix from config |
| `vials_issued` | int | |
| `vials_returned` | int | |
| `vials_used` | int | issued - returned |

---

### `gps`
Lat/lng for map rendering. GPS-valid records only.

| Column | Type | Notes |
|--------|------|-------|
| `record_id` | string | |
| `record_type` | string | `household` or `task` |
| `lat` | float | Filtered: 11–14 |
| `lng` | float | Filtered: 13–17 |
| `facility_name` | string | |
| `facility_id` | string | |
| `vaccinated` | bool | For task records |
| `settlement_type` | string\|null | `URBAN`, `RURAL`, `SLUMS`, `NOMADS_PASTORALISTS` — from `Data.additionalDetails.settlementType` |
| `settlement_name` | string\|null | Neighbourhood/quartier name — from `Data.boundaryHierarchy.settlement` |

---

### `gps_refusals`
Lat/lng for households that refused vaccination. Same index as `gps` (household-index), filtered to records where `reasonForRefusal` exists.

| Column | Type | Notes |
|--------|------|-------|
| `record_id` | string | Household ID |
| `lat` | float | Filtered: 11–14 |
| `lng` | float | Filtered: 13–17 |
| `facility_name` | string | |
| `facility_id` | string | |
| `settlement_name` | string\|null | Neighbourhood/quartier name |
| `settlement_type` | string\|null | `URBAN`, `RURAL`, `SLUMS`, `NOMADS_PASTORALISTS` |
| `user_name` | string\|null | Team code |
| `member_count` | int\|null | Household size |
| `reason_for_refusal` | string\|null | e.g. `NOT_DECISION_MAKER`, `RELIGIOUS_BELIEFS` |
| `reason_not_vaccinated` | string\|null | Broader category e.g. `REFUSAL` |

---

### `gps_zerodose`
Lat/lng for children who had never received OPV before this campaign (`receivedOPVBefore = "NO"`). From task index. Includes both vaccinated and unvaccinated zero-dose children — check `administration_status`.

| Column | Type | Notes |
|--------|------|-------|
| `record_id` | string | ES `_id` of the task record |
| `lat` | float | Filtered: 11–14 |
| `lng` | float | Filtered: 13–17 |
| `facility_name` | string | |
| `facility_id` | string | |
| `settlement_name` | string\|null | Neighbourhood/quartier name |
| `settlement_type` | string\|null | `URBAN`, `RURAL`, `SLUMS`, `NOMADS_PASTORALISTS` |
| `user_name` | string\|null | Team code |
| `age_months` | int\|null | Child age in months |
| `gender` | string\|null | `MALE` / `FEMALE` |
| `administration_status` | string\|null | `ADMINISTRATION_SUCCESS` = vaccinated this campaign |

---

### `microplan`
Coverage vs microplan target by facility.

| Column | Type | Notes |
|--------|------|-------|
| `facility_name` | string | |
| `facility_id` | string | |
| `microplan_target` | int | From config |
| `achieved` | int | Vaccinated to date |
| `pct_complete` | float | |
| `gap` | int | target - achieved |

---

### `settlement`
Breakdown by settlement type.

| Column | Type | Notes |
|--------|------|-------|
| `settlement_type` | string | `URBAN`, `RURAL`, `SLUMS` |
| `household_count` | int | |
| `eligible_children` | int | |
| `vaccinated` | int | |
| `pct_complete` | float | |

---

### `demographics`
Age and gender distribution of vaccinated children.

| Column | Type | Notes |
|--------|------|-------|
| `age_group` | string | `0-11m`, `12-23m`, `24-35m`, `36-47m`, `48-59m` |
| `gender` | string | `M`, `F` |
| `vaccinated_count` | int | |

---

### `inactive_users`
Users who have not synced in the last 24 hours.

| Column | Type | Notes |
|--------|------|-------|
| `user_id` | string | |
| `user_name` | string | |
| `facility_name` | string | |
| `facility_id` | string | |
| `last_sync` | ISO datetime | Null if never synced |
| `hours_since_sync` | float | |

---

### `_metadata`
One row. Machine-readable run info.

| Column | Type |
|--------|------|
| `run_timestamp` | ISO datetime |
| `campaign_id` | string |
| `country` | string |
| `records_per_sheet` | JSON string |
| `extraction_duration_s` | float |
