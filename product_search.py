
"""
Verity AI Product Search
------------------------
Searches Google Shopping through SerpApi.

General conversation is handled separately by pipeline.py.
This module only searches for products when called by the pipeline.

Features:
- Searches Google Shopping in India.
- Applies category, color, brand, and price filters.
- Returns product titles, prices, images, and links.
- Logs useful diagnostics without exposing the API key.
- Never invents product results.
- Does not treat demo-catalogue USD prices as INR.
"""

import os
import re
import logging
import requests


logger = logging.getLogger(__name__)

SERPAPI_URL = "https://serpapi.com/search.json"
REQUEST_TIMEOUT = 30
MAX_RESULTS = 12


# -------------------------------------------------------------
# HELPERS
# -------------------------------------------------------------

def _normal(value):
    """Normalize text for consistent product matching."""
    if value is None:
        return ""

    value = str(value).lower()
    value = value.replace("-", " ").replace("_", " ")
    value = re.sub(r"[^a-z0-9₹ ]+", " ", value)
    value = re.sub(r"\s+", " ", value)

    return value.strip()


def _matches_value(text, value):
    """Match whole words, allowing simple singular/plural variants."""
    text = _normal(text)
    value = _normal(value)

    if not value:
        return True

    variants = {value, value + "s", value + "es"}

    if value.endswith("s"):
        variants.add(value[:-1])

    padded = f" {text} "

    for variant in variants:
        if f" {variant} " in padded:
            return True

    # Allow "t shirt" to match "tshirt".
    if " " in value:
        compact_text = text.replace(" ", "")
        compact_value = value.replace(" ", "")

        if compact_value in compact_text:
            return True

    return False


def _matches_category(product, category):
    """Verify the requested category against the product title."""
    if not category:
        return True

    title = product.get("title", "")

    # Common equivalent category names.
    aliases = {
        "laptop": ("laptop", "laptops", "notebook computer"),
        "smartphone": ("smartphone", "smartphones", "mobile phone"),
        "mobile phone": ("mobile phone", "smartphone", "mobile"),
        "headphone": ("headphone", "headphones", "headset"),
        "earbud": ("earbud", "earbuds", "wireless earphones"),
        "sneaker": ("sneaker", "sneakers", "trainers"),
        "t shirt": ("t shirt", "tshirt", "tee shirt"),
        "jean": ("jean", "jeans", "denim jeans"),
    }

    normalized_category = _normal(category)
    candidates = aliases.get(normalized_category, (category,))

    return any(
        _matches_value(title, candidate)
        for candidate in candidates
    )


def _matches_color(product, color):
    if not color:
        return True

    return _matches_value(product.get("title", ""), color)


def _matches_brand(product, brand):
    if not brand:
        return True

    searchable = " ".join([
        str(product.get("title", "")),
        str(product.get("source", "")),
        str(product.get("brand", "")),
    ])

    return _matches_value(searchable, brand)


def _price(product):
    """
    Return the numeric price when the provider supplies one.

    SerpApi's extracted_price is preferred because it is numeric.
    Google Shopping is queried for India using gl=in.
    """
    value = product.get("extracted_price")

    if value is None:
        value = product.get("price_text")

    if value is None:
        return None

    try:
        cleaned = re.sub(r"[^\d.]", "", str(value))

        if not cleaned:
            return None

        return float(cleaned)

    except (ValueError, TypeError):
        return None


def _matches_price(product, filters):
    min_price = filters.get("min_price")
    max_price = filters.get("max_price")

    if min_price is None and max_price is None:
        return True

    price = _price(product)

    # Do not claim a product matches a price limit if
    # its price is missing or cannot be interpreted.
    if price is None:
        return False

    try:
        if min_price is not None and price < float(min_price):
            return False

        if max_price is not None and price > float(max_price):
            return False

    except (ValueError, TypeError):
        return False

    return True


def _matches_all(product, filters):
    return (
        _matches_category(product, filters.get("category"))
        and _matches_color(product, filters.get("color"))
        and _matches_brand(product, filters.get("brand"))
        and _matches_price(product, filters)
    )


# -------------------------------------------------------------
# GOOGLE SHOPPING / SERPAPI
# -------------------------------------------------------------

