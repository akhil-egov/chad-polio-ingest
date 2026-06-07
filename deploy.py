#!/usr/bin/env python3
"""
deploy.py — push a local extractor file to the remote Jupyter server.

Usage:
    python3 deploy.py extractors/gps.py
    python3 deploy.py extractors/gps.py extractors/gps_refusals.py

The file is uploaded via the Jupyter contents API and lands at:
    <JUPYTER_REMOTE_ROOT>/<your file path>

Reads credentials from .env (JUPYTER_BASE, JUPYTER_TOKEN, JUPYTER_REMOTE_ROOT).
"""

import os
import sys
import json
import ssl
import urllib.request
import urllib.error
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()


def _require(var: str) -> str:
    val = os.environ.get(var)
    if not val:
        print(f"ERROR: {var} is not set. Add it to .env")
        sys.exit(1)
    return val


def _ssl_ctx():
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return ctx


def upload(local_path: str, base: str, token: str, remote_root: str) -> None:
    p = Path(local_path)
    if not p.exists():
        print(f"ERROR: {local_path} not found locally")
        sys.exit(1)

    remote_api_path = f"{remote_root}/{p}"
    url     = f"{base}/api/contents/{remote_api_path}"
    payload = json.dumps({"content": p.read_text(encoding="utf-8"),
                          "type": "file", "format": "text"}).encode("utf-8")
    req = urllib.request.Request(
        url, data=payload, method="PUT",
        headers={"Authorization": f"token {token}",
                 "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, context=_ssl_ctx()) as resp:
            if resp.status in (200, 201):
                print(f"OK  {p}  →  {url}")
    except urllib.error.HTTPError as e:
        print(f"FAILED {local_path}: HTTP {e.code}: {e.read().decode()[:200]}")
        sys.exit(1)
    except Exception as e:
        print(f"FAILED {local_path}: {e}")
        sys.exit(1)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 deploy.py <file> [file2 ...]")
        sys.exit(1)

    base        = _require("JUPYTER_BASE")
    token       = _require("JUPYTER_TOKEN")
    remote_root = _require("JUPYTER_REMOTE_ROOT")

    for f in sys.argv[1:]:
        upload(f, base, token, remote_root)
