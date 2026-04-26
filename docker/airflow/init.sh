#!/usr/bin/env bash
set -e

# Create the Airflow metadata database if it doesn't exist
python - <<'EOF'
import psycopg2, sys
try:
    conn = psycopg2.connect(host="postgres", dbname="securag", user="securag", password="securag")
    conn.autocommit = True
    conn.cursor().execute("CREATE DATABASE airflow OWNER securag")
    conn.close()
    print("airflow database created")
except psycopg2.errors.DuplicateDatabase:
    print("airflow database already exists")
except Exception as e:
    print(f"db create error: {e}", file=sys.stderr)
    sys.exit(1)
EOF

airflow db migrate

airflow users create \
    --username admin \
    --password admin \
    --firstname Admin \
    --lastname User \
    --role Admin \
    --email admin@securag.local 2>/dev/null || true

echo "Airflow init complete"
