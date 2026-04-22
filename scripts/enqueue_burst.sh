#!/usr/bin/env bash
set -euo pipefail

COUNT="${1:-500}"
WORK_MS="${2:-120}"

curl -s -X POST "http://127.0.0.1:8000/enqueue?count=${COUNT}&work_ms=${WORK_MS}"
echo
