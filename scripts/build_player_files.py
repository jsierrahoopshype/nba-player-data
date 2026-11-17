#!/usr/bin/env python3
"""Split the big data files into one small JSON per player for the comparison tool.

The comparison tool (nba-player-comparison-tool.html, served at hoopsmatic.com/compare)
used to download every data file (~15 MB raw) before showing anything. It only ever
needs the rows of the players being compared, so this writes:

  players/index.json        sorted list of player names (search box, URL validation)
  players/<slug>.json       every row, from every dataset the tool reads, that
                            belongs to the players whose name maps to <slug>

The full files (rsStats.json, awards.json, ...) are left untouched: other tools
still read them.

Per-player file format:
  { "<dataset>": [[<row index in the full file>, <row>], ...], ...,
    "links": { "<player name>": { "hub": "<Head to Head hub slug>", "hs": "<headshot stem>" } } }
"links" (from data/h2h-players.json, see h2h_links()) is only for the page's look:
the player's HoopsMatic Head to Head page and headshot.
The row index lets the page rebuild, for the players it has loaded, exactly the
same rows in exactly the same order as the full file, so every filter()/find()
in the page returns what it returned before. Rows are copied as-is.

Matching mirrors the page: a row belongs to a player when the page's lookup field
equals the player's name exactly (no trimming). nba2k rows match on 'Full Name'
or 'First Name' + ' ' + 'Last Name', so they go under both.

slug(): lowercase ASCII letters and digits are kept, every other character becomes
'_' (and a leading '_' gets a 'p' prefix, since GitHub Pages skips '_' files). The page computes the same slug to fetch a file without waiting for the
index. Different names can share a slug (e.g. accented vs plain spelling); they
share the file, and the page de-duplicates rows by index.

Run from the repo root:  python scripts/build_player_files.py
Writes only under players/, removes stale player files, and exits 1 without
writing anything if a source file is missing or malformed.
"""
import json
import os
import re
import sys
import unicodedata

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_DIR = os.path.join(ROOT, 'players')

# dataset key in the page -> (source file, function returning the lookup keys of a row)
def _field(name):
    return lambda row: [row.get(name)]

def _nba2k_keys(row):
    keys = [row.get('Full Name')]
    first, last = row.get('First Name'), row.get('Last Name')
    # Page builds row['First Name'] + ' ' + row['Last Name'] (JS string concat).
    if isinstance(first, str) and isinstance(last, str):
        keys.append(first + ' ' + last)
    return keys

DATASETS = {
    'awards':     ('awards.json',     _field('PLAYER / COACH')),
    'allStar':    ('allStar.json',    _field('NAME')),
    'awardVotes': ('awardVotes.json', _field('PLAYER')),
    'combine':    ('combine-v3.json', _field('PLAYER')),
    'nba2k':      ('nba2k.json',      _nba2k_keys),
    'poSeries':   ('poSeries.json',   _field('NAME')),
    'poStats':    ('poStats.json',    _field('PLAYER')),
    'rsStats':    ('rsStats.json',    _field('PLAYER')),
    'salaries':   ('salaries.json',   _field('PLAYER')),
    'sneakers':   ('sneakers.json',   _field('PLAYER')),
    'bio':        ('bio.json',        _field('PLAYER')),
}


def slug(name):
    # Same rule as playerSlug() in the page: per code point, ASCII letters
    # lowercased, ASCII digits kept, anything else '_'.
    # A leading '_' gets a 'p' prefix: GitHub Pages (Jekyll) does not publish files
    # whose names start with '_'.
    s = ''.join(c.lower() if (c.isascii() and c.isalnum()) else '_' for c in name)
    return 'p' + s if s.startswith('_') else s


H2H_FILE = os.path.join(ROOT, 'data', 'h2h-players.json')


def h2h_slugify(s):
    # nba-head-to-head build/build.mjs slugify(): NFKD, accents dropped, lowercase,
    # every run of other characters -> '-', no leading/trailing '-'.
    s = unicodedata.normalize('NFKD', s)
    s = ''.join(c for c in s if not ('\u0300' <= c <= '\u036f')).lower()
    return re.sub(r'[^a-z0-9]+', '-', s).strip('-')


