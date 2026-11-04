#!/usr/bin/env python3
"""
Syncs combine-v3.json (the Draft Combine rows the comparison tool and the
comparison video generator read) from the HoopsMatic prospect database.

Source: the prospect database's public data file (repo nba-draft-combine,
served by GitHub Pages). No token: it is a plain public GET.

    python scripts/update-combine.py                 # fetch SOURCE_URL
    python scripts/update-combine.py --source f.json # use a local copy
    python scripts/update-combine.py --report r.json # also write a diff report

Rules
- Merge, never wipe: the prospect database wins for every (player, combine
  year) it has; a row that exists only in combine-v3.json is kept as is.
  A metric the prospect database leaves empty keeps the committed value.
- New rows are named after the rsStats.json player they belong to, because
  both pages look a player up with row.PLAYER === <rsStats name>. Matching is
  exact first, then accent/punctuation/suffix tolerant (Jr., Sr., II, III, IV).
  A match must also fit the career: the player's first NBA season has to fall
  within a few years after the combine, so a son is never matched to his
  father's row (or the other way round).
- Output keeps the committed file's shape and order: same keys, string
  values, YEAR descending then PLAYER A-Z, indent 2, no trailing newline.
Exits 1 (and writes nothing) on a fetch error or a source that looks wrong.
"""

import argparse
import json
import re
import sys
import time
import unicodedata

import requests

SOURCE_URL = 'https://jsierrahoopshype.github.io/nba-draft-combine/data/combine.json'
OUTPUT_PATH = 'combine-v3.json'
RS_PATH = 'rsStats.json'

KEYS = ['', 'YEAR', 'PLAYER', 'NB CODE', 'POS', 'BODY FAT %', 'HAND SIZE', 'WEIGHT (LBS)',
        'HEIGHT', 'STANDING', 'WINGSPAN', 'HEIGHT W/O SHOES', 'STANDING REACH',
        'LANE AGILITY', 'SHUTTLE RUN', '3/4 SPRINT', 'STANDING VERT', 'MAX VERT', 'MAX BENCH']
# Fields the prospect database owns. '', PLAYER and NB CODE stay as committed.
DATA_KEYS = KEYS[4:]

SUFFIXES = {'jr', 'sr', 'ii', 'iii', 'iv', 'v'}
# A combine in June of year Y is followed by a first season ending Y+1. Players
# who go back to school or overseas debut later, so allow up to 6 years.
FIRST_SEASON_WINDOW = (0, 6)


# ---------- fetch ----------

def fetch_source(url):
    last = None
    for attempt in range(4):
        try:
            r = requests.get(url, params={'cb': int(time.time())}, timeout=60,
                             headers={'User-Agent': 'nba-player-data combine sync'})
            r.raise_for_status()
            return r.json()
        except (requests.RequestException, ValueError) as e:
            last = e
            time.sleep(2 ** (attempt + 1))
    sys.exit(f'::error::could not fetch {url}: {last}')


def validate_source(src):
    if not isinstance(src, dict) or not isinstance(src.get('players'), list):
        sys.exit('::error::source is not the prospect database format (no players list)')
    players = src['players']
    if len(players) < 1000:
        sys.exit(f'::error::source has only {len(players)} players; refusing')
    for p in players[:50]:
        if not {'season', 'player', 'metrics'} <= set(p):
            sys.exit('::error::source rows lack season/player/metrics; refusing')
    return players


# ---------- formatting (matches the committed strings) ----------

def num(v):
    """243.2 -> '243.2', 299.0 -> '299', 85.3125 -> '85.3125', None -> ''."""
    if v is None:
        return ''
    s = ('%.4f' % float(v)).rstrip('0').rstrip('.')
    return '0' if s in ('', '-0') else s


