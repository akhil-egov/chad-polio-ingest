"""
GPS extractor — lat/lng for map rendering. GPS-valid records only.

Household records from chad-household-index-v1.
record_type = "household", vaccinated = False (household presence, not status).

GPS filter: lat 11-14, lng 13-17 (from config["gps_bounds"])
This filter removes the ~77° India coordinate artefacts that appear in raw data.

vaccinated_count: number of ADMINISTRATION_SUCCESS task records whose GPS coords
(Data.additionalDetails.lat/lng, rounded to 5dp ≈ 1m) match this household's
coordinates. householdId is null on task records so coordinate matching is the
only available join key.

head_of_household: 2-hop join via an unscoped ESClient (member/individual indices
have no campaignNumber field, so the campaign-scoped es client returns 0 hits).
  hop 1: household.clientReferenceId → household-member-index (isHeadOfHousehold=True)
  hop 2: individualClientReferenceId → individual-index → name.givenName/familyName
"""

import math
import pandas as pd
from extractors.base import ESClient


SHEET_NAME = "gps"

COLUMNS = {
    "record_id":         pd.StringDtype(),
    "record_type":       pd.StringDtype(),
    "lat":               "float64",
    "lng":               "float64",
    "facility_name":     pd.StringDtype(),
    "facility_id":       pd.StringDtype(),
    "vaccinated":        "boolean",
    "settlement_type":   pd.StringDtype(),
    "settlement_name":   pd.StringDtype(),
    "user_name":         pd.StringDtype(),
    "member_count":      pd.Int64Dtype(),
    "vaccinated_count":  pd.Int64Dtype(),
    "head_of_household": pd.StringDtype(),
}

_MEMBER_INDEX     = "chad-household-member-index-v1"
_INDIVIDUAL_INDEX = "chad-individual-index-v1"
_BATCH            = 500


def _fetch_head_names(hh_client_refs: set) -> dict:
    """2-hop join using a campaign-unscoped ESClient.

    Member and individual indices have no Data.campaignNumber field, so the
    campaign-scoped es client (from main.py) injects a filter that returns 0 hits.
    A fresh ESClient() with no campaign_number bypasses that filter.
    """
    if not hh_client_refs:
        return {}
    es_raw = ESClient()  # no campaign_number → no campaign filter
    refs = list(hh_client_refs)

    # Hop 1: member index → individualClientReferenceId for household heads
    ind_ref_by_hh = {}
    for i in range(0, len(refs), _BATCH):
        batch = refs[i : i + _BATCH]
        r = es_raw.query(_MEMBER_INDEX, {
            "query": {"bool": {"must": [
                {"terms": {"Data.householdMember.householdClientReferenceId.keyword": batch}},
                {"term":  {"Data.householdMember.isHeadOfHousehold": True}},
            ]}},
            "size": len(batch),
            "_source": ["Data.householdMember.householdClientReferenceId",
                        "Data.householdMember.individualClientReferenceId"],
        })
        for hit in r["hits"]["hits"]:
            m = hit["_source"]["Data"]["householdMember"]
            ind_ref_by_hh[m["householdClientReferenceId"]] = m["individualClientReferenceId"]

    if not ind_ref_by_hh:
        return {}

    # Hop 2: individual index (flat structure — no Data.Individual wrapper)
    ind_refs = list(ind_ref_by_hh.values())
    name_by_ind = {}
    for i in range(0, len(ind_refs), _BATCH):
        batch = ind_refs[i : i + _BATCH]
        r = es_raw.query(_INDIVIDUAL_INDEX, {
            "query": {"terms": {"clientReferenceId.keyword": batch}},
            "size": len(batch),
            "_source": ["clientReferenceId", "name.givenName", "name.familyName"],
        })
        for hit in r["hits"]["hits"]:
            src    = hit["_source"]
            cref   = src.get("clientReferenceId")
            nm     = src.get("name") or {}
            given  = (nm.get("givenName")  or "").strip()
            family = (nm.get("familyName") or "").strip()
            full   = f"{given} {family}".strip() if (given and family and given != family) else (given or family)
            if cref and full:
                name_by_ind[cref] = full

    return {hh: name_by_ind[ind] for hh, ind in ind_ref_by_hh.items() if ind in name_by_ind}


