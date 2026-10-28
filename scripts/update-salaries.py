#!/usr/bin/env python3
"""
Fetches the "Future Salaries" tab from Google Sheets and refreshes the current
season's salary records in salaries.json.

Source: All-Time Database Google Sheet, "Future Salaries" tab.
Output: salaries.json (one record per player-team-year salary).

The Future Salaries tab is laid out wide: PLAYER, TEAM, then one column per
upcoming season (2026, 2027, 2028, ...) holding values like "$30,000,000".
Helper/aggregate columns (CH*, ST*, TOTAL*) are skipped. Each player row is
unpivoted into one record per year column that holds a dollar value.

Records use the same shape and key order as the existing salaries.json:

    {"TEAM": team, "YEAR": year, "PLAYER": name, "SALARY": "$..."}

HOW EACH RUN WORKS (rolling target year):

The sheet drops the finished season's column when a new season starts (the
2026 column disappeared in Oct 2026, which made the old hard-coded
IMPORT_YEARS = {'2026'} fail every day). So the year is no longer hard-coded:

  1. The TARGET YEAR is the earliest year column present in the sheet, i.e.
     the current season. It must fall within current UTC year -1..+1, and must
     not be older than the latest year already in salaries.json.
  2. Every salaries.json record for the target year is REPLACED with what the
     sheet has now, paired with the sheet's TEAM column. For the current
     season that pairing is correct, and it lets trades, signings and changed
     salaries update daily.
  3. Every other year in salaries.json is left exactly as it is. A season
     freezes automatically the day the sheet drops its column: the target
     moves on to the next year and nothing touches the old one again.
  4. Years later than the target (projections) are never imported.
  5. Safety: 0 sheet cells for the target year, or a new row count more than
     20% below the count already in the file for that year, exits with code 1
     without writing.
  6. Offseason: from July 1 of the target year until the sheet drops that
     column, the season is over but the TEAM column already shows next
     season's teams (see HISTORY). The run leaves salaries.json unchanged and
     exits 0, so the season freezes with its in-season teams.

HISTORY (why the TEAM pairing is only trusted for the target year):

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

THE FIX (Sep 2026) was one rule, in the old build_new_records: never append a
(PLAYER, YEAR) the file already has. The rolling target year above replaces
that function, and keeps the same principle: the sheet's current-team column is
only trusted for the season in progress. A finished season is never rewritten,
which is also why the script stops refreshing the target year once its season
has ended (July 1 of the target year), even if the sheet still shows that
column through the offseason with players' NEW teams next to it.

Note what is deliberately NOT changed: deduplicate() still keys on
(PLAYER, YEAR, TEAM). A genuine mid-season trade is two rows for one
player-year under two teams with DIFFERENT amounts, and collapsing those would
lose half a season's salary.
"""

import csv
import json
import re
import sys
from datetime import datetime, timezone
from io import StringIO

import requests

import sheet_guard  # fail clearly and keep the committed file (scripts/sheet_guard.py)

# Google Sheet configuration (All-Time Database, Future Salaries tab)
SHEET_ID = '1ZrDfzqiC31Hu3YCtxT4aZbZF4QVCVyGe6wBytR2LF30'
GID = '1555460703'  # Future Salaries tab
OUTPUT_PATH = 'salaries.json'

# Column-name prefixes to skip (helper / aggregate columns), case-insensitive.
SKIP_PREFIXES = ('CH', 'ST', 'TOTAL')

# The target year is no longer hard-coded: each run uses the EARLIEST year
# column in the sheet (the current season). Later, more speculative out-year
# columns are never imported. Column headers are the season's ENDING year, so
# '2027' is 2026-27.

# A season ending in year Y is over from this (month, day) of Y. From then on
# the target year is frozen even if the sheet still shows its column.
SEASON_OVER_MONTH_DAY = (7, 1)

# Refuse to write if the target year's row count drops by more than this
# fraction versus what salaries.json already holds for that year.
MAX_ROW_DROP = 0.20


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


def sheet_year_columns(csv_text):
    """Return the sheet's year column headers (e.g. ['2027', '2028', ...]).

    Read from the header row, so a year column counts as present even if no
    player has a value in it yet (main() then fails on 0 cells rather than
    silently moving on to the next year).
    """
    rows = list(csv.reader(StringIO(csv_text)))
    if not rows:
        return []
    headers = [h.strip() for h in rows[find_header_row(rows)]]
    return [h for h in headers if is_year_column(h)]


