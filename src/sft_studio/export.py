"""Stratified train/validation split and export to common fine-tuning formats."""

import json
import random
from collections import defaultdict
from pathlib import Path


def stratified_split(pairs: list[dict], val_ratio: float = 0.2, seed: int = 42):
    """Split so every category with 2+ examples appears in both train and validation.

    Single-example categories can't be split, so they go to training first and
    are then drawn at random to top validation up to the target ratio.
    """
    rng = random.Random(seed)
    by_cat = defaultdict(list)
    for p in pairs:
        by_cat[p["category"]].append(p)

    train, val = [], []
    for cat in sorted(by_cat):
        items = by_cat[cat][:]
        rng.shuffle(items)
        n_val = round(len(items) * val_ratio)
        if len(items) >= 2:
            n_val = max(1, min(n_val, len(items) - 1))
        else:
            n_val = 0  # can't split one example; may be drawn into val below
        val += items[:n_val]
        train += items[n_val:]

    target = round(len(pairs) * val_ratio)
    singletons = [p for p in train if len(by_cat[p["category"]]) == 1]
    rng.shuffle(singletons)
    for p in singletons[: max(0, target - len(val))]:
        train.remove(p)
        val.append(p)
    return train, val


def to_chat(pair: dict, system: str | None = None) -> dict:
    """OpenAI-style chat fine-tuning record: {"messages": [...]}."""
    msgs = [{"role": m["role"], "content": m["content"]} for m in pair["messages"]]
    if system:
        msgs = [{"role": "system", "content": system}] + msgs
    return {"messages": msgs}


def to_alpaca(pair: dict) -> dict | None:
    """Instruction / input / output record. Single-turn only; returns None otherwise."""
    if len(pair["messages"]) != 2:
        return None
    return {"instruction": pair["messages"][0]["content"], "input": "", "output": pair["messages"][1]["content"]}


def export(pairs, out_dir: Path, fmt: str = "chat", val_ratio: float = 0.2,
           seed: int = 42, system: str | None = None) -> dict:
    train, val = stratified_split(pairs, val_ratio, seed)
    out_dir.mkdir(parents=True, exist_ok=True)
    counts = {}
    for name, split in (("train", train), ("val", val)):
        records = [to_chat(p, system) if fmt == "chat" else to_alpaca(p) for p in split]
        skipped = records.count(None)
        records = [r for r in records if r is not None]
        with open(out_dir / f"{name}.jsonl", "w", encoding="utf-8") as f:
            for r in records:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
        counts[name] = len(records)
        counts[f"{name}_skipped_multiturn"] = skipped
    return counts
