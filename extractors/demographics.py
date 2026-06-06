"""
Demographics extractor — age and gender distribution of vaccinated children.

ES index: chad-project-task-index-v1
Filter: Data.campaignNumber.keyword = config["campaign_id"]
        + administrationStatus.keyword = "ADMINISTRATION_SUCCESS"

Data.additionalDetails.age is a text field containing string age values (e.g. "0", "12", "36").
We terms-aggregate over it and map string values to 5 age groups in Python.

Age groups (months):
  0-11m  : 0–11
  12-23m : 12–23
  24-35m : 24–35
  36-47m : 36–47
  48-59m : 48–59

Gender: Data.additionalDetails.gender.keyword (M / F)
"""

import pandas as pd
from collections import defaultdict


SHEET_NAME = "demographics"

COLUMNS = {
    "age_group": pd.StringDtype(),     # "0-11m", "12-23m", "24-35m", "36-47m", "48-59m"
    "gender": pd.StringDtype(),        # "M" or "F"
    "vaccinated_count": pd.Int64Dtype(),
}

AGE_GROUPS = [
    (0, 11, "0-11m"),
    (12, 23, "12-23m"),
    (24, 35, "24-35m"),
    (36, 47, "36-47m"),
    (48, 59, "48-59m"),
]


def _age_group(age_str: str):
    """Map a string age value (months) to an age group label. Returns None if unparseable."""
    try:
        age = int(age_str)
    except (ValueError, TypeError):
        return None
    for lo, hi, label in AGE_GROUPS:
        if lo <= age <= hi:
            return label
    return None


def extract(es, config: dict) -> pd.DataFrame:
    """
    Extract age and gender distribution of vaccinated children.

    Parameters
    ----------
    es : ESClient
        Initialised ESClient from base.py.
    config : dict
        Parsed chad.json campaign config.

    Returns
    -------
    pd.DataFrame
        Columns: age_group, gender, vaccinated_count
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
            "by_gender": {
                "terms": {"field": "Data.additionalDetails.gender.keyword", "size": 5},
                "aggs": {
                    "by_age": {
                        "terms": {"field": "Data.additionalDetails.age", "size": 100}
                    }
                }
            }
        }
    }

    resp = es.query(config["indices"]["tasks"], body)

    # Accumulate counts per (gender, age_group)
    counts: dict[tuple[str, str], int] = defaultdict(int)

    for gender_bucket in resp["aggregations"]["by_gender"]["buckets"]:
        gender = gender_bucket["key"]
        for age_bucket in gender_bucket["by_age"]["buckets"]:
            age_str = age_bucket["key"]
            group = _age_group(str(age_str))
            if group is None:
                continue
            counts[(gender, group)] += age_bucket["doc_count"]

    if not counts:
        return _empty_frame()

    rows = [
        {"age_group": group, "gender": gender, "vaccinated_count": count}
        for (gender, group), count in counts.items()
    ]

    df = pd.DataFrame(rows)

    for col, dtype in COLUMNS.items():
        df[col] = df[col].astype(dtype)

    return df[list(COLUMNS.keys())]


def _empty_frame() -> pd.DataFrame:
    df = pd.DataFrame(columns=list(COLUMNS.keys()))
    for col, dtype in COLUMNS.items():
        df[col] = df[col].astype(dtype)
    return df