def _search_serpapi(filters, api_key):
    """Fetch Google Shopping results and apply the requested filters."""

    query_parts = []

    for field in ("brand", "color", "material", "category", "size"):
        value = filters.get(field)

        if value:
            query_parts.append(str(value))

    query = " ".join(query_parts).strip()

    if not query:
        return []

    params = {
        "engine": "google_shopping",
        "q": query,
        "api_key": api_key,
        "location": "India",
        "hl": "en",
        "gl": "in",
    }

    try:
        response = requests.get(
            SERPAPI_URL,
            params=params,
            timeout=REQUEST_TIMEOUT,
        )

        if response.status_code != 200:
            logger.error(
                "SerpApi returned HTTP status %s",
                response.status_code,
            )
            return []

        data = response.json()

        # SerpApi may return HTTP 200 with an API-level error.
        if data.get("error"):
            logger.error(
                "SerpApi API error: %s",
                str(data["error"])[:300],
            )
            return []

        raw_items = data.get("shopping_results", [])

        logger.info(
            "SerpApi returned %s raw shopping results for query %r",
            len(raw_items),
            query,
        )

        products = []

        for item in raw_items:
            price_text = item.get("price") or ""

            product = {
                "title": item.get("title", ""),
                "price": price_text,
                "price_text": price_text,
                "extracted_price": item.get("extracted_price"),
                "source": item.get("source", ""),
                "brand": item.get("brand", ""),
                "image": (
                    item.get("thumbnail")
                    or item.get("serpapi_thumbnail")
                    or ""
                ),
                "image_url": (
                    item.get("thumbnail")
                    or item.get("serpapi_thumbnail")
                    or ""
                ),
                "link": (
                    item.get("product_link")
                    or item.get("link")
                    or ""
                ),
            }

            if not product["title"]:
                continue

            if _matches_all(product, filters):
                products.append(product)

        logger.info(
            "%s products passed Verity AI's filters",
            len(products),
        )

        return products

    except requests.Timeout:
        logger.error("SerpApi request timed out")
        return []

    except requests.RequestException as exc:
        logger.error(
            "SerpApi network request failed: %s",
            type(exc).__name__,
        )
        return []

    except (ValueError, TypeError) as exc:
        logger.error(
            "Could not parse SerpApi response: %s",
            type(exc).__name__,
        )
        return []


# -------------------------------------------------------------
# PUBLIC FUNCTION
# -------------------------------------------------------------

def search_products(filters):
    """
    Search products using ContextLock's current filter state.

    Expected filters may include:
        category, color, brand, material, size,
        min_price, max_price

    Returns:
        {
            "items": [...],
            "note": "..."
        }
    """

    filters = dict(filters or {})

    category = filters.get("category")

    if not isinstance(category, str) or not category.strip():
        return {
            "items": [],
            "note": "Tell me which product you want to find.",
        }

    api_key = os.getenv("SERPAPI_KEY")

    if not api_key:
        logger.warning("SERPAPI_KEY is not configured")

        return {
            "items": [],
            "note": (
                "Product search is not configured yet. "
                "Please check the SERPAPI_KEY environment variable."
            ),
        }

    products = _search_serpapi(filters, api_key)

    # Remove duplicate product listings.
    seen = set()
    clean = []

    for product in products:
        key = (
            _normal(product.get("title")),
            _normal(product.get("source")),
        )

        if key in seen:
            continue

        seen.add(key)
        clean.append(product)

    clean = clean[:MAX_RESULTS]

    if not clean:
        requested = []

        for field in ("brand", "color", "category"):
            if filters.get(field):
                requested.append(str(filters[field]))

        if filters.get("max_price") is not None:
            requested.append(f"up to ₹{filters['max_price']}")

        if filters.get("min_price") is not None:
            requested.append(f"from ₹{filters['min_price']}")

        description = " ".join(requested)

        return {
            "items": [],
            "note": (
                f"No verified matching products were found for "
                f"'{description}'. Try a broader search or a different "
                "price range."
            ),
        }

    return {
        "items": clean,
        "note": (
            f"Found {len(clean)} matching product(s) "
            "from Google Shopping."
        ),
    }
