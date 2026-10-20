"""Quality gates for SFT responses.

Fine-tuning copies style as faithfully as content. Every filler phrase or
placeholder left in the data becomes a habit of the trained model.
"""

import re
from collections import Counter

from .data import final_response, prompt_text

# Phrases that teach a model bad habits: empty openers, AI self-reference, sign-off filler.
BANNED_PHRASES = [
    "as an ai", "as a language model", "great question", "certainly!", "absolutely!",
    "i hope this helps", "feel free to ask", "in conclusion,", "it's important to note",
    "delve into",
]
PLACEHOLDERS = re.compile(r"\b(TODO|TBD|FIXME|lorem ipsum)\b|\[insert", re.IGNORECASE)
MAX_WORDS = 450
DUPLICATE_THRESHOLD = 0.6
MAX_CATEGORY_SHARE = 0.25


def _issue(level, pid, check, detail):
    return {"level": level, "id": pid, "check": check, "detail": detail}


def lint_pair(pair: dict) -> list[dict]:
    issues = []
    pid = pair["id"]
    for i, m in enumerate(pair["messages"]):
        if m["role"] != "assistant":
            continue
        text = m["content"]
        low = text.lower()
        for phrase in BANNED_PHRASES:
            if phrase in low:
                issues.append(_issue("error", pid, "banned_phrase", f"turn {i}: contains '{phrase}'"))
        if PLACEHOLDERS.search(text):
            issues.append(_issue("error", pid, "placeholder", f"turn {i}: unfinished placeholder text"))
        if text.count("```") % 2:
            issues.append(_issue("error", pid, "code_fence", f"turn {i}: unbalanced ``` fence"))
        words = len(text.split())
        if words > MAX_WORDS:
            issues.append(_issue("warning", pid, "length", f"turn {i}: {words} words (max {MAX_WORDS})"))
    if "[Your name]" in final_response(pair):
        # Allowed only as an explicit signature slot in writing tasks.
        if pair["category"] != "writing":
            issues.append(_issue("error", pid, "placeholder", "signature slot outside a writing task"))
    return issues


def _trigrams(text: str) -> set:
    words = re.findall(r"[a-z0-9']+", text.lower())
    return {tuple(words[i:i + 3]) for i in range(len(words) - 2)}


def jaccard(a: str, b: str) -> float:
    ta, tb = _trigrams(a), _trigrams(b)
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


def near_duplicates(pairs: list[dict], threshold: float = DUPLICATE_THRESHOLD) -> list[dict]:
    issues = []
    for i in range(len(pairs)):
        for j in range(i + 1, len(pairs)):
            sim = jaccard(prompt_text(pairs[i]), prompt_text(pairs[j]))
            if sim >= threshold:
                issues.append(_issue("error", pairs[i]["id"], "near_duplicate",
                                     f"prompt is {sim:.0%} similar to {pairs[j]['id']}"))
    return issues


def category_balance(pairs: list[dict], max_share: float = MAX_CATEGORY_SHARE) -> list[dict]:
    counts = Counter(p["category"] for p in pairs)
    return [
        _issue("warning", "-", "category_balance",
               f"'{cat}' is {n / len(pairs):.0%} of the dataset (max {max_share:.0%})")
        for cat, n in counts.items() if n / len(pairs) > max_share
    ]


def lint_dataset(pairs: list[dict]) -> list[dict]:
    issues = [i for p in pairs for i in lint_pair(p)]
    return issues + near_duplicates(pairs) + category_balance(pairs)
