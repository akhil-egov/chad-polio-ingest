"""
Refusals extractor — refusal reason codes by facility.

ES index: chad-household-index-v1
Filter: Data.campaignNumber.keyword = config["campaign_id"]
        + reasonForRefusal exists
Group by: facility name, reason_code
reason_label: raw value (no translation table available)
"""

import pandas as pd


SHEET_NAME = "refusals"

COLUMNS = {
    "facility_name": pd.StringDtype(),
    "facility_id": pd.StringDtype(),
    "reason_code": pd.StringDtype(),   # Raw code from ES (e.g. "CHILD_ABSENT", "REFUSED")
    "reason_label": pd.StringDtype(),  # Human-readable label (same as reason_code for now)
    "count": pd.Int64Dtype(),
}


def extract(es, config: dict) -> pd.DataFrame:
    """
    Extract refusal reason counts by facility.

    Parameters
    ----------
    es : ESClient
        Initialised ESClient from base.py.
    config : dict
        Parsed chad.json campaign config.

    Returns
    -------
    pd.DataFrame
        Columns: facility_name, facility_id, reason_code, reason_label, count
    """
    body = {
        "size": 0,
        "query": {
            "bool": {
                "must": [
                    {"term": {"Data.campaignNumber.keyword": config["campaign_id"]}},
                    {"exists": {"field": "Data.additionalDetails.reasonForRefusal"}}
                ]
            }
        },
        "aggs": {
            "by_facility": {
                "terms": {
                    "field": "Data.boundaryHierarchy.healthFacility.keyword",
                    "size": 50
                },
                "aggs": {
                    "by_reason": {
                        "terms": {
                            "field": "Data.additionalDetails.reasonForRefusal.keyword",
                            "size": 20
                        }
                    }
                }
            }
        }
    }

    resp = es.query(config["indices"]["households"], body)

    facility_prefix_map = config["facility_prefix_map"]

    rows = []
    for fac_bucket in resp["aggregations"]["by_facility"]["buckets"]:
        facility_name = fac_bucket["key"]
        facility_id = facility_prefix_map.get(facility_name, "")

        for reason_bucket in fac_bucket["by_reason"]["buckets"]:
            reason_code = reason_bucket["key"]
            rows.append({
                "facility_name": facility_name,
                "facility_id": facility_id,
                "reason_code": reason_code,
                "reason_label": reason_code,  # No translation table — use raw value
                "count": reason_bucket["doc_count"],
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
