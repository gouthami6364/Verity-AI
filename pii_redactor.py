"""
STEP 1: PII Redactor
Finds private data (email, card, Aadhaar, PAN, phone) in a message
and replaces it with a safe tag like [PHONE_REDACTED].

Run this file to test it:   python pii_redactor.py
"""

import re


# --- Checks if a card number is real, using the Luhn algorithm -------
def luhn_valid(number):
    digits = [int(d) for d in number if d.isdigit()]
    if not 13 <= len(digits) <= 19:
        return False
    total = 0
    for i, d in enumerate(reversed(digits)):
        if i % 2 == 1:          # double every second digit from the right
            d *= 2
            if d > 9:
                d -= 9
        total += d
    return total % 10 == 0


# --- Patterns: each one describes how a type of private data looks ---
# The ORDER matters: if two patterns match the same text, the first wins.
PATTERNS = [
    # FIX: the old pattern swallowed a trailing "." ("me@x.com.").
    ("EMAIL",   re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")),
    ("CARD",    re.compile(r"(?<!\d)(?:\d[ -]?){13,19}(?!\d)")),
    ("AADHAAR", re.compile(r"(?<!\d)(?<!\d[ -])[2-9]\d{3}[ -]?\d{4}[ -]?\d{4}(?![ -]?\d)")),
    # FIX: PAN is now case-insensitive (users type "abcde1234f" too).
    ("PAN",     re.compile(r"\b[A-Z]{5}\d{4}[A-Z]\b", re.IGNORECASE)),
    # FIX: also catches "+91", "91" and leading "0" prefixes.
    ("PHONE",   re.compile(r"(?<!\d)(?:\+91[ -]?|91[ -]?|0)?[6-9]\d{4}[ -]?\d{5}(?!\d)")),
]


def redact(text):
    """Returns (clean_text, findings).

    NOTE: findings contain the raw value. Never log or send them
    to the browser - only send the "type".
    """
    text = text or ""
    found = []   # list of (start, end, type)

    for label, pattern in PATTERNS:
        for m in pattern.finditer(text):
            # A 16-digit number is only a CARD if it passes the Luhn check
            if label == "CARD" and not luhn_valid(m.group()):
                continue
            # Skip if this overlaps something we already found
            if any(m.start() < e and m.end() > s for s, e, _ in found):
                continue
            found.append((m.start(), m.end(), label))

    # Rebuild the message, replacing each found item with a tag
    found.sort()
    clean, last, findings = [], 0, []
    for start, end, label in found:
        clean.append(text[last:start])
        clean.append(f"[{label}_REDACTED]")
        findings.append({"type": label, "value": text[start:end]})
        last = end
    clean.append(text[last:])

    return "".join(clean), findings


# --- Test: runs only when you run this file directly -----------------
if __name__ == "__main__":
    tests = [
        "Hi, I want Nike shoes under 3000",
        "Call me on 9876543210 or +91 98765 43210",
        "My email is fishermane@gmail.com.",
        "Card: 4539 1488 0343 6467",
        "Random number 1234 5678 9012 3456 is not a card",
        "PAN is ABCDE1234F and Aadhaar is 2345 6789 0123",
        "pan abcde1234f",
    ]
    for msg in tests:
        clean, findings = redact(msg)
        print("ORIGINAL :", msg)
        print("CLEANED  :", clean)
        print("FOUND    :", [f["type"] for f in findings] or "nothing")
        print("-" * 60)