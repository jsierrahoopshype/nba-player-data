#!/usr/bin/env python3
"""Refresh data/h2h-players.json from HoopsMatic Head to Head's public player list.

Source: https://jsierrahoopshype.github.io/nba-head-to-head/data/search.json
(nba-head-to-head build/build.mjs: [id, name, hub slug, first season, last season,
All-Star flag, games, headshot stem]). Kept: [name, hub slug, first, last, headshot stem].

build_player_files.py reads the saved copy to give each player in the comparison
tool his Head to Head hub link (https://hoopsmatic.com/head-to-head/player/<slug>/)
and his headshot (nba-headshots, the same file Head to Head shows).

A failed or suspicious fetch never replaces the saved copy: exits 1 and leaves it.
Run from the repo root:  python scripts/update_h2h_players.py
"""
import json
import os
import sys
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, 'data', 'h2h-players.json')
URL = 'https://jsierrahoopshype.github.io/nba-head-to-head/data/search.json'


def main():
    try:
        req = urllib.request.Request(URL, headers={'User-Agent': 'nba-player-data build'})
        with urllib.request.urlopen(req, timeout=60) as r:
            rows = json.loads(r.read().decode('utf-8'))
    except Exception as e:  # network, HTTP or JSON error
        print(f'ERROR: could not read {URL}: {e}', file=sys.stderr)
        return 1

    out = []
    for e in rows if isinstance(rows, list) else []:
        if not (isinstance(e, list) and len(e) >= 8):
            continue
        name, slug, first, last, stem = e[1], e[2], e[3], e[4], e[7]
        if not (isinstance(name, str) and isinstance(slug, str) and slug):
            continue
        out.append([name, slug, first, last, stem if isinstance(stem, str) and stem else None])

    old = []
    if os.path.exists(OUT):
        with open(OUT, encoding='utf-8') as f:
            old = json.load(f)
    if not out or len(out) < 0.9 * len(old):
        print(f'ERROR: {len(out)} players from the source vs {len(old)} saved; keeping the saved copy', file=sys.stderr)
        return 1

    with open(OUT, 'w', encoding='utf-8') as f:
        f.write('[\n' + ',\n'.join(json.dumps(x, ensure_ascii=False) for x in out) + '\n]\n')
    print(f'{len(out)} Head to Head players saved')
    return 0


if __name__ == '__main__':
    sys.exit(main())
