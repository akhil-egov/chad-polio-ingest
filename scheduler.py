#!/usr/bin/env python3
"""
scheduler.py — runs main.run() every hour on the Jupyter server.

Start once from a Jupyter cell:
    import subprocess, Path
    log = open(Path.home() / "pipeline.log", "a")
    proc = subprocess.Popen(["python", "scheduler.py"], stdout=log, stderr=log)
    print(f"Scheduler PID: {proc.pid}")

The process keeps running in the background as long as the server is up.
Kill with: import os; os.kill(<pid>, 15)
"""

import os
import sys
import time
import logging
from datetime import datetime, timezone
from pathlib import Path
from dotenv import load_dotenv

dst = Path(__file__).parent
load_dotenv(dst / ".env")

os.chdir(str(dst))
sys.path.insert(0, str(dst))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)


def seconds_until_next_hour() -> float:
    now = datetime.now()
    secs_past = now.minute * 60 + now.second + now.microsecond / 1e6
    return 3600 - secs_past


def run_once():
    log.info("Pipeline starting...")
    try:
        from main import run
        import importlib, main as m
        importlib.reload(m)          # reload so edits to extractors take effect
        m.run()
        log.info("Pipeline complete.")
    except Exception as e:
        log.exception(f"Pipeline failed: {e}")


if __name__ == "__main__":
    log.info(f"Scheduler started (PID {os.getpid()}). Runs every hour at :00.")

    # Run immediately on startup, then wait for the next hour boundary
    run_once()

    while True:
        wait = seconds_until_next_hour()
        log.info(f"Next run in {wait/60:.1f} min")
        time.sleep(wait)
        run_once()
