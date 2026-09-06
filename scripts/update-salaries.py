#!/usr/bin/env python3
"""
Fetches the "Future Salaries" tab from Google Sheets and appends new salary
records to salaries.json.

Source: All-Time Database Google Sheet, "Future Salaries" tab.
Output: salaries.json (one record per player-team-year salary).

The Future Salaries tab is laid out wide: PLAYER, TEAM, then one column per
upcoming season (2026, 2027, 2028, ...) holding values like "$30,000,000".
Helper/aggregate columns (CH*, ST*, TOTAL*) are skipped. Each player row is
unpivoted into one record per year column that holds a dollar value.

Records use the same shape and key order as the existing salaries.json:

    {"TEAM": team, "YEAR": year, "PLAYER": name, "SALARY": "$..."}

WHAT THE TEAM COLUMN ACTUALLY MEANS, and why this script used to corrupt the
file every time it ran after an offseason:

The sheet has ONE row per player and ONE team column, holding where he is NOW.
The salary columns run several seasons wide. So for anyone who changed teams,
the team column and the salary columns describe different clubs:

    PLAYER        TEAM          2026          2027
    LeBron James  Philadelphia  $52,627,153   $3,876,529

$52,627,153 is what the LAKERS paid him in 2025-26. Philadelphia is where he
plays in 2026-27, for $3,876,529. Pairing that team with that salary produces a
record that is true about neither.

salaries.json already held the correct "LA Lakers / 2026" row. This script
appended the sheet's "Philadelphia / 2026" one on top of it, because
build_new_records skipped its own duplicate check for any year past
EXISTING_THROUGH_YEAR - which was set to 2025, i.e. exactly the year being
imported. 145 players ended up with two 2026 rows carrying one salary.

Consequences, all of them silent: the comparison tool and the video generator
sum salary rows for career earnings, so 168 players were overstated by
$1.36bn in total - Giannis by $54.1m, LeBron by $52.6m. The Doomscroll payroll
cards discarded any player whose team was ambiguous, which emptied more than
half of some rosters.

THE FIX is one rule, in build_new_records: never append a (PLAYER, YEAR) the
file already has. Where the file already knows a season, it knows it from a
source that had the right team; the sheet's current-team column cannot improve
on that and can only contradict it.

Note what is deliberately NOT changed: deduplicate() still keys on
(PLAYER, YEAR, TEAM). A genuine mid-season trade is two rows for one
player-year under two teams with DIFFERENT amounts, and collapsing those would
lose half a season's salary.
"""

import csv
import json
import re
from io import StringIO

import requests

# Google Sheet configuration (All-Time Database, Future Salaries tab)
SHEET_ID = '1ZrDfzqiC31Hu3YCtxT4aZbZF4QVCVyGe6wBytR2LF30'
GID = '1555460703'  # Future Salaries tab
OUTPUT_PATH = 'salaries.json'

# Column-name prefixes to skip (helper / aggregate columns), case-insensitive.
SKIP_PREFIXES = ('CH', 'ST', 'TOTAL')

# Only import salary records for these upcoming season(s). The Future Salaries
# tab projects several years out, but we intentionally ingest just the next
# season to avoid committing the more speculative out-year figures.
#
# The column header is the season's ENDING year, so '2026' is 2025-26.
IMPORT_YEARS = {'2026'}


def fetch_google_sheet_csv(sheet_id, gid):
    """Fetch data from published Google Sheet as CSV."""
    url = f'https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=csv&gid={gid}'
    response = requests.get(url, timeout=60, headers={'User-Agent': 'Mozilla/5.0'})
    response.raise_for_status()
    response.encoding = 'utf-8'
    return response.text


def find_header_row(rows):
    """Return the index of the row that contains both PLAYER and TEAM headers."""
    for i, row in enumerate(rows):
        upper = [c.strip().upper() for c in row]
        if 'PLAYER' in upper and 'TEAM' in upper:
            return i
    return 0


def is_year_column(name):
    """A year column is a bare 4-digit year that is not a skipped helper column."""
    name = name.strip()
    if not re.fullmatch(r'\d{4}', name):
        return False
    if name.upper().startswith(SKIP_PREFIXES):
        return False
    return True


def parse_sheet_records(csv_text):
    """Unpivot the wide Future Salaries CSV into flat salary records."""
    rows = list(csv.reader(StringIO(csv_text)))
    if not rows:
        return []

    header_idx = find_header_row(rows)
    headers = [h.strip() for h in rows[header_idx]]

    # Locate the PLAYER and TEAM columns by header name.
    upper = [h.upper() for h in headers]
    try:
        player_idx = upper.index('PLAYER')
        team_idx = upper.index('TEAM')
    except ValueError:
        raise RuntimeError("Could not locate PLAYER/TEAM columns in the sheet header")

    # Year columns: bare 4-digit headers, excluding CH*/ST*/TOTAL*.
    year_cols = [(i, h) for i, h in enumerate(headers) if is_year_column(h)]

    records = []
    for row in rows[header_idx + 1:]:
        if len(row) <= max(player_idx, team_idx):
            continue
        player = row[player_idx].strip()
        team = row[team_idx].strip()
        if not player:
            continue
        for col_idx, year in year_cols:
            if col_idx >= len(row):
                continue
            salary = row[col_idx].strip()
            if not salary.startswith('$'):
                continue
            records.append({
                'TEAM': team,
                'YEAR': year,
                'PLAYER': player,
                'SALARY': salary,
            })
    return records


