"""
Enumeration extractor — household registration + eligible children + vaccinated children.

THREE separate ES calls:

  1. households_registered
     Index: chad-household-index-v1
     Filter: Data.campaignNumber.keyword = config["campaign_id"]
     Agg: terms on healthFacility.keyword

  2. eligible_children
     Index: chad-project-beneficiary-index-v1
     Filter: Data.campaignNumber.keyword = config["campaign_id"]
             + ageInMonths <= 59  (range query)
             + isHeadOfHousehold = false  (term query)
     Agg: terms on healthFacility.keyword

  3. vaccinated_children
     Index: chad-project-task-index-v1
     Filter: Data.campaignNumber.keyword = config["campaign_id"]
             + administrationStatus.keyword = "ADMINISTRATION_SUCCESS"
     Agg: terms on healthFacility.keyword

Results are joined on facility_name. pct_complete = vaccinated_children / eligible_children * 100.
"""

import pandas as pd


SHEET_NAME = "enumeration"

COLUMNS = {
    "facility_name": pd.StringDtype(),
    "facility_id": pd.StringDtype(),
    "households_registered": pd.Int64Dtype(),
    "eligible_children": pd.Int64Dtype(),
    "vaccinated_children": pd.Int64Dtype(),
    "pct_complete": "float64",
}


def extract(es, config: dict) -> pd.DataFrame:
    """
    Extract household enumeration and vaccination status by facility.
    Requires three separate ES queries across two indices.

    Parameters
    ----------
    es : ESClient
        Initialised ESClient from base.py.
    config : dict
        Parsed chad.json campaign config.

    Returns
    -------
    pd.DataFrame
        Columns: facility_name, facility_id, households_registered,
                 eligible_children, vaccinated_children, pct_complete
    """
    campaign_id = config["campaign_id"]
    facility_prefix_map = config["facility_prefix_map"]

    # Query 1 — household count per facility
    hh_body = {
        "size": 0,
        "query": {"term": {"Data.campaignNumber.keyword": campaign_id}},
        "aggs": {
            "by_facility": {
                "terms": {
                    "field": "Data.boundaryHierarchy.healthFacility.keyword",
                    "size": 50
                }
            }
        }
    }
    hh_resp = es.query(config["indices"]["households"], hh_body)
    households = {
        b["key"]: b["doc_count"]
        for b in hh_resp["aggregations"]["by_facility"]["buckets"]
    }

    # Query 2 — eligible children per facility (beneficiary index)
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
            "by_facility": {
                "terms": {
                    "field": "Data.boundaryHierarchy.healthFacility.keyword",
                    "size": 50
                }
            }
        }
    }
    elig_resp = es.query(config["indices"]["beneficiaries"], elig_body)
    eligible = {
        b["key"]: b["doc_count"]
        for b in elig_resp["aggregations"]["by_facility"]["buckets"]
    }

    # Query 3 — vaccinated children per facility (task index)
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
            "by_facility": {
                "terms": {
                    "field": "Data.boundaryHierarchy.healthFacility.keyword",
                    "size": 50
                }
            }
        }
    }
    vax_resp = es.query(config["indices"]["tasks"], vax_body)
    vaccinated = {
        b["key"]: b["doc_count"]
        for b in vax_resp["aggregations"]["by_facility"]["buckets"]
    }

    # Query 4 — true total household count for the campaign (catches empty-string
    # facility="" records that terms agg silently skips).
    total_hh_body = {
        "size": 0,
        "track_total_hits": True,
        "query": {"term": {"Data.campaignNumber.keyword": campaign_id}},
    }
    total_hh_resp = es.query(config["indices"]["households"], total_hh_body)
    true_total_hh = total_hh_resp["hits"]["total"]["value"]

    # Merge by facility — union of all facility names seen across three queries
    all_facilities = set(households) | set(eligible) | set(vaccinated)

    if not all_facilities:
        return _empty_frame()

    rows = []
    for facility_name in sorted(all_facilities):
        hh_count = households.get(facility_name, 0)
        elig_count = eligible.get(facility_name, 0)
        vax_count = vaccinated.get(facility_name, 0)
        facility_id = facility_prefix_map.get(facility_name, "")

        pct_complete = round(vax_count / elig_count * 100, 2) if elig_count > 0 else 0.0

        rows.append({
            "facility_name": facility_name,
            "facility_id": facility_id,
            "households_registered": hh_count,
            "eligible_children": elig_count,
            "vaccinated_children": vax_count,
            "pct_complete": pct_complete,
        })

    # Check if terms agg missed any households (empty-string or unmapped facility).
    agg_total_hh = sum(households.values())
    unassigned_hh = true_total_hh - agg_total_hh
    if unassigned_hh > 0:
        print(
            f"WARNING [enumeration]: terms agg captured {agg_total_hh} households "
            f"but true total is {true_total_hh}. "
            f"Adding {unassigned_hh} unassigned household(s) as '(unassigned)' row."
        )
        rows.append({
            "facility_name": "(unassigned)",
            "facility_id": "",
            "households_registered": unassigned_hh,
            "eligible_children": 0,
            "vaccinated_children": 0,
            "pct_complete": 0.0,
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
