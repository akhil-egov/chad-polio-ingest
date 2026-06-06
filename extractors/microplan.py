"""
Microplan extractor — coverage vs microplan target by facility.

Reuses coverage.extract() internally — NO additional ES query needed.
Groups coverage output by facility and sums cumulative_vaccinated to get total achieved.
Joins with config["microplan_targets"] for microplan_target.

Derived fields:
  pct_complete = achieved / microplan_target * 100
  gap = microplan_target - achieved
"""

import pandas as pd
from extractors import coverage


SHEET_NAME = "microplan"

COLUMNS = {
    "facility_name": pd.StringDtype(),
    "facility_id": pd.StringDtype(),
    "microplan_target": pd.Int64Dtype(),
    "achieved": pd.Int64Dtype(),
    "pct_complete": "float64",
    "gap": pd.Int64Dtype(),
}


def extract(es, config: dict) -> pd.DataFrame:
    """
    Extract coverage vs microplan target by facility.

    Parameters
    ----------
    es : ESClient
        Initialised ESClient from base.py.
    config : dict
        Parsed chad.json campaign config. Targets from config["microplan_targets"].

    Returns
    -------
    pd.DataFrame
        Columns: facility_name, facility_id, microplan_target, achieved,
                 pct_complete, gap
    """
    facility_prefix_map = config["facility_prefix_map"]
    microplan_targets = config["microplan_targets"]

    # Get coverage data — reuse existing query rather than issuing a new one
    cov_df = coverage.extract(es, config)

    if cov_df.empty:
        # Fall back to targets-only frame with zero achieved
        rows = []
        for facility_name, target in microplan_targets.items():
            facility_id = facility_prefix_map.get(facility_name, "")
            rows.append({
                "facility_name": facility_name,
                "facility_id": facility_id,
                "microplan_target": target,
                "achieved": 0,
                "pct_complete": 0.0,
                "gap": target,
            })
        if not rows:
            return _empty_frame()
        df = pd.DataFrame(rows)
        for col, dtype in COLUMNS.items():
            df[col] = df[col].astype(dtype)
        return df[list(COLUMNS.keys())]

    # Sum total achieved per facility from the last (max cumulative) row per facility
    achieved_series = (
        cov_df.groupby("facility_name")["cumulative_vaccinated"].max()
    )

    # Build output from targets as the base (all facilities present even if no data yet)
    rows = []
    for facility_name, target in microplan_targets.items():
        facility_id = facility_prefix_map.get(facility_name, "")
        achieved = int(achieved_series.get(facility_name, 0) or 0)
        pct_complete = round(achieved / target * 100, 2) if target and target > 0 else 0.0
        gap = target - achieved

        rows.append({
            "facility_name": facility_name,
            "facility_id": facility_id,
            "microplan_target": target,
            "achieved": achieved,
            "pct_complete": pct_complete,
            "gap": gap,
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
