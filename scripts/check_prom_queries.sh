#!/usr/bin/env bash
set -euo pipefail

PROM="http://127.0.0.1:9090"

echo "Queue length:"
curl -sG "${PROM}/api/v1/query" --data-urlencode 'query=max(lab_queue_length)'
echo
echo

echo "Worker CPU:"
curl -sG "${PROM}/api/v1/query" --data-urlencode 'query=max(rate(process_cpu_seconds_total{job="worker"}[1m]))'
echo
