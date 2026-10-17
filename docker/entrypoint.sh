#!/bin/sh
set -e

echo "Waiting for the database..."
python - <<'EOF'
import time, psycopg2
from retrieval.catalog import get_connection
for i in range(30):
    try:
        get_connection().close()
        print("Database is ready.")
        break
    except psycopg2.OperationalError:
        time.sleep(2)
else:
    raise SystemExit("Database never became ready")
EOF

echo "Building schema embeddings..."
python -m retrieval.index

echo "Starting the app..."
exec streamlit run app.py --server.address=0.0.0.0 --server.port=8501