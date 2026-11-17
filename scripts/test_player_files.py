#!/usr/bin/env python3
"""Check players/ against the full data files (run after build_player_files.py).

For every player in players/index.json and every dataset, the rows the page gets
from that player's file (merged by row index, filtered by the page's exact-name
lookup) must equal the rows the page used to get from the full file, in the same
order. Also checks that the index equals the name list the page used to build,
and (if node is installed) that the page's playerSlug() matches slug().

Run from the repo root:  python scripts/test_player_files.py
Exits 1 on the first kind of mismatch, printing examples.
"""
import json
import os
import re
import shutil
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import build_player_files as b  # noqa: E402

ROOT = b.ROOT
HTML = os.path.join(ROOT, 'nba-player-comparison-tool.html')


def page_matches(key, row, name):
    """The page's lookup: does this row belong to `name` in dataset `key`?"""
    if key == 'nba2k':
        first, last = row.get('First Name'), row.get('Last Name')
        return row.get('Full Name') == name or (
            isinstance(first, str) and isinstance(last, str) and first + ' ' + last == name)
    return b.DATASETS[key][1](row)[0] == name


def main():
    failures = 0
    data = {k: json.load(open(os.path.join(ROOT, f), encoding='utf-8')) for k, (f, _) in b.DATASETS.items()}

    expected_names = set()
    for row in data['rsStats']:
        if isinstance(row.get('PLAYER'), str) and row['PLAYER']:
            expected_names.add(row['PLAYER'].strip())
    for row in data['awards']:
        if isinstance(row.get('PLAYER / COACH'), str) and row['PLAYER / COACH']:
            expected_names.add(row['PLAYER / COACH'].strip())
    expected_names.discard('')
    index = json.load(open(os.path.join(b.OUT_DIR, 'index.json'), encoding='utf-8'))
    if set(index) != expected_names or len(index) != len(expected_names):
        print('FAIL: players/index.json differs from the rsStats + awards name list')
        failures += 1

    # Expected rows per (dataset, name), from the full files.
    expected = {k: {} for k in b.DATASETS}
    names = set(index)
    for key, rows in data.items():
        for i, row in enumerate(rows):
            if not isinstance(row, dict):
                continue
            cands = [c for c in b.DATASETS[key][1](row) if isinstance(c, str) and c in names]
            for n in set(cands):
                if page_matches(key, row, n):
                    expected[key].setdefault(n, []).append(i)

    file_cache = {}
    bad = []
    for n in index:
        s = b.slug(n)
        if s not in file_cache:
            with open(os.path.join(b.OUT_DIR, s + '.json'), encoding='utf-8') as f:
                file_cache[s] = json.load(f)
        content = file_cache[s]
        for key in b.DATASETS:
            merged = {}
            for i, row in content.get(key, []):
                merged.setdefault(i, row)
            got = [i for i in sorted(merged) if page_matches(key, merged[i], n)]
            want = expected[key].get(n, [])
            if got != want or any(merged[i] != data[key][i] for i in got):
                bad.append((n, key, len(want), len(got)))
    if bad:
        print(f'FAIL: {len(bad)} player/dataset mismatches, e.g. {bad[:5]}')
        failures += 1

    # "links" (Head to Head page + headshot): only listed names, safe slugs and stems
    bad_links = []
    for s_, content in file_cache.items():
        for n, l in (content.get('links') or {}).items():
            if n not in names or not re.fullmatch(r'[a-z0-9-]+', l.get('hub', '')) or \
                    ('hs' in l and not re.fullmatch(r'[0-9a-z-]+', l['hs'])) or b.slug(n) != s_:
                bad_links.append((s_, n, l))
    if bad_links:
        print(f'FAIL: {len(bad_links)} bad "links" entries, e.g. {bad_links[:3]}')
        failures += 1

    # slug parity with the page's JavaScript
    node = shutil.which('node')
    if node:
        html = open(HTML, encoding='utf-8').read()
        m = re.search(r'function playerSlug\(name\) \{.*?\n        \}', html, re.S)
        if not m:
            print('FAIL: playerSlug() not found in the page')
            failures += 1
        else:
            samples = index + ['Nikola Jokić', 'Luka Dončić', "Shaquille O'Neal", 'Ğ', '𝔸b', ' X ', 'İstanbul']
            js = m.group(0) + '\nconst names = JSON.parse(require("fs").readFileSync(0, "utf8"));\n' \
                 'process.stdout.write(JSON.stringify(names.map(playerSlug)));'
            out = subprocess.run([node, '-e', js], input=json.dumps(samples), capture_output=True, text=True, check=True)
            js_slugs = json.loads(out.stdout)
            diff = [(n, a, p) for n, a, p in zip(samples, js_slugs, map(b.slug, samples)) if a != p]
            if diff:
                print(f'FAIL: JS and Python slugs differ: {diff[:5]}')
                failures += 1
    else:
        print('note: node not found, skipped the JS slug check')

    if failures:
        return 1
    print(f'OK: {len(index)} players x {len(b.DATASETS)} datasets match the full files')
    return 0


if __name__ == '__main__':
    sys.exit(main())
