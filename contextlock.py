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
    "gender",
    "min_price",
    "max_price",
}

NUMERIC_FIELDS = {"min_price", "max_price"}
LOWERCASE_FIELDS = {"category", "color", "material", "gender"}


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
    "gender": null,
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
   "show Nike instead" or "change the brand to Adidas"
   set the brand to the new value and replace the previous brand.

9. Keep existing constraints unchanged unless the latest message
   explicitly changes or removes them.

10. Interpret audience/gender terms as the gender field:
    women's, women, ladies, female, girls -> "women";
    men's, men, gents, male, boys -> "men";
    unisex -> "unisex".
    A request such as "for women" or "make it for men" changes only gender.

11. "under 3000", "below 3000", "less than 3000"
    means max_price = 3000.

12. "above 2000", "over 2000", "more than 2000"
    means min_price = 2000.

13. If the user says "remove the brand" or "no brand",
    put "brand" in remove.

14. Use plain values, not explanations. Prices are plain numbers.

15. If the message contains no shopping constraint, return:
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
    "gender": "gender",
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
        """
        Deterministic fallback used when Groq is unavailable.
        Preserves existing fields and extracts common shopping constraints.
        The category list here is only a fallback; Groq handles dynamic categories.
        """
        text = (message or "").lower().strip()

        result = {
            "set": {},
            "remove": [],
        }

        money = r"(?:₹|rs\.?|inr)?\s*([\d,]+)"

        # Price constraints.
        match = re.search(
            r"(?:under|below|less than|upto|up to|within)\s*" + money,
            text,
        )
        if match:
            result["set"]["max_price"] = int(
                match.group(1).replace(",", "")
            )

        match = re.search(
            r"(?:above|over|more than|atleast|at least)\s*" + money,
            text,
        )
        if match:
            result["set"]["min_price"] = int(
                match.group(1).replace(",", "")
            )

        # Explicitly remove fields.
        for match in re.finditer(
            r"(?:remove|clear|drop|without|no)\s+(?:the\s+)?"
            r"(brand|colou?r|size|material|category|gender|sex|price)",
            text,
        ):
            word = match.group(1)
            if word == "price":
                result["remove"].extend(["min_price", "max_price"])
            elif word in FIELD_ALIASES:
                result["remove"].append(FIELD_ALIASES[word])
            elif word == "sex":
                result["remove"].append("gender")

        # Apparel audience/gender filter.
        if "gender" not in result["remove"]:
            if re.search(r"\b(?:unisex)\b", text):
                result["set"]["gender"] = "unisex"
            elif re.search(r"\b(?:women(?:'s)?|womens|ladies|lady|female|girls?)\b", text):
                result["set"]["gender"] = "women"
            elif re.search(r"\b(?:men(?:'s)?|mens|gents|gentlemen|male|boys?)\b", text):
                result["set"]["gender"] = "men"

        # Extract a category when it is explicitly mentioned.
        # This local list is intentionally broad; the LLM handles dynamic categories.
        categories = [
            "kitten heels", "block heels", "high heels", "stilettos",
            "heels", "pumps", "heeled sandals", "sandals", "flats",
            "running shoes", "sneakers", "shoes", "t-shirt", "t shirt",
            "headphones", "earbuds", "smartphone", "mobile phone",
            "washing machine", "refrigerator", "fridge", "laptop",
            "smartwatch", "watch", "handbag", "backpack", "sunglasses",
            "jeans", "trousers", "shirt", "kurta", "saree", "sari",
            "dress", "jacket", "coat", "camera", "tablet", "chair",
            "sofa", "book", "books",
        ]
        if "category" not in result["remove"]:
            for category in sorted(categories, key=len, reverse=True):
                if re.search(r"\b" + re.escape(category) + r"\b", text):
                    result["set"]["category"] = category.replace("t shirt", "t-shirt")
                    break

        # Extract a color preference.
        if "color" not in result["remove"]:
            for color in COLORS:
                if re.search(r"\b" + re.escape(color) + r"\b", text):
                    result["set"]["color"] = color
                    break

        # Extract common sizes.
        if "size" not in result["remove"]:
            size_match = re.search(
                r"\b(?:size\s*)?(xs|s|m|l|xl|xxl|xxxl|\d{1,2})\b",
                text,
                re.IGNORECASE,
            )
            if size_match and re.search(r"\bsize\b", text):
                result["set"]["size"] = size_match.group(1).upper()

        # Extract a brand only when explicitly introduced. This avoids treating
        # arbitrary words as brands in fallback mode.
        if "brand" not in result["remove"]:
            brand_match = re.search(
                r"\b(?:change|switch|set)\s+(?:the\s+)?brand\s+(?:to|as)\s+"
                r"([a-z0-9][a-z0-9&' -]{0,40})",
                text,
                re.IGNORECASE,
            )
            if not brand_match:
                brand_match = re.search(
                    r"\b(?:brand\s+is|brand:|show|prefer|want)\s+"
                    r"([a-z0-9][a-z0-9&' -]{0,40})",
                    text,
                    re.IGNORECASE,
                )
            if brand_match:
                brand = brand_match.group(1).strip(" .,!?:;")
                brand = re.split(
                    r"[,.;!?]|\b(?:if possible|if available|i don't like|"
                    r"i do not like|no longer|anymore)\b",
                    brand,
                    maxsplit=1,
                    flags=re.IGNORECASE,
                )[0].strip()
                # Stop at common constraint words.
                brand = re.split(
                    r"\b(?:under|below|over|above|in|with|size|color|colour|for|women(?:'s)?|womens|men(?:'s)?|mens|female|male|unisex|ladies|gents|"
                    + "|".join(re.escape(word) for word in sorted(categories + COLORS, key=len, reverse=True))
                    + r")\b",
                    brand,
                    maxsplit=1,
                    flags=re.IGNORECASE,
                )[0].strip()
                if brand and brand not in {"me", "more", "cheaper", "blue", "red"}:
                    result["set"]["brand"] = brand.title()

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
