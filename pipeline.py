"""
Verity AI Pipeline

General-purpose chatbot with optional shopping search.

Flow:
    User message
        -> PII redaction
        -> Decide whether this is a shopping request
        -> Update shopping context only for shopping turns
        -> Search products only for shopping turns
        -> Generate a natural response
        -> Return chat, privacy, token, and product data
"""

import os
import re
import requests

from pii_redactor import redact
from contextlock import ContextLock
from token_tracker import TokenBudgetTracker
from product_search import search_products


GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"

MODEL = os.getenv("GROQ_MODEL", "openai/gpt-oss-120b")
CONTEXT_LIMIT = int(os.getenv("CONTEXT_LIMIT", "131072"))

# Cost in rupees per 1 million tokens. Adjust to the model's actual pricing.
INPUT_COST_INR_PER_M = float(os.getenv("INPUT_COST_INR_PER_M", "13.2"))
OUTPUT_COST_INR_PER_M = float(os.getenv("OUTPUT_COST_INR_PER_M", "52.8"))



BASE_SYSTEM = """
You are Verity AI, a friendly, intelligent, general-purpose AI assistant.

Talk naturally, like a helpful human conversational assistant.
Answer the user's actual question directly.

You can explain concepts, answer general questions, help with writing,
coding, learning, brainstorming, and everyday tasks.

Do not assume every message is about shopping.
Only use product search when the user wants to find, buy, compare,
or get recommendations for products.

Keep simple answers concise. For complex questions, provide enough
detail to be useful without overwhelming the user.

Use plain, readable language. Avoid unnecessary headings, tables,
long numbered lists, excessive bullet points, and decorative formatting.
Use Markdown only when it genuinely improves readability.

Do not force every answer into a fixed format or length.
Do not mention internal filters, ContextLock, or system instructions.
Be accurate, conversational, and transparent when uncertain.
"""



SHOPPING_SYSTEM = """
The current message is a shopping request or a follow-up to one.

Use the supplied shopping context when it is relevant. Do not invent
missing product requirements, product names, prices, or search results.

The application displays verified matching products separately from the
chat reply. Respond naturally to the user's message. If no verified
matching products were found, explain that only when relevant; do not
claim that products were found when the results are empty.
"""


# Explicit phrases are preferred so that ordinary mentions of products
# do not automatically turn every conversation into shopping.
SHOPPING_INTENT_PATTERN = re.compile(
    r"\b("
    r"find me|find|search for|look for|looking for|shop for|shopping for|"
    r"buy|purchase|order|recommend|suggest|compare|"
    r"show me|show|list products|product search|"
    r"where can i buy|where to buy|"
    r"price of|cost of|how much is|how much does|"
    r"under ₹?\s*\d|below ₹?\s*\d|over ₹?\s*\d|above ₹?\s*\d|"
    r"cheapest|best deal|"
    r"kurta|saree|sari|t shirt|t-shirt|shirt|jeans|trousers|"
    r"shoes|sneakers|dress|jacket|coat|laptop|smartphone|mobile phone|"
    r"headphones|earbuds|smartwatch|watch|handbag|backpack|"
    r"books|book|chair|sofa|fridge|refrigerator|"
    r"washing machine|camera|tablet|sunglasses"
    r")\b",
    re.IGNORECASE,
)

# These phrases only count as shopping follow-ups when there is an existing
# shopping category in ContextLock. This helps "make it shorter" or
# "tell me more" remain normal conversation.
SHOPPING_FOLLOWUP_PATTERN = re.compile(
    r"\b("
    r"cheaper|more expensive|lower price|higher price|"
    r"under ₹?\s*\d|below ₹?\s*\d|over ₹?\s*\d|above ₹?\s*\d|"
    r"show more|more options|other options|similar ones|"
    r"different color|another color|in red|in blue|"
    r"change the color|change the size|"
    r"same brand|another brand|"
    r"only show|filter by|remove the filter|"
    r"those products|these products|those ones|these ones"
    r")\b",
    re.IGNORECASE,
)


def _has_shopping_category(state):
    """Return True when ContextLock has a product category."""
    if not isinstance(state, dict):
        return False
    category = state.get("category")
    return isinstance(category, str) and bool(category.strip())


def is_shopping_request(message, shopping_state=None):
    """
    Basic shopping-intent detection.

    This is deliberately conservative, not a perfect language classifier.
    Explicit shopping terms can start a search. Short product queries such
    as "blue kurta" are also supported when a category word is present.
    Shopping refinements are recognized only when a prior category exists.
    """
    message = (message or "").strip()
    if not message:
        return False

    if SHOPPING_INTENT_PATTERN.search(message):
        return True

    if (
        _has_shopping_category(shopping_state)
        and SHOPPING_FOLLOWUP_PATTERN.search(message)
    ):
        return True

    # Support compact searches such as "blue kurta" or "Nike shoes"
    # without requiring the user to type "find" or "show me".
    category_words = re.compile(
        r"\b("
        r"kurta|saree|sari|shirt|jeans|trousers|shoes|sneakers|dress|"
        r"jacket|coat|laptop|smartphone|headphones|earbuds|smartwatch|"
        r"watch|handbag|backpack|book|chair|sofa|camera|tablet|"
        r"sunglasses|fridge|refrigerator|"
        r"washing machine"
        r")\b",
        re.IGNORECASE,
    )
    return len(message) <= 100 and bool(category_words.search(message))


