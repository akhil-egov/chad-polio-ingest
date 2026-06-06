"""
GPS Refusals extractor — lat/lng for households that refused vaccination.

ES index: chad-household-index-v1
Filter: Data.campaignNumber.keyword = campaign_id
        + Data.additionalDetails.reasonForRefusal exists
        + GPS bounds (same as gps.py)

These are household records — same index as gps.py — but filtered to
those where the team recorded a refusal reason. Each dot on the map
represents one household that refused.
"""

import pandas as pd


SHEET_NAME = "gps_refusals"

COLUMNS = {
    "record_id": pd.StringDtype(),
    "lat": "float64",
    "lng": "float64",
    "facility_name": pd.StringDtype(),
    "facility_id": pd.StringDtype(),
    "settlement_name": pd.StringDtype(),  # neighbourhood/quartier
    "settlement_type": pd.StringDtype(),
    "user_name": pd.StringDtype(),
    "member_count": pd.Int64Dtype(),
    "reason_for_refusal": pd.StringDtype(),   # e.g. NOT_DECISION_MAKER, RELIGIOUS_BELIEFS
    "reason_not_vaccinated": pd.StringDtype(), # broader category e.g. REFUSAL
}


def extract(es, config: dict) -> pd.DataFrame:
    """
    Extract GPS-valid household refusal records for map rendering.

    Parameters
    ----------
    es : ESClient
        Initialised ESClient from base.py.
    config : dict
        Parsed chad.json campaign config.

    Returns
    -------
    pd.DataFrame
        Columns defined in COLUMNS above.
    """
    bounds = config["gps_bounds"]
    facility_prefix_map = config["facility_prefix_map"]

    query = {
        "bool": {
            "must": [
                {"term": {"Data.campaignNumber.keyword": config["campaign_id"]}},
                {"exists": {"field": "Data.additionalDetails.reasonForRefusal"}},
                {"range": {"Data.household.address.latitude": {
                    "gte": bounds["lat_min"], "lte": bounds["lat_max"]
                }}},
                {"range": {"Data.household.address.longitude": {
                    "gte": bounds["lon_min"], "lte": bounds["lon_max"]
                }}},
            ]
        }
    }

    count_resp = es.query(
        config["indices"]["households"],
        {"size": 0, "track_total_hits": True, "query": query},
    )
    expected_total = count_resp["hits"]["total"]["value"]
    print(f"GPS Refusals: expecting {expected_total} records")

    body = {
        "query": query,
        "_source": [
            "Data.household.id",
            "Data.household.address.latitude",
            "Data.household.address.longitude",
            "Data.household.memberCount",
            "Data.boundaryHierarchy.healthFacility",
            "Data.boundaryHierarchy.settlement",
            "Data.additionalDetails.settlementType",
            "Data.additionalDetails.reasonForRefusal",
            "Data.additionalDetails.reasonNotVaccinated",
            "Data.userName",
        ],
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
        settlement_name = data.get("boundaryHierarchy", {}).get("settlement") or None
        settlement_type = data.get("additionalDetails", {}).get("settlementType") or None
        user_name = data.get("userName") or None
        reason_for_refusal = data.get("additionalDetails", {}).get("reasonForRefusal") or None
        reason_not_vaccinated = data.get("additionalDetails", {}).get("reasonNotVaccinated") or None

        mc = hh.get("memberCount")
        try:
            member_count = int(mc) if mc is not None else None
        except (ValueError, TypeError):
            member_count = None

        rows.append({
            "record_id": record_id,
            "lat": lat,
            "lng": lng,
            "facility_name": facility_name,
            "facility_id": facility_id,
            "settlement_name": settlement_name,
            "settlement_type": settlement_type,
            "user_name": user_name,
            "member_count": member_count,
            "reason_for_refusal": reason_for_refusal,
            "reason_not_vaccinated": reason_not_vaccinated,
        })

    if len(rows) != expected_total:
        print(
            f"WARNING [gps_refusals]: collected {len(rows)} rows but expected "
            f"{expected_total} (missing {expected_total - len(rows)})"
        )

    if not rows:
        return _empty_frame()

    df = pd.DataFrame(rows)
    for col, dtype in COLUMNS.items():
        df[col] = df[col].astype(dtype)
    return df[list(COLUMNS.keys())]


def _empty_frame() -> pd.DataFrame:
    df = pd.DataFrame(columns=list(COLUMNS.keys()))
    for col, dtype in COLUMNS.items():
        df[col] = df[col].astype(dtype)
    return df
