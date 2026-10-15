"""
Verity AI Pipeline

General-purpose chatbot with optional shopping search.

Flow:
    User message
        -> PII redaction
        -> Decide whether this is a shopping request
        -> Normalize common shopping follow-ups
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


GROQ_URL = os.getenv(
    "GROQ_URL",
    "https://api.groq.com/openai/v1/chat/completions",
)

MODEL = os.getenv("GROQ_MODEL", "openai/gpt-oss-120b")
CONTEXT_LIMIT = int(os.getenv("CONTEXT_LIMIT", "131072"))

# Estimated cost in rupees per 1 million tokens. Adjust to your provider pricing.
INPUT_COST_INR_PER_M = float(os.getenv("INPUT_COST_INR_PER_M", "13.2"))
OUTPUT_COST_INR_PER_M = float(os.getenv("OUTPUT_COST_INR_PER_M", "52.8"))


BASE_SYSTEM = """
You are Verity AI, a friendly, natural, general-purpose AI assistant.

Respond directly to what the user asks. Sound conversational and human,
not like a formal report or an article.

STYLE RULES:
- For simple requests, give a simple, direct answer.
- Avoid unnecessary introductions, headings, summaries, and follow-up offers.
- Use plain text by default.
- Use Markdown only when it genuinely improves readability.
- Match the length of the answer to the user's request.
- Help with general questions, writing, learning, coding, ideas, and everyday tasks.
- Only search for products when the user asks to find, buy, compare, or get recommendations.
- Use the conversation history when resolving short follow-up messages.
- Never claim that products or prices were verified unless the product search returned them.
"""

SHOPPING_SYSTEM = """
The user is shopping or following up on an existing shopping request.

