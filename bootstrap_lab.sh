#!/usr/bin/env bash

set -euo pipefail

echo "==== MCP LAB BOOTSTRAP ===="

BASE_DIR="$PWD/mcp-ansible-lab"
DOCKER_DIR="$BASE_DIR/docker"
AGENT_DIR="$BASE_DIR/agent"
ANSIBLE_DIR="$BASE_DIR/ansible"
METRICS_DIR="$BASE_DIR/metrics"

mkdir -p "$DOCKER_DIR" "$AGENT_DIR" "$ANSIBLE_DIR" "$METRICS_DIR"

echo ""
echo "==[1] VALIDANDO AMBIENTE =="

command -v docker >/dev/null || { echo "Docker não encontrado"; exit 1; }
command -v curl >/dev/null || { echo "curl não encontrado"; exit 1; }

echo "Docker OK"
echo "Curl OK"

echo ""
echo "==[2] ESTADO DO PROMETHEUS =="

PROM="http://localhost:9090"

if curl -s "$PROM" >/dev/null; then
  echo "Prometheus acessível"
else
  echo "Prometheus NÃO acessível -> problema de base"
fi

echo ""
echo "-- Targets:"
curl -s "$PROM/api/v1/targets" | jq '.data.activeTargets[] | {job: .labels.job, health: .health, lastError: .lastError}'

echo ""
echo "-- Query cpu_usage:"
CPU=$(curl -s "$PROM/api/v1/query?query=cpu_usage" | jq -r '.data.result[0].value[1] // "null"')
echo "cpu_usage=$CPU"

if [ "$CPU" = "null" ]; then
  echo "⚠️ Prometheus não está retornando métricas -> pipeline quebrado"
fi

echo ""
echo "==[3] VALIDAÇÃO DO GAP =="

echo "- metrics container? (esperado)"
docker ps | grep metrics || echo "❌ metrics NÃO dockerizado"

echo "- alertmanager?"
docker ps | grep alertmanager || echo "❌ alertmanager ausente"

echo "- grafana?"
docker ps | grep grafana || echo "❌ grafana ausente"

echo "- agent webhook?"
if grep -q "FastAPI" "$AGENT_DIR/server.py" 2>/dev/null; then
  echo "Agent existe"
else
  echo "❌ Agent não estruturado como serviço HTTP"
fi

echo ""
echo "==[4] CRIANDO ESTRUTURA BASE =="

mkdir -p "$BASE_DIR/prometheus"
mkdir -p "$BASE_DIR/alertmanager"
mkdir -p "$BASE_DIR/shared"

echo "1" > "$BASE_DIR/shared/parallelism.txt"

echo ""
echo "==[5] GERANDO PROMETHEUS CONFIG =="

cat > "$BASE_DIR/prometheus/prometheus.yml" <<EOF
global:
  scrape_interval: 5s

scrape_configs:
  - job_name: "metrics"
    static_configs:
      - targets: ["metrics:8000"]
EOF

echo ""
echo "==[6] GERANDO ALERT RULE =="

cat > "$BASE_DIR/prometheus/alerts.yml" <<EOF
groups:
- name: lab.rules
  rules:
  - alert: HighCPU
    expr: cpu_usage > 80
    for: 10s
    labels:
      severity: warning
    annotations:
      summary: "CPU alta detectada"
EOF

echo ""
echo "==[7] ALERTMANAGER =="

cat > "$BASE_DIR/alertmanager/alertmanager.yml" <<EOF
route:
  receiver: agent

receivers:
- name: agent
  webhook_configs:
  - url: "http://agent:8081/alertmanager"
EOF

echo ""
echo "==[8] DOCKER COMPOSE BASE =="

cat > "$BASE_DIR/docker-compose.yml" <<EOF
version: "3.9"

services:
  metrics:
    build: ./metrics
    ports:
      - "127.0.0.1:8000:8000"

  prometheus:
    image: prom/prometheus:latest
    volumes:
      - ./prometheus/prometheus.yml:/etc/prometheus/prometheus.yml
      - ./prometheus/alerts.yml:/etc/prometheus/alerts.yml
    ports:
      - "127.0.0.1:9090:9090"

  alertmanager:
    image: prom/alertmanager:latest
    volumes:
      - ./alertmanager/alertmanager.yml:/etc/alertmanager/alertmanager.yml
    ports:
      - "127.0.0.1:9093:9093"

  agent:
    build: ./agent
    ports:
      - "127.0.0.1:8081:8081"
EOF

echo ""
echo "==[9] METRICS SERVICE =="

cat > "$METRICS_DIR/app.py" <<EOF
from flask import Flask, Response
import random

app = Flask(__name__)

@app.route("/metrics")
def metrics():
    cpu = random.randint(50, 90)
    return Response(f"cpu_usage {cpu}\\n", mimetype="text/plain")

app.run(host="0.0.0.0", port=8000)
EOF

cat > "$METRICS_DIR/Dockerfile" <<EOF
FROM python:3.10-slim
WORKDIR /app
RUN pip install flask
COPY app.py .
CMD ["python", "app.py"]
EOF

echo ""
echo "==[10] RESUMO FINAL =="

echo "✔ Estrutura criada em $BASE_DIR"
echo ""
echo "Próximos passos:"
echo "1. cd $BASE_DIR"
echo "2. docker compose up -d --build"
echo "3. acessar http://localhost:9090"
echo ""
echo "⚠️ Isso NÃO é o estado final do doc."
echo "Isso só resolve seu gargalo atual: base consistente."

echo ""
echo "==== FIM ===="
