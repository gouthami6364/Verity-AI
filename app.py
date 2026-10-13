
from flask import Flask, render_template, request, jsonify
import re

app = Flask(
    __name__,
    static_folder="static",
    static_url_path="/static",
    template_folder="templates",
)

MAX_TOKENS = 131072


def estimate_tokens(text: str) -> int:
    """Estimate token usage; this is not an exact tokenizer."""
    return max(1, len(text) // 4)


def redact(text: str):
    """Basic demo PII redaction."""
    count = 0

    patterns = [
        (
            r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}",
            "[EMAIL REDACTED]",
        ),
        (
            r"\b[A-Z]{5}[0-9]{4}[A-Z]\b",
            "[PAN REDACTED]",
        ),
        (
            r"(?<!\d)(?:\+?91[\s-]?)?[6-9]\d{9}(?!\d)",
            "[PHONE REDACTED]",
        ),
    ]

    for pattern, replacement in patterns:
        text, matches = re.subn(pattern, replacement, text)
        count += matches

    return text, count


@app.route("/")
def index():
    """Render the main application page."""
    return render_template("index.html")


@app.route("/analyze", methods=["POST"])
def analyze():
    """Return a basic refined version of the supplied prompt."""
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
    """Process a chat message with basic PII redaction."""
    data = request.get_json(silent=True) or {}
    message = (data.get("message") or "").strip()

    if not message:
        return jsonify({"error": "Empty message"}), 400

    pii_protection = data.get("pii_protection", True)

    if pii_protection:
        safe_message, pii_count = redact(message)
    else:
        safe_message, pii_count = message, 0

    # Demo response only. Connect your existing AI pipeline here
    # if you want real AI-generated answers.
    answer = (
        f"You said: **{safe_message}**\n\n"
        "(This is a demo response; no AI model is connected in this file.)"
    )

    tokens = estimate_tokens(safe_message) + estimate_tokens(answer)
    token_percent = min(100, tokens / MAX_TOKENS * 100)

    return jsonify({
        "response": answer,
        "reply": answer,
        "safe_message": safe_message,
        "tokens": tokens,
        "token_percent": token_percent,
        "cost": tokens * 0.000001,
        "pii": (
            f"{pii_count} item(s) redacted"
            if pii_count
            else "No PII detected"
        ),
        "pii_found": pii_count,
        "warnings": [],
        "waste_warnings": [],
        "products": [],
    })


@app.route("/health")
def health():
    """Simple endpoint for checking whether Flask is running."""
    return jsonify({"status": "ok"})


if __name__ == "__main__":
    app.run(debug=True)
