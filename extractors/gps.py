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
"""

import math
import pandas as pd


SHEET_NAME = "gps"

COLUMNS = {
    "record_id": pd.StringDtype(),
    "record_type": pd.StringDtype(),
    "lat": "float64",
    "lng": "float64",
    "facility_name": pd.StringDtype(),
    "facility_id": pd.StringDtype(),
    "vaccinated": "boolean",
    "settlement_type": pd.StringDtype(),
    "settlement_name": pd.StringDtype(),
    "user_name": pd.StringDtype(),
    "member_count": pd.Int64Dtype(),
    "vaccinated_count": pd.Int64Dtype(),  # children vaccinated at this household
}


def extract(es, config: dict) -> pd.DataFrame:
    bounds = config["gps_bounds"]
    facility_prefix_map = config["facility_prefix_map"]

    # ── Phase 1: household GPS records ──────────────────────────────────────
    gps_query = {
        "bool": {
            "must": [
                {"term": {"Data.campaignNumber.keyword": config["campaign_id"]}},
                {"range": {"Data.household.address.latitude": {
                    "gte": bounds["lat_min"], "lte": bounds["lat_max"]
                }}},
                {"range": {"Data.household.address.longitude": {
                    "gte": bounds["lon_min"], "lte": bounds["lon_max"]
                }}}
            ]
        }
    }

    count_resp = es.query(
        config["indices"]["households"],
        {"size": 0, "track_total_hits": True, "query": gps_query},
    )
    expected_total = count_resp["hits"]["total"]["value"]
    print(f"GPS: expecting {expected_total} GPS-valid household records")

    body = {
        "query": gps_query,
        "_source": [
            "Data.household.id",
            "Data.household.address.latitude",
            "Data.household.address.longitude",
            "Data.boundaryHierarchy.healthFacility",
            "Data.boundaryHierarchy.settlement",
            "Data.additionalDetails.settlementType",
            "Data.userName",
            "Data.additionalDetails.memberCount",
        ]
    }

    rows = []
    for hit in es.scroll(config["indices"]["households"], body, expected_total=expected_total):
        src = hit.get("_source", {})
        data = src.get("Data", {})
        hh = data.get("household", {})
        addr = hh.get("address", {})
        lat = addr.get("latitude")
        lng = addr.get("longitude")
        record_id = hh.get("id") or hit["_id"]
        facility_name = data.get("boundaryHierarchy", {}).get("healthFacility", "") or ""
        facility_id = facility_prefix_map.get(facility_name, "")
        settlement_type = data.get("additionalDetails", {}).get("settlementType") or None
        settlement_name = data.get("boundaryHierarchy", {}).get("settlement") or None
        user_name = data.get("userName") or None
        mc = data.get("additionalDetails", {}).get("memberCount")
        try:
            member_count = int(mc) if mc is not None else None
        except (ValueError, TypeError):
            member_count = None

        rows.append({
            "record_id": record_id,
            "record_type": "household",
            "lat": lat,
            "lng": lng,
            "facility_name": facility_name,
            "facility_id": facility_id,
            "vaccinated": False,
            "settlement_type": settlement_type,
            "settlement_name": settlement_name,
            "user_name": user_name,
            "member_count": member_count,
            "vaccinated_count": 0,
        })

    if len(rows) != expected_total:
        print(
            f"WARNING [gps]: collected {len(rows)} rows but expected "
            f"{expected_total} (missing {expected_total - len(rows)})"
        )

    if not rows:
        return _empty_frame()

    # ── Phase 2: vaccination counts from task index, joined by GPS coords ───
    # householdId is null on task records; coordinate matching (5dp ≈ 1m) is
    # the only available join key. Same team, same device, same session → exact match.
    print("GPS: fetching task records for per-household vaccination counts...")

    task_query = {
        "bool": {
            "must": [
                {"term": {"Data.campaignNumber.keyword": config["campaign_id"]}},
                {"term": {"Data.administrationStatus.keyword": "ADMINISTRATION_SUCCESS"}},
            ],
            "filter": [
                {"exists": {"field": "Data.additionalDetails.lat"}},
            ]
        }
    }

    task_count = es.query(
        config["indices"]["tasks"],
        {"size": 0, "track_total_hits": True, "query": task_query},
    )["hits"]["total"]["value"]
    print(f"GPS: {task_count} ADMINISTRATION_SUCCESS task records to process")

    task_body = {
        "query": task_query,
        "_source": [
            "Data.additionalDetails.lat",
            "Data.additionalDetails.lng",
            "Data.additionalDetails.longitude",
        ]
    }

    # Build lookup: rounded (lat, lng) -> vaccinated child count
    vacc_by_coords: dict[tuple, int] = {}
    for hit in es.scroll(config["indices"]["tasks"], task_body, expected_total=task_count):
        details = hit.get("_source", {}).get("Data", {}).get("additionalDetails", {})
        try:
            lat_r = round(float(details.get("lat") or details.get("latitude") or "nan"), 5)
            lng_r = round(float(details.get("lng") or details.get("longitude") or "nan"), 5)
        except (ValueError, TypeError):
            continue
        if math.isnan(lat_r) or math.isnan(lng_r):
            continue
        key = (lat_r, lng_r)
        vacc_by_coords[key] = vacc_by_coords.get(key, 0) + 1

    print(f"GPS: {len(vacc_by_coords)} unique vaccinated locations found")

    # Join vaccination counts onto household rows
    matched = 0
    for row in rows:
        if row["lat"] is None or row["lng"] is None:
            continue
        key = (round(float(row["lat"]), 5), round(float(row["lng"]), 5))
        count = vacc_by_coords.get(key, 0)
        row["vaccinated_count"] = count
        if count > 0:
            matched += 1

    print(f"GPS: {matched} households matched to at least one vaccinated child")

    df = pd.DataFrame(rows)
    for col, dtype in COLUMNS.items():
        df[col] = df[col].astype(dtype)
    return df[list(COLUMNS.keys())]


def _empty_frame() -> pd.DataFrame:
    df = pd.DataFrame(columns=list(COLUMNS.keys()))
    for col, dtype in COLUMNS.items():
        df[col] = df[col].astype(dtype)
    return df
