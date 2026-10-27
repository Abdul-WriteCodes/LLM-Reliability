"""Grade objectively scorable LLM outputs and create a review file for claim-level annotation.

Required input: results/model_outputs.jsonl (one JSON object per response):
{"item_id":"NGA-WDI-001", "condition":"A_table_only", "model":"provider/model-id", "repeat":1,
 "response":{"answer":"...", "numeric_value":1.23, "yes_no":null, "evidence":"...", "confidence":0.7, "abstained":false}}

Does not pretend keyword matching is a valid hallucination detector.
"""
from __future__ import annotations
import json
from pathlib import Path
import re
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "results"


def records(path):
    with path.open(encoding="utf-8") as fp:
        return [json.loads(s) for s in fp if s.strip()]


def normalize_yes_no(value):
    if value is None:
        return None
    normalized = str(value).strip().lower()
    if normalized in ("yes", "true"):
        return "yes"
    if normalized in ("no", "false"):
        return "no"
    return None


def grade_one(item, response):
    answer_type = item["answer_type"]
    if answer_type == "number":
        try:
            v = float(response.get("numeric_value"))
        except (TypeError, ValueError):
            return None, "manual: missing or invalid numeric_value"
        # Values are rounded to 2dp in the benchmark. Allow <=0.25 pp tolerance.
        return abs(v - float(item["reference"])) <= 0.25, "automatic numeric"
    if answer_type == "yes_no":
        val = normalize_yes_no(response.get("yes_no"))
        if val is None:
            return None, "manual: missing yes_no field"
        return val == item["reference"], "automatic binary"
    # Interpretation requires claim-level human scoring, not keyword matching.
    return None, "human: correctness + unsupported-claim annotation"


def main():
    path = RESULTS / "model_outputs.jsonl"
    key_path = RESULTS / "answer_key.jsonl"
    if not path.exists():
        raise SystemExit("Provide results/model_outputs.jsonl using the documented response format, then rerun")
    if not key_path.exists():
        raise SystemExit("Missing answer_key.jsonl. Run python scripts/build_benchmark.py")
    key = {row["item_id"]: row for row in records(key_path)}
    rows = []
    for output in records(path):
        item = key.get(output["item_id"])
        if item is None:
            raise ValueError(f"Unknown item ID: {output['item_id']}")
        response = output.get("response", {})
        if isinstance(response, str):
            try:
                response = json.loads(re.sub(r'^```(?:json)?|```$', '', response.strip(), flags=re.I).strip())
            except json.JSONDecodeError:
                response = {"answer": response}
        if not isinstance(response, dict):
            response = {"answer": str(response)}
        correct, grading = grade_one(item, response)
        rows.append({
            "item_id": item["item_id"], "category": item["category"], "condition": output["condition"],
            "model": output["model"], "repeat": output["repeat"], "automated_correct": correct,
            "grading_method": grading, "human_correct": "", "unsupported_claim": "",
            "contradicted_data": "", "fabricated_statistic": "", "unjustified_causality": "",
            "appropriate_abstention": "", "notes": "", "response_text": json.dumps(response, ensure_ascii=False),
        })
    df = pd.DataFrame(rows)
    (RESULTS / "review_annotations.csv").parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(RESULTS / "review_annotations.csv", index=False)
    scored = df.loc[df["automated_correct"].notna()].copy()
    if not scored.empty:
        scored["automated_correct"] = scored["automated_correct"].astype(bool)
        summary = scored.groupby(["model", "condition"], as_index=False).agg(
            evaluated=("automated_correct", "size"),
            accuracy=("automated_correct", "mean"))
        summary.to_csv(RESULTS / "objective_accuracy.csv", index=False)
        print(summary.to_string(index=False))
    print(f"Saved {len(df)} response annotation rows; human review is REQUIRED for unsupported claims")

if __name__ == "__main__":
    main()
