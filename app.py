from flask import Flask, render_template, request, jsonify
import re

app = Flask(__name__)
MAX_TOKENS = 131072


def estimate_tokens(text: str) -> int:
    return max(1, len(text) // 4)


def redact(text: str):
    """Very simple server-side PII redaction (demo)."""
    count = 0
    patterns = [
        (r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", "[EMAIL REDACTED]"),
        (r"\b[A-Z]{5}[0-9]{4}[A-Z]\b", "[PAN REDACTED]"),
        (r"(?<!\d)(?:\+91[\s-]?)?[6-9]\d{9}(?!\d)", "[PHONE REDACTED]"),
    ]
    for pat, repl in patterns:
        text, n = re.subn(pat, repl, text)
        count += n
    return text, count


@app.route("/")
def index():
    return render_template("index.html")


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


@app.route("/chat", methods=["POST"])
def chat():
    data = request.get_json(silent=True) or {}
    message = (data.get("message") or "").strip()
    if not message:
        return jsonify({"error": "Empty message"}), 400

    safe, pii_count = redact(message) if data.get("pii_protection", True) else (message, 0)

    # TODO: replace this echo with a real AI call using `safe`
    answer = f"You said: **{safe}**\n\n(Connect a real AI model in `app.py`.)"

    tokens = estimate_tokens(safe) + estimate_tokens(answer)
    return jsonify({
        "response": answer,
        "safe_message": safe,
        "tokens": tokens,
        "token_percent": tokens / MAX_TOKENS * 100,
        "cost": tokens * 0.000001,
        "pii": f"{pii_count} item(s) redacted" if pii_count else "No PII detected",
        "warnings": [],
    })


if __name__ == "__main__":
    app.run(debug=True)
