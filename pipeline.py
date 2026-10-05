"""
Verity AI Pipeline

Flow:

User message
    ↓
PII redaction
    ↓
ContextLock / AI understanding
    ↓
Sticky shopping context
    ↓
Strict product search
    ↓
Chatbot response
"""

import os
import requests

from pii_redactor import redact
from contextlock import ContextLock
from token_tracker import TokenBudgetTracker
from product_search import search_products


GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"

MODEL = os.getenv(
    "GROQ_MODEL",
    "openai/gpt-oss-120b",
)

CONTEXT_LIMIT = int(os.getenv("CONTEXT_LIMIT", "131072"))

# Cost in rupees per 1 million tokens. Adjust to your model's real pricing.
# Defaults: $0.15 input / $0.60 output at roughly Rs 88 per USD.
INPUT_COST_INR_PER_M = float(os.getenv("INPUT_COST_INR_PER_M", "13.2"))
OUTPUT_COST_INR_PER_M = float(os.getenv("OUTPUT_COST_INR_PER_M", "52.8"))


BASE_SYSTEM = """
You are Verity AI, a friendly shopping assistant.

Reply naturally like a real chatbot.

Keep replies short: at most 2 short sentences.

Do not use tables.

Do not use markdown.

Do not invent product names or prices.

The application separately displays the actual matching products.

If matching products were found, simply acknowledge the request
and tell the user that the matching products are shown below.

If no products were found, politely explain that no verified
matching products were found.

IMPORTANT:

The current shopping context is supplied separately.

Do not override the shopping context yourself.

Do not invent missing product requirements.
"""


def call_llm(system, history, user_message):
    """Returns (reply_text, usage_dict_or_None)."""

    key = os.getenv("GROQ_API_KEY")

    if not key:
        return (
            "I understood your request. "
            "Add GROQ_API_KEY to enable the AI chatbot.",
            None,
        )

    messages = [
        {
            "role": "system",
            "content": system,
        }
    ]

    messages.extend(history)

    messages.append({
        "role": "user",
        "content": user_message,
    })

    try:

        response = requests.post(
            GROQ_URL,
            headers={
                "Authorization": f"Bearer {key}",
                "Content-Type": "application/json",
            },
            json={
                "model": MODEL,
                "temperature": 0.3,
                "messages": messages,
            },
            timeout=30,
        )

        if response.status_code == 429:
            return (
                "The AI service is temporarily busy. "
                "Please try again.",
                None,
            )

        if response.status_code != 200:
            return (
                f"AI service error {response.status_code}.",
                None,
            )

        data = response.json()

        reply = (
            data["choices"][0]["message"].get("content") or ""
        ).strip()

        # FIX: some models can return an empty message.
        if not reply:
            reply = "Here is what I found for you."

        usage = data.get("usage")

        return reply, usage

    except Exception:
        return (
            "I couldn't reach the AI service right now.",
            None,
        )


def _breakdown_total(breakdown):
    """
    token_tracker.py wasn't shared, so read its result defensively.
    Accepts a number or a dict with a total-like key.
    """

    if isinstance(breakdown, (int, float)):
        return int(breakdown)

    if isinstance(breakdown, dict):

        for key in ("total", "total_tokens", "tokens"):
            value = breakdown.get(key)

            if isinstance(value, (int, float)):
                return int(value)

        numbers = [
            v for v in breakdown.values()
            if isinstance(v, (int, float)) and not isinstance(v, bool)
        ]

        return int(sum(numbers))

    return 0


class VerityAI:

    def __init__(self):

        self.lock = ContextLock()

        self.tracker = TokenBudgetTracker()

        self.history = []

        # FIX: remember the last search so follow-ups like "thanks"
        # don't make the product list vanish.
        self.last_products = None

        self.session_cost_inr = 0.0

    # -----------------------------------------------------
    # TOKEN INFO FOR THE DASHBOARD
    # -----------------------------------------------------

    def _build_tokens(self, after, usage):
        """
        FIX: the frontend reads data.tokens
        (total, context_limit, usage_percent, cost_inr),
        but the backend never sent it.
        """

        if usage:
            prompt = usage.get("prompt_tokens") or 0
            completion = usage.get("completion_tokens") or 0

            total = usage.get("total_tokens") or (prompt + completion)

            self.session_cost_inr += (
                prompt * INPUT_COST_INR_PER_M / 1_000_000
                + completion * OUTPUT_COST_INR_PER_M / 1_000_000
            )
        else:
            total = _breakdown_total(after)

        percent = (total / CONTEXT_LIMIT * 100) if CONTEXT_LIMIT else 0

        return {
            "total": int(total),
            "context_limit": CONTEXT_LIMIT,
            "usage_percent": round(percent, 4),
            "cost_inr": round(self.session_cost_inr, 6),
        }

    # -----------------------------------------------------
    # MAIN ENTRY
    # -----------------------------------------------------

    def handle(self, raw_message):

        # -------------------------------------------------
        # 1. Protect PII
        # -------------------------------------------------

        safe_message, pii_found = redact(
            raw_message
        )

        # -------------------------------------------------
        # 2. Understand the latest message
        # -------------------------------------------------

        self.lock.update(
            safe_message
        )

        # -------------------------------------------------
        # 3. Search using CURRENT complete context
        # -------------------------------------------------

        if self.lock.changes:
            self.last_products = search_products(
                self.lock.state
            )

        products = self.last_products

        # -------------------------------------------------
        # 4. Build chatbot context
        # -------------------------------------------------

        system = BASE_SYSTEM

        context_prompt = self.lock.to_prompt()

        if context_prompt:
            system += "\n\n" + context_prompt

        # FIX: the chatbot was never told whether products were found,
        # yet its instructions depend on it.
        if products is not None:

            if products.get("items"):
                system += (
                    "\n\nSearch result: "
                    f"{len(products['items'])} verified matching products "
                    "were found and are displayed below the chat."
                )
            else:
                system += (
                    "\n\nSearch result: no verified matching products "
                    "were found."
                )

        # -------------------------------------------------
        # 5. Token tracking
        # -------------------------------------------------

        before = self.tracker.breakdown(
            system,
            self.history,
            safe_message,
        )

        warnings = self.tracker.find_waste(
            system,
            self.history,
            before,
        )

        self.history = (
            self.tracker.compress_history(
                self.history
            )
        )

        after = self.tracker.breakdown(
            system,
            self.history,
            safe_message,
        )

        # -------------------------------------------------
        # 6. Generate natural chatbot response
        # -------------------------------------------------

        # FIX: call_llm returns (reply, usage). Before, the whole tuple
        # was stored in history, which broke the next API call.
        reply, usage = call_llm(
            system,
            self.history,
            safe_message,
        )

        # -------------------------------------------------
        # 7. Save conversation
        # -------------------------------------------------

        self.history.append({
            "role": "user",
            "content": safe_message,
        })

        self.history.append({
            "role": "assistant",
            "content": reply,
        })

        # -------------------------------------------------
        # 8. Send everything to frontend
        # -------------------------------------------------

        return {
            "reply": reply,

            "safe_message": safe_message,

            "pii_found": [
                {
                    "type": p["type"]
                }
                for p in pii_found
            ],

            "filters": dict(
                self.lock.state
            ),

            "filter_changes": list(
                self.lock.changes
            ),

            "tokens": self._build_tokens(after, usage),

            "tokens_before": before,

            "tokens_after": after,

            "waste_warnings": warnings,

            "products": products,
        }