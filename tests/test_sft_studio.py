import copy
import json

import pytest

from sft_studio.data import load_calibration, load_pairs, validate_schema
from sft_studio.export import export, stratified_split, to_alpaca
from sft_studio.lint import jaccard, lint_dataset, lint_pair, near_duplicates
from sft_studio.rubric import ACCEPT, REJECT, REVISE, agreement, decide, quadratic_weighted_kappa
from sft_studio.verify import count_sentences, verify_dataset, verify_pair


def _pair(pid):
    return copy.deepcopy(next(p for p in load_pairs() if p["id"] == pid))


# ---------- bundled data passes every gate ----------

def test_schema_valid():
    assert validate_schema(load_pairs()) == []


def test_no_lint_errors():
    assert [i for i in lint_dataset(load_pairs()) if i["level"] == "error"] == []


def test_all_verifiable_pairs_pass():
    failures = [r for r in verify_dataset(load_pairs()) if r["status"] == "fail"]
    assert failures == []


def test_calibration_matches_acceptance_rule():
    expected = {"high": ACCEPT, "mid": REVISE, "low": REJECT}
    for c in load_calibration():
        assert decide(c["scores"])["decision"] == expected[c["level"]], c["id"]


# ---------- schema ----------

def test_schema_rejects_bad_turn_order():
    p = _pair("SFT-001")
    p["messages"].reverse()
    assert any("should be 'user'" in e for e in validate_schema([p]))


def test_schema_requires_assistant_last():
    p = _pair("SFT-015")
    p["messages"] = p["messages"][:3]
    assert any("end with an assistant" in e for e in validate_schema([p]))


# ---------- lint ----------

def test_lint_catches_banned_phrase_and_placeholder():
    p = _pair("SFT-001")
    p["messages"][-1]["content"] = "Great question! TODO: finish this."
    checks = {i["check"] for i in lint_pair(p)}
    assert {"banned_phrase", "placeholder"} <= checks


def test_lint_catches_unbalanced_fence():
    p = _pair("SFT-003")
    p["messages"][-1]["content"] += "\n```python\nprint(1)"
    assert "code_fence" in {i["check"] for i in lint_pair(p)}


def test_near_duplicate_detection():
    a, b = _pair("SFT-001"), _pair("SFT-001")
    b["id"] = "COPY"
    b["messages"][0]["content"] += " Please."
    assert near_duplicates([a, b])
    assert jaccard("the cat sat on the mat", "quantum field theory is hard") == 0.0


# ---------- verification ----------

def test_python_verification_catches_broken_code():
    p = _pair("SFT-003")
    p["messages"][-1]["content"] = p["messages"][-1]["content"].replace(
        "result.append(item)", "result.insert(0, item)", 1)
    assert verify_pair(p)["status"] == "fail"


def test_sql_verification_catches_wrong_order():
    p = _pair("SFT-005")
    p["messages"][-1]["content"] = p["messages"][-1]["content"].replace("DESC\nLIMIT", "ASC\nLIMIT", 1)
    assert verify_pair(p)["status"] == "fail"


def test_json_verification_catches_extra_prose():
    p = _pair("SFT-011")
    p["messages"][-1]["content"] = "Here you go:\n" + p["messages"][-1]["content"]
    assert verify_pair(p)["status"] == "fail"


def test_numeric_verification_catches_wrong_value():
    p = _pair("SFT-007")
    p["messages"][-1]["content"] = p["messages"][-1]["content"].replace("28%", "30%")
    assert verify_pair(p)["status"] == "fail"


def test_sentence_counter_ignores_decimals():
    assert count_sentences("Pi is 3.14 roughly. That's it.") == 2


# ---------- rubric ----------

def _scores(**overrides):
    base = dict(correctness=5, completeness=5, instruction_adherence=5, clarity=5, tone=5, concision=5)
    base.update(overrides)
    return base


def test_decide_paths():
    assert decide(_scores())["decision"] == ACCEPT
    assert decide(_scores(completeness=3))["decision"] == REVISE
    assert decide(_scores(correctness=3))["decision"] == REJECT
    assert decide(_scores(tone=1))["decision"] == REJECT


def test_decide_lists_dimensions_to_fix():
    assert decide(_scores(clarity=3, concision=2))["fix"] == ["clarity", "concision"]


def test_qwk_perfect_and_penalises_distance():
    assert quadratic_weighted_kappa([1, 3, 5, 4], [1, 3, 5, 4]) == pytest.approx(1.0)
    near = quadratic_weighted_kappa([1, 2, 3, 4, 5], [2, 2, 3, 4, 4])
    far = quadratic_weighted_kappa([1, 2, 3, 4, 5], [5, 4, 3, 2, 1])
    assert near > 0.5 > far


def test_agreement_summary():
    r = agreement([5, 4, 3], [5, 3, 1])
    assert r["exact"] == pytest.approx(1 / 3) and r["within_one"] == pytest.approx(2 / 3)


# ---------- export ----------

def test_split_is_disjoint_complete_and_reproducible():
    pairs = load_pairs()
    train, val = stratified_split(pairs, 0.2, seed=7)
    ids = [p["id"] for p in train + val]
    assert sorted(ids) == sorted(p["id"] for p in pairs) and len(set(ids)) == len(ids)
    assert [p["id"] for p in val] == [p["id"] for p in stratified_split(pairs, 0.2, seed=7)[1]]


def test_split_puts_multi_example_categories_in_both():
    train, val = stratified_split(load_pairs(), 0.2)
    for cat in ("coding", "explanation"):
        assert any(p["category"] == cat for p in train)
        assert any(p["category"] == cat for p in val)


def test_alpaca_skips_multiturn():
    assert to_alpaca(_pair("SFT-015")) is None
    assert to_alpaca(_pair("SFT-007"))["output"].startswith("No.")


def test_export_writes_valid_chat_jsonl(tmp_path):
    counts = export(load_pairs(), tmp_path, "chat", system="Be concise.")
    rows = [json.loads(l) for l in (tmp_path / "train.jsonl").read_text().splitlines()]
    assert len(rows) == counts["train"]
    assert rows[0]["messages"][0] == {"role": "system", "content": "Be concise."}