Use the supplied shopping context and conversation history.
A short preference such as "I prefer blue ones" refers to the current product
category unless the user clearly changes the category.
Preserve existing constraints, including budget, brand, size, and category,
unless the user explicitly changes or removes them.
Never invent products, prices, search results, or product attributes.
The application may display matching products separately.
Respond naturally and directly. Do not add unnecessary introductions or headings.
If no matching products were found, explain that briefly when relevant.
"""


# Explicit product-shopping phrases that can start a search.
SHOPPING_INTENT_PATTERN = re.compile(
    r"\b("
    r"find me|find|search for|look for|looking for|shop for|shopping for|"
    r"buy|purchase|order|recommend|suggest|compare|"
    r"show me|show|list products|product search|"
    r"where can i buy|where to buy|"
    r"price of|cost of|how much is|how much does|"
    r"under ₹?\s*\d|below ₹?\s*\d|over ₹?\s*\d|above ₹?\s*\d|"
    r"cheapest|best deal|"
    r"kurta|saree|sari|t[\s-]?shirt|shirt|jeans|trousers|"
    r"running shoes|shoes|sneakers|dress|jacket|coat|laptop|"
    r"smartphone|mobile phone|headphones|earbuds|smartwatch|watch|"
    r"handbag|backpack|books|book|chair|sofa|fridge|refrigerator|"
    r"washing machine|camera|tablet|sunglasses"
    r")\b",
    re.IGNORECASE,
)

# These phrases are shopping follow-ups only if a shopping category already exists.
SHOPPING_FOLLOWUP_PATTERN = re.compile(
    r"\b("
    r"cheaper|more expensive|lower price|higher price|"
    r"under ₹?\s*\d|below ₹?\s*\d|over ₹?\s*\d|above ₹?\s*\d|"
    r"show more|more options|other options|similar ones|"
    r"different color|another color|"
    r"in red|in blue|in green|in black|in white|in pink|in yellow|"
    r"in brown|in grey|in gray|"
    r"change the color|change the size|"
    r"same brand|another brand|"
    r"only show|filter by|remove the filter|"
    r"those products|these products|those ones|these ones|"
    r"for men|for women|\bmen\b|\bwomen\b|men's|mens|women's|womens|unisex|male|female|"
    r"ladies|gents|"
    r"i prefer|i'd prefer|i would prefer|"
    r"i want|i'd like|i would like|"
    r"my preference is|"
    r"blue ones|red ones|green ones|black ones|white ones|pink ones|"
    r"yellow ones|brown ones|grey ones|gray ones|"
    r"make them|make it|"
    r"smaller size|larger size|bigger size|size \w+"
    r")\b",
    re.IGNORECASE,
)

COLOR_NAMES = (
    "red", "blue", "green", "black", "white", "pink", "yellow",
    "brown", "grey", "gray", "purple", "orange", "navy", "beige",
)


def _has_shopping_category(state):
    """Return True when ContextLock has a product category."""
    if not isinstance(state, dict):
        return False
    category = state.get("category")
    return isinstance(category, str) and bool(category.strip())


def normalize_shopping_followup(message):
    """
    Normalize common follow-up phrasing to simpler phrases that a context parser
    can recognize. For example, "I prefer blue ones" becomes "in blue".
    """
    text = (message or "").strip()

    color_pattern = re.compile(
        r"\b(?:i prefer|i'd prefer|i would prefer|"
        r"i want|i'd like|i would like|my preference is)\s+"
        r"(" + "|".join(map(re.escape, COLOR_NAMES)) + r")"
        r"(?:\s+(?:ones?|shoes?|items?|products?))?\b",
        re.IGNORECASE,
    )

    match = color_pattern.search(text)
    if match:
        color = match.group(1).lower()
        # Preserve other constraints in the same message, if present.
        text = color_pattern.sub(f"in {color}", text, count=1)

    return text


def is_shopping_request(message, shopping_state=None):
    """Detect explicit shopping requests and follow-ups to an active search."""
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

    # Compact queries such as "blue kurta" or "Nike shoes".
    category_words = re.compile(
        r"\b("
        r"kurta|saree|sari|t[\s-]?shirt|shirt|jeans|trousers|"
        r"running shoes|shoes|sneakers|dress|jacket|coat|laptop|"
        r"smartphone|headphones|earbuds|smartwatch|watch|handbag|"
        r"backpack|book|chair|sofa|camera|tablet|sunglasses|"
        r"fridge|refrigerator|washing machine"
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
            return f"AI service error ({response.status_code}).", None

        data = response.json()
        choices = data.get("choices", [])
        reply = (
            choices[0].get("message", {}).get("content") or ""
            if choices else ""
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
        self.last_products = None
        self.session_cost_inr = 0.0

    def _build_tokens(self, after, usage):
        """Report this request's context-window use and cumulative session cost."""
        if usage:
            prompt = int(usage.get("prompt_tokens") or 0)
            completion = int(usage.get("completion_tokens") or 0)
            # Context occupancy is the prompt (system + conversation history +
            # current user message). Completion tokens are not part of the
            # prompt's context usage, so don't add them to the context meter.
            context_tokens = prompt or int(after.get("total", 0))

            self.session_cost_inr += (
                prompt * INPUT_COST_INR_PER_M / 1_000_000
                + completion * OUTPUT_COST_INR_PER_M / 1_000_000
            )
        else:
            prompt = _breakdown_total(after)
            completion = 0
            context_tokens = prompt

        percent = (context_tokens / CONTEXT_LIMIT * 100) if CONTEXT_LIMIT else 0

        return {
            "total": int(context_tokens),
            "context_tokens": int(context_tokens),
            "input_tokens": int(prompt),
            "output_tokens": int(completion),
            "context_limit": CONTEXT_LIMIT,
            "usage_percent": round(percent, 4),
            "cost_inr": round(self.session_cost_inr, 6),
        }

    def handle(
        self,
        raw_message,
        pii_protection=True,
        context_lock=True,
        token_manager=True,
        gender_filter=None,
    ):
        """Process one user message and return the response payload."""
        if not isinstance(raw_message, str):
            raw_message = ""

        # Redact before intent detection, context updates, history, and LLM use
        # only when the user has enabled the privacy filter.
        if pii_protection:
            safe_message, pii_found = redact(raw_message)
        else:
            safe_message, pii_found = raw_message, []

        # Normalize follow-ups such as "I prefer blue ones" into a phrase
        # that ContextLock can extract, e.g. "in blue".
        context_message = normalize_shopping_followup(safe_message)

        # Detect follow-ups against the existing context BEFORE updating it.
        shopping_state = self.lock.state if context_lock else {}
        shopping_request = is_shopping_request(context_message, shopping_state)
        gender_filter = str(gender_filter or "").strip().lower()
        if gender_filter not in {"", "all", "men", "women", "unisex"}:
            gender_filter = ""

        # Always define these so the response payload works for non-shopping turns.
        filter_changes = []
        products = None

        if shopping_request and context_lock:
            # Update the context exactly once, preserving existing constraints.
            self.lock.update(context_message)
            if gender_filter == "all":
                self.lock._apply({"set": {}, "remove": ["gender"]})
            elif gender_filter:
                self.lock._apply({"set": {"gender": gender_filter}, "remove": []})
            filter_changes = list(self.lock.changes or [])

            # Optional debugging; remove these lines after testing.
            print("DEBUG shopping_request:", shopping_request)
            print("DEBUG shopping_state:", self.lock.state)

            # Search again after each shopping request or refinement.
            self.last_products = search_products(self.lock.state)
            products = self.last_products
        elif shopping_request:
            # With Context Lock off, search this request only. Do not retain or
            # apply constraints from prior shopping turns.
            self.lock.changes = []
            request_context = ContextLock()
            request_context.update(context_message)
            if gender_filter == "all":
                request_context._apply({"set": {}, "remove": ["gender"]})
            elif gender_filter:
                request_context._apply({"set": {"gender": gender_filter}, "remove": []})
            self.last_products = search_products(request_context.state)
            products = self.last_products

        system = BASE_SYSTEM

        if shopping_request:
            system += "\n\n" + SHOPPING_SYSTEM
            if context_lock:
                context_prompt = self.lock.to_prompt()
            else:
                context_prompt = request_context.to_prompt()

            if context_prompt:
                system += "\n\nCurrent shopping context:\n" + context_prompt

            if products is not None:
                items = (
                    products.get("items", [])
                    if isinstance(products, dict)
                    else []
                )
                item_count = len(items)

                if item_count:
                    system += (
                        f"\n\nSearch status: {item_count} matching product(s) "
                        "were returned by the product search and may be shown "
                        "separately by the application. Do not invent details "
                        "that are not in the supplied shopping context."
                    )
                else:
                    note = (
                        products.get("note", "")
                        if isinstance(products, dict)
                        else ""
                    )
                    system += (
                        "\n\nSearch status: no matching products were returned."
                    )
                    if note:
                        system += "\nSearch note: " + str(note)

        # Estimate tokens and compress history before constructing the LLM call.
        before = self.tracker.breakdown(
            system,
            self.history,
            safe_message,
        )
        warnings = (
            self.tracker.find_waste(system, self.history, before)
            if token_manager
            else []
        )

        self.history = self.tracker.compress_history(self.history)

        after = self.tracker.breakdown(
            system,
            self.history,
            safe_message,
        )

        reply, usage = call_llm(system, self.history, safe_message)

        # Store only redacted messages. History persists while server.py
        # reuses this VerityAI instance for the same chat/session ID.
        self.history.append({"role": "user", "content": safe_message})
        self.history.append({"role": "assistant", "content": reply})

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
            "tokens": self._build_tokens(after, usage) if token_manager else None,
            "tokens_before": before,
            "tokens_after": after,
            "waste_warnings": warnings,
            "products": products,
        }
