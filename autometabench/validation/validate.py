#!/usr/bin/env python3
"""Check benchmark drift against the 2026-09-29 visually reviewed source ledger.

This does not perform a new visual/OCR audit of a PDF. PDF hashes identify the
version used by reviewers; the source ledger records their numeric transcription.
"""
from __future__ import annotations
import argparse
import csv
import hashlib
import json
from decimal import Decimal, InvalidOperation
from pathlib import Path


def rows(path):
    with path.open(encoding='utf-8-sig', newline='') as handle:
        reader = csv.DictReader(handle)
        fields = reader.fieldnames or []
        if not fields or len(set(fields)) != len(fields):
            raise ValueError(f'Invalid or duplicate headers: {path}')
        result = list(reader)
        if any(None in row or any(v is None for v in row.values()) for row in result):
            raise ValueError(f'Malformed CSV row: {path}')
        return result


def numeric(value):
    try:
        return Decimal(value).is_finite()
    except (InvalidOperation, ValueError, TypeError):
        return False


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def validate(root, pdf_dir=None):
    validation = root / 'validation'
    errors = []
    ledger = rows(validation / 'extraction_numeric_cells.csv')
    reference = json.loads((validation / 'meta_reference.json').read_text())
    source_manifest = rows(validation / 'source_manifest.csv')
    files = sorted((root / 'data_extraction/results').glob('*.csv'))
    tables = {'data_extraction/results/' + f.name: rows(f) for f in files}
    actual_keys = {(f, i, c) for f, rs in tables.items()
                   for i, row in enumerate(rs, 1) for c, v in row.items() if numeric(v)}
    expected_keys = set()
    for item in ledger:
        key = (item['file'], int(item['data_row']), item['column'])
        if key in expected_keys:
            errors.append(f'Duplicate source-ledger entry: {key}')
        expected_keys.add(key)
        try:
            actual = tables[key[0]][key[1] - 1][key[2]]
            if Decimal(actual) != Decimal(item['source_value']):
                errors.append(f'Extraction mismatch {key}: {actual} != {item["source_value"]}')
        except (KeyError, IndexError, InvalidOperation):
            errors.append(f'Missing or nonnumeric extraction cell: {key}')
        if not item['source_type'] or not item['pdf_page'] or not item['figure_or_table']:
            errors.append(f'Missing provenance: {key}')
    if actual_keys != expected_keys:
        errors.append(f'Numeric coverage mismatch: {len(actual_keys - expected_keys)} unreviewed; '
                      f'{len(expected_keys - actual_keys)} missing')
    units = rows(root / 'meta_analysis/units.csv')
    by_id = {u['unit_id']: u for u in units}
    if len(by_id) != len(units):
        errors.append('Duplicate meta unit IDs')
    if set(by_id) != {r['unit_id'] for r in reference}:
        errors.append('Meta unit scope differs from reviewed reference')
    for ref in reference:
        uid = ref['unit_id']
        actual = by_id.get(uid, {})
        if actual != ref['expected_unit']:
            errors.append(f'Meta row differs from reviewed reference: {uid}')
        for key, field in ref['numeric_fields'].items():
            value = actual.get(key)
            if field['status'] == 'not_reported_in_forest':
                if value != '':
                    errors.append(f'Unreported meta field populated: {uid}.{key}')
            elif not numeric(value) or Decimal(value) != Decimal(field['value']):
                errors.append(f'Meta numeric mismatch: {uid}.{key}')
        if actual:
            effect = Decimal(actual['pooled_effect'])
            if not Decimal(actual['ci_lower']) <= effect <= Decimal(actual['ci_upper']):
                errors.append(f'Invalid pooled CI: {uid}')
            threshold = Decimal(1) if actual['effect_measure'] in ('OR', 'RR') else Decimal(0)
            direction = 'positive' if effect > threshold else 'negative' if effect < threshold else 'null'
            if actual['analysis_type'] == 'proportion':
                direction = 'not_applicable'
            if actual['direction'] != direction:
                errors.append(f'Wrong pooled direction: {uid}')
            if actual['i2'] and not 0 <= Decimal(actual['i2']) <= 100:
                errors.append(f'I2 out of range: {uid}')
            if actual['tau2'] and Decimal(actual['tau2']) < 0:
                errors.append(f'Negative tau2: {uid}')
            if 'data_extraction/results/' + actual['result_file'] not in tables:
                errors.append(f'Missing linked extraction file: {uid}')
    for entry in rows(validation / 'verified_file_hashes.csv'):
        p = root / entry['file']
        if not p.is_file() or digest(p) != entry['sha256']:
            errors.append(f'File drift from reviewed version: {entry["file"]}')
    reviews = [json.loads(line) for line in (root / 'reviews.jsonl').read_text().splitlines()]
    if {r['review_pmid'] for r in reviews} != {r['review_pmid'] for r in source_manifest}:
        errors.append('Source manifest does not cover review inventory')
    checked_pdfs = 0
    if pdf_dir:
        for source in source_manifest:
            p = pdf_dir / (source['review_pmid'] + '.pdf')
            if not p.is_file() or digest(p) != source['source_pdf_sha256']:
                errors.append(f'Source PDF missing or changed: {source["review_pmid"]}')
            else:
                checked_pdfs += 1
    result = {'status': 'pass' if not errors else 'fail', 'extraction_files': len(files),
              'extraction_rows': sum(map(len, tables.values())),
              'numeric_cells_checked': len(expected_keys), 'meta_units': len(units),
              'source_pdfs_hash_checked': checked_pdfs, 'errors': errors}
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--benchmark-root', type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument('--source-pdf-dir', type=Path)
    args = parser.parse_args()
    result = validate(args.benchmark_root, args.source_pdf_dir)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    raise SystemExit(0 if result['status'] == 'pass' else 1)
