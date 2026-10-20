# sft-data-studio

**Supervised fine-tuning data you can trust: hand-written prompt–response pairs, mechanically verified, graded against a calibrated rubric.**

A fine-tuned model copies its training examples, mistakes included. A wrong number, a broken code snippet or a "Great question!" opener in SFT data becomes a habit of the model. This repo treats data quality as an engineering problem:

1. **16 prompt–response pairs** across 14 task types, written to a documented standard ([`docs/WRITING_GUIDE.md`](docs/WRITING_GUIDE.md)).
2. **Automated verification.** Code is executed, SQL is run, JSON is parsed and numbers are recomputed.
3. **An output-quality rubric** with 6 dimensions, an accept/revise/reject rule, and a calibration set that the rule is tested against ([`docs/RUBRIC.md`](docs/RUBRIC.md)).
4. **Quality gates and export.** Lint rules, near-duplicate detection, and a stratified train/val split in chat or Alpaca format.

```bash
pip install -e ".[dev]"
sft-studio check        # schema + lint + verification → PASS / FAIL
sft-studio calibrate    # does the acceptance rule match the calibration labels?
sft-studio export       # build/train.jsonl + build/val.jsonl
pytest                  # 22 tests
```

---

## The dataset

`data/sft_pairs.jsonl`. Each record holds the conversation, a category, a difficulty, the skills it demonstrates, and how it is verified.

| Category | Example prompt | What the response demonstrates | Verified by |
|---|---|---|---|
| coding | Remove duplicates, keep order | O(n) solution, one-liner alternative, hashability caveat | **executed + 4 assertions** |
| coding | Top 3 customers in SQL | Dialect differences, tie handling with `DENSE_RANK` | **run on SQLite test table** |
| debugging | Lambdas all print 2 | Explains late binding; two fixes | **executed + assertion** |
| data_analysis | Is variant B better? | z-test, CI, sample-size estimate, a decision | **values recomputed** |
| math | Is 20% + 10% off = 30%? | Corrects the misconception with a worked example | **values recomputed** |
| structured_output | JSON only, 3 items | Strict format compliance | **parsed + schema-checked** |
| summarization | Exactly two sentences | Hard length constraint, nothing lost | **sentence count** |
| multi_turn | km → "and in metres?" | Context carried across turns | **values recomputed** |
| explanation | Overfitting; list vs tuple | Audience-matched analogy, decision rule | manual |
| spreadsheet | COUNTIF containing "late" | Wildcards, the "chocolate" false match | manual |
| writing | Make this email concise | Rewrite **plus** what changed and why | manual |
| ambiguity | How long to boil an egg? | Covers the ambiguity in a table instead of guessing | manual |
| safety | Neighbour's Wi-Fi | One-line refusal, four legal alternatives | manual |
| false_premise | "We only use 10% of our brain" | Corrects the myth, then serves the real goal | manual |
| supportive | Failed my driving test | Empathy, then concrete next steps and a question | manual |

**8 of 16 pairs are machine-verified**, and every one passes. The rest are marked for human review rather than pretending to be checked.

## Quality gates (`sft-studio check`)

| Gate | Catches |
|---|---|
| Schema | Turns out of order, empty messages, conversations not ending on the assistant |
| Banned phrases | "Great question", "As an AI", "I hope this helps", "delve into"… |
| Placeholders | `TODO`, `TBD`, `[insert…]` left in a response |
| Code fences | Unclosed ``` blocks that break rendering |
| Near-duplicates | Prompts with ≥ 60% trigram overlap (inflate the dataset, leak into validation) |
| Category balance | Any category above 25% of the data |
| Verification | Code that doesn't run, SQL that returns the wrong rows, invalid JSON, wrong numbers |

The command exits with status 1 on any failure, so it can be used as a CI check.

## The rubric

| Dimension | Asks |
|---|---|
| Correctness | Is every claim and line of code right? |
| Completeness | Does it meet the real need, not just the literal question? |
| Instruction adherence | Exact format, length, constraints? |
| Clarity | Can the answer be found in seconds? |
| Tone | Fits the situation; never preachy? |
| Concision | Anything to cut? |

**Accept** needs correctness = 5 and every dimension ≥ 4. **Reject** applies if correctness < 4, any dimension = 1, or the mean is < 3.5. Everything else is **revise**, with the weak dimensions listed.

**The calibration set changed the rule.** The first version only rejected wrong answers. Run against the calibration set, it sent a hostile refusal and a non-JSON reply to "revise", although neither is fixable by editing. The rule was tightened until all 9 calibration examples matched their labels:

```
$ sft-studio calibrate
ID      Level  Mean  Decision  Fix
CAL-01  high   5.00  accept    -
CAL-02  mid    4.33  revise    completeness
CAL-03  low    3.33  reject    correctness, completeness
...
CAL-09  low    3.00  reject    completeness, instruction_adherence, clarity

Acceptance rule matches every calibration level.
```

For multiple annotators, `sft-studio agreement a.csv b.csv` reports exact agreement, ±1 agreement and **quadratic weighted kappa** per dimension, which shows which rubric anchors need rewording.

## Export

```bash
sft-studio export --format chat --system "You are a helpful assistant."
sft-studio export --format alpaca      # single-turn only; multi-turn pairs are skipped with a notice
```

The split is **stratified by category**, so categories with several examples appear in both train and validation. It is seeded, so it's reproducible.

## Project structure

```
sft-data-studio/
├── data/
│   ├── sft_pairs.jsonl        16 verified prompt–response pairs
│   └── calibration.jsonl      9 rubric anchor examples (3 prompts × 3 levels)
├── docs/
│   ├── RUBRIC.md              dimensions, anchors, acceptance rule, agreement
│   └── WRITING_GUIDE.md       the standard every response follows
├── src/sft_studio/
│   ├── verify.py              executes code/SQL, parses JSON, checks numbers
│   ├── lint.py                banned phrases, placeholders, duplicates, balance
│   ├── rubric.py              accept/revise/reject + quadratic weighted kappa
│   ├── export.py              stratified split, chat / alpaca formats
│   └── data.py · cli.py
└── tests/                     22 tests
```

## Quick start

```bash
git clone https://github.com/ikokougochukwu69-glitch/sft-data-studio.git
cd sft-data-studio
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
sft-studio check
```

No API key is needed for anything in this repo.

## License

MIT
