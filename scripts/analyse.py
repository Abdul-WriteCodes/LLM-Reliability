"""Reproducible economic growth decomposition and visualisations."""
from __future__ import annotations
import json
from pathlib import Path
import sys
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from config import START_YEAR, END_YEAR, CORE
DATA = ROOT / "data" / "nigeria_wdi_2010_2025.csv"
OUT = ROOT / "outputs"


def percent_change(a, b):
    """Percentage change from a to b."""
    return 100 * (b / a - 1)


def decompose(df):
    df = df.copy().sort_values("year").reset_index(drop=True)
    for col in CORE:
        df[f"{col}_growth_pct"] = df[col].pct_change(fill_method=None) * 100
        df[f"{col}_index"] = df[col] / df[col].iloc[0] * 100
    df["calculated_gdp_pc"] = df["real_gdp_lcu"] / df["population"]
    df["identity_error_pct"] = (
        (df["calculated_gdp_pc"] / df["real_gdp_per_capita_lcu"]) - 1
    ) * 100
    for col in CORE:
        df[f"logchange_{col}"] = np.log(df[col]).diff()
    df["log_decomposition_residual"] = (
        df["logchange_real_gdp_per_capita_lcu"]
        - (df["logchange_real_gdp_lcu"] - df["logchange_population"])
    )
    return df


def main():
    if not DATA.exists():
        raise SystemExit("Missing WDI snapshot. First run python scripts/fetch_wdi.py")
    OUT.mkdir(parents=True, exist_ok=True)
    df = pd.read_csv(DATA)
    assert df["year"].tolist() == list(range(START_YEAR, END_YEAR + 1)), "Unexpected year coverage"
    df = decompose(df)
    df.to_csv(OUT / "analysis_table.csv", index=False, float_format="%.12g")

    fig, ax = plt.subplots(figsize=(10, 5.5))
    for col, label in [
        ("real_gdp_lcu", "Real GDP"),
        ("real_gdp_per_capita_lcu", "Real GDP per capita"),
        ("population", "Population"),
    ]:
        ax.plot(df["year"], df[f"{col}_index"], marker="o", markersize=3, label=label)
    ax.axhline(100, linewidth=0.9, linestyle="--", alpha=0.5)
    ax.set(xlabel="Year", ylabel=f"Index ({START_YEAR} = 100)", title="Nigeria: aggregate output, population and output per person")
    ax.legend(loc="best")
    ax.grid(axis="y", alpha=0.2)
    fig.tight_layout()
    fig.savefig(OUT / "indexed_growth.png", dpi=180)
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(10, 5.5))
    for col, label in [
        ("real_gdp_lcu", "Real GDP growth"),
        ("real_gdp_per_capita_lcu", "Real GDP per capita growth"),
        ("population", "Population growth"),
    ]:
        ax.plot(df["year"], df[f"{col}_growth_pct"], marker="o", markersize=3, label=label)
    ax.axhline(0, linewidth=0.8, alpha=0.6)
    ax.set(xlabel="Year", ylabel="Annual change (%)", title="Nigeria: annual output and population growth")
    ax.legend(loc="best")
    ax.grid(axis="y", alpha=0.2)
    fig.tight_layout()
    fig.savefig(OUT / "annual_growth.png", dpi=180)
    plt.close(fig)

    first, last = df.iloc[0], df.iloc[-1]
    summary = {
        "start_year": int(first["year"]), "end_year": int(last["year"]),
        "n_annual_observations": int(len(df)),
        "real_gdp_total_change_pct": percent_change(first["real_gdp_lcu"], last["real_gdp_lcu"]),
        "real_gdp_pc_total_change_pct": percent_change(first["real_gdp_per_capita_lcu"], last["real_gdp_per_capita_lcu"]),
        "population_total_change_pct": percent_change(first["population"], last["population"]),
        "years_real_gdp_up_per_capita_down": df.loc[
            (df["real_gdp_lcu_growth_pct"] > 0) & (df["real_gdp_per_capita_lcu_growth_pct"] < 0), "year"
        ].astype(int).tolist(),
        "max_absolute_gdp_population_identity_discrepancy_pct": float(df["identity_error_pct"].abs().max()),
        "max_absolute_annual_log_decomposition_residual": float(df["log_decomposition_residual"].abs().max()),
    }
    (OUT / "key_results.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    findings = f"""# Nigerian growth: computed findings (WDI snapshot)

Period: {START_YEAR}–{END_YEAR} inclusive ({len(df)} annual observations / {END_YEAR - START_YEAR} elapsed years).

- Real GDP cumulative change: **{summary['real_gdp_total_change_pct']:+.2f}%**.
- Real GDP per capita cumulative change: **{summary['real_gdp_pc_total_change_pct']:+.2f}%**.
- Population cumulative change: **{summary['population_total_change_pct']:+.2f}%**.
- Years when real GDP grew but real GDP per capita fell: **{summary['years_real_gdp_up_per_capita_down']}**.
- Largest GDP/population vs reported per-capita identity discrepancy: **{summary['max_absolute_gdp_population_identity_discrepancy_pct']:.6f}%**.

**Interpretation:** Real GDP per capita measures production per person, not median disposable household income,
poverty, or the distribution of economic gains. GDP/population is an accounting identity, not a causal
model of why GDP changes. Additional welfare outcomes require separate data.

Source, indicator definitions, retrieval date and raw API responses are saved in `data/`.
"""
    (OUT / "findings.md").write_text(findings, encoding="utf-8")
    if summary["max_absolute_gdp_population_identity_discrepancy_pct"] > 0.25:
        print("WARNING: GDP/population not close to reported GDP per capita; review series definition and vintages.")
    print(findings)

if __name__ == "__main__":
    main()
