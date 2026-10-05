"""
Product Search
--------------
Searches for products using the complete ContextLock state.

The search is intentionally strict.

If the user asks for:

    blue kurta

a blue shirt, blue book, blue chessboard, etc. must NOT be returned.

If the search service cannot verify the requested product type,
it is safer to return no result than an unrelated product.
"""

import os
import re
import requests


# -------------------------------------------------------------
# HELPERS
# -------------------------------------------------------------

def _normal(value):
    if value is None:
        return ""

    value = str(value).lower()

    value = value.replace("-", " ")
    value = value.replace("_", " ")

    value = re.sub(r"[^a-z0-9₹ ]+", " ", value)
    value = re.sub(r"\s+", " ", value)

    return value.strip()


def _text(product):
    parts = [
        product.get("title", ""),
        product.get("source", ""),
        product.get("brand", ""),
    ]

    return _normal(" ".join(str(x) for x in parts if x))


def _matches_value(text, value):
    """
    Whole-word match with simple plural handling.

    FIX: the old version used plain substring matching, so "tee"
    matched "steel" and "red" matched "bored". Now it matches words.
    "Levi's" -> "levi s" also matches "levis" and "t shirt" matches
    "tshirt".
    """

    value = _normal(value)

    if not value:
        return True

    text = _normal(text)

    variants = {value, value + "s", value + "es"}

    if value.endswith("s"):
        variants.add(value[:-1])

    padded = f" {text} "

    for variant in variants:
        if f" {variant} " in padded:
            return True

    # Multi-word values: ignore spaces ("t shirt" == "tshirt").
    if " " in value:
        compact_text = text.replace(" ", "")
        compact_value = value.replace(" ", "")

        if compact_value in compact_text:
            return True

    return False


def _matches_category(product, category):

    if not category:
        return True

    # Category must be verifiable from the product title.
    return _matches_value(product.get("title", ""), category)


def _matches_color(product, color):

    if not color:
        return True

    return _matches_value(product.get("title", ""), color)


def _matches_brand(product, brand):

    if not brand:
        return True

    return _matches_value(_text(product), brand)


def _price(product):

    value = product.get("extracted_price")

    if value is None:
        value = product.get("price_text")

    if value is None:
        return None

    try:
        text = re.sub(r"[^\d.]", "", str(value))

        if not text:
            return None

        return float(text)

    except Exception:
        return None


def _matches_price(product, filters):

    min_price = filters.get("min_price")
    max_price = filters.get("max_price")

    if min_price is None and max_price is None:
        return True

    price = _price(product)

    # Price constraint but unknown price -> do NOT pretend it matches.
    if price is None:
        return False

    if min_price is not None and price < float(min_price):
        return False

    if max_price is not None and price > float(max_price):
        return False

    return True


# -------------------------------------------------------------
# STRICT FILTER
# -------------------------------------------------------------

def _matches_all(product, filters):

    return (
        _matches_category(product, filters.get("category"))
        and _matches_color(product, filters.get("color"))
        and _matches_brand(product, filters.get("brand"))
        and _matches_price(product, filters)
    )


# -------------------------------------------------------------
# SERPAPI / GOOGLE SHOPPING
# -------------------------------------------------------------

def _search_serpapi(filters, api_key):

    # FIX: size and material are now part of the search query too.
    pieces = []

    for field in ("brand", "color", "material", "category", "size"):
        if filters.get(field):
            pieces.append(str(filters[field]))

    query = " ".join(pieces).strip()

    if not query:
        return []

    try:

        response = requests.get(
            "https://serpapi.com/search.json",
            params={
                "engine": "google_shopping",
                "q": query,
                "api_key": api_key,
                "location": "India",
                "hl": "en",
                "gl": "in",
            },
            timeout=30,
        )

        if response.status_code != 200:
            return []

        data = response.json()

        products = []

        for item in data.get("shopping_results", []):

            price_text = item.get("price", "") or ""

            product = {
                "title": item.get("title", ""),
                "price": price_text,          # FIX: the frontend reads this
                "price_text": price_text,
                "extracted_price": item.get("extracted_price"),
                "source": item.get("source", ""),
                "image": item.get("thumbnail", ""),
                # FIX: Google Shopping often only has "product_link".
                "link": item.get("link") or item.get("product_link") or "",
            }

            if _matches_all(product, filters):
                products.append(product)

        return products

    except Exception:
        return []


