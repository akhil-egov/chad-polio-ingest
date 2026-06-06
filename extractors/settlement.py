"""
Settlement extractor — breakdown by settlement type (URBAN / RURAL / SLUMS).

THREE queries — all grouped by settlementType.keyword (campaign-wide, not per facility):

  1. household_count  — chad-household-index-v1
  2. eligible_children — chad-project-beneficiary-index-v1
     filter: ageInMonths <= 59 AND isHeadOfHousehold = false
  3. vaccinated — chad-project-task-index-v1
     filter: administrationStatus = ADMINISTRATION_SUCCESS

pct_complete = vaccinated / eligible_children * 100
"""

import pandas as pd


SHEET_NAME = "settlement"

COLUMNS = {
    "settlement_type": pd.StringDtype(),  # URBAN / RURAL / SLUMS
    "household_count": pd.Int64Dtype(),
    "eligible_children": pd.Int64Dtype(),
    "vaccinated": pd.Int64Dtype(),
    "pct_complete": "float64",
}


def extract(es, config: dict) -> pd.DataFrame:
    """
    Extract settlement-type breakdown of households, eligible children, and vaccinations.

    Parameters
    ----------
    es : ESClient
        Initialised ESClient from base.py.
    config : dict
        Parsed chad.json campaign config.

    Returns
    -------
    pd.DataFrame
        Columns: settlement_type, household_count, eligible_children,
                 vaccinated, pct_complete
    """
    campaign_id = config["campaign_id"]

    # Query 1 — household count by settlement type
    hh_body = {
        "size": 0,
        "query": {"term": {"Data.campaignNumber.keyword": campaign_id}},
        "aggs": {
            "by_settlement": {
                "terms": {
                    "field": "Data.additionalDetails.settlementType.keyword",
                    "size": 10
                }
            }
        }
    }
    hh_resp = es.query(config["indices"]["households"], hh_body)
    households = {
        b["key"]: b["doc_count"]
        for b in hh_resp["aggregations"]["by_settlement"]["buckets"]
    }

    # Query 2 — eligible children by settlement type
    elig_body = {
        "size": 0,
        "query": {
            "bool": {
                "must": [
                    {"term": {"Data.campaignNumber.keyword": campaign_id}},
                    {"term": {"Data.additionalDetails.isHeadOfHousehold": False}},
                    {"range": {"Data.additionalDetails.ageInMonths": {"lte": 59}}}
                ]
            }
        },
        "aggs": {
            "by_settlement": {
                "terms": {
                    "field": "Data.additionalDetails.settlementType.keyword",
                    "size": 10
                }
            }
        }
    }
    elig_resp = es.query(config["indices"]["beneficiaries"], elig_body)
    eligible = {
        b["key"]: b["doc_count"]
        for b in elig_resp["aggregations"]["by_settlement"]["buckets"]
    }

    # Query 3 — vaccinated by settlement type
    vax_body = {
        "size": 0,
        "query": {
            "bool": {
                "must": [
                    {"term": {"Data.campaignNumber.keyword": campaign_id}},
                    {"term": {"Data.administrationStatus.keyword": "ADMINISTRATION_SUCCESS"}}
                ]
            }
        },
        "aggs": {
            "by_settlement": {
                "terms": {
                    "field": "Data.additionalDetails.settlementType.keyword",
                    "size": 10
                }
            }
        }
    }
    vax_resp = es.query(config["indices"]["tasks"], vax_body)
    vaccinated = {
        b["key"]: b["doc_count"]
        for b in vax_resp["aggregations"]["by_settlement"]["buckets"]
    }

    all_types = set(households) | set(eligible) | set(vaccinated)

    if not all_types:
        return _empty_frame()

    rows = []
    for settlement_type in sorted(all_types):
        hh_count = households.get(settlement_type, 0)
        elig_count = eligible.get(settlement_type, 0)
        vax_count = vaccinated.get(settlement_type, 0)
        pct_complete = round(vax_count / elig_count * 100, 2) if elig_count > 0 else 0.0

        rows.append({
            "settlement_type": settlement_type,
            "household_count": hh_count,
            "eligible_children": elig_count,
            "vaccinated": vax_count,
            "pct_complete": pct_complete,
        })

    df = pd.DataFrame(rows)

    for col, dtype in COLUMNS.items():
        df[col] = df[col].astype(dtype)

    return df[list(COLUMNS.keys())]


def _empty_frame() -> pd.DataFrame:
    df = pd.DataFrame(columns=list(COLUMNS.keys()))
    for col, dtype in COLUMNS.items():
        df[col] = df[col].astype(dtype)
    return df
