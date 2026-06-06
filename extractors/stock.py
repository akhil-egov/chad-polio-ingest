"""
Stock extractor — vial reconciliation by facility. Supply-side only.

ES index: chad-user-action-location-capture-index-v1
Filter: Data.campaignNumber.keyword = config["campaign_id"]

vials_issued: sum of Data.additionalDetails.totalVialsReceivedForDay
vials_returned: sum of Data.additionalDetails.totalReturned
vials_used: computed as issued - returned (no dose estimates, per CONTRACT.md decision #2)

NOTE: No doses_per_vial, no doses_administered. Dose reconciliation is a future view.
"""

import pandas as pd


SHEET_NAME = "stock"

COLUMNS = {
    "facility_name": pd.StringDtype(),
    "facility_id": pd.StringDtype(),
    "vials_issued": pd.Int64Dtype(),
    "vials_returned": pd.Int64Dtype(),
    "vials_used": pd.Int64Dtype(),     # issued - returned
}


def extract(es, config: dict) -> pd.DataFrame:
    """
    Extract vial stock reconciliation by facility.

    Parameters
    ----------
    es : ESClient
        Initialised ESClient from base.py.
    config : dict
        Parsed chad.json campaign config.

    Returns
    -------
    pd.DataFrame
        Columns: facility_name, facility_id, vials_issued, vials_returned, vials_used
    """
    body = {
        "size": 0,
        "query": {"term": {"Data.campaignNumber.keyword": config["campaign_id"]}},
        "aggs": {
            "by_facility": {
                "terms": {
                    "field": "Data.boundaryHierarchy.healthFacility.keyword",
                    "size": 50
                },
                "aggs": {
                    "vials_issued": {
                        "sum": {"field": "Data.additionalDetails.totalVialsReceivedForDay"}
                    },
                    "vials_returned": {
                        "sum": {"field": "Data.additionalDetails.totalReturned"}
                    }
                }
            }
        }
    }

    resp = es.query(config["indices"]["actions"], body)

    facility_prefix_map = config["facility_prefix_map"]

    rows = []
    for fac_bucket in resp["aggregations"]["by_facility"]["buckets"]:
        facility_name = fac_bucket["key"]
        facility_id = facility_prefix_map.get(facility_name, "")
        vials_issued = int(fac_bucket["vials_issued"]["value"] or 0)
        vials_returned = int(fac_bucket["vials_returned"]["value"] or 0)
        vials_used = vials_issued - vials_returned

        rows.append({
            "facility_name": facility_name,
            "facility_id": facility_id,
            "vials_issued": vials_issued,
            "vials_returned": vials_returned,
            "vials_used": vials_used,
        })

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
