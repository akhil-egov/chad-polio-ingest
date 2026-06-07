#!/usr/bin/env python3
"""
Hourly pipeline runner — invoked by cron on the Jupyter server.
Sets ES credentials from environment or falls back to hardcoded values in .env.
"""
import os
import sys
from pathlib import Path
from dotenv import load_dotenv

dst = Path(__file__).parent
load_dotenv(dst / ".env")  # loads ES_URL, ES_AUTH_HEADER etc.

os.chdir(str(dst))
sys.path.insert(0, str(dst))

from main import run
run()
