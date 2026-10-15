import logging
import re
import threading
import time
import uuid
from collections import OrderedDict

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
MAX_SESSIONS = 500
SESSION_TTL = 60 * 60 * 24  # 24 hours
sessions = OrderedDict()
sessions_lock = threading.RLock()


class ChatSession:
    """One AI instance, including context and history, per browser conversation."""

    def __init__(self):
        self.bot = VerityAI()
        self.lock = threading.RLock()
        self.last_access = time.time()


def _get_chat_id(data):
    chat_id = data.get("chat_id") or data.get("session_id")
    if not isinstance(chat_id, str):
        chat_id = ""
    chat_id = chat_id.strip()[:128]
    return chat_id or str(uuid.uuid4())


def _get_session(chat_id):
    now = time.time()
    with sessions_lock:
        expired = [key for key, value in sessions.items()
                   if now - value.last_access > SESSION_TTL]
        for key in expired:
            sessions.pop(key, None)

        chat = sessions.get(chat_id)
        if chat is not None:
            chat.last_access = now
            sessions.move_to_end(chat_id)
            return chat

        while len(sessions) >= MAX_SESSIONS:
            sessions.popitem(last=False)
        chat = ChatSession()
        sessions[chat_id] = chat
        return chat


def estimate_tokens(text: str) -> int:
    """Estimate token usage; this is not an exact tokenizer."""
    return max(1, len(text) // 4)


def redact(text: str):
    """Basic PII redaction for email, Indian PAN, and Indian phone numbers."""
    count = 0
    patterns = [
        (r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", "[EMAIL REDACTED]"),
        (r"\b[A-Z]{5}[0-9]{4}[A-Z]\b", "[PAN REDACTED]"),
        (r"(?<!\d)(?:\+?91[\s-]?)?[6-9]\d{9}(?!\d)", "[PHONE REDACTED]"),
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
    if not isinstance(data, dict):
        return jsonify({"error": "Invalid request"}), 400
    message = data.get("message") or ""
    if not isinstance(message, str):
        return jsonify({"error": "Message must be text"}), 400
    message = message.strip()
    if not message:
        return jsonify({"error": "Empty message"}), 400

    chat_id = _get_chat_id(data)
    pii_protection = data.get("pii_protection", True) is True
    context_lock = data.get("context_lock", True) is True
    token_manager = data.get("token_manager", True) is True
    gender_filter = data.get("gender_filter", "")
    if not isinstance(gender_filter, str):
        gender_filter = ""
    message = message[:10000]

    try:
        session = _get_session(chat_id)
        with session.lock:
            session.last_access = time.time()
            result = session.bot.handle(
                message,
                pii_protection=pii_protection,
                context_lock=context_lock,
                token_manager=token_manager,
                gender_filter=gender_filter,
            )

        if isinstance(result, dict):
            answer = result.get("response") or result.get("reply") or result.get("answer") or ""
            safe_message = result.get("safe_message", message)
            pii_count = len(result.get("pii_found") or [])
            context_state = result.get("filters") or {}
            filter_changes = result.get("filter_changes") or []
            shopping_active = result.get("shopping_active", False) is True
            token_metrics = result.get("tokens")
            products = normalize_products(result.get("products", []))
            warnings = result.get("warnings", [])
            waste_warnings = result.get("waste_warnings", [])
        elif isinstance(result, str):
            answer, products, warnings, waste_warnings = result, [], [], []
            safe_message, pii_count = message, 0
            context_state = {}
            filter_changes = []
            shopping_active = False
            token_metrics = None
        else:
            logger.error("Unexpected VerityAI.handle result type: %s", type(result).__name__)
            return jsonify({"error": "The AI pipeline returned an unexpected response."}), 500

        if not answer:
            answer = "I couldn't generate a response. Please try again."
        token_percent = (
            token_metrics.get("usage_percent")
            if isinstance(token_metrics, dict)
            else None
        )
        session_cost = (
            token_metrics.get("cost_inr")
            if isinstance(token_metrics, dict)
            else None
        )
        if not pii_protection:
            pii_status = "Protection disabled"
        elif pii_count:
            pii_status = f"Protected {pii_count} PII item(s)"
        else:
            pii_status = "Protection on — no PII detected"
        return jsonify({
            "response": answer,
            "reply": answer,
            "safe_message": safe_message,
            "chat_id": chat_id,
            "tokens": token_metrics if token_manager else None,
            "token_percent": token_percent if token_manager else None,
            "cost": session_cost if token_manager else None,
            "pii": f"{pii_count} item(s) redacted" if pii_count else "No PII detected",
            "pii_found": pii_count,
            "pii_status": pii_status,
            "context_state": context_state,
            "context_active": bool(context_lock and context_state),
            "filter_changes": filter_changes,
            "shopping_active": shopping_active,
            "features": {
                "pii_protection": pii_protection,
                "context_lock": context_lock,
                "token_manager": token_manager,
            },
            "warnings": warnings,
            "waste_warnings": waste_warnings,
            "products": products,
        })
    except Exception:
        logger.exception("Error processing /chat request")
        return jsonify({"error": "The request could not be processed. Check the server logs."}), 500


@app.route("/health")
def health():
    return jsonify({"status": "ok"})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)
