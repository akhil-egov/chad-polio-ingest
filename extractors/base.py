"""
Elasticsearch connection wrapper.
This is the ONLY file in the repo that makes HTTP calls to Elasticsearch.
All credentials are loaded from environment variables (.env for local, kernel env for Jupyter).
"""

import os
import requests
from dotenv import load_dotenv

load_dotenv()


class ESClient:
    """Thin wrapper around the Elasticsearch REST API using basic auth."""

    def __init__(self):
        self.base_url = os.environ["ES_URL"].rstrip("/")
        # verify=False is intentional — ES cluster uses a self-signed cert
        self._session = requests.Session()
        self._session.verify = False
        self._session.headers.update({"Content-Type": "application/json"})

        # Auth priority: ES_AUTH_HEADER > ES_USER+ES_PASS
        auth_header = os.environ.get("ES_AUTH_HEADER")
        if auth_header:
            self._session.headers["Authorization"] = auth_header
        else:
            self._session.auth = (os.environ["ES_USER"], os.environ["ES_PASS"])

    def query(self, index: str, body: dict) -> dict:
        """
        POST a single search request to {ES_URL}/{index}/_search.
        Returns the parsed JSON response.
        Raises RuntimeError with status code + body on any HTTP error.
        """
        url = f"{self.base_url}/{index}/_search"
        resp = self._session.post(url, json=body)
        if not resp.ok:
            raise RuntimeError(
                f"ES query failed [{resp.status_code}] on index '{index}': {resp.text}"
            )
        return resp.json()

    def scroll(self, index: str, body: dict, size: int = 1000, expected_total: int = None):
        """
        Generator that handles ES scroll pagination.
        Yields one hit dict at a time across all pages.
        Automatically cleans up the scroll context when done or on error.

        Parameters
        ----------
        index : str
            ES index name.
        body : dict
            ES query body (without 'size' — that is added internally).
        size : int
            Page size per scroll batch (default 1000).
        expected_total : int, optional
            If provided, a warning is printed after scrolling if the number of
            yielded hits does not match this value.  Useful for catching
            scroll-window expiry that silently truncates results.

        Usage:
            for hit in es.scroll("my-index", {"query": {...}}):
                doc = hit["_source"]
        """
        scroll_id = None
        all_hits_count = 0
        try:
            # Initial search — open a 5-minute scroll window
            init_body = {**body, "size": size}
            url = f"{self.base_url}/{index}/_search?scroll=5m"
            resp = self._session.post(url, json=init_body)
            if not resp.ok:
                raise RuntimeError(
                    f"ES scroll init failed [{resp.status_code}] on index '{index}': {resp.text}"
                )
            data = resp.json()
            scroll_id = data.get("_scroll_id")
            hits = data.get("hits", {}).get("hits", [])

            while hits:
                for hit in hits:
                    all_hits_count += 1
                    yield hit

                # Fetch next page
                scroll_resp = self._session.post(
                    f"{self.base_url}/_search/scroll",
                    json={"scroll": "5m", "scroll_id": scroll_id},
                )
                scroll_resp.raise_for_status()
                scroll_data = scroll_resp.json()
                scroll_id = scroll_data.get("_scroll_id", scroll_id)
                hits = scroll_data.get("hits", {}).get("hits", [])

        finally:
            # Always clean up the scroll context to free server resources
            if scroll_id:
                try:
                    self._session.delete(
                        f"{self.base_url}/_search/scroll",
                        json={"scroll_id": scroll_id},
                    )
                except Exception:
                    pass  # Best-effort cleanup — do not mask original errors

        if expected_total is not None and all_hits_count != expected_total:
            print(
                f"WARNING: scroll on '{index}' returned {all_hits_count} hits "
                f"but expected {expected_total} "
                f"(missing {expected_total - all_hits_count}). "
                "Scroll window may have expired mid-pagination."
            )
