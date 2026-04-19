from flask import Flask, Response
import random

app = Flask(__name__)

@app.route("/metrics")
def metrics():
    cpu = random.randint(50, 90)
    return Response(f"cpu_usage {cpu}\n", mimetype="text/plain")

app.run(host="0.0.0.0", port=8000)
