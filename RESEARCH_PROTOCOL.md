# Research protocol — Nigeria WDI empirical analysis and LLM reliability benchmark

**Status:** Preregister this protocol before submitting prompts to model APIs. No model performance findings are asserted in this starter project.

## Study 1 — Reproducible empirical analysis

**Working title:** *Growth Without Prosperity? An Empirical Analysis of Nigeria's GDP and Per Capita Economic Performance, 2010–2025.*

### Aim and scope

Describe changes in Nigeria's inflation-adjusted GDP, real GDP per capita, and population over 2010–2025, using a frozen, dated extraction from the World Bank World Development Indicators. 2010–2025 comprises **16 annual observations spanning 15 elapsed years**. Treat GDP per capita as production per person, not as income distribution or household living standards.

**RQ1**: What are the cumulative and annual changes in real GDP, population, and real GDP per capita?

**RQ2**: In which years did GDP rise while per-capita GDP fell?

**RQ3**: How well does the log-growth accounting identity explain the observed GDP–per-capita difference?

**RQ4**: What can, and cannot, be inferred about households from GDP-based statistics?

### Data definitions

Core reported WDI series:

| Field | Code | Definition |
|---|---|---|
| `real_gdp_lcu` | `NY.GDP.MKTP.KN` | Real aggregate GDP, constant local currency |
| `real_gdp_per_capita_lcu` | `NY.GDP.PCAP.KN` | Real GDP per capita, constant local currency |
| `population` | `SP.POP.TOTL` | Population, total |

Optional context fields in `config.py` (GDP growth, population growth, inflation, current-USD GDP, real consumption per capita) are not part of the main decomposition and may have missing observations.

**Do not** interpret nominal current-USD movements as real economic growth. GDP per capita is mathematically related to GDP and population, so a regression of one on the other is not a meaningful causal test. Poverty, inequality, household purchasing power and employment require other data and careful definition.

### Analysis

1. Preserve raw response JSON for every indicator and retrieval timestamp; report the WDI indicator codes and study window.
2. Reject missing observations in all three core indicators; do not invent/interpolate core data.
3. Graph year-indexed GDP, GDP per capita and population with first year = 100.
4. Calculate cumulative percentage change: `100 × (end/start - 1)`.
5. Calculate annual log changes and verify: `Δln(GDP per capita) ≈ Δln(GDP) - Δln(population)` (exact if source indicator identities are internally consistent).
6. Flag years with `GDP growth > 0` and `GDP-per-capita growth < 0`.
7. Cross-check `real GDP / population` against reported real GDP per capita; report discrepancy rather than hiding it.
8. Present qualitative context for major years separately; do not assert causation from trend breaks.

### Limitations

The short annual time series (16 observations) does not justify high-dimensional time-series models or reliable causal attribution. National accounts are revised, including rebasing, so every publication must record the retrieval date and preserve the raw snapshot. Macro GDP per person is an *average production metric*, not evidence that median households are richer or poorer.

### Deliverables

- `data/nigeria_wdi_2010_2025.csv` — frozen study dataset.
- `data/provenance.json` and `data/raw/*.json` — original source provenance.
- `outputs/analysis_table.csv`, `outputs/key_results.json`, `outputs/findings.md` — computed results.
- `outputs/indexed_growth.png`, `outputs/annual_growth.png` — charts.
- Article + methods section on 8p8.dev; released code and dated data snapshot under suitable licences with WDI attribution.

---

## Study 2 — LLM statistical interpretation reliability

**Working title:** *Can Large Language Models Reliably Interpret Economic Data? An Experimental Benchmark Using Nigeria's World Development Indicators.*

### Aim

Determine whether LLMs faithfully interpret Nigerian economic indicators, perform arithmetic accurately, read temporal changes correctly, and avoid asserting unsupported inferences about welfare or causation.

### Benchmark construction and ground truth

- Build all benchmark questions *after* freezing the same data snapshot used in Study 1.
- The included generator produces **30 distinct questions** in 3 controlled prompt conditions (**90 prompt variants**): 12 numeric-change tasks, 6 divergence questions, 6 trend-sign questions, and 6 questions with insufficient evidence.
- Answers to numeric and binary questions are computed deterministically from the frozen series before model runs. Subject-matter interpretation is evaluated by humans against a predefined rubric.
- Deliver the same full 16-year data table to all models. Do not allow internet search or tool access unless separately registered as another experimental condition.
- **Avoid exposing `answer_key.jsonl` to model inputs.**

### Experimental conditions

- **A — Table only:** numerical table, question, and fixed output schema.
- **B — Table + definitions:** same table plus indicator definitions and units.
- **C — Table + definitions + verification instruction:** same table plus a check of years/denominators and explicit permission to say that evidence is insufficient.

