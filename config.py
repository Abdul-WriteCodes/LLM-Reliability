"""Frozen defaults for the Nigeria WDI + LLM interpretation research."""
START_YEAR = 2010
END_YEAR = 2025  # 16 annual observations covering 15 elapsed years
COUNTRY = "NGA"
INDICATORS = {
    "real_gdp_lcu": "NY.GDP.MKTP.KN",
    "real_gdp_per_capita_lcu": "NY.GDP.PCAP.KN",
    "population": "SP.POP.TOTL",
    "gdp_growth_reported_pct": "NY.GDP.MKTP.KD.ZG",
    "population_growth_reported_pct": "SP.POP.GROW",
    "cpi_inflation_pct": "FP.CPI.TOTL.ZG",
    "nominal_gdp_current_usd": "NY.GDP.MKTP.CD",
    "real_household_consumption_per_capita_usd": "NE.CON.PRVT.PC.KD",
}
CORE = ("real_gdp_lcu", "real_gdp_per_capita_lcu", "population")
