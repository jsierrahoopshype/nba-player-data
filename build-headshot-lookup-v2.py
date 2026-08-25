"""
Build player-headshots.json from the nba-headshots METADATA rather than from
the GitHub directory listing.

Why: the face/ folder still contains orphan files from earlier fetch runs
(e.g. 2585-chris-paul.png holds Zaza Pachulia's face, 193-hakeem-olajuwon.png
holds Anthony Mason's). Listing the directory and fuzzy-matching names picked
those up. The metadata is authoritative -- each record pairs a player with
their own headshot.filename, and it was verified to contain no duplicate
nba_ids.

Run from the nba-player-data repo root. Expects nba-headshots checked out as
a sibling folder; override with --headshots-repo.

    python build-headshot-lookup-v2.py

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


def norm(s):
    """Accent- and punctuation-insensitive key for matching names."""
    s = unicodedata.normalize('NFKD', str(s))
    s = ''.join(c for c in s if not unicodedata.combining(c))
    return ''.join(c for c in s if c.isalnum()).lower()


def strip_suffix(s):
    """Drop Jr/Sr/II/III/IV so 'Tim Hardaway Jr' can meet 'Tim Hardaway Jr.'."""
    out = norm(s)
    for suf in ('jr', 'sr', 'iv', 'iii', 'ii'):
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
            if not name or not fname:
                continue
            if not head.get('face'):
                continue  # no face crop generated for this player

            slug = fname[:-4] if fname.lower().endswith('.png') else fname
            pid = str(rec.get('nba_id'))

            # An id must belong to exactly one player.
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

    # Index the metadata names once, exact-normalised and suffix-stripped.
    exact = {}
    loose = {}
    for name, slug in meta.items():
        exact.setdefault(norm(name), (name, slug))
        loose.setdefault(strip_suffix(name), (name, slug))

    lookup = {}
    unmatched = []
    for player in players:
        hit = exact.get(norm(player)) or loose.get(strip_suffix(player))
        if hit:
            lookup[player] = hit[1]
        else:
            unmatched.append(player)

    # Every slug should be claimed by at most one player name.
    rev = {}
    dupes = []
    for name, slug in lookup.items():
        if slug in rev:
            dupes.append((slug, rev[slug], name))
        else:
            rev[slug] = name

    print('\nMatched %d / %d players' % (len(lookup), len(players)))
    if dupes:
        print('\n  WARNING: one image claimed by two players:')
        for slug, a, b in dupes:
            print('    %s: %s / %s' % (slug, a, b))
    else:
        print('No image is shared by two players.')

    json.dump(lookup, open(OUTPUT, 'w', encoding='utf-8'),
              ensure_ascii=False, indent=2, sort_keys=True)
    print('\nWrote %s (%d entries)' % (OUTPUT, len(lookup)))

    for probe in ('Chris Paul', 'Hakeem Olajuwon', 'Zaza Pachulia',
                  'Anthony Mason', 'Patrick Ewing', 'Kevin Garnett'):
        print('  %-18s -> %s' % (probe, lookup.get(probe, '(unmatched)')))

    if unmatched:
        print('\n%d players have no headshot (first 25):' % len(unmatched))
        for n in unmatched[:25]:
            print('   ', n)


if __name__ == '__main__':
    main()
