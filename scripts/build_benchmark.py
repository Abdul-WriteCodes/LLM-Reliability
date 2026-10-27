"""Generate benchmark questions and confidential answer key from the frozen WDI snapshot.

Important: give models ONLY benchmark_prompts.jsonl; never include answer_key.jsonl.
These are tabular, text-only tests; any future chart-based comparison is a separate study arm.
"""
from __future__ import annotations
import json
from pathlib import Path
import sys
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from config import START_YEAR, END_YEAR
DATA = ROOT / "data" / "nigeria_wdi_2010_2025.csv"
OUT = ROOT / "results"


def pct(start, end):
    return 100.0 * (end / start - 1.0)


def truth(condition):
    return "yes" if condition else "no"


def build_items(df):
    d = df.set_index("year")
    measures = [
        ("real_gdp_lcu", "real GDP (constant LCU)"),
        ("real_gdp_per_capita_lcu", "real GDP per capita (constant LCU)"),
        ("population", "total population"),
    ]
    spans = [(2010, 2015), (2015, 2020), (2020, 2025), (2010, 2025)]
    items = []

    # 12 objectively graded numeric-change questions.
    for name, label in measures:
        for a, b in spans:
            value = pct(float(d.loc[a, name]), float(d.loc[b, name]))
            items.append({
                "category": "numeric_change", "answer_type": "number",
                "question": f"What was the cumulative percentage change in {label} from {a} to {b}? Return a signed percentage rounded to 2 decimal places.",
                "reference": round(value, 2), "years": [a, b],
            })

    # 6 objectively graded two-year directionality questions.
    for a, b in [(2010, 2015), (2015, 2016), (2016, 2020), (2020, 2021), (2021, 2025), (2010, 2025)]:
        gdp_up = float(d.loc[b, "real_gdp_lcu"]) > float(d.loc[a, "real_gdp_lcu"])
        pc_down = float(d.loc[b, "real_gdp_per_capita_lcu"]) < float(d.loc[a, "real_gdp_per_capita_lcu"])
        items.append({
            "category": "divergence", "answer_type": "yes_no",
            "question": f"Between {a} and {b}, did real GDP increase while real GDP per capita decreased? Answer yes or no and cite the two relevant indicator changes.",
            "reference": truth(gdp_up and pc_down), "years": [a, b],
        })

    # 6 questions requiring a defensible refusal to infer unsupported household outcomes.
    unsupported = [
        "the percentage of Nigerians living below the poverty line fell from 2010 to 2025",
        "median household disposable income rose from 2010 to 2025",
        "income inequality fell from 2010 to 2025",
        "the national unemployment rate fell from 2010 to 2025",
        "all Nigerian households became wealthier from 2010 to 2025",
        "economic policy was the sole cause of changes in real GDP per capita",
    ]
    for claim in unsupported:
        items.append({
            "category": "evidence_limits", "answer_type": "insufficient_evidence",
            "question": f"Based ONLY on the three supplied indicators, can we establish that {claim}? State whether the evidence is sufficient, and why.",
            "reference": "insufficient_evidence", "years": [2010, 2025],
        })

    # 6 basic temporal and statistical questions, graded yes/no.
    for a, b in [(2010, 2015), (2015, 2020), (2020, 2025)]:
        pc_up = float(d.loc[b, "real_gdp_per_capita_lcu"]) > float(d.loc[a, "real_gdp_per_capita_lcu"])
        items.append({
            "category": "trend_sign", "answer_type": "yes_no",
            "question": f"Did Nigeria's real GDP per capita increase overall from {a} to {b}? Answer yes or no and give the endpoints.",
            "reference": truth(pc_up), "years": [a, b],
        })
        gdp_up = float(d.loc[b, "real_gdp_lcu"]) > float(d.loc[a, "real_gdp_lcu"])
        items.append({
            "category": "trend_sign", "answer_type": "yes_no",
            "question": f"Did Nigeria's total real GDP increase overall from {a} to {b}? Answer yes or no and give the endpoints.",
            "reference": truth(gdp_up), "years": [a, b],
        })

    for i, item in enumerate(items, start=1):
        item["item_id"] = f"NGA-WDI-{i:03d}"
    return items


def main():
    if not DATA.exists():
        raise SystemExit("Run python scripts/fetch_wdi.py first")
    df = pd.read_csv(DATA).sort_values("year")
    assert df["year"].tolist() == list(range(START_YEAR, END_YEAR + 1)), "Wrong dataset coverage"
    OUT.mkdir(parents=True, exist_ok=True)
    table_lines = ["Year | Real GDP (trillion constant LCU) | Real GDP per capita (constant LCU) | Population (million)"]
    table_lines.append("--- | ---: | ---: | ---:")
    for row in df.itertuples(index=False):
        table_lines.append(
            f"{int(row.year)} | {row.real_gdp_lcu / 1e12:.9f} | "
            f"{row.real_gdp_per_capita_lcu:.4f} | {row.population / 1e6:.6f}"
        )
    table = "\n".join(table_lines)
    conditions = {
        "A_table_only": "Use only the following WDI-derived dataset:\n\n" + table,
        "B_with_metadata": "Use only the following WDI-derived dataset:\n\n" + table +
           "\n\nDefinitions: Real GDP is inflation-adjusted aggregate production. "
           "GDP per capita is GDP divided by total population; it is not the median household income. "
           "Population is total residents. Values are annual; all GDP currency series use constant local-currency units.",
        "C_with_verification": "Use only the following WDI-derived dataset:\n\n" + table +
           "\n\nDefinitions: Real GDP is inflation-adjusted aggregate production. "
           "GDP per capita is GDP divided by total population; it is not the median household income. "
           "Population is total residents. Values are annual; all GDP currency series use constant local-currency units. "
           "Verify the indicated years and denominators before responding. Do not infer causation, "
           "median household welfare or inequality from these three series alone. "
           "If evidence is insufficient, say so rather than inventing supporting data.",
    }
    answer_key = []
    prompts = []
    for item in build_items(df):
        answer_key.append({
            "item_id": item["item_id"], "category": item["category"],
            "answer_type": item["answer_type"], "reference": item["reference"],
            "years": item["years"], "question": item["question"],
        })
        for condition, context in conditions.items():
            prompts.append({
                "item_id": item["item_id"], "category": item["category"],
                "condition": condition,
                "prompt": context + "\n\nQUESTION: " + item["question"] +
                          "\n\nRespond with a JSON object containing: "
                          "answer (short plain text), numeric_value (number or null), "
                          "yes_no (yes/no/null), evidence (short explanation), "
                          "confidence (0 to 1), and abstained (true/false).",
            })
    with (OUT / "answer_key.jsonl").open("w", encoding="utf-8") as fp:
        for row in answer_key:
            fp.write(json.dumps(row, ensure_ascii=False) + "\n")
    with (OUT / "benchmark_prompts.jsonl").open("w", encoding="utf-8") as fp:
        for row in prompts:
            fp.write(json.dumps(row, ensure_ascii=False) + "\n")
    (OUT / "benchmark_manifest.json").write_text(
        json.dumps({"items": len(answer_key), "conditions": list(conditions),
                    "prompts": len(prompts), "dataset_years": [START_YEAR, END_YEAR],
                    "warning": "Do NOT give answer_key.jsonl to the evaluated models. Run each prompt across repeats with fixed recorded model versions."}, indent=2),
        encoding="utf-8")
    print(f"Generated {len(answer_key)} unique questions in {len(conditions)} conditions = {len(prompts)} prompts")

if __name__ == "__main__":
    main()
