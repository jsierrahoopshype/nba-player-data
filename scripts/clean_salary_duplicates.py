#!/usr/bin/env python3
"""
ONE-TIME CLEANUP for salaries.json.

    cd "C:\\Users\\Jorge Sierra\\Documents\\nba-player-data"
    python scripts\\clean_salary_duplicates.py --dry-run     <- look first
    python scripts\\clean_salary_duplicates.py               <- then do it

Fixing update-salaries.py stops NEW bad rows. It does not remove the ones
already committed, and those are what the comparison tool is summing today.

WHY THIS IS SCOPED TO ONE SEASON, which the first version of this script was
not, and would have deleted real money:

The bug lives entirely in update-salaries.py, which only ever writes years in
its IMPORT_YEARS - currently {'2026'}. Every bad row was created there. So this
only touches those years, and it reports everything else without changing it.

The first version matched on "same salary, different teams" across the whole
file and proposed removing 175 rows. Its own examples gave it away:

    Marcus Camby 2015: keeping TOR $4,177,208, dropping HOU
    Zylan Cheatham 2022: keeping UTA $85,578, dropping MIA, NOP
    Briante Weber 2016: keeping MIA $30,887, dropping MEM

Those are 10-day contracts. The 10-day minimum is a fixed formula, so a
journeyman who signs one with two clubs in a season is paid the SAME amount by
each. Two rows, one salary, two teams - and both are real. Deleting them would
have understated those careers, which is the same class of error as the
overstatement this exists to fix, only harder to notice.

Identical salaries are not evidence of a copy. What identifies the bug is
WHERE the row came from, and only the importer's own years can contain one.

WHAT IT REMOVES, inside those years

A player-season holding one salary under several teams, because the Future
Salaries sheet has one TEAM column meaning "where he is now" while its salary
columns span several seasons:

    LA Lakers     2026   $52,627,153   <- real: what the Lakers paid in 2025-26
    Philadelphia  2026   $52,627,153   <- where he plays in 2026-27, wrong money

WHAT IT KEEPS

Different amounts, always: a genuine mid-season trade splits a salary into two
unequal halves. Anything outside the scoped years, always. And where the stats
cannot say which team is real, it keeps the FIRST row in file order, because
appended rows go on the end - the original was there before this bug existed.

Every removal is reported. Nothing is written in --dry-run. A timestamped
backup is written before any change.
"""

import argparse
import json
import os
import shutil
import sys
from datetime import datetime

SALARIES = 'salaries.json'
STATS = 'rsStats.json'

# The seasons update-salaries.py writes, and therefore the only ones that can
# hold a row it invented. Keep this in step with IMPORT_YEARS in that script.
DEFAULT_SCOPE = ['2026']

# The salaries file spells teams both ways ("LAL" up to 2025, "LA Lakers" in
# 2026); rsStats has its own spelling. Both are normalised before comparing or
# the tiebreak silently never matches and every case falls back to file order.
TEAM_CODE = {
    'atlanta': 'ATL', 'boston': 'BOS', 'brooklyn': 'BKN', 'charlotte': 'CHA',
    'chicago': 'CHI', 'cleveland': 'CLE', 'dallas': 'DAL', 'denver': 'DEN',
    'detroit': 'DET', 'golden state': 'GSW', 'houston': 'HOU', 'indiana': 'IND',
    'la clippers': 'LAC', 'la lakers': 'LAL', 'los angeles clippers': 'LAC',
    'los angeles lakers': 'LAL', 'memphis': 'MEM', 'miami': 'MIA',
    'milwaukee': 'MIL', 'minnesota': 'MIN', 'new orleans': 'NOP',
    'new york': 'NYK', 'oklahoma city': 'OKC', 'orlando': 'ORL',
    'philadelphia': 'PHI', 'phoenix': 'PHX', 'portland': 'POR',
    'sacramento': 'SAC', 'san antonio': 'SAS', 'toronto': 'TOR',
    'utah': 'UTA', 'washington': 'WAS',
}


def team_code(t):
    raw = (t or '').strip()
    return TEAM_CODE.get(raw.lower(), raw.upper())


def load(path):
    if not os.path.exists(path):
        sys.exit(f"Could not find {path}. Run this from the nba-player-data folder.")
    with open(path, encoding='utf-8') as f:
        return json.load(f)