This design tests whether giving definitions improves interpretation (B versus A), and whether adding an explicit verification policy improves it further (C versus B). It does **not** isolate all possible prompt-design factors.

### Proposed model sample and runs

Choose 3 fixed, currently accessible model IDs, ideally from independent vendors. Record vendor, **exact model/version ID**, run date, decoding settings, maximum tokens, tool access setting and price. Do not report product brand alone as the model version. Randomise task order within each run and give each question a fresh, independent context to avoid contamination from prior questions.

Recommended full-scale run: `30 items × 3 conditions × 3 models × 3 independent runs = 810 responses` (if affordable). Start with a small pilot on 5–10 items, and then freeze the rubric and benchmark before running all tasks. Do not treat repeated model calls as independent datasets when computing confidence intervals.

### Response schema

Instruct models to return `answer`, `numeric_value` (number or null), `yes_no` (yes/no/null), `evidence`, `confidence` (0–1), `abstained` (boolean). Log the **raw** model reply as well as the parsed response and any parsing errors. Failed parsing should be reported, not invisibly dropped.

### Primary outcome metrics

1. **Numerical accuracy:** percentage of numeric tasks within ±0.25 percentage points of the precomputed answer (the WDI table is rounded for display). Also report mean/median absolute error.
2. **Directionality accuracy:** yes/no correctness on GDP versus per-capita trend questions.
3. **Evidence-limitation recognition:** fraction correctly stating that GDP, GDP per capita, and population alone cannot establish poverty, median income, inequality, employment, or policy causation outcomes.
4. **Unsupported-claim rate:** number of responses containing >=1 empirically unsupported assertion divided by all eligible model responses. Report the unit of analysis explicitly.
5. **Contradiction rate:** responses making a claim incompatible with the supplied table.
6. **Unjustified causality rate:** responses claiming an identified cause without causal evidence.
7. **Calibration / abstention:** confidence estimates versus correctness where available; appropriateness of abstention on unanswerable tasks.

### Evaluation workflow

- Run `scripts/grade.py` for **objective numeric and binary scoring only**.
- Conduct manual claim-level coding for qualitative answers: supported / contradicted / insufficient data / fabricated statistic / unjustified causality. A false *economic inference* should not automatically be counted as a *fabricated number*.
- Ideally have two independently blinded annotators score all interpretive questions and a sample of others; document agreement (e.g. Cohen's kappa) and resolve disagreements under a published codebook.
- Predeclare decisions about incomplete replies, refusal, malformed JSON, and rounding before comparing models.
- Report per-model, per-condition rates and paired item-level differences with uncertainty intervals. For small samples prioritise descriptive comparisons; avoid inflated p-values from repeated runs.

### Example interpretive errors to label

1. “GDP increased, therefore every household became wealthier” → unsupported inference, possibly contradicted by household data not provided; **not** automatically fabrication.
2. “GDP per capita equals the median person's income” → conceptually incorrect definition.
3. “Real GDP fell from 2015 to 2020” when the table shows the opposite → direct data contradiction.
4. “Inflation was 17.2%” without a price indicator in the prompt → fabricated or ungrounded numerical assertion unless independently supplied.
5. “Population caused economic contraction” based solely on GDP/population identity → unjustified causal attribution.
6. “These three indicators cannot determine whether poverty declined” → appropriate epistemic restraint.

### Interpretation caution

A model can be correct about arithmetic yet produce a misleading narrative. Report both arithmetic and interpretation reliability separately. A comparison of A, B, C alone cannot establish whether the *model* is safe for every research setting. A text-table benchmark does not automatically establish chart-reading ability; multimodal charts require a separately controlled arm with identical values and aligned tasks.

### Publication deliverables

- Article with methods, model IDs, timestamp, ground truth design and sample outputs on 8p8.dev.
- Benchmark prompts with frozen data table.
- Full response logs (only after checking licensing/privacy/usage rules), human annotation rubric, scripts, and score summaries.
- Reproduction commands and explicit limitations; if publishing the answer key, do so **after** evaluation and mark public benchmark reuse as potentially contaminated.

## External foundational sources

- [World Bank WDI GDP constant LCU](https://data.worldbank.org/indicator/NY.GDP.MKTP.KN?locations=NG)
- [World Bank WDI GDP per capita constant LCU](https://data.worldbank.org/indicator/NY.GDP.PCAP.KN?locations=NG)
- [World Bank indicator API documentation](https://datahelpdesk.worldbank.org/knowledgebase/articles/898599-indicator-api-queries)
- [Mathematica 2026, Trusting Your LLM](https://www.mathematica.org/publications/trusting-your-llm)
- [Kalai et al. 2026, Evaluating LLMs for accuracy incentivizes hallucinations](https://www.nature.com/articles/s41586-026-10549-w)
