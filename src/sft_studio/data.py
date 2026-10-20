"""Load SFT pairs and calibration examples, and check their structure."""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT / "data"

DIFFICULTIES = {"easy", "medium", "hard"}
VERIFICATION_TYPES = {"manual", "python_exec", "sql_exec", "json", "numeric", "sentence_count"}


def read_jsonl(path: Path) -> list[dict]:
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def load_pairs(path: Path = DATA_DIR / "sft_pairs.jsonl") -> list[dict]:
    return read_jsonl(path)


def load_calibration(path: Path = DATA_DIR / "calibration.jsonl") -> list[dict]:
    return read_jsonl(path)


def prompt_text(pair: dict) -> str:
    """The first user message: the prompt that defines the example."""
    return next(m["content"] for m in pair["messages"] if m["role"] == "user")


def final_response(pair: dict) -> str:
    return pair["messages"][-1]["content"]


def validate_schema(pairs: list[dict]) -> list[str]:
    errors, seen = [], set()
    for p in pairs:
        pid = p.get("id", "?")
        if pid in seen:
            errors.append(f"{pid}: duplicate id")
        seen.add(pid)
        if not p.get("category"):
            errors.append(f"{pid}: missing category")
        if p.get("difficulty") not in DIFFICULTIES:
            errors.append(f"{pid}: difficulty must be one of {sorted(DIFFICULTIES)}")
        if p.get("verification", {}).get("type") not in VERIFICATION_TYPES:
            errors.append(f"{pid}: unknown verification type")

        msgs = p.get("messages", [])
        if not msgs:
            errors.append(f"{pid}: no messages")
            continue
        expected = "user"
        for i, m in enumerate(msgs):
            if m.get("role") != expected:
                errors.append(f"{pid}: message {i} should be '{expected}', got '{m.get('role')}'")
                break
            if not m.get("content", "").strip():
                errors.append(f"{pid}: message {i} is empty")
            expected = "assistant" if expected == "user" else "user"
        if msgs[-1].get("role") != "assistant":
            errors.append(f"{pid}: conversation must end with an assistant message")
    return errors
