import os
import threading
import time
import requests

from fastapi import FastAPI
from prometheus_client import Gauge, generate_latest, CONTENT_TYPE_LATEST
from starlette.responses import Response

app = FastAPI(title="lab-worker")

QUEUE_URL = os.getenv("QUEUE_URL", "http://queue:8000").rstrip("/")
CONFIG_FILE = os.getenv("CONFIG_FILE", "/shared/parallelism.txt")

WORKER_PARALLELISM = Gauge("lab_worker_parallelism", "Configured worker parallelism")
WORKER_ACTIVE_SLOTS = Gauge("lab_worker_active_slots", "Currently active worker slots")

stop_event = threading.Event()
threads: list[threading.Thread] = []
parallelism = 1
active_slots = 0
active_lock = threading.Lock()

def read_parallelism() -> int:
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            value = int(f.read().strip())
            return max(1, value)
    except Exception:
        return 1

def cpu_work(work_ms: int) -> None:
    end = time.time() + (work_ms / 1000.0)
    x = 0
    while time.time() < end:
        x += 1

def worker_loop(slot_id: int) -> None:
    global active_slots
    while not stop_event.is_set():
        try:
            r = requests.get(f"{QUEUE_URL}/dequeue", timeout=2)
            r.raise_for_status()
            payload = r.json()

            if payload.get("status") != "ok":
                time.sleep(0.2)
                continue

            work_ms = int(payload["item"].get("work_ms", 100))

            with active_lock:
                active_slots += 1
                WORKER_ACTIVE_SLOTS.set(active_slots)

            cpu_work(work_ms)

        except Exception:
            time.sleep(0.5)
        finally:
            with active_lock:
                if active_slots > 0:
                    active_slots -= 1
                WORKER_ACTIVE_SLOTS.set(active_slots)

def start_workers() -> None:
    global threads, parallelism
    parallelism = read_parallelism()
    WORKER_PARALLELISM.set(parallelism)
    stop_event.clear()
    threads = []
    for i in range(parallelism):
        t = threading.Thread(target=worker_loop, args=(i,), daemon=True)
        t.start()
        threads.append(t)

def stop_workers() -> None:
    stop_event.set()
    for t in threads:
        t.join(timeout=1)

@app.on_event("startup")
def on_startup() -> None:
    start_workers()

@app.get("/health")
def health() -> dict:
    return {
        "status": "ok",
        "parallelism": parallelism,
        "active_slots": active_slots,
        "queue_url": QUEUE_URL,
    }

@app.post("/reload")
def reload_workers() -> dict:
    stop_workers()
    start_workers()
    return {"status": "reloaded", "parallelism": parallelism}

@app.get("/metrics")
def metrics() -> Response:
    WORKER_PARALLELISM.set(parallelism)
    WORKER_ACTIVE_SLOTS.set(active_slots)
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