def feet_inches(inches):
    """95.5 -> "7' 11.50''" (the format the 2010s+ rows use)."""
    if inches is None:
        return ''
    ft = int(inches // 12)
    return "%d' %.2f''" % (ft, inches - ft * 12)


def raw(p, metric):
    m = (p.get('metrics') or {}).get(metric) or {}
    return m.get('raw')


def to_row(p):
    disp = p.get('display') or {}
    bf = raw(p, 'Body Fat %')
    return {
        'POS': (p.get('position') or '').replace('-', ''),
        'BODY FAT %': '' if bf is None else '%.2f%%' % bf,
        'HAND SIZE': num(raw(p, 'hand_area')),
        'WEIGHT (LBS)': num(raw(p, 'Weight (lbs)')),
        'HEIGHT': num(raw(p, 'Height without shoes (in)')),
        'STANDING': num(raw(p, 'Standing reach (in)')),
        # Built from the raw inches so every new row has one format ("7' 0.00''");
        # the source's display strings vary by year ("6'5.5''", "7' 1''").
        'WINGSPAN': feet_inches(raw(p, 'Wingspan (in)')) or disp.get('Wingspan', ''),
        'HEIGHT W/O SHOES': feet_inches(raw(p, 'Height without shoes (in)')) or disp.get('Height without shoes', ''),
        'STANDING REACH': feet_inches(raw(p, 'Standing reach (in)')) or disp.get('Standing reach', ''),
        'LANE AGILITY': num(raw(p, 'Lane Agility (sec)')),
        'SHUTTLE RUN': num(raw(p, 'Modified Lane Agility (sec)')),
        '3/4 SPRINT': num(raw(p, '3/4 Court Sprint (sec)')),
        'STANDING VERT': num(raw(p, 'Standing Vertical Leap (in)')),
        'MAX VERT': num(raw(p, 'Max Vertical Leap (in)')),
        'MAX BENCH': num(raw(p, 'Bench Press (reps)')),
    }


# Two spellings of the same measurement are not a change ("7' 1''" vs "7' 1.00''",
# "95" vs "95.0"). Compare on the parsed number when both sides parse.
def as_number(s):
    s = str(s).strip()
    m = re.fullmatch(r"(\d+)'\s*([\d.]+)''", s)
    if m:
        return int(m.group(1)) * 12 + float(m.group(2))
    try:
        return float(s.rstrip('%'))
    except ValueError:
        return None


def decimals(s):
    m = re.search(r'\.(\d+)', str(s))
    return len(m.group(1)) if m else 0


def same_value(a, b):
    """Equal, or one is just the other at lower precision (103.75 vs 103.7,
    196.44 vs 196.4): the committed, more precise value is kept. A real
    difference at the shared precision (3.14 vs 3.15) is a change."""
    if a == b:
        return True
    na, nb = as_number(a), as_number(b)
    if na is None or nb is None:
        return False
    da, db = decimals(a), decimals(b)
    # Whole numbers ("78", "299") are exact values, not a lower precision.
    if min(da, db) == 0 or da == db:
        return abs(na - nb) < 1e-6
    return abs(na - nb) < 10 ** -min(da, db) - 1e-9


FEET_FIELDS = {'WINGSPAN': 'Wingspan (in)', 'HEIGHT W/O SHOES': 'Height without shoes (in)',
               'STANDING REACH': 'Standing reach (in)'}


def same_feet(old, raw_inches):
    """old "8' 7.75''" vs the source's raw 103.7 inches: same precision rule as
    same_value, on total inches (the inches part's decimals, trailing zeros
    dropped, give the old value's precision)."""
    m = re.fullmatch(r"(\d+)'\s*([\d.]+)''", str(old).strip())
    if not m or raw_inches is None:
        return False
    total = int(m.group(1)) * 12 + float(m.group(2))
    if abs(total - raw_inches) < 1e-6:
        return True
    d_old = decimals(m.group(2).rstrip('0').rstrip('.') if '.' in m.group(2) else m.group(2))
    d_new = decimals(num(raw_inches))
    if min(d_old, d_new) == 0 or d_old == d_new:
        return False
    return abs(total - raw_inches) < 10 ** -min(d_old, d_new) - 1e-9


# ---------- names ----------

def tokens(name):
    s = unicodedata.normalize('NFKD', name)
    s = ''.join(c for c in s if not unicodedata.combining(c)).lower()
    s = re.sub(r"[.'`’]", '', s)        # E.J. -> ej, O'Neal -> oneal
    s = re.sub(r'[^a-z0-9]+', ' ', s)        # hyphens, commas -> spaces
    return s.split()


# Formal first name -> the short form rsStats uses (Nathaniel Ament = Nate Ament).
NICKNAMES = {
    'christopher': 'chris', 'nathaniel': 'nate', 'nathan': 'nate', 'raymond': 'ray',
    'michael': 'mike', 'matthew': 'matt', 'joshua': 'josh', 'herbert': 'herb',
    'nicholas': 'nick', 'jonathan': 'jon', 'william': 'will', 'robert': 'rob',
    'daniel': 'dan', 'anthony': 'tony', 'alexander': 'alex', 'benjamin': 'ben',
    'cameron': 'cam', 'zachary': 'zach', 'jacob': 'jake', 'samuel': 'sam',
    'thomas': 'tom', 'timothy': 'tim', 'patrick': 'pat', 'joseph': 'joe',
    'gregory': 'greg', 'kenneth': 'ken', 'ronald': 'ron', 'donald': 'don',
    'edward': 'ed', 'frederick': 'fred', 'jeffrey': 'jeff', 'steven': 'steve',
    'stephen': 'steve', 'bradley': 'brad', 'douglas': 'doug', 'charles': 'charlie',
}


def nick_key(name):
    t = [x for x in tokens(name) if x not in SUFFIXES]
    if t:
        t[0] = NICKNAMES.get(t[0], t[0])
    return ' '.join(t)


def initial_key(name):
    """'judah mintz' -> 'j mintz': only used inside one combine year."""
    t = [x for x in tokens(name) if x not in SUFFIXES]
    return (t[0][0] + ' ' + t[-1]) if len(t) >= 2 else ' '.join(t)


def sorted_key(name):
    return ' '.join(sorted(t for t in tokens(name) if t not in SUFFIXES))


def full_key(name):
    return ' '.join(tokens(name))


def base_key(name):
    return ' '.join(t for t in tokens(name) if t not in SUFFIXES)


def suffix_of(name):
    s = [t for t in tokens(name) if t in SUFFIXES]
    return s[-1] if s else ''


def plausible(first_season, combine_year):
    lo, hi = FIRST_SEASON_WINDOW
    return combine_year + lo <= first_season <= combine_year + hi


class RsIndex:
    def __init__(self, rs_rows):
        self.first, self.last = {}, {}
        for r in rs_rows:
            n, y = r['PLAYER'], int(r['YEAR'])
            self.first[n] = min(self.first.get(n, y), y)
            self.last[n] = max(self.last.get(n, y), y)
        self.by_full, self.by_base, self.by_nick, self.by_sorted = {}, {}, {}, {}
        for n in self.first:
            self.by_full.setdefault(full_key(n), set()).add(n)
            self.by_base.setdefault(base_key(n), set()).add(n)
            self.by_nick.setdefault(nick_key(n), set()).add(n)
            self.by_sorted.setdefault(sorted_key(n), set()).add(n)

    def match(self, name, year):
        """Returns (rsStats name or None, how, note)."""
        ok = lambda c: plausible(self.first[c], year)
        if name in self.first and ok(name):
            return name, 'exact', ''
        c = {x for x in self.by_full.get(full_key(name), ()) if ok(x)}
        if len(c) == 1:
            return c.pop(), 'normalized', ''
        if len(c) > 1:
            return None, '', 'ambiguous: ' + ', '.join(sorted(c))
        suf = suffix_of(name)
        c = {x for x in self.by_base.get(base_key(name), ()) if ok(x)}
        # Never trade one explicit suffix for another (II is not III).
        c = {x for x in c if not suf or not suffix_of(x) or suffix_of(x) == suf}
        if len(c) == 1:
            return c.pop(), 'suffix-tolerant', ''
        if len(c) > 1:
            return None, '', 'ambiguous: ' + ', '.join(sorted(c))
        c = {x for x in self.by_nick.get(nick_key(name), ()) if ok(x)}
        c = {x for x in c if not suf or not suffix_of(x) or suffix_of(x) == suf}
        if len(c) == 1:
            return c.pop(), 'nickname', ''
        if len(c) > 1:
            return None, '', 'ambiguous: ' + ', '.join(sorted(c))
        # Family name first (Hansen Yang = Yang Hansen).
        c = {x for x in self.by_sorted.get(sorted_key(name), ()) if ok(x)}
        if len(c) == 1:
            return c.pop(), 'reordered', ''
        if name in self.first:
            return None, '', ('namesake: %s played %d-%d, not after a %d combine'
                              % (name, self.first[name], self.last[name], year))
        return None, '', ''

    def loose(self, name, year):
        """Plausible rsStats players with the same last name and first initial."""
        t = [x for x in tokens(name) if x not in SUFFIXES]
        if len(t) < 2:
            return []
        out = []
        for n in self.first:
            u = [x for x in tokens(n) if x not in SUFFIXES]
            if len(u) >= 2 and u[-1] == t[-1] and u[0][0] == t[0][0] and plausible(self.first[n], year):
                out.append(n)
        return sorted(out)


# ---------- merge ----------

def sort_key(r):
    return (-int(r['YEAR']), r['PLAYER'].lower())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--source', help='local prospect database JSON instead of SOURCE_URL')
    ap.add_argument('--report', help='write a JSON diff report here')
    args = ap.parse_args()

    if args.source:
        with open(args.source, encoding='utf-8') as f:
            src = json.load(f)
    else:
        src = fetch_source(SOURCE_URL)
    players = validate_source(src)

    with open(OUTPUT_PATH, encoding='utf-8') as f:
        old_text = f.read()
    existing = json.loads(old_text)
    with open(RS_PATH, encoding='utf-8') as f:
        rs = RsIndex(json.load(f))

    # Existing rows by (year, name key), on both PLAYER and NB CODE spellings.
    ex_full, ex_base, ex_init = {}, {}, {}
    for i, r in enumerate(existing):
        for n in {r['PLAYER'], r['NB CODE']}:
            ex_full.setdefault((r['YEAR'], full_key(n)), set()).add(i)
            ex_base.setdefault((r['YEAR'], base_key(n)), set()).add(i)
            ex_init.setdefault((r['YEAR'], initial_key(n)), set()).add(i)

    # Pair prospect rows with committed rows of the same combine year. Pass 1:
    # same name up to accents/punctuation/suffix. Pass 2, for what is left: same
    # last name and first initial (Judah/Judiah Mintz, Ray/Raymond Spalding),
    # only when exactly one prospect and one committed row qualify.
    pair, used_existing = {}, set()
    for j, p in enumerate(players):
        year, pname = str(int(p['season'])), p['player'].strip()
        hit = ex_full.get((year, full_key(pname))) or ex_base.get((year, base_key(pname))) or set()
        if not hit:
            # A row an earlier run added under the rsStats name (Nathaniel Ament
            # was written as Nate Ament, Hansen Yang as Yang Hansen).
            m = rs.match(pname, int(year))[0]
            hit = ex_full.get((year, full_key(m)), set()) if m else set()
        hit = hit - used_existing
        if len(hit) == 1:
            pair[j] = hit.pop()
            used_existing.add(pair[j])
    left = {}
    for j, p in enumerate(players):
        if j not in pair:
            left.setdefault((str(int(p['season'])), initial_key(p['player'].strip())), []).append(j)
    for k, js in left.items():
        hit = ex_init.get(k, set()) - used_existing
        if len(js) == 1 and len(hit) == 1:
            pair[js[0]] = hit.pop()
            used_existing.add(pair[js[0]])

    out = [dict(r) for r in existing]
    report = {'source_generated_at': src.get('generated_at'), 'source_rows': len(players),
              'added': [], 'changed': [], 'renamed': [], 'kept_on_empty': 0,
              'unmatched_possible': [], 'skipped_namesake': [], 'ambiguous': [],
              'unmatched_new_by_class': {}}
    assigned = {}   # rsStats name -> set of prospect full keys

    for j, p in enumerate(players):
        year = str(int(p['season']))
        pname = p['player'].strip()
        new = to_row(p)

        if j in pair:
            row = out[pair[j]]
            for k in DATA_KEYS:
                if new[k] == '':
                    if row[k] != '':
                        report['kept_on_empty'] += 1
                    continue
                if k in FEET_FIELDS and same_feet(row[k], raw(p, FEET_FIELDS[k])):
                    continue
                if not same_value(row[k], new[k]):
                    report['changed'].append({'player': row['PLAYER'], 'year': year, 'metric': k,
                                              'old': row[k], 'new': new[k]})
                    row[k] = new[k]
            # A committed row the pages cannot find (its PLAYER is not an rsStats
            # name) gets the rsStats name, but only when the committed PLAYER or
            # NB CODE already is that name up to accents, punctuation or a suffix
            # (DaRon Holmes II -> DaRon Holmes). A deliberate disambiguation such
            # as "Deonte Burton (1991)" is left alone.
            if row['PLAYER'] not in rs.first and '(' not in row['PLAYER']:
                m, how, _ = rs.match(pname, int(year))
                if m and base_key(m) in {base_key(row['PLAYER']), base_key(row['NB CODE'])}:
                    report['renamed'].append({'year': year, 'old': row['PLAYER'], 'new': m, 'how': how})
                    row['PLAYER'] = m
            continue

        m, how, note = rs.match(pname, int(year))
        if note.startswith('namesake'):
            # Adding it under this name would show this prospect's combine on a
            # different (older) NBA player's comparison.
            report['skipped_namesake'].append({'player': pname, 'year': year, 'note': note})
            continue
        if note.startswith('ambiguous'):
            report['ambiguous'].append({'player': pname, 'year': year, 'note': note})
        row = {k: '' for k in KEYS}
        row.update(new)
        row['YEAR'] = year
        row['PLAYER'] = m or pname
        row['NB CODE'] = m or pname
        row[''] = str(rs.last[m]) if m else ''
        out.append(row)
        report['added'].append({'player': row['PLAYER'], 'source_name': pname, 'year': year,
                                'match': how or 'none'})
        if m:
            assigned.setdefault(m, set()).add(full_key(pname))
        else:
            report['unmatched_new_by_class'][year] = report['unmatched_new_by_class'].get(year, 0) + 1
            cands = rs.loose(pname, int(year))
            if cands:
                report['unmatched_possible'].append({'player': pname, 'year': year, 'candidates': cands})

    # One rsStats player must never collect rows from two different people.
    for m, keys in assigned.items():
        if len(keys) > 1:
            sys.exit('::error::%s would get rows from different people: %s' % (m, sorted(keys)))

    out.sort(key=sort_key)
    out = [{k: r.get(k, '') for k in KEYS} for r in out]
    text = json.dumps(out, indent=2, ensure_ascii=False)

    by_class = {}
    for a in report['added']:
        by_class[a['year']] = by_class.get(a['year'], 0) + 1
    print(f"source: {len(players)} prospect rows (generated {src.get('generated_at')})")
    print(f"{OUTPUT_PATH}: {len(existing)} -> {len(out)} rows")
    print('added by class:', dict(sorted(by_class.items())))
    print(f"changed values in existing rows: {len(report['changed'])}")
    print(f"renamed existing rows to their rsStats name: {len(report['renamed'])}")
    print(f"empty in source, committed value kept: {report['kept_on_empty']}")
    for u in report['unmatched_possible']:
        print(f"UNMATCHED (possible NBA player) {u['year']} {u['player']}: {', '.join(u['candidates'])}")
    for u in report['skipped_namesake']:
        print(f"SKIPPED {u['year']} {u['player']}: {u['note']}")
    for u in report['ambiguous']:
        print(f"AMBIGUOUS {u['year']} {u['player']}: {u['note']}")

    if args.report:
        with open(args.report, 'w', encoding='utf-8') as f:
            json.dump(report, f, indent=2, ensure_ascii=False)
    if text == old_text:
        print('No change.')
        return
    with open(OUTPUT_PATH, 'w', encoding='utf-8') as f:
        f.write(text)
    print(f'Wrote {OUTPUT_PATH}.')


if __name__ == '__main__':
    main()
