#!/usr/bin/env python3
"""
Fetches the NBA 2K player ratings sheet from Google Sheets and regenerates
nba2k.json.

Source: NBA 2K ratings Google Sheet (gid 1425851076).
Output: nba2k.json -- one record per player with keys:
    "Full Name", "First Name", "Last Name", then one key per 2K edition
    from "2K00" through "2K26" (all uppercase K), every record carrying the
    full set of edition keys ("" when a player has no rating that year).

Edition column headers in the sheet are matched flexibly (e.g. "2K16",
"2k24", "NBA 2K24", "2024") and normalized to the canonical uppercase
"2Knn" form. Players appearing more than once are deduplicated by Full Name,
keeping the row with the most non-empty rating values.
"""

import csv
import json
import re
from io import StringIO

import requests

# Google Sheet configuration (NBA 2K ratings tab)
SHEET_ID = '1giIJWPabo6vgiY8R1rapcWl3h8VgqOlS4zTTiR-bdpo'
GID = '1425851076'

OUTPUT_PATH = 'nba2k.json'

# Canonical edition keys, all uppercase K: 2K00, 2K01, ... 2K26.
EDITIONS = [f"2K{n:02d}" for n in range(0, 27)]

# Header matching for the name columns (compared case-insensitively).
FULL_NAME_HEADERS = ('full name', 'player', 'player name', 'name')
FIRST_NAME_HEADERS = ('first name', 'first')
LAST_NAME_HEADERS = ('last name', 'last')

# Edition header patterns: "2K16" / "2k 24" / "NBA 2K24" ... and bare years "2016".
_EDITION_2K = re.compile(r'2[kK]\s*0*(\d{1,2})')
_EDITION_YEAR = re.compile(r'^\s*(?:19|20)(\d{2})\s*$')


def fetch_google_sheet_csv(sheet_id, gid):
    """Fetch data from published Google Sheet as CSV."""
    url = f'https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=csv&gid={gid}'
    response = requests.get(url, timeout=60, headers={'User-Agent': 'Mozilla/5.0'})
    response.raise_for_status()
    return response.text


def edition_key(header):
    """Return the canonical '2Knn' key for an edition column header, else None."""
    h = str(header or '')
    m = _EDITION_2K.search(h)
    if m:
        return f"2K{int(m.group(1)):02d}"
    m = _EDITION_YEAR.match(h)
    if m:
        return f"2K{int(m.group(1)):02d}"
    return None


def find_header_row(rows):
    """Index of the header row: contains a name column and >= 1 edition column."""
    for i, row in enumerate(rows):
        lower = [str(c).strip().lower() for c in row]
        has_name = any(any(h in cell for cell in lower) for h in FULL_NAME_HEADERS) \
            or (any(h in lower for h in FIRST_NAME_HEADERS) and any(h in lower for h in LAST_NAME_HEADERS))
        has_edition = any(edition_key(c) for c in row)
        if has_name and has_edition:
            return i
    return 0


def _find_col(lower_headers, candidates):
    """Index of the first header exactly matching one of candidates, else None."""
    for cand in candidates:
        if cand in lower_headers:
            return lower_headers.index(cand)
    return None


def split_full_name(full):
    """Split a full name into (first, last): first token vs. the remainder."""
    parts = full.split()
    if not parts:
        return '', ''
    if len(parts) == 1:
        return parts[0], ''
    return parts[0], ' '.join(parts[1:])


def parse_sheet_records(csv_text):
    """Parse the wide 2K ratings CSV into uniform records with all edition keys."""
    rows = list(csv.reader(StringIO(csv_text)))
    if not rows:
        return []

    header_idx = find_header_row(rows)
    headers = [str(h).strip() for h in rows[header_idx]]
    lower = [h.lower() for h in headers]

    full_idx = _find_col(lower, FULL_NAME_HEADERS)
    first_idx = _find_col(lower, FIRST_NAME_HEADERS)
    last_idx = _find_col(lower, LAST_NAME_HEADERS)

    # Map each edition column to its canonical key (first column wins per key).
    edition_cols = []  # list of (col_idx, canonical_key)
    for idx, h in enumerate(headers):
        key = edition_key(h)
        if key in EDITIONS:
            edition_cols.append((idx, key))

    records = []
    for row in rows[header_idx + 1:]:
        def cell(i):
            return row[i].strip() if (i is not None and i < len(row)) else ''

        full = cell(full_idx)
        first = cell(first_idx)
        last = cell(last_idx)

        if not full and (first or last):
            full = f"{first} {last}".strip()
        if full and not first and not last:
            first, last = split_full_name(full)

        if not full:
            continue  # skip rows without a usable player name

        # Collect ratings into canonical edition keys (first non-empty wins).
        vals = {}
        for col_idx, key in edition_cols:
            if col_idx < len(row):
                v = row[col_idx].strip()
                if v and not vals.get(key):
                    vals[key] = v

        record = {'Full Name': full, 'First Name': first, 'Last Name': last}
        for key in EDITIONS:
            record[key] = vals.get(key, '')
        records.append(record)

    return records


def non_empty_ratings(record):
    """Count of populated edition values in a record."""
    return sum(1 for k in EDITIONS if record.get(k, '') != '')


def deduplicate_by_full_name(records):
    """Keep one record per Full Name: the one with the most non-empty ratings.

    First-appearance order is preserved; ties keep the earlier record.
    """
    best = {}
    order = []
    for rec in records:
        name = rec['Full Name']
        if name not in best:
            best[name] = rec
            order.append(name)
        elif non_empty_ratings(rec) > non_empty_ratings(best[name]):
            best[name] = rec
    return [best[name] for name in order]


def main():
    print(f"Fetching NBA 2K ratings from Google Sheet {SHEET_ID} (gid={GID})...")
    csv_text = fetch_google_sheet_csv(SHEET_ID, GID)
    print(f"Fetched {len(csv_text)} bytes")

    parsed = parse_sheet_records(csv_text)
    print(f"Parsed {len(parsed)} player rows")

    records = deduplicate_by_full_name(parsed)
    print(f"After dedup by Full Name: {len(records)} players")

    if not records:
        raise RuntimeError("0 records parsed; refusing to overwrite nba2k.json")

    # Compact format matching the existing nba2k.json (default separators, UTF-8).
    with open(OUTPUT_PATH, 'w', encoding='utf-8') as f:
        json.dump(records, f, ensure_ascii=False)

    print(f"Successfully wrote {OUTPUT_PATH} with {len(records)} records")
    sample = records[0]
    latest = next((k for k in reversed(EDITIONS) if sample.get(k)), None)
    print(f"Sample: {sample['Full Name']} (latest rated edition in row: {latest}={sample.get(latest, '')})")


if __name__ == '__main__':
    main()
