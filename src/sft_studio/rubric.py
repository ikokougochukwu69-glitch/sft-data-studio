"""Output-quality rubric: acceptance decisions and inter-annotator agreement.

Unlike a pairwise preference rubric, this scores ONE response on an absolute
1-5 scale and decides whether it is good enough to train on.
"""

DIMENSIONS = ("correctness", "completeness", "instruction_adherence", "clarity", "tone", "concision")

ACCEPT = "accept"
REVISE = "revise"
REJECT = "reject"


def decide(scores: dict) -> dict:
    """Gate a response for inclusion in an SFT dataset.

    - reject: correctness below 4 (wrong content can't be fixed by editing style),
      OR any dimension at 1, OR mean below 3.5 (too broken to be worth rewriting;
      writing a new response is cheaper).
    - accept: correctness 5, every other dimension at least 4, mean at least 4.5.
    - revise: everything in between, with the dimensions to fix.
    """
    missing = [d for d in DIMENSIONS if d not in scores]
    if missing:
        raise ValueError(f"missing scores: {missing}")
    mean = sum(scores[d] for d in DIMENSIONS) / len(DIMENSIONS)
    weak = [d for d in DIMENSIONS if scores[d] < 4]

    if scores["correctness"] < 4 or min(scores.values()) == 1 or mean < 3.5:
        decision = REJECT
    elif scores["correctness"] == 5 and not weak and mean >= 4.5:
        decision = ACCEPT
    else:
        decision = REVISE
    return {"decision": decision, "mean": round(mean, 2), "fix": weak}


def quadratic_weighted_kappa(a: list[int], b: list[int], min_score: int = 1, max_score: int = 5) -> float:
    """Agreement between two annotators on an ordinal scale.

    Disagreements are penalised by squared distance, so 4 vs 5 costs far less
    than 1 vs 5. Standard metric for rubric-score agreement.
    """
    if len(a) != len(b) or not a:
        raise ValueError("score lists must be non-empty and the same length")
    k = max_score - min_score + 1
    observed = [[0] * k for _ in range(k)]
    for x, y in zip(a, b):
        observed[x - min_score][y - min_score] += 1
    n = len(a)
    hist_a = [sum(row) for row in observed]
    hist_b = [sum(observed[i][j] for i in range(k)) for j in range(k)]

    num = den = 0.0
    for i in range(k):
        for j in range(k):
            w = (i - j) ** 2 / (k - 1) ** 2
            expected = hist_a[i] * hist_b[j] / n
            num += w * observed[i][j]
            den += w * expected
    return 1.0 if den == 0 else 1 - num / den


def agreement(a: list[int], b: list[int]) -> dict:
    n = len(a)
    return {
        "n": n,
        "exact": sum(x == y for x, y in zip(a, b)) / n,
        "within_one": sum(abs(x - y) <= 1 for x, y in zip(a, b)) / n,
        "qwk": quadratic_weighted_kappa(a, b),
    }
