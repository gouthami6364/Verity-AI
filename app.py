from flask import Flask, render_template, request, jsonify
from pipeline import VerityAI
import os

app = Flask(__name__)
sessions = {}

@app.route("/", methods=["GET"])
def home():
    return render_template("index.html")

@app.route("/chat", methods=["POST"])
def chat():
    data = request.get_json(silent=True) or {}
    message = (data.get("message") or "").strip()

    if not message:
        return jsonify({"error": "Empty message"}), 400

    session_id = str(
        data.get("session_id")
        or data.get("chat_id")
        or "default"
    )

    if session_id not in sessions:
        sessions[session_id] = VerityAI()

    result = sessions[session_id].handle(message)
    return jsonify(result)

@app.route("/analyze", methods=["POST"])
def analyze():
    data = request.get_json(silent=True) or {}
    message = (data.get("message") or "").strip()

    if not message:
        return jsonify({"error": "Empty message"}), 400

    refined = message[0].upper() + message[1:]

    if not refined.endswith(("?", ".", "!")):
        refined += "."

    return jsonify({"refined_prompt": refined})

if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=int(os.environ.get("PORT", 5000)),
        debug=False
    )
