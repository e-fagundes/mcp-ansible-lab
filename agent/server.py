from fastmcp import FastMCP
import subprocess
import requests

mcp = FastMCP("ansible-agent")


@mcp.tool()
def get_context():
    """
    Busca métrica cpu_usage do Prometheus.
    """
    try:
        response = requests.get(
            "http://prometheus:9090/api/v1/query?query=cpu_usage",
            timeout=2
        )
        data = response.json()

        results = data.get("data", {}).get("result", [])

        # ⚠️ Evita crash se não houver dados
        if not results:
            return {
                "cpu_usage": None,
                "status": "no_data",
                "error": "No metrics returned from Prometheus"
            }

        value = float(results[0]["value"][1])

        return {
            "cpu_usage": value,
            "status": "degraded" if value > 80 else "normal"
        }

    except Exception as e:
        return {
            "cpu_usage": None,
            "status": "error",
            "error": str(e)
        }


@mcp.tool()
def remediate():
    """
    Executa playbook Ansible dentro do container.
    """
    try:
        result = subprocess.run(
            [
                "ansible-playbook",
                "/ansible/remediate.yml",
                "-i",
                "localhost,"
            ],
            capture_output=True,
            text=True
        )

        return {
            "status": "executed",
            "stdout": result.stdout,
            "stderr": result.stderr
        }

    except Exception as e:
        return {"error": str(e)}


@mcp.tool()
def decide_and_act():
    """
    Toma decisão baseada no contexto.
    """
    context = get_context()

    # ⚠️ Proteção contra erro ou ausência de dados
    if context.get("cpu_usage") is None:
        return {
            "decision": "no_action",
            "reason": "no_data_or_error",
            "context": context
        }

    if context["cpu_usage"] > 80:
        result = remediate()
        return {
            "decision": "remediation_triggered",
            "context": context,
            "result": result
        }

    return {
        "decision": "no_action",
        "context": context
    }


if __name__ == "__main__":
    mcp.run()
