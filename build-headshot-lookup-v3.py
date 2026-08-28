"""
Build player-headshots.json from the nba-headshots METADATA.

v3 change: two-pass matching so a father and son never share one image.

  Pass 1  exact (accent/punctuation-insensitive) name match. Each image
          matched this way is CLAIMED.
  Pass 2  suffix-tolerant match (Jr/Sr/II/III/IV) for players still
          unmatched, but only against images nobody claimed in pass 1.

That ordering is what fixes the father/son pairs. "Larry Nance Jr" matches
his own record exactly and claims 1626204-larry-nance-jr; "Larry Nance"
then finds it already taken and is reported as having no headshot, rather
than borrowing his son's face. Pass 2 still does its original job for the
harmless cases (rsStats spells a name without the suffix and only the
suffixed record exists).

Run from the nba-player-data repo root, with nba-headshots as a sibling
folder (override with --headshots-repo):

    python build-headshot-lookup-v3.py

Output: player-headshots.json  {"LeBron James": "2544-lebron-james", ...}
"""

import argparse
import glob
import json
import os
import unicodedata

DEFAULT_HEADSHOTS_REPO = os.path.join('..', 'nba-headshots')
OUTPUT = 'player-headshots.json'
RS_STATS = 'rsStats.json'
SUFFIXES = ('jr', 'sr', 'iv', 'iii', 'ii')


def norm(s):
    """Accent- and punctuation-insensitive key for matching names."""
    s = unicodedata.normalize('NFKD', str(s))
    s = ''.join(c for c in s if not unicodedata.combining(c))
    return ''.join(c for c in s if c.isalnum()).lower()


def strip_suffix(s):
    out = norm(s)
    for suf in SUFFIXES:
        if out.endswith(suf):
            return out[: -len(suf)]
    return out


def iter_records(obj):
    if isinstance(obj, list):
        for r in obj:
            if isinstance(r, dict):
                yield r
    elif isinstance(obj, dict):
        for v in obj.values():
            if isinstance(v, dict):
                yield v
            elif isinstance(v, list):
                for r in v:
                    if isinstance(r, dict):
                        yield r


def load_metadata(repo):
    """name -> slug (filename without .png), from every metadata json."""
    meta_dir = os.path.join(repo, 'players', 'metadata')
    if not os.path.isdir(meta_dir):
        raise SystemExit('Metadata folder not found: ' + os.path.abspath(meta_dir))

    by_name = {}
    seen_ids = {}
    conflicts = []

    for path in sorted(glob.glob(os.path.join(meta_dir, '*.json'))):
        try:
            data = json.load(open(path, encoding='utf-8'))
        except Exception as exc:
            print('  skip %s (%s)' % (os.path.basename(path), exc))
            continue

        for rec in iter_records(data):
            name = rec.get('full_name') or rec.get('name')
            head = rec.get('headshot') or {}
            fname = head.get('filename')
            if not name or not fname or not head.get('face'):
                continue

            slug = fname[:-4] if fname.lower().endswith('.png') else fname
            pid = str(rec.get('nba_id'))

            if pid in seen_ids and norm(seen_ids[pid]) != norm(name):
                conflicts.append((pid, seen_ids[pid], name))
                continue
            seen_ids[pid] = name

            by_name[name] = slug

    if conflicts:
        print('\n  WARNING: nba_id claimed by two players (skipped the later one):')
        for pid, first, second in conflicts:
            print('    %s: %s / %s' % (pid, first, second))

    return by_name


def load_player_names(path):
    data = json.load(open(path, encoding='utf-8'))
    names = set()
    for row in data:
        n = row.get('PLAYER')
        if n:
            names.add(n.strip())
    return sorted(names)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--headshots-repo', default=DEFAULT_HEADSHOTS_REPO)
    args = ap.parse_args()

    print('Reading headshot metadata from %s ...' % os.path.abspath(args.headshots_repo))
    meta = load_metadata(args.headshots_repo)
    print('  %d players with a face crop in metadata' % len(meta))

    print('Reading player names from %s ...' % RS_STATS)
    players = load_player_names(RS_STATS)
    print('  %d unique players' % len(players))

    exact = {}
    loose = {}
    for name, slug in meta.items():
        exact.setdefault(norm(name), slug)
        loose.setdefault(strip_suffix(name), slug)

    lookup = {}
    claimed = set()

    # Pass 1 -- exact matches win and claim their image.
    for player in players:
        slug = exact.get(norm(player))
        if slug:
            lookup[player] = slug
            claimed.add(slug)

    # Pass 2 -- suffix-tolerant, but only for unclaimed images.
    loose_hits = []
    for player in players:
        if player in lookup:
            continue
        slug = loose.get(strip_suffix(player))
        if slug and slug not in claimed:
            lookup[player] = slug
            claimed.add(slug)
            loose_hits.append((player, slug))

    unmatched = [p for p in players if p not in lookup]

    # Nothing should be shared after the two passes; check anyway.
    rev = {}
    dupes = []
    for name, slug in lookup.items():
        if slug in rev:
            dupes.append((slug, rev[slug], name))
        else:
            rev[slug] = name

    print('\nMatched %d / %d players (%d via suffix fallback)'
          % (len(lookup), len(players), len(loose_hits)))
    if dupes:
        print('\n  WARNING: one image claimed by two players:')
        for slug, a, b in dupes:
            print('    %s: %s / %s' % (slug, a, b))
    else:
        print('No image is shared by two players.')

    json.dump(lookup, open(OUTPUT, 'w', encoding='utf-8'),
              ensure_ascii=False, indent=2, sort_keys=True)
    print('\nWrote %s (%d entries)' % (OUTPUT, len(lookup)))

    print('\nFather/son check:')
    for probe in ('Larry Nance', 'Larry Nance Jr',
                  'Tim Hardaway', 'Tim Hardaway Jr',
                  'Jaren Jackson', 'Jaren Jackson Jr',
                  'Gary Trent', 'Gary Trent Jr',
                  'Glenn Robinson', 'Glenn Robinson III'):
        print('  %-20s -> %s' % (probe, lookup.get(probe, '(no headshot)')))

    print('\nEarlier fixes still good:')
    for probe in ('Chris Paul', 'Hakeem Olajuwon', 'Patrick Ewing', 'Kevin Garnett'):
        print('  %-20s -> %s' % (probe, lookup.get(probe, '(no headshot)')))

    if loose_hits:
        print('\n%d matched only via suffix fallback (first 20):' % len(loose_hits))
        for name, slug in loose_hits[:20]:
            print('    %-24s -> %s' % (name, slug))

    print('\n%d players have no headshot.' % len(unmatched))


if __name__ == '__main__':
    main()
