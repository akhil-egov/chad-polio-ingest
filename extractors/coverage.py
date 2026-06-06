"""
Coverage extractor — daily vaccinations by facility and day.

ES index: chad-project-task-index-v1
Filter: Data.campaignNumber.keyword = config["campaign_id"]
Group by: facility name, date
Count: administrationStatus = ADMINISTRATION_SUCCESS
Target: from config["microplan_targets"]
Cumulative: running sum ordered by date per facility
"""

import pandas as pd


SHEET_NAME = "coverage"

COLUMNS = {
    "facility_name": pd.StringDtype(),
    "facility_id": pd.StringDtype(),
    "date": pd.StringDtype(),          # YYYY-MM-DD string
    "vaccinated": pd.Int64Dtype(),
    "target": pd.Int64Dtype(),
    "cumulative_vaccinated": pd.Int64Dtype(),
    "pct_complete": "float64",
}


def extract(es, config: dict) -> pd.DataFrame:
    """
    Extract daily vaccination coverage by facility.

    Parameters
    ----------
    es : ESClient
        Initialised ESClient from base.py.
    config : dict
        Parsed chad.json campaign config.

    Returns
    -------
    pd.DataFrame
        Columns: facility_name, facility_id, date, vaccinated, target,
                 cumulative_vaccinated, pct_complete
    """
    body = {
        "size": 0,
        "query": {
            "bool": {
                "must": [
                    {"term": {"Data.campaignNumber.keyword": config["campaign_id"]}},
                    {"term": {"Data.administrationStatus.keyword": "ADMINISTRATION_SUCCESS"}}
                ]
            }
        },
        "aggs": {
            "by_facility": {
                "terms": {"field": "Data.boundaryHierarchy.healthFacility.keyword", "size": 50},
                "aggs": {
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
    microplan_targets = config["microplan_targets"]

    rows = []
    for fac_bucket in resp["aggregations"]["by_facility"]["buckets"]:
        facility_name = fac_bucket["key"]
        facility_id = facility_prefix_map.get(facility_name, "")
        target = microplan_targets.get(facility_name, 0)

        for date_bucket in fac_bucket["by_date"]["buckets"]:
            date_str = date_bucket["key_as_string"]
            vaccinated = date_bucket["doc_count"]
            rows.append({
                "facility_name": facility_name,
                "facility_id": facility_id,
                "date": date_str,
                "vaccinated": vaccinated,
                "target": target,
            })

    # Second query — vaccinated records where taskDates does NOT exist (null dates).
    # These records have a valid facility but no date, so the date_histogram above
    # silently omits them.  We add them as "undated" rows so the total vaccinated
    # count across all rows is accurate, even though they cannot be plotted on a
    # timeline.
    undated_body = {
        "size": 0,
        "query": {
            "bool": {
                "must": [
                    {"term": {"Data.campaignNumber.keyword": config["campaign_id"]}},
                    {"term": {"Data.administrationStatus.keyword": "ADMINISTRATION_SUCCESS"}},
                    {"exists": {"field": "Data.boundaryHierarchy.healthFacility"}}
                ],
                "must_not": [
                    {"exists": {"field": "Data.taskDates"}}
                ]
            }
        },
        "aggs": {
            "by_facility": {
                "terms": {
                    "field": "Data.boundaryHierarchy.healthFacility.keyword",
                    "size": 50
                }
            }
        }
    }
    undated_resp = es.query(config["indices"]["tasks"], undated_body)
    for fac_bucket in undated_resp["aggregations"]["by_facility"]["buckets"]:
        facility_name = fac_bucket["key"]
        facility_id = facility_prefix_map.get(facility_name, "")
        target = microplan_targets.get(facility_name, 0)
        vaccinated = fac_bucket["doc_count"]
        rows.append({
            "facility_name": facility_name,
            "facility_id": facility_id,
            "date": "undated",
            "vaccinated": vaccinated,
            "target": target,
        })

    if not rows:
        return _empty_frame()

    df = pd.DataFrame(rows)
    df = df.sort_values(["facility_name", "date"]).reset_index(drop=True)

    # Cumulative vaccinated per facility — undated rows get 0, dated rows get running sum.
    # Vectorised to avoid pandas 2.x groupby.apply() column-drop issue.
    dated_mask = df["date"] != "undated"
    df["cumulative_vaccinated"] = 0
    df.loc[dated_mask, "cumulative_vaccinated"] = (
        df[dated_mask].groupby("facility_name")["vaccinated"].cumsum()
    )

    # pct_complete = cumulative / target * 100 (guard against zero target).
    # Undated rows use pct_complete=0 since they have cumulative_vaccinated=0.
    df["pct_complete"] = df.apply(
        lambda r: round(r["cumulative_vaccinated"] / r["target"] * 100, 2)
        if r["target"] and r["target"] > 0 and r["date"] != "undated" else 0.0,
        axis=1,
    )

    # Cast to declared dtypes
    for col, dtype in COLUMNS.items():
        df[col] = df[col].astype(dtype)

    return df[list(COLUMNS.keys())]


def _empty_frame() -> pd.DataFrame:
    df = pd.DataFrame(columns=list(COLUMNS.keys()))
    for col, dtype in COLUMNS.items():
        df[col] = df[col].astype(dtype)
    return df
