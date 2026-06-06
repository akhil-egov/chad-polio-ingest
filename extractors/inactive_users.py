"""
Inactive users extractor — users who have not synced in the last N hours.

Queries the task index for max(syncedTimeStamp) per user.
All users seen in the task index are the universe — if a user's last sync
exceeds the threshold, they appear in this report.

Threshold: config["inactive_threshold_hours"] (default 24h)

ES index: chad-project-task-index-v1
Filter: Data.campaignNumber.keyword = config["campaign_id"]
Agg: terms on userName.keyword (size 600)
     sub-agg: max on syncedTimeStamp
     sub-agg: terms on healthFacility.keyword (size 1)
     sub-agg: terms on nameOfUser.keyword (size 1)
"""

import pandas as pd
from datetime import datetime, timezone


SHEET_NAME = "inactive_users"

COLUMNS = {
    "user_id": pd.StringDtype(),
    "user_name": pd.StringDtype(),
    "facility_name": pd.StringDtype(),
    "facility_id": pd.StringDtype(),
    "last_sync": pd.StringDtype(),     # ISO datetime string, or None/pd.NA if never synced
    "hours_since_sync": "float64",     # None/NaN if never synced
}


def extract(es, config: dict) -> pd.DataFrame:
    """
    Extract users who have not synced within the configured threshold.

    Parameters
    ----------
    es : ESClient
        Initialised ESClient from base.py.
    config : dict
        Parsed chad.json campaign config.
        Threshold read from config["inactive_threshold_hours"].

    Returns
    -------
    pd.DataFrame
        Columns: user_id, user_name, facility_name, facility_id,
                 last_sync, hours_since_sync
        Only rows where hours_since_sync > inactive_threshold_hours OR last_sync is None.
    """
    body = {
        "size": 0,
        "query": {"term": {"Data.campaignNumber.keyword": config["campaign_id"]}},
        "aggs": {
            "by_user": {
                "terms": {"field": "Data.userName.keyword", "size": 600},
                "aggs": {
                    "facility": {
                        "terms": {
                            "field": "Data.boundaryHierarchy.healthFacility.keyword",
                            "size": 1
                        }
                    },
                    "full_name": {
                        "terms": {"field": "Data.nameOfUser.keyword", "size": 1}
                    },
                    "last_sync": {"max": {"field": "Data.syncedTimeStamp"}}
                }
            }
        }
    }

    resp = es.query(config["indices"]["tasks"], body)

    facility_prefix_map = config["facility_prefix_map"]
    threshold_hours = config["inactive_threshold_hours"]
    now = datetime.now(timezone.utc)

    rows = []
    for user_bucket in resp["aggregations"]["by_user"]["buckets"]:
        user_id = user_bucket["key"]

        fac_buckets = user_bucket["facility"]["buckets"]
        facility_name = fac_buckets[0]["key"] if fac_buckets else ""
        facility_id = facility_prefix_map.get(facility_name, "")

        name_buckets = user_bucket["full_name"]["buckets"]
        user_name = name_buckets[0]["key"] if name_buckets else ""

        last_sync_ms = user_bucket["last_sync"]["value"]
        if last_sync_ms is not None:
            last_sync_dt = datetime.fromtimestamp(last_sync_ms / 1000, tz=timezone.utc)
            last_sync_iso = last_sync_dt.isoformat()
            hours_since_sync = (now - last_sync_dt).total_seconds() / 3600
        else:
            last_sync_iso = None
            hours_since_sync = None

        # Keep only inactive users
        if hours_since_sync is None or hours_since_sync > threshold_hours:
            rows.append({
                "user_id": user_id,
                "user_name": user_name,
                "facility_name": facility_name,
                "facility_id": facility_id,
                "last_sync": last_sync_iso,
                "hours_since_sync": hours_since_sync,
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
