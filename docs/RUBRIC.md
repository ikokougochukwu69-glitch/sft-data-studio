# Output Quality Rubric

Scores **one response** on an absolute 1–5 scale and decides whether it is good enough to train on. A pairwise preference rubric asks "which is better?"; this one asks "is this good enough to teach a model?"

## Dimensions

| Dimension | 5 | 3 | 1 |
|---|---|---|---|
| **Correctness** | Every claim and every line of code is right | Core answer right, but a secondary claim is wrong or imprecise | Core answer wrong |
| **Completeness** | Covers what the user actually needs, including the obvious follow-up | Answers the literal question; the user will have to ask again | Leaves the main need unmet |
| **Instruction adherence** | Exact format, length and constraints | Minor drift (an extra sentence, a slightly wrong format) | Ignores the instructions |
| **Clarity** | Answer findable in seconds; structure fits the length | Right content, but buried or loosely organised | Confusing or self-contradictory |
| **Tone** | Fits the situation: direct for tasks, warm for distress, never preachy | Slightly off: stiff, over-eager or mildly condescending | Hostile, moralising or dismissive |
| **Concision** | Nothing to cut | Noticeable padding or repetition | Mostly padding |

Scores 2 and 4 sit between the anchors.

## Acceptance rule

Implemented in `src/sft_studio/rubric.py` and checked against the calibration set by `sft-studio calibrate`.

| Decision | Rule | Why |
|---|---|---|
| **Reject** | correctness < 4, **or** any dimension = 1, **or** mean < 3.5 | Wrong content can't be fixed by editing style. A response that fails badly on any one dimension is cheaper to rewrite than to repair. |
| **Accept** | correctness = 5, every dimension ≥ 4, mean ≥ 4.5 | SFT data is copied, not averaged. The model imitates every example, so the bar is "would I want the model to answer exactly like this?" |
| **Revise** | everything else | The output lists the dimensions below 4 so the writer knows what to fix. |

**Correctness must be 5, not just 4, to accept.** A 4 means a secondary claim is wrong, and the model will learn that claim.

## How the rule was calibrated

The first version only rejected responses with low correctness. When it was checked against the calibration set, two "low" examples came out as "revise":

- **CAL-06**, a hostile refusal: technically correct to refuse, but tone 1 and completeness 1.
- **CAL-09**, a bullet list where JSON was required: instruction adherence 1.

Neither can be repaired by editing; both need rewriting. The rule now also rejects any response with a 1 on any dimension, or a mean below 3.5. All 9 calibration examples now match their intended level. Tuning a rule against labelled anchors before applying it to new data is the whole purpose of a calibration set.

## Calibration set (`data/calibration.jsonl`)

Three prompts, each answered at three quality levels, with per-dimension scores and a written justification. New annotators should score these blind and compare their scores before rating real data.

| Prompt | High (accept) | Mid (revise) | Low (reject) |
|---|---|---|---|
| Stacked discount | Correct, explains the misconception | Correct but no explanation | Confirms "30%" |
| Neighbour's Wi-Fi | Brief refusal + 4 alternatives | Curt refusal, 1 alternative | Moralising, no help |
| JSON-only list | Valid JSON only | Correct JSON wrapped in prose | Bullet list, 2 of 3 items |

## Measuring annotator agreement

When two people score the same responses, export each person's scores to CSV (`id` + one column per dimension) and run:

```bash
sft-studio agreement annotator_a.csv annotator_b.csv
```

It reports, per dimension:
- **Exact agreement:** identical scores.
- **±1 agreement:** scores within one point.
- **Quadratic weighted kappa (QWK):** agreement corrected for chance, where a 1-vs-5 disagreement costs 16× more than a 4-vs-5. Above 0.8 is strong. Below 0.6 means the anchors for that dimension need rewording.
