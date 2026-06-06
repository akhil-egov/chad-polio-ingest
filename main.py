"""
main.py — entry point for the chad-polio-ingest extraction pipeline.

Usage as a function:
    from main import run
    path = run(country="chad", reports="all")

Usage as CLI:
    python main.py --country chad --reports all
    python main.py --country chad --reports coverage,activity
"""

import argparse
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv

from extractors.base import ESClient
from extractors import (
    coverage,
    activity,
    refusals,
    enumeration,
    stock,
    gps,
    gps_refusals,
    gps_zerodose,
    microplan,
    settlement,
    demographics,
    inactive_users,
)

# Map of report name -> extractor module. Order determines sheet order in Excel.
EXTRACTORS = {
    "coverage": coverage,
    "activity": activity,
    "refusals": refusals,
    "enumeration": enumeration,
    "stock": stock,
    "gps": gps,
    "gps_refusals": gps_refusals,
    "gps_zerodose": gps_zerodose,
    "microplan": microplan,
    "settlement": settlement,
    "demographics": demographics,
    "inactive_users": inactive_users,
}


def _load_config(country: str) -> dict:
    """Load and parse config/{country}.json."""
    config_path = Path(__file__).parent / "config" / f"{country}.json"
    if not config_path.exists():
        raise FileNotFoundError(f"Config not found: {config_path}")
    with open(config_path, encoding="utf-8") as fh:
        return json.load(fh)


def _resolve_reports(reports: str) -> list[str]:
    """
    Resolve the reports argument to a list of extractor keys.

    "all" returns every key in EXTRACTORS (in definition order).
    A comma-separated string like "coverage,activity" returns those keys.
    Unknown names raise ValueError.
    """
    if reports.strip().lower() == "all":
        return list(EXTRACTORS.keys())

    requested = [r.strip() for r in reports.split(",") if r.strip()]
    unknown = [r for r in requested if r not in EXTRACTORS]
    if unknown:
        raise ValueError(
            f"Unknown report(s): {unknown}. Valid names: {list(EXTRACTORS.keys())}"
        )
    return requested


def _output_path(country: str, output_dir: str) -> Path:
    """Build a timestamped output path. Never overwrites existing files."""
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M")
    return out_dir / f"{country}_{timestamp}.xlsx"


def _build_metadata_row(
    run_timestamp: str,
    campaign_id: str,
    country: str,
    records_per_sheet: dict,
    extraction_duration_s: float,
) -> pd.DataFrame:
    """Return a single-row DataFrame for the _metadata sheet."""
    return pd.DataFrame(
        [
            {
                "run_timestamp": run_timestamp,
                "campaign_id": campaign_id,
                "country": country,
                "records_per_sheet": json.dumps(records_per_sheet),
                "extraction_duration_s": round(extraction_duration_s, 3),
            }
        ]
    )


def run(country: str = "chad", reports: str = "all") -> str:
    """
    Run the extraction pipeline.

    Parameters
    ----------
    country : str
        Country key — must match a file in config/{country}.json.
    reports : str
        "all" to run every extractor, or a comma-separated list of report names
        (e.g. "coverage,activity").

    Returns
    -------
    str
        Absolute path to the output Excel file.
    """
    load_dotenv()

    # ------------------------------------------------------------------ setup
    config = _load_config(country)
    report_keys = _resolve_reports(reports)
    output_dir = os.environ.get("OUTPUT_DIR", "output")
    out_path = _output_path(country, output_dir)

    run_timestamp = datetime.now(timezone.utc).isoformat()
    start_time = time.monotonic()

    es = ESClient()

    # ----------------------------------------------------------- run extractors
    sheet_data: dict[str, pd.DataFrame] = {}
    records_per_sheet: dict[str, int] = {}

    for name in report_keys:
        extractor = EXTRACTORS[name]
        print(f"[{datetime.now().strftime('%H:%M:%S')}] Extracting: {name} ...")
        try:
            df = extractor.extract(es, config)
        except Exception as exc:
            # Log and continue so one broken extractor doesn't abort the run.
            # The sheet will be absent from the Excel file, which the dashboard
            # must handle gracefully (it checks sheet presence before loading).
            print(f"  ERROR in {name}: {exc}")
            continue

        sheet_data[name] = df
        records_per_sheet[name] = len(df)
        print(f"  -> {len(df)} rows")

    extraction_duration_s = time.monotonic() - start_time

    # ---------------------------------------------------------------- write Excel
    metadata_df = _build_metadata_row(
        run_timestamp=run_timestamp,
        campaign_id=config["campaign_id"],
        country=country,
        records_per_sheet=records_per_sheet,
        extraction_duration_s=extraction_duration_s,
    )

    print(f"\nWriting {out_path} ...")
    with pd.ExcelWriter(out_path, engine="openpyxl") as writer:
        # Data sheets first (in EXTRACTORS definition order)
        for name in report_keys:
            if name in sheet_data:
                sheet_data[name].to_excel(writer, sheet_name=name, index=False)

        # Metadata sheet last
        metadata_df.to_excel(writer, sheet_name="_metadata", index=False)

    elapsed = time.monotonic() - start_time
    print(f"Done in {elapsed:.1f}s — {out_path}")
    return str(out_path.resolve())


# ------------------------------------------------------------------ CLI entry point

def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Extract WHO AFRO polio campaign data from Elasticsearch to Excel."
    )
    parser.add_argument(
        "--country",
        default="chad",
        help="Country key (must match config/<country>.json). Default: chad",
    )
    parser.add_argument(
        "--reports",
        default="all",
        help=(
            'Comma-separated list of reports to run, or "all". '
            f"Available: {', '.join(EXTRACTORS.keys())}. Default: all"
        ),
    )
    return parser


if __name__ == "__main__":
    parser = _build_arg_parser()
    args = parser.parse_args()
    output_file = run(country=args.country, reports=args.reports)
    print(f"\nOutput: {output_file}")
