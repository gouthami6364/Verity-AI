"""
STEP 6, TEST 3: Private data (PII) test
Checks how well the PII Redactor finds private data.

We wrote sample messages and marked EXACTLY which private data each one contains.
Then we compare what the redactor found with what it should have found.

  Precision = of everything it flagged, how much was really private?
  Recall    = of all the private data that exists, how much did it catch?

Run this file:   python test_pii.py
"""

from pii_redactor import redact

# Each test: (message, [ (type, exact text) ... ] that SHOULD be found)
TESTS = [
    # ---- normal cases ----
    ("My phone is 9876543210",                    [("PHONE", "9876543210")]),
    ("Call +91 98765 43210 tonight",              [("PHONE", "+91 98765 43210")]),
    ("Reach me at 98765-43210",                   [("PHONE", "98765-43210")]),
    ("WhatsApp: +91-9876543210",                  [("PHONE", "+91-9876543210")]),
    ("Contact 9123456780 or 8123456789",          [("PHONE", "9123456780"), ("PHONE", "8123456789")]),
    ("Mail me at ravi.kumar@gmail.com",           [("EMAIL", "ravi.kumar@gmail.com")]),
    ("anu_2024@college.edu.in is my email",       [("EMAIL", "anu_2024@college.edu.in")]),
    ("Card number 4539 1488 0343 6467",           [("CARD", "4539 1488 0343 6467")]),
    ("Pay with 4539-1488-0343-6467 please",       [("CARD", "4539-1488-0343-6467")]),
    ("My card 4532015112830366",                  [("CARD", "4532015112830366")]),
    ("Amex 3782 822463 10005",                    [("CARD", "3782 822463 10005")]),
    ("Aadhaar 2345 6789 0123",                    [("AADHAAR", "2345 6789 0123")]),
    ("My aadhaar is 234567890123",                [("AADHAAR", "234567890123")]),
    ("PAN ABCDE1234F",                            [("PAN", "ABCDE1234F")]),
    ("Call 9876543210 or mail a.b@x.com",         [("PHONE", "9876543210"), ("EMAIL", "a.b@x.com")]),

    # ---- hard cases (unusual writing styles) ----
    ("My number is 098765 43210",                 [("PHONE", "098765 43210")]),
    ("email: anu at gmail dot com",               [("EMAIL", "anu at gmail dot com")]),
    ("pan: abcde1234f",                           [("PAN", "abcde1234f")]),

    # ---- no private data at all (should find NOTHING) ----
    ("I want Nike shoes under 3000",              []),
    ("Order number 1234567890 was delivered",     []),
    ("The price is 49999 rupees",                 []),
    ("Random 1234 5678 9012 3456",                []),
    ("Model SM-A546B costs 28999",                []),
    ("Reference 4111 1111 1111 1112 for ticket",  []),
    ("Call 100 for police",                       []),
    ("Use code 9999999999 for the discount",      []),   # looks like a phone number but is not one
]

tp = fp = fn = 0
failures = []

for message, expected in TESTS:
    _, findings = redact(message)
    found = {(f["type"], f["value"].strip()) for f in findings}
    want = set(expected)

    tp += len(found & want)
    fp += len(found - want)
    fn += len(want - found)

    for item in found - want:
        failures.append(("FALSE ALARM (flagged but not private)", message, item))
    for item in want - found:
        failures.append(("MISSED (private data not caught)", message, item))

precision = tp / (tp + fp) if tp + fp else 0
recall = tp / (tp + fn) if tp + fn else 0

print(f"Messages tested         : {len(TESTS)}")
print(f"Private items that exist: {tp + fn}")
print()
print(f"Correctly caught        : {tp}")
print(f"Missed                  : {fn}")
print(f"False alarms            : {fp}")
print()
print(f"Precision : {precision * 100:.0f}%")
print(f"Recall    : {recall * 100:.0f}%")

if failures:
    print("\nFailure cases (report these honestly):")
    for kind, message, item in failures:
        print(f"  - {kind}")
        print(f"      message: {message}")
        print(f"      item   : {item[0]} -> {item[1]}")