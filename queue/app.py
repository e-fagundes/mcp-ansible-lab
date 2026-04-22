from collections import deque
from fastapi import FastAPI
from prometheus_client import Gauge, generate_latest, CONTENT_TYPE_LATEST
from starlette.responses import Response

app = FastAPI(title="lab-queue")

QUEUE = deque()

QUEUE_LENGTH = Gauge("lab_queue_length", "Current queue length in the lab queue")

def update_metrics() -> None:
    QUEUE_LENGTH.set(len(QUEUE))

@app.get("/health")
def health() -> dict:
    return {"status": "ok", "queue_length": len(QUEUE)}

@app.post("/enqueue")
def enqueue(count: int = 1, work_ms: int = 100) -> dict:
    for _ in range(count):
        QUEUE.append({"work_ms": work_ms})
    update_metrics()
    return {"status": "enqueued", "count": count, "queue_length": len(QUEUE)}

@app.get("/dequeue")
def dequeue() -> dict:
    if not QUEUE:
        update_metrics()
        return {"status": "empty"}
    item = QUEUE.popleft()
    update_metrics()
    return {"status": "ok", "item": item, "queue_length": len(QUEUE)}

@app.get("/metrics")
def metrics() -> Response:
    update_metrics()
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
