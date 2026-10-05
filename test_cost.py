"""
STEP 6, TEST 2: Cost test
Measures how many tokens (and how much money) are saved when the
Token Budget Tracker shortens old conversation history.

We build fake conversations of different lengths, then compare the size of the
message sent to the AI BEFORE and AFTER shortening.

Run this file:   python test_cost.py
"""

from token_tracker import TokenBudgetTracker, COUNTER

tracker = TokenBudgetTracker()

SYSTEM = ("You are a helpful shopping assistant. Keep answers short and clear.\n"
          "The user has set these requirements. Follow ALL of them in every answer unless the user changes them:\n"
          "- category: shoes\n- brand: nike\n- max price: 3000")

# Realistic chat lines (questions from the user, answers from the bot)
USER_LINES = [
    "Show me some running shoes with good grip and a light body for daily use.",
    "Do you have any with a soft sole that is comfortable for long walks?",
    "Which of these are available in black or dark colours?",
    "Are any of them suitable for wide feet or flat feet?",
    "What is the difference between the first and the second option?",
    "Can you tell me which one lasts longer with regular use?",
    "Do any of these come with a warranty or an easy return policy?",
    "Which one would you suggest for a beginner who walks every morning?",
    "Are there cheaper options that are still good quality?",
    "Is there a discount or sale going on for any of these right now?",
]
BOT_LINES = [
    "Here are three options with strong grip, a light body and a cushioned sole that suit everyday running and walking.",
    "Yes, the second and third options have extra soft soles and are comfortable for long walks and standing.",
    "The first and third options are available in black, and the second comes in dark grey and navy blue.",
    "The third option has a wider fit and good arch support, which is helpful for wide or flat feet.",
    "The first is lighter and faster for running, while the second has more cushioning and feels softer for walking.",
    "The second option uses thicker rubber on the bottom, so it usually lasts longer with regular daily use.",
    "All three come with a standard six month warranty and a seven day return policy if the size does not fit.",
    "For a beginner, I would suggest the second option because it is soft, stable and easy to wear every day.",
    "The first option is the cheapest and still has good quality, though it has a little less cushioning.",
    "A small seasonal discount is available on the first and third options for a limited time.",
]

NEW_MESSAGE = "Which one is the best value for money?"


def make_history(turns):
    """Builds a fake conversation with the given number of question-answer pairs."""
    history = []
    for i in range(turns):
        history.append({"role": "user", "content": USER_LINES[i % 10]})
        history.append({"role": "assistant", "content": BOT_LINES[i % 10]})
    return history


print("Token counter used:", COUNTER)
print()
print(f"{'Turns':<8}{'Before':<10}{'After':<10}{'Saved':<10}{'Cost before':<14}{'Cost after':<12}")
print("-" * 64)

total_before = total_after = 0
compressed_before = compressed_after = 0
compressed_count = 0
turn_list = [2, 4, 6, 8, 10, 15, 20]

for turns in turn_list:
    history = make_history(turns)
    before = tracker.breakdown(SYSTEM, history, NEW_MESSAGE)
    shorter = tracker.compress_history(history)
    after = tracker.breakdown(SYSTEM, shorter, NEW_MESSAGE)

    saved = before["total"] - after["total"]
    pct = saved / before["total"] * 100
    total_before += before["total"]
    total_after += after["total"]
    if saved > 0:
        compressed_count += 1
        compressed_before += before["total"]
        compressed_after += after["total"]

    print(f"{turns:<8}{before['total']:<10}{after['total']:<10}{f'{pct:.0f}%':<10}"
          f"${before['estimated_cost_usd']:<13.6f}${after['estimated_cost_usd']:<11.6f}")

print("-" * 64)
print(f"All {len(turn_list)} conversations together:")
print(f"   Tokens: {total_before} -> {total_after}   "
      f"({(total_before - total_after) / total_before * 100:.0f}% saved)")
if compressed_count:
    print(f"Only the {compressed_count} long conversations (where shortening was triggered):")
    print(f"   Tokens: {compressed_before} -> {compressed_after}   "
          f"({(compressed_before - compressed_after) / compressed_before * 100:.0f}% saved)")
print()
print("Note: short conversations are not shortened, so they show 0% saved.")
