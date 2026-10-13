
from flask import Flask, render_template, request, jsonify
import re
import logging

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
    """Redact common types of personal information."""
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


def error_response(message, status=500):
    """Return a consistent JSON error response."""
    return jsonify({
        "error": message,
        "response": message,
        "reply": message,
        "products": [],
    }), status


@app.route("/")
def index():
    """Render the main application page."""
    return render_template("index.html")


@app.route("/analyze", methods=["POST"])
def analyze():
    """Return a refined version of the supplied prompt."""
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
    """Process messages using VerityAI and preserve the API response format."""
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
        # Call your existing AI pipeline instead of returning a demo echo.
        result = VerityAI.handle(safe_message)

        # Support pipelines that return either a string or a dictionary.
        if isinstance(result, str):
            answer = result
            products = []
            pipeline_warnings = []
        elif isinstance(result, dict):
            answer = (
                result.get("response")
                or result.get("reply")
                or result.get("answer")
                or result.get("message")
                or ""
            )
            products = result.get("products") or []
            pipeline_warnings = (
                result.get("warnings")
                or result.get("waste_warnings")
                or []
            )

            if not isinstance(answer, str):
                answer = str(answer)

            if not isinstance(products, list):
                # Some pipelines wrap product results in an "items" field.
                if isinstance(products, dict):
                    products = products.get("items", [])
                else:
                    products = []

            if not isinstance(pipeline_warnings, list):
                pipeline_warnings = [str(pipeline_warnings)]
        else:
            logger.error(
                "Unexpected pipeline result type: %s",
                type(result).__name__,
            )
            return error_response(
                "The AI pipeline returned an unsupported response format.",
                502,
            )

        if not answer and not products:
            answer = "The AI pipeline returned an empty response."

        tokens = estimate_tokens(safe_message) + estimate_tokens(answer)
        token_percent = min(100, tokens / MAX_TOKENS * 100)

        return jsonify({
            "response": answer,
            "reply": answer,
            "safe_message": safe_message,
            "tokens": tokens,
            "token_percent": round(token_percent, 6),
            "cost": round(tokens * 0.000001, 8),
            "pii": (
                f"{pii_count} item(s) redacted"
                if pii_count
                else "No PII detected"
            ),
            "pii_found": pii_count,
            "warnings": pipeline_warnings,
            "waste_warnings": pipeline_warnings,
            "products": products,
        })

    except Exception:
        logger.exception("Error processing /chat request")
        return error_response(
            "Sorry, Verity AI could not process that request. "
            "Check the application logs for details.",
            500,
        )


@app.route("/health")
def health():
    """Check whether Flask is running."""
    return jsonify({"status": "ok"})


if __name__ == "__main__":
    app.run(debug=False)