def extract(es, config: dict) -> pd.DataFrame:
    bounds             = config["gps_bounds"]
    facility_prefix_map = config["facility_prefix_map"]

    # ── Phase 1: household GPS records ──────────────────────────────────────
    gps_query = {"bool": {"must": [
        {"range": {"Data.household.address.latitude":  {"gte": bounds["lat_min"], "lte": bounds["lat_max"]}}},
        {"range": {"Data.household.address.longitude": {"gte": bounds["lon_min"], "lte": bounds["lon_max"]}}},
    ]}}

    count_resp    = es.query(config["indices"]["households"],
                             {"size": 0, "track_total_hits": True, "query": gps_query})
    expected_total = count_resp["hits"]["total"]["value"]
    print(f"GPS: expecting {expected_total} GPS-valid household records")

    rows = []
    for hit in es.scroll(config["indices"]["households"], {
        "query": gps_query,
        "_source": [
            "Data.household.id",
            "Data.household.clientReferenceId",
            "Data.household.address.latitude",
            "Data.household.address.longitude",
            "Data.boundaryHierarchy.healthFacility",
            "Data.boundaryHierarchy.settlement",
            "Data.additionalDetails.settlementType",
            "Data.additionalDetails.memberCount",
            "Data.userName",
        ],
    }, expected_total=expected_total):
        src  = hit.get("_source", {})
        data = src.get("Data", {})
        hh   = data.get("household", {})
        addr = hh.get("address", {})
        fn   = data.get("boundaryHierarchy", {}).get("healthFacility", "") or ""
        mc   = data.get("additionalDetails", {}).get("memberCount")
        try:   member_count = int(mc) if mc is not None else None
        except: member_count = None

        rows.append({
            "record_id":     hh.get("id") or hit["_id"],
            "_client_ref":   hh.get("clientReferenceId"),
            "record_type":   "household",
            "lat":           addr.get("latitude"),
            "lng":           addr.get("longitude"),
            "facility_name": fn,
            "facility_id":   facility_prefix_map.get(fn, ""),
            "vaccinated":    False,
            "settlement_type": data.get("additionalDetails", {}).get("settlementType") or None,
            "settlement_name": data.get("boundaryHierarchy", {}).get("settlement") or None,
            "user_name":     data.get("userName") or None,
            "member_count":  member_count,
            "vaccinated_count": 0,
        })

    if not rows:
        return _empty_frame()

    # ── Phase 2: vaccination counts from task index ──────────────────────────
    print("GPS: fetching task records for per-household vaccination counts...")

    task_query = {"bool": {"must": [
        {"term": {"Data.administrationStatus.keyword": "ADMINISTRATION_SUCCESS"}},
        {"exists": {"field": "Data.additionalDetails.lat"}},
    ]}}

    task_count = es.query(config["indices"]["tasks"],
                          {"size": 0, "track_total_hits": True, "query": task_query}
                          )["hits"]["total"]["value"]
    print(f"GPS: {task_count} ADMINISTRATION_SUCCESS task records to process")

    vacc_by_coords: dict[tuple, int] = {}
    for hit in es.scroll(config["indices"]["tasks"], {
        "query": task_query,
        "_source": ["Data.additionalDetails.lat", "Data.additionalDetails.lng"],
    }, expected_total=task_count):
        details = hit.get("_source", {}).get("Data", {}).get("additionalDetails", {})
        try:
            lat_r = round(float(details.get("lat") or "nan"), 5)
            lng_r = round(float(details.get("lng") or "nan"), 5)
        except (ValueError, TypeError):
            continue
        if math.isnan(lat_r) or math.isnan(lng_r):
            continue
        vacc_by_coords[(lat_r, lng_r)] = vacc_by_coords.get((lat_r, lng_r), 0) + 1

    print(f"GPS: {len(vacc_by_coords)} unique vaccinated locations found")

    matched = 0
    for row in rows:
        if row["lat"] is None or row["lng"] is None:
            continue
        key   = (round(float(row["lat"]), 5), round(float(row["lng"]), 5))
        count = vacc_by_coords.get(key, 0)
        row["vaccinated_count"] = count
        if count > 0:
            matched += 1

    print(f"GPS: {matched} households matched to at least one vaccinated child")

    # ── Phase 3: head-of-household names (2-hop join) ────────────────────────
    client_refs = set(r["_client_ref"] for r in rows if r.get("_client_ref"))
    head_map    = _fetch_head_names(client_refs)
    print(f"GPS: head-of-household names resolved for {len(head_map)}/{len(client_refs)} households")

    for row in rows:
        row["head_of_household"] = head_map.get(row.pop("_client_ref") or "", None)

    df = pd.DataFrame(rows)
    for col in COLUMNS:
        if col not in df.columns:
            df[col] = pd.NA
    df = df[list(COLUMNS.keys())]
    for col, dtype in COLUMNS.items():
        try:   df[col] = df[col].astype(dtype)
        except: pass
    return df


def _empty_frame() -> pd.DataFrame:
    df = pd.DataFrame(columns=list(COLUMNS.keys()))
    for col, dtype in COLUMNS.items():
        df[col] = df[col].astype(dtype)
    return df
