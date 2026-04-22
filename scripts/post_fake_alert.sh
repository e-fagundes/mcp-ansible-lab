#!/usr/bin/env bash
set -euo pipefail

curl -s -X POST "http://127.0.0.1:8081/alertmanager" \
  -H "Content-Type: application/json" \
  -d '{
    "receiver": "decision-agent",
    "status": "firing",
    "alerts": [
      {
        "status": "firing",
        "labels": { "alertname": "LabBacklogAndCpuHigh", "severity": "warning" },
        "annotations": { "summary": "Fake firing", "description": "Test payload" }
      }
    ],
    "groupLabels": { "alertname": "LabBacklogAndCpuHigh" },
    "commonLabels": { "alertname": "LabBacklogAndCpuHigh" },
    "commonAnnotations": { "summary": "Fake firing" },
    "externalURL": "http://127.0.0.1:9093",
    "version": "4",
    "groupKey": "test",
    "truncatedAlerts": 0
  }'
echo
