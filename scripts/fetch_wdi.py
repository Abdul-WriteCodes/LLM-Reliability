""" This script pulls dataset from the World Development Indicators (WDI) 

Key Operation: Download WDI Nigeria data, preserving raw source responses and fetch metadata.

Run this on the repository root to execute this script: `python scripts/fetch_wdi.py` 
Note: Running this requires internet access to the World Bank API for it to be successful in pulling dataset.
"""
from __future__ import annotations
import json
from datetime import datetime, timezone
from pathlib import Path
import sys
import time
import requests
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from config import CORE, COUNTRY, START_YEAR, END_YEAR, INDICATORS

DATA = ROOT / "data"
RAW = DATA / "raw"


def get_indicator(session: requests.Session, code: str):
    url = f"https://api.worldbank.org/v2/country/{COUNTRY}/indicator/{code}"
    params = {"format": "json", "date": f"{START_YEAR}:{END_YEAR}", "per_page": 2000}
    for attempt in range(3):
        try:
            response = session.get(url, params=params, timeout=35)
            response.raise_for_status()
            payload = response.json()
            if not (isinstance(payload, list) and len(payload) == 2 and isinstance(payload[1], list)):
                raise ValueError(f"Unexpected WDI API response for {code}: {str(payload)[:400]}")
            return response.url, payload
        except (requests.RequestException, ValueError):
            if attempt == 2:
                raise
            time.sleep(2 ** attempt)
    raise RuntimeError("unreachable")


def main():
    RAW.mkdir(parents=True, exist_ok=True)
    data_by_year = {year: {"year": year} for year in range(START_YEAR, END_YEAR + 1)}
    session = requests.Session()
    session.headers.update({"User-Agent": "NigeriaWDIResearch/1.0 (academic reproducibility)"})
    audit = {
        "country": COUNTRY,
        "start_year": START_YEAR,
        "end_year": END_YEAR,
        "retrieved_at_utc": datetime.now(timezone.utc).isoformat(),
        "source": "World Bank World Development Indicators API v2",
        "api": {},
        "indicator_codes": INDICATORS,
        "licenses": ["World Bank indicator pages: CC BY-4.0; attribution required"],
    }
    for name, code in INDICATORS.items():
        url, payload = get_indicator(session, code)
        (RAW / f"{code.replace('.', '_')}.json").write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        audit["api"][name] = url
        for row in payload[1]:
            year = int(row["date"])
            if year in data_by_year:
                data_by_year[year][name] = row.get("value")
        print(f"Fetched {name} ({code})")
    df = pd.DataFrame(sorted(data_by_year.values(), key=lambda r: r["year"]))
    for col in INDICATORS:
        df[col] = pd.to_numeric(df.get(col), errors="coerce")
    for col in CORE:
        missing = df.loc[df[col].isna(), "year"].tolist()
        if missing:
            raise ValueError(f"Core indicator {col} missing for years {missing}; don't silently interpolate")
    if (df["population"] <= 0).any() or (df["real_gdp_lcu"] <= 0).any():
        raise ValueError("GDP and population must be positive")
    df.to_csv(DATA / "nigeria_wdi_2010_2025.csv", index=False, float_format="%.12g")
    (DATA / "provenance.json").write_text(json.dumps(audit, indent=2), encoding="utf-8")
    print("Saved frozen local snapshot and source provenance in data/")

if __name__ == "__main__":
    main()
