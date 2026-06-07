#!/usr/bin/env python3
"""
deploy.py — push a local extractor file to the remote Jupyter server.

Usage:
    python deploy.py extractors/gps.py
    python deploy.py extractors/gps.py extractors/gps_refusals.py

The file is uploaded via the Jupyter contents API and lands at:
    <JUPYTER_REMOTE_ROOT>/<your file path>

No copy-paste, no Jupyter cells needed.
"""

import sys
import json
import base64
from pathlib import Path
import urllib.request
import urllib.error

JUPYTER_BASE   = "https://campaigns.afro.who.int/jupyter/user/reportsadmin"
JUPYTER_TOKEN  = "ca92f2898a594ce48cb4c839abb92ed2"
REMOTE_ROOT    = "HCM_CUSTOM_REPORTS/CHAD_POLIO_PILOT/DST"


def upload(local_path: str) -> None:
    p = Path(local_path)
    if not p.exists():
        print(f"ERROR: {local_path} not found locally")
        sys.exit(1)

    content = p.read_text(encoding="utf-8")
    remote_rel = str(p)  # e.g. "extractors/gps.py"
    remote_api_path = f"{REMOTE_ROOT}/{remote_rel}"

    urls = [
        f"{JUPYTER_BASE}/api/contents/{remote_api_path}",
    ]

    payload = json.dumps({
        "content": content,
        "type": "file",
        "format": "text",
    }).encode("utf-8")

    headers = {
        "Authorization": f"token {JUPYTER_TOKEN}",
        "Content-Type": "application/json",
    }

    last_err = None
    for url in urls:
        req = urllib.request.Request(url, data=payload, headers=headers, method="PUT")
        try:
            import ssl
            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
            with urllib.request.urlopen(req, context=ctx) as resp:
                if resp.status in (200, 201):
                    print(f"OK  {remote_rel}  →  {url}")
                    return
        except urllib.error.HTTPError as e:
            last_err = f"HTTP {e.code}: {e.read().decode()[:200]}"
        except Exception as e:
            last_err = str(e)

    print(f"FAILED to upload {local_path}: {last_err}")
    sys.exit(1)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python deploy.py <file> [file2 ...]")
        sys.exit(1)
    for f in sys.argv[1:]:
        upload(f)
