import sys
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.analyse import decompose, percent_change
from scripts.build_benchmark import build_items
from scripts.grade import grade_one


def synthetic_data():
    years = list(range(2010, 2026))
    population = [1000.0 * (1.02 ** (year - 2010)) for year in years]
    gdp = [100000.0 * (1.025 ** (year - 2010)) for year in years]
    pc = [g/p for g, p in zip(gdp, population)]
    return pd.DataFrame({"year": years, "population": population,
                         "real_gdp_lcu": gdp, "real_gdp_per_capita_lcu": pc})


def test_exact_log_identity():
    d = decompose(synthetic_data())
    assert d["identity_error_pct"].abs().max() < 1e-9
    assert d["log_decomposition_residual"].abs().max() < 1e-10


def test_cumulative_change():
    assert abs(percent_change(100, 120) - 20) < 1e-9
    assert abs(percent_change(100, 90) + 10) < 1e-9


def test_benchmark_size_and_answers():
    items = build_items(synthetic_data())
    assert len(items) == 30
    assert sum(t["answer_type"] == "number" for t in items) == 12
    assert sum(t["answer_type"] == "yes_no" for t in items) == 12
    assert sum(t["answer_type"] == "insufficient_evidence" for t in items) == 6
    assert all(t["item_id"].startswith("NGA-WDI-") for t in items)


def test_grade_types():
    assert grade_one({"answer_type":"number", "reference": 5.0}, {"numeric_value":5.1})[0] is True
    assert grade_one({"answer_type":"yes_no", "reference":"yes"}, {"yes_no":"no"})[0] is False
    assert grade_one({"answer_type":"insufficient_evidence", "reference":"insufficient_evidence"}, {"answer":"No proof"})[0] is None
