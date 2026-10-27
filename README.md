# Nigeria WDI: one dataset, two reproducible 8p8.dev research studies

An **executable starter project** for two linked research tracks:

1. **Reproducible economic analysis:** aggregate real GDP, population and real GDP per capita in Nigeria (2010–2025).
2. **LLM interpretation benchmark:** factual numerical reasoning and epistemic reliability about the exact same data.

**Important:** This ZIP does **not** claim to contain a freshly downloaded Nigerian dataset or actual model evaluations. The code fetches the data from the official WDI API when *you run it online*. No LLM API call is made by the starter code. Final results must be calculated and checked locally before publication.

## Quick start

From this folder using Python 3.10+:

```bash
python -m venv .venv
# Activate it in your shell, then:
pip install -r requirements.txt
python scripts/fetch_wdi.py
python scripts/analyse.py
python scripts/build_benchmark.py
pytest -q
```

These steps produce:

```text
data/
  nigeria_wdi_2010_2025.csv
  provenance.json
  raw/*.json
outputs/
  analysis_table.csv
  key_results.json
  findings.md
  indexed_growth.png
  annual_growth.png
results/
  benchmark_manifest.json
  benchmark_prompts.jsonl     # Provide ONLY these prompts to models
  answer_key.jsonl             # DO NOT give these to models
```

The first run requires internet access to `https://api.worldbank.org`. Freeze the dated `data/` files in version control or an archival release. To update the snapshot, deliberately rerun the fetch step and version the change, not silently replace it.

## Running the LLM experiment

Read `RESEARCH_PROTOCOL.md` before making any API calls. Pick and pin exact model IDs, log prompts, tool access, time, and decoding parameters. For each record in `results/benchmark_prompts.jsonl`, collect a response and write a line in `results/model_outputs.jsonl`:

```json
{"item_id":"NGA-WDI-001","condition":"A_table_only","model":"vendor/exact-version","repeat":1,"response":{"answer":"Increased 5.12%","numeric_value":5.12,"yes_no":null,"evidence":"Computed from the two annual GDP observations","confidence":0.9,"abstained":false}}
```

(The `5.12` shown above is only a **format illustration**, not a Nigerian WDI result.)

Then:

```bash
python scripts/grade.py
```

Objective accuracy reports are calculated where possible. `results/review_annotations.csv` is generated for independent manual reviews of claims, invented facts, misleading interpretations and unwarranted causality. The code **does not** use unreliable keyword heuristics to label hallucinations.

## Two suggested publication pages

- **8p8.dev/research/**: *Growth Without Prosperity? Nigeria's GDP, Population, and Per-Capita Output, 2010–2025.* Embed charts and link the dated dataset and reproducible source.
- **8p8.dev/research/**: *Can LLMs Reliably Interpret Economic Data? A Nigerian WDI Benchmark.* Show evaluation conditions, human rubrics, model version metadata and failures/successes.

Actual URLs/slugs are illustrative, not routes created by this ZIP.

## Key cautions

- **2010–2025 = 16 inclusive annual observations** (15 years elapsed). A window from 2011–2025 has 15 observations.
- **Real GDP and population are not independent of real GDP per capita**: the latter is GDP divided by population. Decomposition is an identity, not causal econometrics.
- **GDP per capita is not median income or a household welfare measure**. Never claim it proves changes in poverty or prosperity without supporting data.
- **Constant LCU** values express inflation-adjusted local production, not current USD amounts.
- National accounts change after statistical revisions; preserve data and retrieval timestamps.
- WDI series can contain nulls; this project refuses to silently fill missing *core* data.

Source: World Bank World Development Indicators, CC BY 4.0 indicator pages; cite the World Bank and retrieval date.

## Experimental runner (added)

A ready-to-use cross-provider runner is included in `scripts/run_llm.py`.
It accepts **your existing** `results/benchmark_prompts.jsonl`, sends each
prompt in a separate context via the OpenAI Responses, Google Gemini or
Anthropic Messages REST APIs, and appends to `results/model_outputs.jsonl`.
It NEVER sends the answer key and NEVER makes network calls in `--dry-run`.

Run the following from this project directory:

```bash
# Safe, no billable calls; needs generated results/benchmark_prompts.jsonl
python scripts/run_llm.py --provider openai --model gpt-6-luna --dry-run

# Set each provider API key in your terminal or an environment secret store
# Mac/Linux: export OPENAI_API_KEY="..."
# Windows PowerShell: $env:OPENAI_API_KEY="..."

# Initial pilot: 8 questions across the 4 task categories x 3 conditions = 24 calls/model
# Save pilot results separately so pilot data isn't mixed into preregistered main study
python scripts/run_llm.py --provider openai --model gpt-6-luna --repeats 1 \
 --items NGA-WDI-001,NGA-WDI-005,NGA-WDI-013,NGA-WDI-016,NGA-WDI-019,NGA-WDI-022,NGA-WDI-025,NGA-WDI-028 \
 --output results/pilot_outputs.jsonl

# Full study (after checking and freezing the pilot protocol):
python scripts/run_llm.py --provider openai --model gpt-6-luna --repeats 3
python scripts/run_llm.py --provider gemini --model gemini-3.8-flash --repeats 3
python scripts/run_llm.py --provider anthropic --model claude-haiku-5-5 --repeats 3
python scripts/grade.py
```

**Full study:** 90 prompt variants x 3 repeats = 270 API calls per model,
or 810 total for 3 models. Be mindful of API charges and rate limits. First
try `--max-calls 3`; you can rerun the same command because completed responses
are safely skipped using model+item+condition+repeat+prompt fingerprint.
Do NOT change the data or prompts after collecting the first formal response.

Environment variables: `OPENAI_API_KEY`, `GEMINI_API_KEY`, `ANTHROPIC_API_KEY`.
Do not paste them into source files or commit them. The runner omits
`temperature` by default because providers/models differ in support;
optionally supply `--temperature 0` only if the selected API model supports it.
Log any differences in decoding settings in the methods section.

The default response file is `results/model_outputs.jsonl`; full API payloads
are separately retained in `results/model_outputs_raw_log.jsonl`. The runner
records model IDs, timestamps, prompt SHA256, raw output, token usage, parsing
errors and finish status. API failures are logged and can be retried by rerunning.
Model call success does not imply economic correctness. `scripts/grade.py`
automates only numeric/directionality items; `results/review_annotations.csv`
needs independent review of unsupported inference, hallucination and causality.

**Provider REST documentation:**
- OpenAI: https://developers.openai.com/api/docs/quickstart
- Google: https://ai.google.dev/api/generate-content
- Anthropic: https://platform.claude.com/docs/en/api/messages/create

Model IDs in examples are illustrative and require access in your own accounts.
Pricing, supported settings and available versions may change.

You can now score pilot data without overwriting the main-study results:

```bash
python scripts/grade.py --input results/pilot_outputs.jsonl --prefix pilot_
# Generates results/pilot_objective_accuracy.csv and results/pilot_review_annotations.csv
```

Read `HUMAN_ANNOTATION_RUBRIC.md` for blind human coding instructions. The updated
grader treats missing/invalid numeric or yes/no fields as incorrect rather than
silently excluding them from an accuracy denominator; report schema compliance
separately. This is an explicit scoring-policy improvement to freeze before the
main study.
