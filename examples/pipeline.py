#!/usr/bin/env python3
"""Offline CSV shards with independently checkable integer results.

prepare creates a new directory; workers read exactly their own shard. An
aggregate refuses missing/corrupt/incorrect partials instead of publishing a
partial result. Only the failed shard needs to be rerun after input repair.
"""
import argparse
import csv
import json
import os
from pathlib import Path
import re
import sys
import tempfile

SHARDS = 4
ROWS_PER_SHARD = 1000
MANIFEST = {'columns': ['id', 'value'], 'shards': [
    {'index': i, 'input': f'input/shard-{i}.csv', 'row_count': ROWS_PER_SHARD}
    for i in range(SHARDS)
]}


def write_json(path, value):
    fd, temporary = tempfile.mkstemp(prefix='.pipeline-', dir=path.parent)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as stream:
            json.dump(value, stream, sort_keys=True)
            stream.write('\n')
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def manifest(run_dir):
    value = json.loads((run_dir / 'manifest.json').read_text(encoding='utf-8'))
    if value != MANIFEST:
        raise ValueError('Manifest does not describe the exact four teaching shards')
    return value


def prepare(run_dir):
    run_dir.mkdir(exist_ok=False)
    (run_dir / 'input').mkdir()
    (run_dir / 'partials').mkdir()
    for item in MANIFEST['shards']:
        with (run_dir / item['input']).open('w', newline='', encoding='utf-8') as stream:
            writer = csv.writer(stream)
            writer.writerow(MANIFEST['columns'])
            first = item['index'] * ROWS_PER_SHARD + 1
            for identifier in range(first, first + ROWS_PER_SHARD):
                writer.writerow((identifier, 2 * identifier))
    write_json(run_dir / 'manifest.json', MANIFEST)
    return {'prepared': str(run_dir), 'shards': SHARDS, 'row_count': SHARDS * ROWS_PER_SHARD}


def worker(run_dir, index):
    if not 0 <= index < SHARDS:
        raise ValueError('index must be 0..3')
    target = run_dir / 'partials' / f'{index}.json'
    # A failed rerun must not leave an earlier success artifact for this shard.
    target.unlink(missing_ok=True)
    item = manifest(run_dir)['shards'][index]
    count, total = 0, 0
    first = index * ROWS_PER_SHARD + 1
    with (run_dir / item['input']).open(newline='', encoding='utf-8') as stream:
        reader = csv.DictReader(stream)
        if reader.fieldnames != ['id', 'value']:
            raise ValueError('CSV header must be id,value')
        for row in reader:
            if set(row) != {'id', 'value'} or any(not isinstance(v, str) or not re.fullmatch(r'[0-9]+', v) for v in row.values()):
                raise ValueError(f'Shard {index} row {count + 1}: expected two integer fields')
            identifier, value = int(row['id']), int(row['value'])
            if identifier != first + count or value != 2 * identifier:
                raise ValueError(f'Shard {index} row {count + 1}: unexpected id or value')
            count += 1
            if count > item['row_count']:
                raise ValueError(f'Shard {index}: too many rows')
            total += value
    if count != item['row_count']:
        raise ValueError(f'Shard {index}: expected {item["row_count"]} rows, got {count}')
    result = {'index': index, 'row_count': count, 'value_sum': total}
    write_json(target, result)
    return result


def aggregate(run_dir):
    target = run_dir / 'summary.json'
    target.unlink(missing_ok=True)
    items = manifest(run_dir)['shards']
    count, total = 0, 0
    for item in items:
        index = item['index']
        partial = json.loads((run_dir / 'partials' / f'{index}.json').read_text(encoding='utf-8'))
        first, last = index * ROWS_PER_SHARD + 1, (index + 1) * ROWS_PER_SHARD
        expected = {'index': index, 'row_count': ROWS_PER_SHARD, 'value_sum': (first + last) * ROWS_PER_SHARD}
        if (not isinstance(partial, dict) or set(partial) != set(expected)
                or any(type(v) is not int for v in partial.values()) or partial != expected):
            raise ValueError(f'Shard {index}: invalid partial index, count or sum: {partial!r}')
        count += partial['row_count']
        total += partial['value_sum']
    result = {'shards': len(items), 'row_count': count, 'value_sum': total}
    write_json(target, result)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest='operation', required=True)
    for name in ('prepare', 'worker', 'aggregate'):
        command = subparsers.add_parser(name)
        command.add_argument('--run-dir', type=Path, required=True)
        if name == 'worker':
            command.add_argument('--index', type=int, required=True)
    args = parser.parse_args()
    try:
        if args.operation == 'prepare':
            result = prepare(args.run_dir)
        elif args.operation == 'worker':
            result = worker(args.run_dir, args.index)
        else:
            result = aggregate(args.run_dir)
    except (OSError, ValueError, csv.Error) as exc:
        print(f'pipeline {args.operation}: {exc}', file=sys.stderr)
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
