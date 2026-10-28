"""Re-grade archived LLM responses, recovering one valid JSON object from a fenced block.

This script never modifies original model output or answer key files. Outputs use a
new default ``regraded_`` prefix and refuse to overwrite an existing file.

Example from repository root:
  python scripts/grade_recovered.py --input results/gpt4o_mini_outputs.jsonl \
      --answer-key results/answer_key.jsonl --prefix gpt4o_mini_audit_

Method: First retain the response object parsed during inference. If the recorded
parser failed, only recover a *single* valid fenced JSON object in raw_text.
No semantic guessing from prose. Report original JSON parsing success separately.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import re
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RESULTS = ROOT / 'results'
FENCE_PATTERN = re.compile(r'```(?:json)?\s*(\{[\s\S]*?\})\s*```', re.IGNORECASE)
TOLERANCES = (0.01, 0.02, 0.05, 0.25)


def read_jsonl(path: Path):
    with path.open(encoding='utf-8-sig') as handle:
        for line_number, line in enumerate(handle, 1):
            if line.strip():
                try:
                    yield json.loads(line)
                except json.JSONDecodeError as err:
                    raise ValueError(f'{path}:{line_number}: bad JSONL record: {err}') from err


def recover_response(record):
    """Returns response dict (or None), recovery label and source parse status."""
    response = record.get('response')
    original_ok = not bool(record.get('parse_error'))
    if original_ok and isinstance(response, dict):
        return response, 'original_parser', True
    raw = record.get('raw_text') or (response or {}).get('answer', '')
    if not isinstance(raw, str):
        return None, 'unrecoverable_no_raw_text', original_ok
    matches = FENCE_PATTERN.findall(raw)
    parsed = []
    for match in matches:
        try:
            obj = json.loads(match)
            if isinstance(obj, dict):
                parsed.append(obj)
        except json.JSONDecodeError:
            pass
    if len(parsed) == 1:
        return parsed[0], 'single_fenced_json', original_ok
    if len(parsed) > 1:
        return None, 'ambiguous_multiple_json_objects', original_ok
    try:
        obj = json.loads(raw.strip())
        if isinstance(obj, dict):
            return obj, 'raw_json_only', original_ok
    except json.JSONDecodeError:
        pass
    return None, 'unrecoverable', original_ok


def normalized_yes_no(value):
    if value is None:
        return None
    s = str(value).strip().lower()
    return {'yes': 'yes', 'true': 'yes', 'no': 'no', 'false': 'no'}.get(s)


def evaluate(item, response, tolerance):
    """Do not treat missing/unparseable values as demonstrated substantive errors."""
    kind = item['answer_type']
    if kind == 'insufficient_evidence':
        return None, None, 'human_review_required'
    if not isinstance(response, dict):
        return None, None, 'unscorable_unparseable_output'
    if kind == 'number':
        try:
            val = float(response.get('numeric_value'))
            if not math.isfinite(val):
                raise ValueError('Nonfinite number')
        except (ValueError, TypeError):
            return None, None, 'unscorable_missing_numeric_value'
        difference = abs(val - float(item['reference']))
        return difference <= tolerance + 1e-10, difference, 'numeric_tolerance'
    if kind == 'yes_no':
        val = normalized_yes_no(response.get('yes_no'))
        if val is None:
            return None, None, 'unscorable_missing_yes_no'
        return val == item['reference'], None, 'binary_exact'
    raise ValueError(f'Unexpected answer_type: {kind}')


def write_csv(path, rows, columns):
    with path.open('w', newline='', encoding='utf-8-sig') as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, extrasaction='ignore')
        writer.writeheader()
        writer.writerows(rows)


def percent(n, d):
    return round(100*n/d, 2) if d else None


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--input', type=Path, default=DEFAULT_RESULTS / 'model_outputs.jsonl')
    ap.add_argument('--answer-key', type=Path, default=DEFAULT_RESULTS / 'answer_key.jsonl')
    ap.add_argument('--output-dir', type=Path, default=DEFAULT_RESULTS)
    ap.add_argument('--prefix', default='regraded_')
    ap.add_argument('--tolerance', type=float, default=0.25, help='Absolute percentage-point threshold, original = 0.25')
    ap.add_argument('--overwrite', action='store_true', help='Explicitly replace files with this audit prefix only')
    args = ap.parse_args()
    if not args.prefix or any(x in args.prefix for x in ['/', '\\']):
        ap.error('--prefix must be non-empty without directory separators')
    if args.tolerance < 0:
        ap.error('--tolerance must be nonnegative')
    for p in (args.input, args.answer_key):
        if not p.is_file():
            ap.error(f'File not found: {p}')
    outputs = [
        args.output_dir / (args.prefix + name) for name in (
            'review_annotations.csv', 'objective_accuracy.csv', 'format_compliance.csv',
            'accuracy_sensitivity.csv', 'category_accuracy.csv', 'audit_summary.md')
    ]
    if not args.overwrite:
        existing = [str(p) for p in outputs if p.exists()]
        if existing:
            ap.error('Refusing overwrite: ' + ', '.join(existing) + '. Use a new prefix or --overwrite.')
    keys = {x['item_id']:x for x in read_jsonl(args.answer_key)}
    source = list(read_jsonl(args.input))
    rows=[]
    for r in source:
        item = keys.get(r['item_id'])
        if item is None:
            raise ValueError(f'Unknown item_id {r["item_id"]}')
        answer, method, originally_parsed = recover_response(r)
        correct, numeric_error, grading_method = evaluate(item, answer, args.tolerance)
        row={
            'item_id': r['item_id'], 'category': item['category'], 'condition': r['condition'],
            'model': r['model'], 'repeat': r.get('repeat'), 'answer_type': item['answer_type'],
            'reference': item['reference'], 'question': item.get('question', ''),
            'original_parser_ok': originally_parsed, 'original_parse_error': r.get('parse_error') or '',
            'recovery_method': method, 'recovered_answer': (answer or {}).get('answer',''),
            'recovered_numeric_value': (answer or {}).get('numeric_value'),
            'recovered_yes_no': (answer or {}).get('yes_no'),
            'evidence': (answer or {}).get('evidence', ''),
            'automated_correct': correct, 'absolute_numeric_error_pp': numeric_error,
            'grading_method': grading_method,
            'human_correct': '', 'unsupported_claim': '', 'contradicted_data':'',
            'fabricated_statistic':'', 'unjustified_causality':'',
            'appropriate_abstention':'', 'notes':'',
            'response_text': json.dumps(answer or {},ensure_ascii=False),
            'finish_reason':r.get('finish_reason',''),
        }
        rows.append(row)
    conditions=sorted({r['condition'] for r in rows})
    groups=sorted({(r['model'],r['condition']) for r in rows})
    summary=[]
    format_rows=[]
    for model,cond in groups:
        rs=[r for r in rows if r['model']==model and r['condition']==cond]
        scored=[r for r in rs if r['automated_correct'] is not None]
        correct=sum(bool(r['automated_correct']) for r in scored)
        summary.append({'model':model,'condition':cond,'total_responses':len(rs),
                        'evaluated':len(scored),'correct':correct,'incorrect':len(scored)-correct,
                        'unscored_human_or_parse':len(rs)-len(scored),
                        'accuracy':correct/len(scored) if scored else ''})
        success=sum(bool(r['original_parser_ok']) for r in rs)
        recovered=sum(r['recovery_method']=='single_fenced_json' for r in rs)
        format_rows.append({'model':model,'condition':cond,'responses':len(rs),
                            'original_parser_successes':success,
                            'original_parser_failure_count':len(rs)-success,
                            'original_parser_success_rate':success/len(rs),
                            'recovered_fenced_json_count':recovered})
    sensitivity=[]
    for tol in sorted(set(TOLERANCES+(args.tolerance,))):
        for model, cond in groups:
            selected=[r for r in rows if r['model']==model and r['condition']==cond]
            graded=[]
            for r in selected:
                it=keys[r['item_id']]
                ans,_,_=recover_response(next(x for x in source if x['item_id']==r['item_id'] and x['condition']==r['condition'] and x.get('repeat')==r['repeat'] and x['model']==r['model']))
                okay, _,_ = evaluate(it,ans,tol)
                if okay is not None: graded.append(okay)
            sensitivity.append({'tolerance_pp':tol,'model':model,'condition':cond,'evaluated':len(graded),
                                'correct':sum(graded), 'accuracy':sum(graded)/len(graded) if graded else ''})
    categories=[]
    for category in sorted({r['category'] for r in rows}):
        subset=[r for r in rows if r['category']==category]
        scored=[r for r in subset if r['automated_correct'] is not None]
        categories.append({'category':category,'responses':len(subset),'evaluated':len(scored),
                           'correct':sum(bool(r['automated_correct']) for r in scored),
                           'incorrect':sum(r['automated_correct'] is False for r in scored),
                           'human_only':len(subset)-len(scored)})
    args.output_dir.mkdir(parents=True,exist_ok=True)
    write_csv(outputs[0],rows,list(rows[0]))
    write_csv(outputs[1],summary,list(summary[0]))
    write_csv(outputs[2],format_rows,list(format_rows[0]))
    write_csv(outputs[3],sensitivity,list(sensitivity[0]))
    write_csv(outputs[4],categories,list(categories[0]))
    scored=[r for r in rows if r['automated_correct'] is not None]
    correct=sum(bool(r['automated_correct']) for r in scored)
    original_ok=sum(bool(r['original_parser_ok']) for r in rows)
    recovered=sum(r['recovery_method']=='single_fenced_json' for r in rows)
    md=['# Archived LLM outputs — parsing and accuracy audit','',
        '## Source provenance', '',
        f'- Raw responses SHA-256: `{hashlib.sha256(args.input.read_bytes()).hexdigest()}`',
        f'- Answer key SHA-256: `{hashlib.sha256(args.answer_key.read_bytes()).hexdigest()}`', '',
        f'- Original output records: **{len(rows)}**',
        f'- Original parser successes: **{original_ok}/{len(rows)}**',
        f'- Single fenced JSON responses recovered: **{recovered}**',
        f'- After recovery, objective accuracy at ±{args.tolerance:g} percentage points: **{correct}/{len(scored)} ({percent(correct,len(scored))}%)**',
        f'- Human-only or unscorable records: **{len(rows)-len(scored)}**','',
        '## Condition breakdown','',
        '| Condition | Correct | Evaluated | Accuracy |', '|---|---:|---:|---:|']
    for s in summary:
        md.append(f'| {s["condition"]} | {s["correct"]} | {s["evaluated"]} | {100*s["accuracy"]:.2f}% |')
    md+=['','## Important interpretation notes','',
         '1. The original `parse_error` is preserved as a separate formatting/compliance result. Extracting a single JSON object enclosed in a fenced code block does **not** mean the original response followed the JSON-only instruction.',
         '2. Numeric recovery uses only a valid fenced JSON object present verbatim in the original output. No economic answer is inferred from free-form prose.',
         '3. The original scorer allowed ±0.25 percentage points; use the sensitivity CSV to evaluate tighter thresholds. Do not conflate approximate numeric accuracy and exact two-decimal accuracy.',
         '4. The six insufficient-evidence questions (per prompt condition) require blind human assessment of reasoning, claims, and caution. Automated yes/no correctness does not validate its evidence text.',
         '5. The script does not edit the original raw response file or ground-truth key. Original annotation CSV files are never overwritten without an explicit --overwrite with the chosen output prefix.','',
         '## Specific errors requiring inspection','',
         '| ID | Condition | Type | Reference | Recovered value |','|---|---|---|---|---|']
    for r in rows:
        if r['automated_correct'] is False:
            md.append(f'| {r["item_id"]} | {r["condition"]} | {r["answer_type"]} | {r["reference"]} | {r["recovered_numeric_value"] if r["answer_type"]=="number" else r["recovered_yes_no"]} |')
    outputs[-1].write_text('\n'.join(md)+'\n',encoding='utf-8')
    print(f'{len(rows)} outputs checked, {recovered} recoveries, {correct}/{len(scored)} correct at ±{args.tolerance} percentage points.')
    for s in summary:
        print(f'{s["condition"]}: {s["correct"]}/{s["evaluated"]} = {100*s["accuracy"]:.2f}%')
    print('Files saved to', args.output_dir)

if __name__=='__main__':
    main()
