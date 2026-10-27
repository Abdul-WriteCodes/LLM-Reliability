"""Execute *existing* WDI benchmark prompts against one API model.

Three API providers supported without additional dependencies beyond requests:
OpenAI Responses, Gemini generateContent, Anthropic Messages.

Never sends answer_key.jsonl; each question is an isolated API request.
Run with --dry-run first. No model calls or billing take place in dry-run.
"""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import random
import re
import sys
import time
from urllib.parse import quote

import requests

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT = ROOT / 'results' / 'benchmark_prompts.jsonl'
DEFAULT_OUTPUT = ROOT / 'results' / 'model_outputs.jsonl'
KEYS = {'openai': 'OPENAI_API_KEY', 'gemini': 'GEMINI_API_KEY', 'anthropic': 'ANTHROPIC_API_KEY'}


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def sha(s: str) -> str:
    return hashlib.sha256(s.encode('utf-8')).hexdigest()


def read_jsonl(path: Path):
    if not path.exists():
        return []
    with path.open(encoding='utf-8') as handle:
        return [json.loads(line) for line in handle if line.strip()]


def append_jsonl(path: Path, obj: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('a', encoding='utf-8') as handle:
        handle.write(json.dumps(obj, ensure_ascii=False) + '\n')
        handle.flush()


def parse_output(text: str):
    """Parse response if possible; don't silently convert malformed JSON to a valid answer."""
    s = text.strip()
    if s.startswith('```'):
        s = re.sub(r'^```(?:json)?\s*', '', s, flags=re.I)
        s = re.sub(r'\s*```$', '', s)
    try:
        d = json.loads(s)
        if isinstance(d, dict):
            return d, None
        return {'answer': text}, 'Model returned JSON that was not an object'
    except json.JSONDecodeError as exc:
        return {'answer': text}, f'Malformed JSON: {exc}'


def do_request(session, provider, model, prompt, max_tokens, temperature, timeout):
    key = os.environ.get(KEYS[provider], '').strip()
    if not key:
        raise RuntimeError(f'Set {KEYS[provider]} as an environment variable (not in source code).')
    if provider == 'openai':
        url = 'https://api.openai.com/v1/responses'
        headers = {'Authorization': f'Bearer {key}', 'Content-Type': 'application/json'}
        body = {'model': model, 'input': prompt, 'max_output_tokens': max_tokens, 'store': False}
        if temperature is not None:
            body['temperature'] = temperature
    elif provider == 'gemini':
        url = f'https://generativelanguage.googleapis.com/v1beta/models/{quote(model, safe="-_.")}:generateContent'
        headers = {'x-goog-api-key': key, 'Content-Type': 'application/json'}
        # Do not impose a provider-specific JSON mode: all providers receive the same JSON instruction.
        conf = {'maxOutputTokens': max_tokens}
        if temperature is not None:
            conf['temperature'] = temperature
        body = {'contents': [{'role': 'user', 'parts': [{'text': prompt}]}], 'generationConfig': conf}
    else:
        url = 'https://api.anthropic.com/v1/messages'
        headers = {'x-api-key': key, 'anthropic-version': '2023-06-01', 'Content-Type': 'application/json'}
        body = {'model': model, 'max_tokens': max_tokens, 'messages': [{'role': 'user', 'content': prompt}]}
        if temperature is not None:
            body['temperature'] = temperature

    resp = session.post(url, json=body, headers=headers, timeout=timeout)
    if resp.status_code >= 400:
        err = resp.text[:1200]
        raise requests.HTTPError(f'HTTP {resp.status_code}: {err}', response=resp)
    data = resp.json()
    if provider == 'openai':
        parts = [part.get('text', '') for item in data.get('output', [])
                 for part in item.get('content', []) if part.get('type') == 'output_text']
        text = '\n'.join(parts)
        usage = data.get('usage', {})
        actual_model = data.get('model', model)
        finish = data.get('status')
    elif provider == 'gemini':
        candidates = data.get('candidates') or []
        cand = candidates[0] if candidates else {}
        parts = cand.get('content', {}).get('parts', [])
        text = '\n'.join(part.get('text', '') for part in parts if 'text' in part)
        usage = data.get('usageMetadata', {})
        actual_model = data.get('modelVersion', model)
        finish = cand.get('finishReason')
    else:
        text = '\n'.join(part.get('text', '') for part in data.get('content', []) if part.get('type') == 'text')
        usage = data.get('usage', {})
        actual_model = data.get('model', model)
        finish = data.get('stop_reason')
    return {'text': text, 'raw': data, 'usage': usage, 'actual_model': actual_model,
            'finish_reason': finish, 'api_id': data.get('id')}


def main(argv=None):
    p = argparse.ArgumentParser(description='Run controlled WDI LLM benchmark against one API model')
    p.add_argument('--provider', choices=sorted(KEYS), required=True)
    p.add_argument('--model', required=True, help='Exact API model ID; e.g. gpt-6-luna')
    p.add_argument('--input', type=Path, default=DEFAULT_INPUT)
    p.add_argument('--output', type=Path, default=DEFAULT_OUTPUT)
    p.add_argument('--raw-log', type=Path, default=None)
    p.add_argument('--repeats', type=int, default=1)
    p.add_argument('--items', help='Comma-separated item IDs; omit to run the entire benchmark')
    p.add_argument('--condition', help='Optional exact condition, e.g. A_table_only')
    p.add_argument('--max-calls', type=int, default=None, help='Cap NEW paid calls for this invocation')
    p.add_argument('--max-output-tokens', type=int, default=2048)
    p.add_argument('--temperature', type=float, default=None, help='Omit by default; not all models support this')
    p.add_argument('--seed', type=int, default=42)
    p.add_argument('--pause', type=float, default=0.25, help='Seconds between successful calls')
    p.add_argument('--timeout', type=int, default=120)
    p.add_argument('--dry-run', action='store_true')
    args = p.parse_args(argv)
    if args.repeats < 1 or (args.max_calls is not None and args.max_calls < 1):
        p.error('--repeats and --max-calls must be >= 1')
    prompts = read_jsonl(args.input)
    if not prompts:
        p.error(f'No prompts in {args.input}. Run scripts/build_benchmark.py first.')
    expected = {'item_id', 'condition', 'prompt'}
    if any(not expected.issubset(row) for row in prompts):
        p.error('Prompt JSONL must contain item_id, condition, and prompt')
    if args.items:
        selected = set(args.items.split(','))
        prompts = [r for r in prompts if r['item_id'] in selected]
        missing = selected - {r['item_id'] for r in prompts}
        if missing:
            p.error(f'Unknown item IDs: {sorted(missing)}')
    if args.condition:
        prompts = [r for r in prompts if r['condition'] == args.condition]
    if not prompts:
        p.error('No prompts match the filters')
    jobs = []
    for repeat in range(1, args.repeats + 1):
        selected = prompts[:]
        random.Random(args.seed + repeat).shuffle(selected)
        jobs.extend((r, repeat) for r in selected)

    # Safe resume: model label, prompt fingerprint and repeat must all match.
    completed = {(row.get('model'), row.get('item_id'), row.get('condition'),
                  row.get('repeat'), row.get('prompt_sha256')) for row in read_jsonl(args.output)}
    model_label = f'{args.provider}/{args.model}'
    pending = [(r, repeat) for r, repeat in jobs if (
        model_label, r['item_id'], r['condition'], repeat, sha(r['prompt'])) not in completed]
    print(f'{model_label}: {len(jobs)} planned, {len(jobs) - len(pending)} already complete, {len(pending)} pending')
    if args.max_calls is not None:
        pending = pending[:args.max_calls]
        print(f'Cap applies: {len(pending)} NEW calls this run')
    if args.dry_run:
        if pending:
            first, rpt = pending[0]
            print(f'DRY RUN. First job: {first["item_id"]}, {first["condition"]}, repeat={rpt}; {len(first["prompt"])} characters')
        print('No API calls made. No outputs written.')
        return 0
    if not os.environ.get(KEYS[args.provider], '').strip():
        p.error(f'Missing {KEYS[args.provider]} environment variable')
    raw_path = args.raw_log or args.output.with_name(args.output.stem + '_raw_log.jsonl')
    if raw_path.resolve() == args.output.resolve():
        p.error('--raw-log must differ from --output')
    session = requests.Session()
    successes, errors = 0, 0
    for row, repeat in pending:
        base = {'item_id': row['item_id'], 'category': row.get('category'), 'condition': row['condition'],
                'model': model_label, 'repeat': repeat, 'prompt_sha256': sha(row['prompt']), 'timestamp_utc': utc_now(),
                'max_output_tokens': args.max_output_tokens, 'temperature': args.temperature, 'tools_enabled': False}
        for attempt in range(1, 4):
            try:
                res = do_request(session, args.provider, args.model, row['prompt'],
                                 args.max_output_tokens, args.temperature, args.timeout)
                response, parse_error = parse_output(res['text'])
                append_jsonl(args.output, {**base, 'response': response, 'raw_text': res['text'],
                         'parse_error': parse_error, 'usage': res['usage'], 'actual_model': res['actual_model'],
                         'finish_reason': res['finish_reason'], 'api_id': res['api_id']})
                append_jsonl(raw_path, {**base, 'status': 'ok', 'raw_api_response': res['raw'],
                                            'parse_error': parse_error})
                successes += 1
                print(f'OK {successes}/{len(pending)}: {row["item_id"]} {row["condition"]} repeat {repeat}' +
                      (' (JSON parse issue)' if parse_error else ''))
                time.sleep(args.pause)
                break
            except requests.HTTPError as exc:
                status = exc.response.status_code if exc.response is not None else 0
                if status not in (429, 500, 502, 503, 504):
                    print(f'Non-retryable API error: {exc}', file=sys.stderr)
                    append_jsonl(raw_path, {**base, 'status': 'error', 'error': str(exc)})
                    return 2
                error = str(exc)
            except (requests.RequestException, ValueError) as exc:
                error = str(exc)
            except RuntimeError as exc:
                print(str(exc), file=sys.stderr)
                return 2
            if attempt < 3:
                time.sleep(2 ** attempt)
            else:
                errors += 1
                append_jsonl(raw_path, {**base, 'status': 'error', 'error': error})
                print(f'ERROR: {row["item_id"]} {row["condition"]}: {error}', file=sys.stderr)
    print(f'Finished: {successes} responses saved, {errors} failed calls (retry by rerunning).')
    return 1 if errors else 0


if __name__ == '__main__':
    raise SystemExit(main())
