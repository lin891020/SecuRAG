"""SecuRAG Auto-Ingest DAG

Scans /watched_docs every 6 hours for new PDF/TXT/MD files that have not
yet been ingested into the SecuRAG knowledge base, and uploads them via the
backend API.

Drop files into the watched_docs/ folder in the project root and they will
be automatically indexed on the next DAG run.

The work itself lives in `securag_ingest_lib`, which imports no Airflow and so
can be tested by the backend suite; this file is the schedule and the XCom
plumbing. Keeping a DAG thin is the usual way to make its logic testable --
`airflow` is only installed in the Airflow image.
"""

from datetime import datetime, timedelta

from airflow import DAG
from airflow.operators.python import PythonOperator

from securag_ingest_lib import ingest, scan


def scan_watch_folder(**context):
    new_files = scan()
    context["ti"].xcom_push(key="new_files", value=new_files)
    return len(new_files)


def ingest_new_files(**context):
    new_files = context["ti"].xcom_pull(key="new_files", task_ids="scan_watch_folder")
    return ingest(new_files)


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

    scan_task = PythonOperator(
        task_id="scan_watch_folder",
        python_callable=scan_watch_folder,
    )

    ingest_task = PythonOperator(
        task_id="ingest_new_files",
        python_callable=ingest_new_files,
    )

    scan_task >> ingest_task
