"""Command-line entry point.

    sft-studio check                 schema + lint + verification (exit 1 on any error)
    sft-studio calibrate             apply the acceptance rule to the calibration set
    sft-studio agreement a.csv b.csv inter-annotator agreement on rubric scores
    sft-studio export --format chat  stratified train/val files
"""

import argparse
import csv
import sys
from collections import Counter
from pathlib import Path

from .data import ROOT, load_calibration, load_pairs, validate_schema
from .export import export
from .lint import lint_dataset
from .rubric import DIMENSIONS, agreement, decide
from .verify import verify_dataset


def cmd_check(_args) -> int:
    pairs = load_pairs()
    print(f"{len(pairs)} pairs · categories: "
          + ", ".join(f"{c} ({n})" for c, n in sorted(Counter(p['category'] for p in pairs).items())))

    schema = validate_schema(pairs)
    print(f"\nSchema: {'OK' if not schema else f'{len(schema)} error(s)'}")
    for e in schema:
        print(f"  ERROR {e}")

    issues = lint_dataset(pairs)
    errors = [i for i in issues if i["level"] == "error"]
    print(f"\nLint: {len(errors)} error(s), {len(issues) - len(errors)} warning(s)")
    for i in issues:
        print(f"  {i['level'].upper():7} {i['id']:8} {i['check']}: {i['detail']}")

    results = verify_dataset(pairs)
    status = Counter(r["status"] for r in results)
    print(f"\nVerification: {status['pass']} passed, {status['fail']} failed, "
          f"{status['manual']} need human review")
    for r in results:
        if r["status"] != "manual":
            print(f"  {r['status'].upper():4} {r['id']} [{r['type']}] {r['detail']}")

    failed = bool(schema or errors or status["fail"])
    print("\nRESULT:", "FAIL" if failed else "PASS")
    return 1 if failed else 0


def cmd_calibrate(_args) -> int:
    expected = {"high": "accept", "mid": "revise", "low": "reject"}
    mismatches = 0
    print(f"{'ID':7} {'Level':5} {'Mean':>5}  Decision  Fix")
    for c in load_calibration():
        d = decide(c["scores"])
        ok = d["decision"] == expected[c["level"]]
        mismatches += not ok
        print(f"{c['id']:7} {c['level']:5} {d['mean']:5.2f}  {d['decision']:8}  "
              f"{', '.join(d['fix']) or '-'}{'' if ok else '   <-- unexpected'}")
    print("\nAcceptance rule matches every calibration level." if not mismatches
          else f"\n{mismatches} calibration example(s) disagree with the acceptance rule.")
    return 1 if mismatches else 0


def _read_scores(path: Path) -> dict:
    """CSV with columns: id, then one column per rubric dimension."""
    with open(path, newline="", encoding="utf-8") as f:
        return {row["id"]: {d: int(row[d]) for d in DIMENSIONS} for row in csv.DictReader(f)}


def cmd_agreement(args) -> int:
    a, b = _read_scores(args.annotator_a), _read_scores(args.annotator_b)
    shared = sorted(set(a) & set(b))
    if not shared:
        print("No shared ids between the two files.")
        return 1
    print(f"{len(shared)} items scored by both annotators\n")
    print(f"{'Dimension':22} {'Exact':>6} {'±1':>6} {'QWK':>6}")
    for d in DIMENSIONS:
        r = agreement([a[i][d] for i in shared], [b[i][d] for i in shared])
        print(f"{d:22} {r['exact']:6.0%} {r['within_one']:6.0%} {r['qwk']:6.2f}")
    return 0


def cmd_export(args) -> int:
    counts = export(load_pairs(), args.out, args.format, args.val_ratio, args.seed, args.system)
    print(f"Wrote {counts['train']} train / {counts['val']} val records to {args.out}")
    skipped = counts["train_skipped_multiturn"] + counts["val_skipped_multiturn"]
    if skipped:
        print(f"Skipped {skipped} multi-turn example(s): the alpaca format is single-turn only.")
    return 0


def main(argv=None) -> None:
    p = argparse.ArgumentParser(description="Build, verify and grade SFT data.")
    sub = p.add_subparsers(dest="command", required=True)
    sub.add_parser("check", help="Validate, lint and verify the dataset")
    sub.add_parser("calibrate", help="Check the acceptance rule against calibration examples")

    ag = sub.add_parser("agreement", help="Inter-annotator agreement from two score CSVs")
    ag.add_argument("annotator_a", type=Path)
    ag.add_argument("annotator_b", type=Path)

    ex = sub.add_parser("export", help="Write train/val files")
    ex.add_argument("--format", choices=["chat", "alpaca"], default="chat")
    ex.add_argument("--val-ratio", type=float, default=0.2)
    ex.add_argument("--seed", type=int, default=42)
    ex.add_argument("--system", help="Optional system prompt added to every chat record")
    ex.add_argument("--out", type=Path, default=ROOT / "build")

    args = p.parse_args(argv)
    handler = {"check": cmd_check, "calibrate": cmd_calibrate,
               "agreement": cmd_agreement, "export": cmd_export}[args.command]
    sys.exit(handler(args))


if __name__ == "__main__":
    main()
