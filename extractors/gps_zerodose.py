"""
GPS Zero-dose extractor — lat/lng for children who had never received OPV before.

ES index: chad-project-task-index-v1
Filter: Data.campaignNumber.keyword = campaign_id
        + Data.additionalDetails.receivedOPVBefore.keyword = "NO"

GPS coordinates are stored as strings in additionalDetails (lat/lng).
Bounds filtering is applied in Python after extraction.

"Zero dose" = child registered in this campaign who had no prior OPV history.
This includes both successfully vaccinated zero-dose children and those who
were not vaccinated (check administration_status to distinguish).
"""

import pandas as pd


SHEET_NAME = "gps_zerodose"

COLUMNS = {
    "record_id": pd.StringDtype(),
    "lat": "float64",
    "lng": "float64",
    "facility_name": pd.StringDtype(),
    "facility_id": pd.StringDtype(),
    "settlement_name": pd.StringDtype(),  # neighbourhood/quartier
    "settlement_type": pd.StringDtype(),
    "user_name": pd.StringDtype(),
    "age_months": pd.Int64Dtype(),        # age in months
    "gender": pd.StringDtype(),           # MALE / FEMALE
    "administration_status": pd.StringDtype(),  # ADMINISTRATION_SUCCESS or other
}


def extract(es, config: dict) -> pd.DataFrame:
    """
    Extract zero-dose child task records with GPS for map rendering.

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

    # GPS is stored as strings in additionalDetails — can't use range query.
    # Fetch all zero-dose records and apply bounds in Python.
    query = {
        "bool": {
            "must": [
                {"term": {"Data.campaignNumber.keyword": config["campaign_id"]}},
                {"term": {"Data.additionalDetails.receivedOPVBefore.keyword": "NO"}},
            ]
        }
    }

    count_resp = es.query(
        config["indices"]["tasks"],
        {"size": 0, "track_total_hits": True, "query": query},
    )
    expected_total = count_resp["hits"]["total"]["value"]
    print(f"GPS Zero-dose: expecting {expected_total} task records with receivedOPVBefore=NO")

    body = {
        "query": query,
        "_source": [
            "Data.boundaryHierarchy.healthFacility",
            "Data.boundaryHierarchy.settlement",
            "Data.additionalDetails.lat",
            "Data.additionalDetails.lng",
            "Data.additionalDetails.settlementType",
            "Data.additionalDetails.age",
            "Data.additionalDetails.gender",
            "Data.administrationStatus",
            "Data.userName",
        ],
    }

    rows = []
    skipped_no_gps = 0

    for hit in es.scroll(config["indices"]["tasks"], body, expected_total=expected_total):
        src = hit.get("_source", {})
        data = src.get("Data", {})
        details = data.get("additionalDetails", {})

        # Parse string GPS coords
        try:
            lat = float(details.get("lat") or details.get("latitude") or "nan")
            lng = float(details.get("lng") or details.get("longitude") or "nan")
        except (ValueError, TypeError):
            skipped_no_gps += 1
            continue

        # Apply GPS bounds in Python
        if not (bounds["lat_min"] <= lat <= bounds["lat_max"]
                and bounds["lon_min"] <= lng <= bounds["lon_max"]):
            skipped_no_gps += 1
            continue

        facility_name = data.get("boundaryHierarchy", {}).get("healthFacility", "") or ""
        facility_id = facility_prefix_map.get(facility_name, "")
        settlement_name = data.get("boundaryHierarchy", {}).get("settlement") or None
        settlement_type = details.get("settlementType") or None
        user_name = data.get("userName") or None
        administration_status = data.get("administrationStatus") or None

        try:
            age_months = int(details.get("age")) if details.get("age") is not None else None
        except (ValueError, TypeError):
            age_months = None

        gender = details.get("gender") or None

        rows.append({
            "record_id": hit["_id"],
            "lat": lat,
            "lng": lng,
            "facility_name": facility_name,
            "facility_id": facility_id,
            "settlement_name": settlement_name,
            "settlement_type": settlement_type,
            "user_name": user_name,
            "age_months": age_months,
            "gender": gender,
            "administration_status": administration_status,
        })

    if skipped_no_gps:
        print(f"  -> skipped {skipped_no_gps} records outside GPS bounds or missing coords")

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
