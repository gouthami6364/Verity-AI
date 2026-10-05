"""
STEP 6, TEST 1: Memory test
Checks how well ContextLock remembers requirements over a conversation.

  - Verity AI  : uses ContextLock (remembers across all messages)
  - Baseline   : an ordinary bot with NO memory, it only understands the LAST message

Each conversation has the "correct" final requirements written by us.
Run this file:   python test_memory.py
"""

from contextlock import ContextLock

# Each test: (name, list of user messages, what the bot SHOULD remember at the end)
TESTS = [
    ("1. Simple adding",
     ["I want Nike shoes under 3000", "Make it black", "Show me something nice"],
     {"category": "shoes", "brand": "nike", "max_price": 3000, "color": "black"}),

    ("2. Price with k",
     ["Looking for a Samsung phone", "budget of 20k", "in blue"],
     {"category": "phone", "brand": "samsung", "max_price": 20000, "color": "blue"}),

    ("3. Change and remove",
     ["I need a laptop under 50000", "Actually make it Dell", "Remove the price limit"],
     {"category": "laptop", "brand": "dell"}),

    ("4. Colour correction",
     ["Show me Puma shirt", "white colour", "change colour to red"],
     {"category": "shirt", "brand": "puma", "color": "red"}),

    ("5. Min and max price",
     ["Apple watch above 10000", "less than 30000"],
     {"category": "watch", "brand": "apple", "min_price": 10000, "max_price": 30000}),

    ("6. Remove brand",
     ["I want a bag", "Adidas", "Any brand", "pink"],
     {"category": "bag", "color": "pink"}),

    ("7. Short price",
     ["Headphones below 3k", "boat brand", "black"],
     {"category": "headphones", "max_price": 3000, "brand": "boat", "color": "black"}),

    ("8. Unknown brand",
     ["I want Skechers shoes under 2500", "in grey"],
     {"category": "shoes", "brand": "skechers", "max_price": 2500, "color": "grey"}),

    ("9. Negation (not X)",
     ["Laptop under 40000", "Not Lenovo, I prefer HP"],
     {"category": "laptop", "max_price": 40000, "brand": "hp"}),
]


def run_verity(messages):
    lock = ContextLock()
    for m in messages:
        lock.update(m)
    return lock.state


def run_baseline(messages):
    lock = ContextLock()
    lock.update(messages[-1])          # only the last message, no memory
    return lock.state


def score(got, expected):
    """Counts how many of the expected requirements were remembered correctly."""
    correct = sum(1 for k, v in expected.items() if got.get(k) == v)
    wrong_extra = [k for k in got if k not in expected]    # remembered something that should not be there
    return correct, len(expected), wrong_extra


total_verity = total_base = total_expected = 0
all_clean_verity = all_clean_base = 0

print(f"{'Test':<26}{'Verity AI':<14}{'Baseline':<12}")
print("-" * 52)
for name, messages, expected in TESTS:
    v_got = run_verity(messages)
    b_got = run_baseline(messages)
    v_ok, n, v_extra = score(v_got, expected)
    b_ok, _, b_extra = score(b_got, expected)
    total_verity += v_ok
    total_base += b_ok
    total_expected += n
    all_clean_verity += (v_ok == n and not v_extra)
    all_clean_base += (b_ok == n and not b_extra)
    print(f"{name:<26}{f'{v_ok}/{n}':<14}{f'{b_ok}/{n}':<12}")
    if v_ok < n or v_extra:
        print(f"    Verity AI remembered : {v_got}")
        print(f"    It should have       : {expected}")

print("-" * 52)
print(f"Requirements remembered correctly:")
print(f"   Verity AI : {total_verity}/{total_expected}  ({total_verity / total_expected * 100:.0f}%)")
print(f"   Baseline  : {total_base}/{total_expected}  ({total_base / total_expected * 100:.0f}%)")
print(f"Conversations fully correct:")
print(f"   Verity AI : {all_clean_verity}/{len(TESTS)}")
print(f"   Baseline  : {all_clean_base}/{len(TESTS)}")