def played_teams(stat_rows):
    """(PLAYER, YEAR) -> set of teams rsStats has him playing for."""
    out = {}
    for r in stat_rows:
        player, year = r.get('PLAYER'), str(r.get('YEAR') or '')
        if not player or not year:
            continue
        out.setdefault((player, year), set()).add(team_code(r.get('TEAM')))
    return out


def collisions(groups):
    """Player-seasons holding ONE salary under SEVERAL teams."""
    out = []
    for (player, year), rows in groups.items():
        if len(rows) < 2:
            continue
        if len({r.get('SALARY') for _, r in rows}) != 1:
            continue          # different amounts: a real mid-season split
        if len({team_code(r.get('TEAM')) for _, r in rows}) < 2:
            continue
        out.append(((player, year), rows))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--dry-run', action='store_true',
                    help='report what would be removed and write nothing')
    ap.add_argument('--year', action='append', default=None,
                    help='season(s) to clean; repeatable. Default: '
                         + ', '.join(DEFAULT_SCOPE))
    args = ap.parse_args()
    scope = set(args.year or DEFAULT_SCOPE)

    salaries = load(SALARIES)
    played = played_teams(load(STATS))
    print(f"{len(salaries)} salary rows loaded")
    print(f"cleaning season(s): {', '.join(sorted(scope))}")

    groups = {}
    for i, r in enumerate(salaries):
        key = (r.get('PLAYER'), str(r.get('YEAR') or ''))
        groups.setdefault(key, []).append((i, r))

    all_hits = collisions(groups)
    in_scope = [h for h in all_hits if h[0][1] in scope]
    out_scope = [h for h in all_hits if h[0][1] not in scope]

    drop_idx = set()
    by_stats = by_order = 0
    examples = []

    for (player, year), rows in in_scope:
        st = played.get((player, year))
        match = [(i, r) for i, r in rows if st and team_code(r.get('TEAM')) in st]
        if len(match) == 1:
            keep = match[0]
            by_stats += 1
        else:
            keep = rows[0]
            by_order += 1
        for i, r in rows:
            if i != keep[0]:
                drop_idx.add(i)
        if len(examples) < 10:
            examples.append(
                f"{player} {year}: keeping {keep[1].get('TEAM')} "
                f"{keep[1].get('SALARY')}, dropping "
                + ", ".join(r.get('TEAM') for i, r in rows if i != keep[0])
            )

    print(f"\nIN SCOPE  ({', '.join(sorted(scope))})")
    print(f"  player-seasons with one salary under several teams  {len(in_scope)}")
    print(f"    resolved by rsStats (the team he actually played for) {by_stats}")
    print(f"    resolved by file order (stats could not decide)       {by_order}")
    print(f"  rows to remove                                      {len(drop_idx)}")

    if examples:
        print("\n  examples:")
        for e in examples:
            print("     " + e)

    print(f"\nOUT OF SCOPE - left alone                             {len(out_scope)}")
    if out_scope:
        print("  Other seasons also have one salary under several teams. Those are")
        print("  10-day and prorated-minimum contracts: the amount is a fixed")
        print("  formula, so two clubs really do pay the same figure. They are real")
        print("  and are NOT touched. A few, to see for yourself:")
        for (player, year), rows in sorted(out_scope, key=lambda h: h[0][1])[:5]:
            teams = " / ".join(r.get('TEAM') for _, r in rows)
            print(f"     {player} {year}: {teams}  {rows[0][1].get('SALARY')}")

    if not drop_idx:
        print("\nNothing to clean in scope. salaries.json is already right.")
        return

    if args.dry_run:
        print("\n--dry-run: nothing was written. Re-run without it to apply.")
        return

    stamp = datetime.now().strftime('%Y%m%d-%H%M%S')
    backup = f"{SALARIES}.bak-{stamp}"
    shutil.copyfile(SALARIES, backup)
    print(f"\nbackup written to {backup}")

    cleaned = [r for i, r in enumerate(salaries) if i not in drop_idx]
    with open(SALARIES, 'w', encoding='utf-8') as f:
        json.dump(cleaned, f, ensure_ascii=False, indent=2)
    print(f"wrote {SALARIES}: {len(salaries)} -> {len(cleaned)} rows")
    print("\nCommit it, then the comparison tool and the video generator are")
    print("correct without either of them changing a line.")


if __name__ == '__main__':
    main()
