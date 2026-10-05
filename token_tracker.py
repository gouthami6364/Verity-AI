"""
Token Tracker
-------------
Tracks actual/estimated token usage and prompt quality.

The actual Groq API usage is supplied by pipeline.py.

GPT-OSS 120B:
    Input:  $0.15 / 1M tokens
    Output: $0.60 / 1M tokens

The USD -> INR rate can be supplied with:

    USD_TO_INR=90

or fetched from a free exchange-rate endpoint.
"""

import os
import re
import time
import requests


MODEL_CONTEXT = 131072

INPUT_PRICE_USD_PER_1M = 0.15
OUTPUT_PRICE_USD_PER_1M = 0.60

FALLBACK_USD_TO_INR = 90.0

_exchange_cache = {
    "rate": None,
    "expires": 0.0,
}


def get_usd_to_inr():

    # Allow manual override.
    manual = os.getenv("USD_TO_INR")

    if manual:
        try:
            value = float(manual)
            if value > 0:
                return value
        except Exception:
            pass

    # Use the cached rate while it is still fresh.
    now = time.time()

    if (
        _exchange_cache["rate"] is not None
        and now < _exchange_cache["expires"]
    ):
        return _exchange_cache["rate"]

    rate = None

    try:

        response = requests.get(
            "https://api.frankfurter.app/latest",
            params={
                "from": "USD",
                "to": "INR",
            },
            timeout=5,
        )

        if response.status_code == 200:
            rate = float(response.json()["rates"]["INR"])

    except Exception:
        rate = None

    if rate is not None:
        # Good rate: cache for one hour.
        _exchange_cache["rate"] = rate
        _exchange_cache["expires"] = now + 3600
        return rate

    # FIX: the old code did NOT cache failures, so with no internet
    # every call waited for the 5 second timeout (twice per message).
    # Now the fallback is cached for 5 minutes before retrying.
    fallback = _exchange_cache["rate"] or FALLBACK_USD_TO_INR

    _exchange_cache["rate"] = fallback
    _exchange_cache["expires"] = now + 300

    return fallback


def _to_int(value):
    # FIX: int(None) raised TypeError when Groq returned null.
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


class TokenBudgetTracker:

    def __init__(self):

        self.total_input_tokens = 0
        self.total_output_tokens = 0
        self.total_tokens = 0

    # ---------------------------------------------------------
    # COST HELPER (the same maths was copy-pasted twice before)
    # ---------------------------------------------------------

    def _cost(self, input_tokens, output_tokens):

        usd_to_inr = get_usd_to_inr()

        input_cost_usd = (
            input_tokens / 1_000_000
        ) * INPUT_PRICE_USD_PER_1M

        output_cost_usd = (
            output_tokens / 1_000_000
        ) * OUTPUT_PRICE_USD_PER_1M

        total_cost_usd = input_cost_usd + output_cost_usd

        return {
            "input_cost_usd": input_cost_usd,
            "output_cost_usd": output_cost_usd,
            "estimated_cost_usd": total_cost_usd,

            "input_cost_inr": input_cost_usd * usd_to_inr,
            "output_cost_inr": output_cost_usd * usd_to_inr,
            "cost_inr": total_cost_usd * usd_to_inr,

            "usd_to_inr": usd_to_inr,
        }

    # ---------------------------------------------------------
    # ESTIMATION
    # ---------------------------------------------------------

    def estimate_text_tokens(self, text):

        if not text:
            return 0

        # Rough estimation for live typing.
        # Actual Groq token counts are used after the request.
        return max(1, round(len(text) / 4))

    def breakdown(
        self,
        system,
        history,
        user_message,
    ):

        text = system or ""

        for message in history:
            text += " " + str(message.get("content", ""))

        text += " " + str(user_message or "")

        estimated = self.estimate_text_tokens(text)

        return {
            "input_estimated": estimated,
            "output_estimated": 0,
            "total": estimated,
            "context_limit": MODEL_CONTEXT,
            "usage_percent": round(
                (estimated / MODEL_CONTEXT) * 100,
                4,
            ),
        }

    # ---------------------------------------------------------
    # ACTUAL GROQ USAGE
    # ---------------------------------------------------------

    def record_actual_usage(self, usage):
        """
        Records one request. The returned dict describes THIS request
        (its size = how full the context window is). Use current()
        for session totals.
        """

        if not usage:
            return self.current()

        input_tokens = _to_int(usage.get("prompt_tokens"))
        output_tokens = _to_int(usage.get("completion_tokens"))

        total_tokens = (
            _to_int(usage.get("total_tokens"))
            or (input_tokens + output_tokens)
        )

        self.total_input_tokens += input_tokens
        self.total_output_tokens += output_tokens
        self.total_tokens += total_tokens

        result = {
            "input": input_tokens,
            "output": output_tokens,
            "total": total_tokens,

            "context_limit": MODEL_CONTEXT,

            "usage_percent": round(
                (total_tokens / MODEL_CONTEXT) * 100,
                4,
            ),
        }

        result.update(self._cost(input_tokens, output_tokens))

        return result

    # ---------------------------------------------------------
    # CURRENT SESSION TOTALS
    # ---------------------------------------------------------

    def current(self):

        result = {
            "input": self.total_input_tokens,
            "output": self.total_output_tokens,
            "total": self.total_tokens,

            "context_limit": MODEL_CONTEXT,

            "usage_percent": round(
                (self.total_tokens / MODEL_CONTEXT) * 100,
                4,
            ),
        }

        result.update(
            self._cost(
                self.total_input_tokens,
                self.total_output_tokens,
            )
        )

        return result

    # ---------------------------------------------------------
    # PROMPT WASTE WARNINGS
    # ---------------------------------------------------------

    def find_waste(
        self,
        system,
        history,
        current_message,
    ):
        """
        current_message must be the user's text.
        (pipeline.py used to pass the token breakdown dict here.)
        """

        warnings = []

        text = str(current_message or "").strip()

        if not text:
            return warnings

        # Very long user message.
        if len(text) > 2000:
            warnings.append(
                "Prompt is long. Remove unnecessary details."
            )

        # Repeated words.
        words = re.findall(
            r"\b[a-zA-Z]{3,}\b",
            text.lower(),
        )

        if words:

            counts = {}

            for word in words:
                counts[word] = counts.get(word, 0) + 1

            repeated = [
                word
                for word, count in counts.items()
                if count >= 5
            ]

            if repeated:
                warnings.append(
                    "Repeated words detected: "
                    + ", ".join(repeated[:3])
                )

        # FIX: short messages are normal AFTER the first one
        # ("make it black", "under 3000"). Only warn on the opener.
        if not history and len(text.split()) <= 2:
            warnings.append(
                "Add more detail such as product type, "
                "color, brand or budget."
            )

        # Contradiction detection.
        lowered = text.lower()

        if "cheap" in lowered and "expensive" in lowered:
            warnings.append(
                "The prompt contains conflicting requirements."
            )

        return warnings

    # ---------------------------------------------------------
    # HISTORY COMPRESSION
    # ---------------------------------------------------------

    def compress_history(self, history):

        # Keep the latest 12 messages.
        if len(history) <= 12:
            return history

        trimmed = history[-12:]

        # FIX: never start with an assistant message
        # (some APIs reject a conversation that opens that way).
        while trimmed and trimmed[0].get("role") != "user":
            trimmed = trimmed[1:]

        return trimmed