def build_new_records(sheet_records, existing):
    """Filter sheet records to those the file does not already have.

    ONE RULE: a (PLAYER, YEAR) already in salaries.json is never appended
    again.

    This is what changed. The old version read:

        if year_after_existing(rec['YEAR']) or key not in existing_player_year:

    with EXISTING_THROUGH_YEAR = 2025, so the left side was True for every
    record in IMPORT_YEARS and the duplicate check on the right never ran. Each
    run after an offseason therefore wrote a second row for every player who
    had moved, pairing his new team with his old salary.

    The sheet cannot improve on a season the file already holds: its TEAM
    column says where the player is today, not who paid him that year. It can
    only contradict it. Where the file has nothing, the sheet is the only
    source and is used as-is.

    The local `have` set grows as records are accepted, so two sheet rows for
    one player-year cannot slip through either.
    """
    have = {(r.get('PLAYER'), r.get('YEAR')) for r in existing}
    new_records = []
    for rec in sheet_records:
        key = (rec['PLAYER'], rec['YEAR'])
        if key in have:
            continue
        new_records.append(rec)
        have.add(key)
    return new_records


def deduplicate(records):
    """Drop duplicates by (PLAYER, YEAR, TEAM), preserving first occurrence.

    UNCHANGED, and deliberately not tightened to (PLAYER, YEAR): a genuine
    mid-season trade is two rows for one player-year under two teams with
    different amounts that sum to the season. Collapsing those would silently
    delete half a season's salary from every traded player in the file.
    """
    seen = set()
    out = []
    for r in records:
        key = (r.get('PLAYER'), r.get('YEAR'), r.get('TEAM'))
        if key in seen:
            continue
        seen.add(key)
        out.append(r)
    return out


def report_player_year_collisions(records):
    """Warn about any player-year left holding one salary under several teams.

    After the fix this should print nothing. If it ever prints, something has
    reintroduced the bug and the number to watch is on screen rather than in a
    comparison tool three weeks later.
    """
    by_key = {}
    for r in records:
        by_key.setdefault((r.get('PLAYER'), r.get('YEAR')), []).append(r)
    bad = []
    for (player, year), rows in by_key.items():
        if len(rows) < 2:
            continue
        if len({r.get('SALARY') for r in rows}) == 1:
            bad.append((player, year, [r.get('TEAM') for r in rows]))
    if bad:
        print(f"  WARNING: {len(bad)} player-season(s) hold one salary under several teams.")
        for player, year, teams in sorted(bad)[:5]:
            print(f"    {player} {year}: {' / '.join(teams)}")
        print("  These double-count anywhere salary rows are summed.")
    return bad


def main():
    print(f"Fetching Future Salaries from Google Sheet {SHEET_ID} (gid={GID})...")
    csv_text = fetch_google_sheet_csv(SHEET_ID, GID)
    print(f"Fetched {len(csv_text)} bytes")

    sheet_records = parse_sheet_records(csv_text)
    print(f"Parsed {len(sheet_records)} salary cells from the sheet")
    if not sheet_records:
        raise RuntimeError("No salary records parsed from sheet; refusing to modify salaries.json")

    # Only ingest the configured upcoming season(s).
    sheet_records = [r for r in sheet_records if r['YEAR'] in IMPORT_YEARS]
    print(f"{len(sheet_records)} salary cells after restricting to years {sorted(IMPORT_YEARS)}")
    if not sheet_records:
        raise RuntimeError(f"No records for years {sorted(IMPORT_YEARS)}; refusing to modify salaries.json")

    with open(OUTPUT_PATH, encoding='utf-8') as f:
        existing = json.load(f)
    print(f"Loaded {len(existing)} existing records from {OUTPUT_PATH}")

    new_records = build_new_records(sheet_records, existing)
    skipped = len(sheet_records) - len(new_records)
    print(f"{len(new_records)} candidate records to append "
          f"({skipped} skipped: the file already has that player-season)")

    combined = deduplicate(existing + new_records)
    added = len(combined) - len(existing)
    print(f"After dedup by (PLAYER, YEAR, TEAM): {len(combined)} total ({added} net new)")

    report_player_year_collisions(combined)

    with open(OUTPUT_PATH, 'w', encoding='utf-8') as f:
        json.dump(combined, f, ensure_ascii=False, indent=2)
    print(f"Successfully wrote {OUTPUT_PATH}")

    if new_records:
        sample = new_records[0]
        print(f"Sample new record: {sample['PLAYER']} {sample['YEAR']} {sample['SALARY']} ({sample['TEAM']})")


if __name__ == '__main__':
    main()