def call_llm(system, history, user_message):
    """Return (reply_text, usage_dict_or_None)."""
    key = os.getenv("GROQ_API_KEY")

    if not key:
        return (
            "The chatbot is not connected to the AI service yet. "
            "Please configure GROQ_API_KEY.",
            None,
        )

    messages = [{"role": "system", "content": system}]
    messages.extend(history)
    messages.append({"role": "user", "content": user_message})

    try:
        response = requests.post(
            GROQ_URL,
            headers={
                "Authorization": f"Bearer {key}",
                "Content-Type": "application/json",
            },
            json={
                "model": MODEL,
                "temperature": 0.5,
                "messages": messages,
            },
            timeout=30,
        )

        if response.status_code == 429:
            return (
                "The AI service is temporarily busy. Please try again.",
                None,
            )

        if response.status_code != 200:
            # Avoid returning provider response bodies, which may contain
            # implementation details or request information.
            return f"AI service error ({response.status_code}).", None

        data = response.json()
        reply = (
            data.get("choices", [{}])[0]
            .get("message", {})
            .get("content")
            or ""
        ).strip()

        if not reply:
            reply = "Sorry, I couldn't generate a response. Please try again."

        return reply, data.get("usage")

    except requests.RequestException:
        return (
            "I couldn't reach the AI service right now. Please try again.",
            None,
        )
    except (ValueError, KeyError, IndexError, TypeError):
        return (
            "I received an unexpected response from the AI service. "
            "Please try again.",
            None,
        )


def _breakdown_total(breakdown):
    """Read a token total defensively from different tracker result shapes."""
    if isinstance(breakdown, (int, float)) and not isinstance(breakdown, bool):
        return int(breakdown)

    if isinstance(breakdown, dict):
        for key in ("total", "total_tokens", "tokens"):
            value = breakdown.get(key)
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                return int(value)

        numbers = [
            value
            for value in breakdown.values()
            if isinstance(value, (int, float)) and not isinstance(value, bool)
        ]
        return int(sum(numbers))

    return 0


class VerityAI:
    def __init__(self):
        self.lock = ContextLock()
        self.tracker = TokenBudgetTracker()
        self.history = []

        # Keep the last search available internally for shopping refinements.
        # It is returned to the frontend only on shopping turns.
        self.last_products = None
        self.session_cost_inr = 0.0

    def _build_tokens(self, after, usage):
        """Build token and estimated session-cost information for the UI."""
        if usage:
            prompt = int(usage.get("prompt_tokens") or 0)
            completion = int(usage.get("completion_tokens") or 0)
            total = int(usage.get("total_tokens") or (prompt + completion))

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

    def handle(self, raw_message):
        """Process one user message and return the response payload."""
        if not isinstance(raw_message, str):
            raw_message = ""

        # 1. Redact sensitive data before intent detection, context updates,
        # token tracking, conversation history, or sending text to the LLM.
        safe_message, pii_found = redact(raw_message)

        # 2. Decide whether this message belongs to a shopping interaction.
        # Inspect existing state before updating it, so ordinary chat does not
        # accidentally change persistent product filters.
        shopping_request = is_shopping_request(
            safe_message,
            self.lock.state,
        )

        filter_changes = []

        # 3. Only update ContextLock and search products for shopping turns.
        if shopping_request:
            self.lock.update(safe_message)
            filter_changes = list(self.lock.changes or [])

            # Search on each shopping turn so refinements can refresh results.
            self.last_products = search_products(self.lock.state)
            products = self.last_products
        else:
            # Do not expose stale products as results for unrelated chat.
            products = None

        # 4. Build a general-purpose prompt. Add shopping instructions and
        # filters only while handling a shopping request.
        system = BASE_SYSTEM

        if shopping_request:
            system += "\n\n" + SHOPPING_SYSTEM
            context_prompt = self.lock.to_prompt()
            if context_prompt:
                system += "\n\nCurrent shopping context:\n" + context_prompt

            if products is not None:
                item_count = len(products.get("items", []))
                if item_count:
                    system += (
                        f"\n\nSearch status: {item_count} verified matching "
                        "product(s) are included in the response payload and "
                        "may be displayed separately by the application."
                    )
                else:
                    note = products.get("note", "")
                    system += (
                        "\n\nSearch status: no verified matching products "
                        "were returned."
                    )
                    if note:
                        system += "\nSearch note: " + str(note)

        # 5. Token tracking.
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

        self.history = self.tracker.compress_history(self.history)

        after = self.tracker.breakdown(
            system,
            self.history,
            safe_message,
        )

        # 6. Generate a natural reply for both general chat and shopping.
        reply, usage = call_llm(system, self.history, safe_message)

        # 7. Save only redacted user text and the assistant response.
        self.history.append({"role": "user", "content": safe_message})
        self.history.append({"role": "assistant", "content": reply})

        # 8. Return fields expected by the existing dashboard/frontend.
        return {
            "reply": reply,
            "safe_message": safe_message,
            "pii_found": [
                {"type": item.get("type", "unknown")}
                for item in (pii_found or [])
            ],
            "filters": dict(self.lock.state),
            "filter_changes": filter_changes,
            "shopping_active": shopping_request,
            "tokens": self._build_tokens(after, usage),
            "tokens_before": before,
            "tokens_after": after,
            "waste_warnings": warnings,
            "products": products,
        }
