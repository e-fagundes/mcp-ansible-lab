from flask import Flask, request, jsonify
from server import decide_and_act

app = Flask(__name__)

@app.route("/alertmanager", methods=["POST"])
def alert():
    data = request.json

    result = decide_and_act()

    return jsonify({
        "status": "received",
        "decision": result
    })

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8081)
