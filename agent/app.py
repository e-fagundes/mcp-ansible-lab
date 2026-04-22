import os
import time
from dataclasses import dataclass
from typing import Any, Dict

import ansible_runner
import requests
import yaml
from fastapi import FastAPI, Request
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Gauge, generate_latest
from starlette.responses import Response

app = FastAPI(title="lab-decision-agent")

PROMETHEUS_URL = os.getenv("PROMETHEUS_URL", "http://prometheus:9090").rstrip("/")
RULES_FILE = os.getenv("RULES_FILE", "/app/rules.yml")
RUNNER_PRIVATE_DATA_DIR = os.getenv("RUNNER_PRIVATE_DATA_DIR", "/app/runner")
PARALLELISM_FILE = os.getenv("PARALLELISM_FILE", "/shared/parallelism.txt")
COOLDOWN_DEFAULT = int(os.getenv("ALERT_COOLDOWN_SECONDS", "120"))

DECISIONS = Counter("lab_decisions_total", "Decisions taken by agent", ["result", "rule"])
LAST_DECISION_TS = Gauge("lab_last_decision_timestamp", "Unix timestamp of last decision run")
LAST_CONTEXT_QUEUE = Gauge("lab_last_context_queue_length", "Last queue length seen by agent")
LAST_CONTEXT_CPU = Gauge("lab_last_context_worker_cpu", "Last worker cpu seen by agent")

@dataclass
class Rule:
    name: str
    enabled: bool
    cooldown_seconds: int
    queue_length_gt: float
    worker_cpu_gt: float
    playbook: str
    desired_parallelism: int

_last_trigger: Dict[str, float] = {}

def load_rule() -> Rule:
    with open(RULES_FILE, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    r0 = cfg["rules"][0]
    return Rule(
        name=str(r0["name"]),
        enabled=bool(r0.get("enabled", True)),
        cooldown_seconds=int(r0.get("cooldown_seconds", COOLDOWN_DEFAULT)),
        queue_length_gt=float(r0["when"]["queue_length_gt"]),
        worker_cpu_gt=float(r0["when"]["worker_cpu_gt"]),
        playbook=str(r0["action"]["playbook"]),
        desired_parallelism=int(r0["action"]["desired_parallelism"]),
    )

def prom_query(promql: str) -> float:
    r = requests.get(
        f"{PROMETHEUS_URL}/api/v1/query",
        params={"query": promql},
        timeout=3,
    )
    r.raise_for_status()
    data = r.json()
    result = data.get("data", {}).get("result", [])
    if not result:
        return 0.0
    return float(result[0]["value"][1])

def read_current_parallelism() -> int:
    try:
        with open(PARALLELISM_FILE, "r", encoding="utf-8") as f:
            return int(f.read().strip())
    except Exception:
        return 1

def in_cooldown(rule_name: str, cooldown_s: int) -> bool:
    last = _last_trigger.get(rule_name)
    return last is not None and (time.time() - last) < cooldown_s

def mark_trigger(rule_name: str) -> None:
    _last_trigger[rule_name] = time.time()
    LAST_DECISION_TS.set(_last_trigger[rule_name])

def run_playbook(playbook: str, extravars: Dict[str, Any]) -> Dict[str, Any]:
    r = ansible_runner.run(
        private_data_dir=RUNNER_PRIVATE_DATA_DIR,
        playbook=playbook,
        extravars=extravars,
    )
    return {"status": r.status, "rc": r.rc, "stats": r.stats}

@app.get("/health")
def health() -> dict:
    return {"status": "ok", "prometheus": PROMETHEUS_URL}

@app.get("/metrics")
def metrics() -> Response:
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)

@app.post("/alertmanager")
async def alertmanager_webhook(req: Request) -> dict:
    payload = await req.json()
    status = payload.get("status", "")
    rule = load_rule()

    if not rule.enabled:
        DECISIONS.labels(result="disabled", rule=rule.name).inc()
        return {"ok": True, "action": "disabled"}

    if status != "firing":
        DECISIONS.labels(result="ignored", rule=rule.name).inc()
        return {"ok": True, "status": status, "action": "none"}

    if in_cooldown(rule.name, rule.cooldown_seconds):
        DECISIONS.labels(result="cooldown", rule=rule.name).inc()
        return {"ok": True, "status": status, "action": "cooldown"}

    qlen = prom_query("max(lab_queue_length)")
    cpu = prom_query('max(rate(process_cpu_seconds_total{job="worker"}[1m]))')

    LAST_CONTEXT_QUEUE.set(qlen)
    LAST_CONTEXT_CPU.set(cpu)

    current_p = read_current_parallelism()

    match = (
        (qlen > rule.queue_length_gt)
        and (cpu > rule.worker_cpu_gt)
        and (current_p < rule.desired_parallelism)
    )

    if not match:
        DECISIONS.labels(result="no_match", rule=rule.name).inc()
        return {
            "ok": True,
            "match": False,
            "context": {
                "queue_length": qlen,
                "worker_cpu": cpu,
                "current_parallelism": current_p,
            },
        }

    try:
        res = run_playbook(rule.playbook, {"desired_parallelism": rule.desired_parallelism})
        mark_trigger(rule.name)
        DECISIONS.labels(result="triggered", rule=rule.name).inc()
        return {
            "ok": True,
            "match": True,
            "context": {
                "queue_length": qlen,
                "worker_cpu": cpu,
                "current_parallelism": current_p,
            },
            "action": {
                "playbook": rule.playbook,
                "desired_parallelism": rule.desired_parallelism,
                "result": res,
            },
        }
    except Exception as e:
        DECISIONS.labels(result="error", rule=rule.name).inc()
        return {"ok": False, "error": str(e)}