def h2h_links(names, rs_rows):
    """name -> {"hub": Head to Head hub slug, "hs": headshot stem or absent}.

    From data/h2h-players.json (scripts/update_h2h_players.py). A player is matched by
    name (Head to Head's slug rule, then a looser one) and career years: our rsStats
    YEAR is the season's end year, Head to Head's first/last its start year. Only a
    single candidate whose career overlaps ours gets a link; none or several: no link.
    Missing file: no links (the page then shows initials and plain names)."""
    try:
        with open(H2H_FILE, encoding='utf-8') as f:
            h2h = json.load(f)
    except (OSError, ValueError):
        print('note: data/h2h-players.json missing or unreadable, no Head to Head links')
        return {}
    by = {}
    for e in h2h:
        by.setdefault(h2h_slugify(e[0]), []).append(e)
    years = {}
    for r in rs_rows:
        n, y = r.get('PLAYER'), str(r.get('YEAR', ''))
        if isinstance(n, str) and y.isdigit():
            lo, hi = years.get(n.strip(), (9999, 0))
            years[n.strip()] = (min(lo, int(y) - 1), max(hi, int(y) - 1))

    def overlaps(e, yr):
        return yr is None or not (isinstance(e[2], int) and isinstance(e[3], int)) or \
            (e[2] <= yr[1] + 1 and yr[0] - 1 <= e[3])

    def loose(n):
        # second try: no "(1965)" tag, no Jr./Sr./II-V, no punctuation ("AJ" = "A.J.", "Amare" = "Amar'e")
        n = re.sub(r'\s*\(\d{4}\)\s*$', '', n)
        k = h2h_slugify(n)
        k = re.sub(r'-(jr|sr|ii|iii|iv|v)$', '', k)
        return k.replace('-', '')

    by_loose = {}
    for e in h2h:
        by_loose.setdefault(loose(e[0]), []).append(e)

    out = {}
    for n in names:
        cands = [e for e in by.get(h2h_slugify(n), []) if overlaps(e, years.get(n))]
        if not cands:
            cands = [e for e in by_loose.get(loose(n), []) if overlaps(e, years.get(n))]
        # several players fit (same name, overlapping careers): no link rather than a wrong one
        if len(cands) == 1:
            e = cands[0]
            link = {'hub': e[1]}
            if e[4]:
                link['hs'] = e[4]
            out[n] = link
    return out


def main():
    data = {}
    for key, (fname, _) in DATASETS.items():
        path = os.path.join(ROOT, fname)
        try:
            with open(path, encoding='utf-8') as f:
                rows = json.load(f)
        except (OSError, ValueError) as e:
            print(f'ERROR: cannot read {fname}: {e}', file=sys.stderr)
            return 1
        if not isinstance(rows, list) or not rows:
            print(f'ERROR: {fname} is not a non-empty list', file=sys.stderr)
            return 1
        data[key] = rows

    # Player list exactly as the page built it: rsStats PLAYER + awards 'PLAYER / COACH', trimmed.
    names = set()
    for row in data['rsStats']:
        if isinstance(row.get('PLAYER'), str) and row['PLAYER']:
            names.add(row['PLAYER'].strip())
    for row in data['awards']:
        if isinstance(row.get('PLAYER / COACH'), str) and row['PLAYER / COACH']:
            names.add(row['PLAYER / COACH'].strip())
    names.discard('')

    files = {}  # slug -> {dataset: [[idx, row], ...]}
    for key, (_, keyfn) in DATASETS.items():
        for idx, row in enumerate(data[key]):
            if not isinstance(row, dict):
                continue
            seen = set()
            for k in keyfn(row):
                if not isinstance(k, str) or not k:
                    continue
                s = slug(k)
                if s in seen:
                    continue
                seen.add(s)
                files.setdefault(s, {}).setdefault(key, []).append([idx, row])

    # Head to Head hub link + headshot per listed player, under "links" in his file.
    links = h2h_links(names, data['rsStats'])
    for n, link in links.items():
        files.setdefault(slug(n), {}).setdefault('links', {})[n] = link

    # Every listed player must have a file (they all come from rsStats/awards rows).
    missing = [n for n in names if slug(n) not in files]
    if missing:
        print(f'ERROR: no rows for {len(missing)} listed players, e.g. {missing[:3]}', file=sys.stderr)
        return 1

    os.makedirs(OUT_DIR, exist_ok=True)
    written = changed = 0
    for s, content in files.items():
        path = os.path.join(OUT_DIR, s + '.json')
        text = json.dumps(content, ensure_ascii=False, separators=(',', ':'))
        old = None
        if os.path.exists(path):
            with open(path, encoding='utf-8') as f:
                old = f.read()
        if old != text:
            with open(path, 'w', encoding='utf-8') as f:
                f.write(text)
            changed += 1
        written += 1

    index_text = json.dumps(sorted(names), ensure_ascii=False, separators=(',', ':'))
    with open(os.path.join(OUT_DIR, 'index.json'), 'w', encoding='utf-8') as f:
        f.write(index_text)

    keep = {s + '.json' for s in files} | {'index.json'}
    removed = 0
    for fn in os.listdir(OUT_DIR):
        if fn.endswith('.json') and fn not in keep:
            os.remove(os.path.join(OUT_DIR, fn))
            removed += 1

    print(f'{len(names)} players ({len(links)} with a Head to Head page), {written} player files ({changed} changed, {removed} removed)')
    return 0


if __name__ == '__main__':
    sys.exit(main())
