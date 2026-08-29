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

Existing records are preserved; new ones are appended and the whole list is
deduplicated by (PLAYER, YEAR, TEAM), so re-running is idempotent.
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

# Existing data is complete through this year; see dedup logic in build_new_records.
EXISTING_THROUGH_YEAR = 2025

# Only import salary records for these upcoming season(s). The Future Salaries
# tab projects several years out, but we intentionally ingest just the next
# season to avoid committing the more speculative out-year figures.
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


def year_after_existing(year):
    """True if the YEAR is beyond the range already fully covered by salaries.json."""
    try:
        return int(year) > EXISTING_THROUGH_YEAR
    except (ValueError, TypeError):
        return str(year) > str(EXISTING_THROUGH_YEAR)


def build_new_records(sheet_records, existing):
    """Filter sheet records to those worth adding.

    A sheet record is a candidate if its YEAR is beyond the existing coverage
    OR the (PLAYER, YEAR) combination is not already present in the file.
    """
    existing_player_year = {(r.get('PLAYER'), r.get('YEAR')) for r in existing}

    new_records = []
    for rec in sheet_records:
        key = (rec['PLAYER'], rec['YEAR'])
        if year_after_existing(rec['YEAR']) or key not in existing_player_year:
            new_records.append(rec)
    return new_records


def deduplicate(records):
    """Drop duplicates by (PLAYER, YEAR, TEAM), preserving first occurrence."""
    seen = set()
    out = []
    for r in records:
        key = (r.get('PLAYER'), r.get('YEAR'), r.get('TEAM'))
        if key in seen:
            continue
        seen.add(key)
        out.append(r)
    return out


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
    print(f"{len(new_records)} candidate records to append")

    combined = deduplicate(existing + new_records)
    added = len(combined) - len(existing)
    print(f"After dedup by (PLAYER, YEAR, TEAM): {len(combined)} total ({added} net new)")

    with open(OUTPUT_PATH, 'w', encoding='utf-8') as f:
        json.dump(combined, f, ensure_ascii=False, indent=2)

    print(f"Successfully wrote {OUTPUT_PATH}")
    if new_records:
        sample = new_records[0]
        print(f"Sample new record: {sample['PLAYER']} {sample['YEAR']} {sample['SALARY']} ({sample['TEAM']})")


if __name__ == '__main__':
    main()
