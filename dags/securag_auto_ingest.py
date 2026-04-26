"""SecuRAG Auto-Ingest DAG

Scans /watched_docs every 6 hours for new PDF/TXT/MD files that have not
yet been ingested into the SecuRAG knowledge base, and uploads them via the
backend API.

Drop files into the watched_docs/ folder in the project root and they will
be automatically indexed on the next DAG run.
"""

import os
from datetime import datetime, timedelta
from pathlib import Path

import requests
from airflow import DAG
from airflow.operators.python import PythonOperator

BACKEND_URL = os.getenv("SECURAG_BACKEND_URL", "http://backend:8000/api")
WATCH_DIR = Path("/watched_docs")
ALLOWED_EXTENSIONS = {".pdf", ".txt", ".md"}


def _get_ingested_filenames() -> set[str]:
    resp = requests.get(f"{BACKEND_URL}/documents", timeout=10)
    resp.raise_for_status()
    return {d["filename"] for d in resp.json().get("documents", [])}


def scan_watch_folder(**context):
    """Find files in /watched_docs not yet in the knowledge base."""
    if not WATCH_DIR.exists():
        print(f"Watch directory {WATCH_DIR} does not exist — nothing to scan.")
        context["ti"].xcom_push(key="new_files", value=[])
        return 0

    ingested = _get_ingested_filenames()
    new_files = [
        str(f)
        for f in WATCH_DIR.iterdir()
        if f.is_file() and f.suffix.lower() in ALLOWED_EXTENSIONS and f.name not in ingested
    ]

    context["ti"].xcom_push(key="new_files", value=new_files)
    print(f"Found {len(new_files)} new file(s): {[Path(p).name for p in new_files]}")
    return len(new_files)


def ingest_new_files(**context):
    """Upload each new file to SecuRAG via the documents API."""
    new_files = context["ti"].xcom_pull(key="new_files", task_ids="scan_watch_folder")

    if not new_files:
        print("No new files to ingest.")
        return 0

    failed = []
    for file_path in new_files:
        path = Path(file_path)
        try:
            with path.open("rb") as f:
                resp = requests.post(
                    f"{BACKEND_URL}/documents/upload",
                    files={"file": (path.name, f, "application/octet-stream")},
                    timeout=300,
                )
                resp.raise_for_status()
            print(f"Ingested: {path.name}")
        except Exception as exc:
            print(f"Failed to ingest {path.name}: {exc}")
            failed.append(path.name)

    if failed:
        raise RuntimeError(f"Ingestion failed for: {failed}")

    print(f"Done — {len(new_files) - len(failed)} file(s) ingested successfully.")
    return len(new_files) - len(failed)


default_args = {
    "owner": "securag",
    "retries": 1,
    "retry_delay": timedelta(minutes=5),
    "email_on_failure": False,
}

with DAG(
    dag_id="securag_auto_ingest",
    description="Auto-ingest new documents from watched_docs/ into the SecuRAG knowledge base",
    schedule="0 */6 * * *",
    start_date=datetime(2024, 1, 1),
    catchup=False,
    default_args=default_args,
    tags=["securag", "ingestion"],
) as dag:

    scan = PythonOperator(
        task_id="scan_watch_folder",
        python_callable=scan_watch_folder,
    )

    ingest = PythonOperator(
        task_id="ingest_new_files",
        python_callable=ingest_new_files,
    )

    scan >> ingest
