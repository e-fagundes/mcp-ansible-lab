import os
import contextlib
import requests
from starlette.applications import Starlette
from starlette.routing import Mount
from mcp.server.fastmcp import FastMCP

PROMETHEUS_URL = os.getenv("PROMETHEUS_URL", "http://prometheus:9090").rstrip("/")
AGENT_URL = os.getenv("AGENT_URL", "http://agent:8081").rstrip("/")
AGENT_ADMIN_TOKEN = os.getenv("AGENT_ADMIN_TOKEN", "")

mcp = FastMCP("Lab MCP-like Ops", stateless_http=True, json_response=True)

def prom_query(promql: str) -> float:
    r = requests.get(
        f"{PROMETHEUS_URL}/api/v1/query",
        params={"query": promql},
        timeout=3,
    )
    r.raise_for_status()
    result = r.json().get("data", {}).get("result", [])
    if not result:
        return 0.0
    return float(result[0]["value"][1])

@mcp.tool()
def get_context() -> dict:
    """Retorna contexto operacional (fila, CPU e paralelismo atual)."""
    agent_ctx = requests.get(f"{AGENT_URL}/context", timeout=5)
    agent_ctx.raise_for_status()
    return agent_ctx.json()

@mcp.tool()
def get_status() -> dict:
    """Retorna o status de health do agent."""
    r = requests.get(f"{AGENT_URL}/health", timeout=5)
    r.raise_for_status()
    return r.json()

@mcp.tool()
def remediate(desired_parallelism: int = 4, dry_run: bool = True) -> dict:
    """Dispara remediação via agent. dry_run é true por padrão."""
    r = requests.post(
        f"{AGENT_URL}/run",
        json={
            "desired_parallelism": desired_parallelism,
            "dry_run": dry_run,
            "token": AGENT_ADMIN_TOKEN,
            "reason": "mcp_gateway",
        },
        timeout=15,
    )
    r.raise_for_status()
    return r.json()

@mcp.tool()
def explain_current_state() -> dict:
    """Explicação determinística do estado atual, sem LLM."""
    qlen = prom_query("max(lab_queue_length)")
    cpu = prom_query('max(rate(process_cpu_seconds_total{job="worker"}[1m]))')
    ctx = requests.get(f"{AGENT_URL}/context", timeout=5).json()["context"]

    explanation = []
    if qlen > 50:
        explanation.append("A fila está acima do threshold operacional.")
    else:
        explanation.append("A fila está abaixo do threshold operacional.")

    if cpu > 0.70:
        explanation.append("A CPU do worker está alta.")
    else:
        explanation.append("A CPU do worker está abaixo do threshold de escala.")

    if ctx["current_parallelism"] >= 4:
        explanation.append("O paralelismo atual já atingiu o alvo de remediação.")
    else:
        explanation.append("Ainda existe espaço para escalar o worker.")

    return {
        "context": {
            "queue_length": qlen,
            "worker_cpu": cpu,
            "current_parallelism": ctx["current_parallelism"],
        },
        "explanation": explanation,
    }

@contextlib.asynccontextmanager
async def lifespan(app: Starlette):
    async with mcp.session_manager.run():
        yield

app = Starlette(
    routes=[
        Mount("/", app=mcp.streamable_http_app()),
    ],
    lifespan=lifespan,
)
