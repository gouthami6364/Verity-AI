
import logging
import re

from flask import Flask, render_template, request, jsonify
from pipeline import VerityAI

app = Flask(
    __name__,
    static_folder="static",
    static_url_path="/static",
    template_folder="templates",
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

MAX_TOKENS = 131072


def estimate_tokens(text: str) -> int:
    """Estimate token usage; this is not an exact tokenizer."""
    return max(1, len(text) // 4)


def redact(text: str):
    """Basic PII redaction for email, Indian PAN, and Indian phone numbers."""
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


def normalize_products(products):
    """Normalize product results for the frontend."""
    if products is None:
        return []

    if isinstance(products, list):
        return products

    if isinstance(products, dict):
        items = products.get("items")
        if isinstance(items, list):
            return items

        # Some pipelines return a single product as a dictionary.
        if any(key in products for key in ("title", "name", "link", "url")):
            return [products]

    return []


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

    pii_protection = data.get("pii_protection", True)

    if pii_protection:
        safe_message, pii_count = redact(message)
    else:
        safe_message, pii_count = message, 0

    try:
        # Pass both arguments required by VerityAI.handle().
        result = VerityAI.handle(safe_message, message)

        if isinstance(result, dict):
            answer = (
                result.get("response")
                or result.get("reply")
                or result.get("answer")
                or ""
            )
            products = normalize_products(result.get("products", []))
            warnings = result.get("warnings", [])
            waste_warnings = result.get("waste_warnings", [])
        elif isinstance(result, str):
            answer = result
            products = []
            warnings = []
            waste_warnings = []
        else:
            logger.error(
                "Unexpected VerityAI.handle result type: %s",
                type(result).__name__,
            )
            return jsonify({
                "error": "The AI pipeline returned an unexpected response."
            }), 500

        if not answer:
            answer = "I couldn't generate a response. Please try again."

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
            "warnings": warnings,
            "waste_warnings": waste_warnings,
            "products": products,
        })

    except Exception:
        logger.exception("Error processing /chat request")
        return jsonify({
            "error": "The request could not be processed. Check the server logs."
        }), 500


@app.route("/health")
def health():
    return jsonify({"status": "ok"})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)
