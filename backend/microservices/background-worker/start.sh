#!/usr/bin/env bash
set -euo pipefail

export PYTHONPATH=/app/backend
cd /app/backend/microservices/background-worker

celery -A worker_app.celery_app worker -B -l info -Q default,preview,email,indexing,channels,connectors,verification,emma_reactive,trustgraph_extraction &
CELERY_PID=$!

uvicorn worker_app.main:app --host 0.0.0.0 --port 8100 &
UVICORN_PID=$!

trap "kill -TERM $CELERY_PID $UVICORN_PID" TERM INT
wait -n $CELERY_PID $UVICORN_PID
