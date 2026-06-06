"""
Activity extractor — per-user task count by date and last sync time.

ES index: chad-project-task-index-v1
Filter: Data.campaignNumber.keyword = config["campaign_id"]
Group by: user_id, user_name, facility, date
Metrics: task_count (count of docs), last_sync (max of syncedTimeStamp)
is_inactive: True if last_sync is more than config["inactive_threshold_hours"] ago
"""

import pandas as pd
from datetime import datetime, timezone


SHEET_NAME = "activity"

COLUMNS = {
    "facility_name": pd.StringDtype(),
    "facility_id": pd.StringDtype(),
    "user_id": pd.StringDtype(),
    "user_name": pd.StringDtype(),
    "date": pd.StringDtype(),          # YYYY-MM-DD string
    "task_count": pd.Int64Dtype(),
    "last_sync": pd.StringDtype(),     # ISO datetime string
    "is_inactive": "boolean",
}


def extract(es, config: dict) -> pd.DataFrame:
    """
    Extract per-user daily activity and sync status.

    Parameters
    ----------
    es : ESClient
        Initialised ESClient from base.py.
    config : dict
        Parsed chad.json campaign config.

    Returns
    -------
    pd.DataFrame
        Columns: facility_name, facility_id, user_id, user_name, date,
                 task_count, last_sync, is_inactive
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
                    "last_sync": {"max": {"field": "Data.syncedTimeStamp"}},
                    "by_date": {
                        "date_histogram": {
                            "field": "Data.taskDates",
                            "calendar_interval": "day",
                            "format": "yyyy-MM-dd"
                        }
                    }
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

        # Extract facility name (top bucket or empty string)
        fac_buckets = user_bucket["facility"]["buckets"]
        facility_name = fac_buckets[0]["key"] if fac_buckets else ""
        facility_id = facility_prefix_map.get(facility_name, "")

        # Extract full name (top bucket or empty string)
        name_buckets = user_bucket["full_name"]["buckets"]
        user_name = name_buckets[0]["key"] if name_buckets else ""

        # last_sync — epoch ms from max agg
        last_sync_ms = user_bucket["last_sync"]["value"]
        if last_sync_ms is not None:
            last_sync_dt = datetime.fromtimestamp(last_sync_ms / 1000, tz=timezone.utc)
            last_sync_iso = last_sync_dt.isoformat()
            hours_since = (now - last_sync_dt).total_seconds() / 3600
            is_inactive = hours_since > threshold_hours
        else:
            last_sync_iso = None
            is_inactive = True

        # One row per date
        for date_bucket in user_bucket["by_date"]["buckets"]:
            if date_bucket["doc_count"] == 0:
                continue
            rows.append({
                "facility_name": facility_name,
                "facility_id": facility_id,
                "user_id": user_id,
                "user_name": user_name,
                "date": date_bucket["key_as_string"],
                "task_count": date_bucket["doc_count"],
                "last_sync": last_sync_iso,
                "is_inactive": is_inactive,
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
