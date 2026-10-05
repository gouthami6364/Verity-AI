"""
ContextLock
-----------
Understands natural-language shopping requests and keeps the useful
constraints sticky across the conversation.

Examples:

"show me a blue kurta"
    -> category=kurta, color=blue

"make it black"
    -> category=kurta, color=black

"under 3000"
    -> category=kurta, color=black, max_price=3000

"actually levi's"
    -> category=kurta, color=black, brand=Levi's

"show me jeans instead"
    -> category=jeans, color=black, brand=Levi's, max_price=3000
"""

import json
import os
import re
import requests


GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
MODEL = os.getenv("GROQ_MODEL", "openai/gpt-oss-120b")

ALLOWED_FIELDS = {
    "category",
    "brand",
    "color",
    "material",
    "size",
    "min_price",
    "max_price",
}

NUMERIC_FIELDS = {"min_price", "max_price"}
LOWERCASE_FIELDS = {"category", "color", "material"}


PROMPT = """
You are the natural-language understanding layer of a shopping chatbot.

Read the user's latest message and extract ONLY shopping constraints
that are explicitly stated or clearly implied.

You are also given the CURRENT context so you know what already exists.
Only output what the latest message changes.

Return ONLY valid JSON.

Schema:

{
  "set": {
    "category": null,
    "brand": null,
    "color": null,
    "material": null,
    "size": null,
    "min_price": null,
    "max_price": null
  },
  "remove": []
}

Rules:

1. Do NOT invent constraints.

2. Categories are completely dynamic.
   There is NO fixed category list.

3. Brands are completely dynamic.
   There is NO fixed brand list.

4. Correct obvious spelling mistakes when the intended shopping
   product is clear.
   Example:
   "kurth" -> "kurta"
   "shooes" -> "shoes"

5. If the user says:
   "blue"
   only change color to blue.
   Do NOT remove the existing category.

6. If the user says:
   "make it black"
   change color to black.

7. If the user explicitly changes the product:
   "show me jeans instead"
   change category to jeans.

8. If the user explicitly changes the brand:
   "show Nike instead"
   change brand to Nike.

9. Keep existing constraints unchanged unless the latest message
   explicitly changes or removes them.

10. "under 3000", "below 3000", "less than 3000"
    means max_price = 3000.

11. "above 2000", "over 2000", "more than 2000"
    means min_price = 2000.

12. If the user says "remove the brand" or "no brand",
    put "brand" in remove.

13. Use plain values, not explanations. Prices are plain numbers.

14. If the message contains no shopping constraint, return:
{
  "set": {},
  "remove": []
}

Examples:

User: "blue kurta"
{
  "set": {
    "category": "kurta",
    "color": "blue"
  },
  "remove": []
}

User: "make it black"
{
  "set": {
    "color": "black"
  },
  "remove": []
}

User: "under 3000"
{
  "set": {
    "max_price": 3000
  },
  "remove": []
}

User: "show levi's"
{
  "set": {
    "brand": "Levi's"
  },
  "remove": []
}

User: "show jeans instead"
{
  "set": {
    "category": "jeans"
  },
  "remove": []
}

User: "remove the brand"
{
  "set": {},
  "remove": ["brand"]
}
"""


COLORS = [
    "black", "white", "blue", "red", "green", "yellow", "pink",
    "purple", "orange", "brown", "grey", "gray", "beige", "maroon", "navy",
]

# Words people use -> our field names
FIELD_ALIASES = {
    "brand": "brand",
    "color": "color",
    "colour": "color",
    "size": "size",
    "material": "material",
    "category": "category",
}