# -------------------------------------------------------------
# DUMMYJSON DEMO SEARCH (used only when there is no SERPAPI_KEY)
# -------------------------------------------------------------

DUMMYJSON_CATEGORIES = {
    "beauty": "beauty",
    "fragrances": "fragrances",
    "furniture": "furniture",
    "groceries": "groceries",
    "home decoration": "home-decoration",
    "kitchen accessories": "kitchen-accessories",
    "laptops": "laptops",
    "mens shirts": "mens-shirts",
    "mens shoes": "mens-shoes",
    "mens watches": "mens-watches",
    "mobile accessories": "mobile-accessories",
    "motorcycle": "motorcycle",
    "skin care": "skin-care",
    "smartphones": "smartphones",
    "sports accessories": "sports-accessories",
    "sunglasses": "sunglasses",
    "tablets": "tablets",
    "tops": "tops",
    "vehicle": "vehicle",
    "womens bags": "womens-bags",
    "womens dresses": "womens-dresses",
    "womens jewellery": "womens-jewellery",
    "womens shoes": "womens-shoes",
    "womens watches": "womens-watches",
}


def _search_dummyjson(filters):
    """
    DummyJSON is only a demo catalogue. Unknown category = no results.
    """

    endpoint = DUMMYJSON_CATEGORIES.get(_normal(filters.get("category")))

    if not endpoint:
        return []

    try:

        response = requests.get(
            f"https://dummyjson.com/products/category/{endpoint}",
            timeout=15,
        )

        if response.status_code != 200:
            return []

        # FIX: the category was already verified by the endpoint, so we
        # must NOT re-check it against the title ("mens shirts" is never
        # inside a title, so everything used to be rejected).
        other_filters = dict(filters)
        other_filters.pop("category", None)

        products = []

        for item in response.json().get("products", []):

            price = item.get("price")

            product = {
                "title": item.get("title", ""),
                # FIX: DummyJSON prices are USD, not rupees.
                "price": f"${price}" if price is not None else "",
                "price_text": f"${price}" if price is not None else "",
                "extracted_price": price,
                "source": "Demo catalogue",
                "image": item.get("thumbnail", ""),
                "link": "",
            }

            if _matches_all(product, other_filters):
                products.append(product)

        return products

    except Exception:
        return []


# -------------------------------------------------------------
# PUBLIC FUNCTION
# -------------------------------------------------------------

def search_products(filters):

    filters = dict(filters or {})

    if not filters:
        return {
            "items": [],
            "note": "Tell me what product you want.",
        }

    # FIX: without a category (e.g. only "blue") we can't verify results,
    # so don't search at all.
    if not filters.get("category"):
        return {
            "items": [],
            "note": "Tell me which product you are looking for.",
        }

    # FIX: read the key at call time, not at import time.
    api_key = os.getenv("SERPAPI_KEY")

    if api_key:
        products = _search_serpapi(filters, api_key)
    else:
        products = _search_dummyjson(filters)

    seen = set()
    clean = []

    for product in products:

        key = (
            product.get("title", ""),
            product.get("source", ""),
        )

        if key in seen:
            continue

        seen.add(key)
        clean.append(product)

    clean = clean[:12]

    if not clean:

        parts = []

        if filters.get("color"):
            parts.append(str(filters["color"]))

        if filters.get("brand"):
            parts.append(str(filters["brand"]))

        if filters.get("category"):
            parts.append(str(filters["category"]))

        if filters.get("max_price") is not None:
            parts.append(f"under ₹{filters['max_price']}")

        if filters.get("min_price") is not None:
            parts.append(f"above ₹{filters['min_price']}")

        request_text = " ".join(parts)

        note = f"I couldn't find verified products matching '{request_text}'."

        if not api_key:
            note += " (SERPAPI_KEY is not set, so only the demo catalogue was searched.)"

        return {
            "items": [],
            "note": note,
        }

    return {
        "items": clean,
        "note": "Showing products matching your current requirements.",
    }