"""The auto-ingest logic, with no Airflow in it.

Separated from `securag_auto_ingest.py` so it can be tested. The DAG module
imports `airflow`, which only exists in the Airflow image, so anything defined
there cannot be imported by the backend's test suite -- and the idempotency
this module is careful about is exactly the sort of thing that needs a test
rather than a careful read.

The DAG keeps the scheduling and the XCom plumbing; everything here takes
ordinary arguments and returns ordinary values.
"""

from __future__ import annotations

import os
from pathlib import Path

import requests

BACKEND_URL = os.getenv("SECURAG_BACKEND_URL", "http://backend:8000/api")
WATCH_DIR = Path("/watched_docs")
ALLOWED_EXTENSIONS = {".pdf", ".txt", ".md"}


def ingested_filenames(backend_url: str | None = None) -> set[str]:
    """What the knowledge base already holds, by filename."""
    resp = requests.get(f"{backend_url or BACKEND_URL}/documents", timeout=10)
    resp.raise_for_status()
    return {d["filename"] for d in resp.json().get("documents", [])}


def scan(watch_dir: Path | None = None, backend_url: str | None = None) -> list[str]:
    """Files in the watch folder that the knowledge base does not have yet."""
    directory = watch_dir or WATCH_DIR
    if not directory.exists():
        print(f"Watch directory {directory} does not exist — nothing to scan.")
        return []

    already = ingested_filenames(backend_url)
    found = [
        str(f)
        for f in directory.iterdir()
        if f.is_file()
        and f.suffix.lower() in ALLOWED_EXTENSIONS
        and f.name not in already
    ]
    print(f"Found {len(found)} new file(s): {[Path(p).name for p in found]}")
    return found


def ingest(new_files: list[str] | None, backend_url: str | None = None) -> int:
    """Upload each file that is still missing. Returns how many went in.

    Re-reads what is already indexed rather than trusting the list the scan
    produced. The Airflow task that calls this has ``retries: 1`` and raises
    when any single upload fails, so a run that ingested nine files and failed
    on the tenth used to come back and upload all ten again -- the list still
    named the nine, because it was written before any of them existed in the
    knowledge base. A duplicate document is a duplicate set of chunks answering
    every future query. One extra HTTP request makes the retry idempotent.
    """
    if not new_files:
        print("No new files to ingest.")
        return 0

    try:
        already = ingested_filenames(backend_url)
    except requests.RequestException as exc:
        # Stopping is better than re-uploading: the failure mode of guessing
        # wrong here is silent duplication, which nothing downstream detects.
        raise RuntimeError(f"Could not check what is already ingested: {exc}") from exc

    pending = [p for p in new_files if Path(p).name not in already]
    if len(pending) != len(new_files):
        skipped = [Path(p).name for p in new_files if Path(p).name in already]
        print(f"Already ingested since the scan, skipping: {skipped}")
    if not pending:
        print("Everything from the scan is already in the knowledge base.")
        return 0

    failed: list[str] = []
    for file_path in pending:
        path = Path(file_path)
        try:
            with path.open("rb") as handle:
                resp = requests.post(
                    f"{backend_url or BACKEND_URL}/documents/upload",
                    files={"file": (path.name, handle, "application/octet-stream")},
                    timeout=300,
                )
                resp.raise_for_status()
            print(f"Ingested: {path.name}")
        except (requests.RequestException, OSError) as exc:
            print(f"Failed to ingest {path.name}: {exc}")
            failed.append(path.name)

    if failed:
        raise RuntimeError(f"Ingestion failed for: {failed}")

    print(f"Done — {len(pending)} file(s) ingested successfully.")
    return len(pending)
