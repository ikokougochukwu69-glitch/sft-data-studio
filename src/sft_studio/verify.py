"""Mechanically verify the claims in SFT responses.

A wrong answer in fine-tuning data is worse than a missing one: the model
learns to say it confidently. Anything checkable gets checked.
"""

import contextlib
import io
import json
import re
import sqlite3

from .data import final_response

_BLOCK = re.compile(r"```(\w*)\n(.*?)```", re.DOTALL)


def code_blocks(text: str, language: str) -> list[str]:
    return [body for lang, body in _BLOCK.findall(text) if lang == language]


def _python_exec(pair, spec):
    blocks = code_blocks(final_response(pair), "python")
    namespace: dict = {}
    with contextlib.redirect_stdout(io.StringIO()):  # keep example prints out of the report
        exec(blocks[spec["block"]], namespace)
        for test in spec["tests"]:
            exec(test, namespace)


def _sql_exec(pair, spec):
    query = code_blocks(final_response(pair), "sql")[spec["block"]]
    con = sqlite3.connect(":memory:")
    for stmt in spec["setup"]:
        con.execute(stmt)
    rows = [list(r) for r in con.execute(query).fetchall()]
    if rows != spec["expected"]:
        raise AssertionError(f"query returned {rows}, expected {spec['expected']}")


def _json(pair, spec):
    data = json.loads(final_response(pair))
    if spec.get("expect_type") == "list" and not isinstance(data, list):
        raise AssertionError("expected a JSON array")
    if "length" in spec and len(data) != spec["length"]:
        raise AssertionError(f"expected {spec['length']} items, got {len(data)}")
    for item in data:
        if set(item) != set(spec["required_keys"]):
            raise AssertionError(f"item keys {sorted(item)} != {sorted(spec['required_keys'])}")


def _numeric(pair, spec):
    text = " ".join(m["content"] for m in pair["messages"] if m["role"] == "assistant")
    missing = [s for s in spec["must_contain"] if s not in text]
    if missing:
        raise AssertionError(f"response is missing expected values: {missing}")


def count_sentences(text: str) -> int:
    # Split on . ! ? followed by whitespace or end of text; ignores decimals like 7.5.
    return len([s for s in re.split(r"(?<=[.!?])\s+", text.strip()) if s])


def _sentence_count(pair, spec):
    n = count_sentences(final_response(pair))
    if n != spec["expected"]:
        raise AssertionError(f"{n} sentences, expected {spec['expected']}")


CHECKS = {
    "python_exec": _python_exec,
    "sql_exec": _sql_exec,
    "json": _json,
    "numeric": _numeric,
    "sentence_count": _sentence_count,
}


def verify_pair(pair: dict) -> dict:
    spec = pair.get("verification", {"type": "manual"})
    kind = spec["type"]
    if kind == "manual":
        return {"id": pair["id"], "type": kind, "status": "manual", "detail": "needs human review"}
    try:
        CHECKS[kind](pair, spec)
        return {"id": pair["id"], "type": kind, "status": "pass", "detail": ""}
    except Exception as e:  # report every failure the same way
        return {"id": pair["id"], "type": kind, "status": "fail", "detail": f"{type(e).__name__}: {e}"}


def verify_dataset(pairs: list[dict]) -> list[dict]:
    return [verify_pair(p) for p in pairs]
