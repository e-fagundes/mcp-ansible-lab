from flask import Flask, Response
import random

app = Flask(__name__)

@app.route("/metrics")
def metrics():
    cpu = 95

    return Response(
        f"cpu_usage {cpu}\n",
        mimetype="text/plain"
    )

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000)