class ContextLock:

    def __init__(self):
        self.state = {}
        self.changes = []

    def update(self, message):
        self.changes = []

        extracted = self._extract(message)

        if not extracted:
            return self.state

        self._apply(extracted)

        return self.state

    # ---------------------------------------------------------
    # AI UNDERSTANDING
    # ---------------------------------------------------------

    def _extract(self, message):

        key = os.getenv("GROQ_API_KEY")

        if not key:
            return self._local_fallback(message)

        # FIX: the model now sees the current context, so messages like
        # "remove the colour" or "make it cheaper" can be understood.
        user_content = (
            "Current context: " + json.dumps(self.state, ensure_ascii=False)
            + "\nLatest message: " + message
        )

        try:
            response = requests.post(
                GROQ_URL,
                headers={
                    "Authorization": f"Bearer {key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": MODEL,
                    "temperature": 0,
                    "messages": [
                        {"role": "system", "content": PROMPT},
                        {"role": "user", "content": user_content},
                    ],
                },
                timeout=30,
            )

            if response.status_code != 200:
                return self._local_fallback(message)

            content = (
                response.json()["choices"][0]["message"].get("content") or ""
            )

            # FIX: more robust than stripping fences with 3 regexes -
            # grab everything from the first "{" to the last "}".
            start = content.find("{")
            end = content.rfind("}")

            if start == -1 or end == -1 or end <= start:
                return self._local_fallback(message)

            result = json.loads(content[start:end + 1])

            if not isinstance(result, dict):
                return self._local_fallback(message)

            return result

        except Exception:
            return self._local_fallback(message)

    # ---------------------------------------------------------
    # VALUE CLEANING
    # ---------------------------------------------------------

    @staticmethod
    def _clean_value(field, value):
        """Returns a clean value, or None if the value is unusable."""

        if value is None:
            return None

        if field in NUMERIC_FIELDS:
            # FIX: the model sometimes returns "3000" or "₹3,000".
            if isinstance(value, bool):
                return None

            if isinstance(value, (int, float)):
                number = float(value)
            else:
                digits = re.sub(r"[^\d.]", "", str(value))
                if not digits:
                    return None
                try:
                    number = float(digits)
                except ValueError:
                    return None

            return int(number) if number.is_integer() else number

        text = str(value).strip()

        if not text:
            return None

        if field in LOWERCASE_FIELDS:
            text = text.lower()

        return text

    # ---------------------------------------------------------
    # APPLY CHANGES
    # ---------------------------------------------------------

    def _apply(self, extracted):

        values = extracted.get("set", {})
        remove = extracted.get("remove", [])

        if not isinstance(values, dict):
            values = {}

        if not isinstance(remove, list):
            remove = []

        # Explicitly set values
        for field, value in values.items():

            if field not in ALLOWED_FIELDS:
                continue

            value = self._clean_value(field, value)

            if value is None:
                continue

            old_value = self.state.get(field)

            self.state[field] = value

            if old_value != value:
                self.changes.append({
                    "field": field,
                    "old": old_value,
                    "new": value,
                })

        # Explicitly removed values
        for field in remove:

            if not isinstance(field, str):
                continue

            if field not in ALLOWED_FIELDS:
                continue

            if field in self.state:

                old_value = self.state.pop(field)

                self.changes.append({
                    "field": field,
                    "old": old_value,
                    "new": None,
                })

    # ---------------------------------------------------------
    # LOCAL FALLBACK (used when there is no API key / API fails)
    # ---------------------------------------------------------

    def _local_fallback(self, message):

        text = message.lower()

        result = {
            "set": {},
            "remove": [],
        }

        # FIX: the old "[₹rs.]?" was a character class, not "₹ or rs".
        money = r"(?:₹|rs\.?|inr)?\s*([\d,]+)"

        # Price
        match = re.search(
            r"(?:under|below|less than|upto|up to|within)\s*" + money,
            text,
        )

        if match:
            result["set"]["max_price"] = int(
                match.group(1).replace(",", "") or 0
            )

        match = re.search(
            r"(?:above|over|more than|atleast|at least)\s*" + money,
            text,
        )

        if match:
            result["set"]["min_price"] = int(
                match.group(1).replace(",", "") or 0
            )

        # Removals: "remove the brand", "no size", "clear colour"
        for match in re.finditer(
            r"(?:remove|clear|drop|without|no)\s+(?:the\s+)?"
            r"(brand|colou?r|size|material|category|price)",
            text,
        ):
            word = match.group(1)

            if word == "price":
                result["remove"].extend(["min_price", "max_price"])
            else:
                result["remove"].append(FIELD_ALIASES[word])

        # Colors - skip when the user is removing the color
        if "color" not in result["remove"]:
            for color in COLORS:
                if re.search(r"\b" + re.escape(color) + r"\b", text):
                    result["set"]["color"] = color
                    break

        return result

    # ---------------------------------------------------------
    # PROMPT FOR THE CHATBOT
    # ---------------------------------------------------------

    def to_prompt(self):

        if not self.state:
            return ""

        lines = [
            "The user's current shopping requirements are:",
        ]

        for key, value in self.state.items():
            lines.append(f"- {key}: {value}")

        lines.append(
            "Treat these requirements as the current context. "
            "Do not invent additional requirements."
        )

        return "\n".join(lines)