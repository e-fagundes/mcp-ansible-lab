# agent/app.py
import os
import logging
import json
from fastapi import FastAPI, Request
import requests
import redis

app = FastAPI()

# Configure logging: envia para STDOUT e arquivo
LOG_FILE = os.environ.get("AGENT_LOG_FILE", "/tmp/decision_agent.log")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(LOG_FILE)
    ],
)

PROM_URL = os.environ.get("PROM_URL", "http://prometheus:9090")
QUEUE_HOST = os.environ.get("QUEUE_HOST", "queue")  # serviço do Rabbit ou Redis
QUEUE_PORT = int(os.environ.get("QUEUE_PORT", "6379"))
QUEUE_CHANNEL = os.environ.get("QUEUE_CHANNEL", "actions")

# Inicializa redis para enfileirar jobs
redis_client = redis.Redis(host=QUEUE_HOST, port=QUEUE_PORT, decode_responses=True)

def query_prometheus(query: str) -> float | None:
    """Consulta a métrica e devolve um valor numérico ou None."""
    try:
        resp = requests.get(f"{PROM_URL}/api/v1/query", params={"query": query}, timeout=5)
        data = resp.json()
        result = data.get("data", {}).get("result", [])
        if result:
            value = float(result[0]["value"][1])
            return value
    except Exception as exc:
        logging.error(f"Erro consultando Prometheus: {exc}")
    return None

def enqueue_action(context: dict):
    """Envia contexto e nome da playbook para a fila. Worker irá executar."""
    payload = {"playbook": "/ansible/remediate.yml", "context": context}
    redis_client.rpush(QUEUE_CHANNEL, json.dumps(payload))
    logging.info("Ação enfileirada com sucesso")

@app.post("/alertmanager")
async def alertmanager_webhook(request: Request):
    """Recebe alerts do Alertmanager e decide se aciona remediação."""
    data = await request.json()
    # Apenas exemplo: extrai primeiro alerta, usa label 'severity'
    alerts = data.get("alerts", [])
    severity = alerts[0]["labels"].get("severity") if alerts else "unknown"
    cpu_usage = query_prometheus("cpu_usage")

    context = {"cpu_usage": cpu_usage, "severity": severity, "status": "no_action"}

    if cpu_usage is None:
        context["status"] = "error"
        logging.warning(f"Não foi possível obter cpu_usage: {context}")
        return {"decision": {"decision": "no_action", "context": context}}

    if cpu_usage > 80:
        # Exemplo de decisão: CPU > 80 dispara playbook
        context["status"] = "degraded"
        enqueue_action(context)
        logging.info(f"Remediação disparada: {context}")
        return {"decision": {"decision": "remediation_triggered", "context": context}}

    logging.info(f"Sem ação necessária: {context}")
    return {"decision": {"decision": "no_action", "context": context}}