def build_target_year_records(sheet_records, target_year):
    """Sheet records for the target year only, one per (PLAYER, YEAR).

    The sheet has one row per player, so a repeated (PLAYER, YEAR) is a sheet
    error; the first occurrence wins (the same rule the old append logic
    applied) and the rest are reported so they don't double-count silently.
    """
    have = set()
    out = []
    dropped = []
    for rec in sheet_records:
        if rec['YEAR'] != target_year:
            continue
        key = (rec['PLAYER'], rec['YEAR'])
        if key in have:
            dropped.append(rec)
            continue
        have.add(key)
        out.append(rec)
    if dropped:
        print(f"  WARNING: {len(dropped)} repeated player row(s) in the sheet for {target_year}; "
              f"kept the first of each.")
        for r in dropped[:5]:
            print(f"    {r['PLAYER']} ({r['TEAM']}) {r['SALARY']}")
    return out


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


def fail(msg):
    """Print why and exit 1 without touching salaries.json."""
    print(f"ERROR: {msg}")
    print(f"Refusing to modify {OUTPUT_PATH}.")
    sys.exit(1)


def count_by_year(records):
    counts = {}
    for r in records:
        counts[r.get('YEAR')] = counts.get(r.get('YEAR'), 0) + 1
    return counts


def main():
    print(f"Fetching Future Salaries from Google Sheet {SHEET_ID} (gid={GID})...")
    csv_text = sheet_guard.fetch_checked('Future Salaries tab', 'salaries.json', fetch_google_sheet_csv, SHEET_ID, GID)
    print(f"Fetched {len(csv_text)} bytes")

    sheet_records = parse_sheet_records(csv_text)
    print(f"Parsed {len(sheet_records)} salary cells from the sheet")
    if not sheet_records:
        fail("No salary records parsed from sheet")

    # Target year = earliest year column in the sheet (the current season).
    year_cols = sheet_year_columns(csv_text)
    print(f"Year columns in sheet: {year_cols}")
    if not year_cols:
        fail("No year columns found in the sheet header")
    target_year = min(year_cols, key=int)
    print(f"Target year: {target_year} (= {int(target_year) - 1}-{target_year[2:]} season)")

    # Sanity check: the current season ends within a year of today's UTC year.
    utc_year = datetime.now(timezone.utc).year
    if not (utc_year - 1 <= int(target_year) <= utc_year + 1):
        fail(f"Target year {target_year} is outside {utc_year - 1}-{utc_year + 1} "
             f"(current UTC year {utc_year} -1/+1)")

    # Offseason: the target season has ended but the sheet hasn't dropped its
    # column yet, and its TEAM column now shows where players go NEXT season.
    now = datetime.now(timezone.utc)
    season_over = datetime(int(target_year), *SEASON_OVER_MONTH_DAY, tzinfo=timezone.utc)
    if now >= season_over:
        print(f"Season {target_year} ended ({season_over:%Y-%m-%d}); the sheet's TEAM column "
              f"now reflects next season, so {target_year} stays frozen.")
        print(f"Leaving {OUTPUT_PATH} unchanged until the sheet drops the {target_year} column.")
        return

    with open(OUTPUT_PATH, encoding='utf-8') as f:
        existing = json.load(f)
    print(f"Loaded {len(existing)} existing records from {OUTPUT_PATH}")

    # Never step backwards: if the sheet ever re-adds a finished season's
    # column, it must not overwrite that frozen season with current teams.
    existing_years = [int(r['YEAR']) for r in existing
                      if re.fullmatch(r'\d{4}', str(r.get('YEAR', '')))]
    if existing_years and int(target_year) < max(existing_years):
        fail(f"Target year {target_year} is older than the latest year already in "
             f"{OUTPUT_PATH} ({max(existing_years)}); that season is frozen")

    new_target = deduplicate(build_target_year_records(sheet_records, target_year))
    old_target_count = sum(1 for r in existing if r.get('YEAR') == target_year)
    print(f"{target_year}: {len(new_target)} records from the sheet, "
          f"{old_target_count} currently in {OUTPUT_PATH}")

    if not new_target:
        fail(f"Sheet has 0 salary cells for target year {target_year}")
    if old_target_count and len(new_target) < old_target_count * (1 - MAX_ROW_DROP):
        fail(f"{target_year} would drop from {old_target_count} to {len(new_target)} records, "
             f"more than {int(MAX_ROW_DROP * 100)}% fewer")

    # Every other year is kept verbatim and in its original order; the target
    # year is replaced wholesale and appended at the end, as new seasons always
    # have been.
    kept = [r for r in existing if r.get('YEAR') != target_year]
    combined = kept + new_target
    print(f"Kept {len(kept)} records for other years untouched; "
          f"replaced {old_target_count} {target_year} records with {len(new_target)}")
    print(f"Total: {len(existing)} -> {len(combined)}")

    report_player_year_collisions(combined)

    with open(OUTPUT_PATH, 'w', encoding='utf-8') as f:
        json.dump(combined, f, ensure_ascii=False, indent=2)
    print(f"Successfully wrote {OUTPUT_PATH}")

    sample = new_target[0]
    print(f"Sample {target_year} record: {sample['PLAYER']} {sample['SALARY']} ({sample['TEAM']})")


if __name__ == '__main__':
    main()
