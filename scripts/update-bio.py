#!/usr/bin/env python3
"""
Fetches the bio tab from Google Sheets and generates bio.json.
Source: All-Time Database, gid 1488063724.
"""

import csv
import json
from io import StringIO
import requests

SHEET_ID = '1ZrDfzqiC31Hu3YCtxT4aZbZF4QVCVyGe6wBytR2LF30'
GID = '1488063724'
OUTPUT_PATH = 'bio.json'
OVERRIDES_PATH = 'data/bio_birthdate_overrides.json'
FIELDS = ['PLAYER', 'BIRTHDAY', 'POS', 'HEIGHT', 'WEIGHT', 'NATIONALITY', 'DRAFT']


def fetch_google_sheet_csv(sheet_id, gid):
    url = f'https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=csv&gid={gid}'
    response = requests.get(url, timeout=60, headers={'User-Agent': 'Mozilla/5.0'})
    response.raise_for_status()
    response.encoding = 'utf-8'
    return response.text


def find_header_row(rows):
    for i, row in enumerate(rows):
        upper = [str(c).strip().upper() for c in row]
        if 'PLAYER' in upper and 'BIRTHDAY' in upper:
            return i
    return 0


def parse_sheet_records(csv_text):
    rows = list(csv.reader(StringIO(csv_text)))
    if not rows:
        return []
    header_idx = find_header_row(rows)
    headers = [str(h).strip().upper() for h in rows[header_idx]]

    idx = {}
    for field in FIELDS:
        try:
            idx[field] = headers.index(field)
        except ValueError:
            # Try partial match for fields with slashes
            for j, h in enumerate(headers):
                if field in h:
                    idx[field] = j
                    break
            if field not in idx:
                print(f"Warning: could not find column '{field}', skipping")
                idx[field] = None

    def cell(row, i):
        if i is None or i >= len(row):
            return ''
        return row[i].strip()

    seen = set()
    records = []
    for row in rows[header_idx + 1:]:
        player = cell(row, idx.get('PLAYER'))
        if not player or player in seen:
            continue
        seen.add(player)
        record = {field: cell(row, idx.get(field)) for field in FIELDS}
        records.append(record)
    return records


def apply_birthdate_overrides(records, path=OVERRIDES_PATH):
    """Replace BIRTHDAY with correct_value only while the sheet still holds wrong_value.

    If the sheet value differs (fixed or edited by hand), the sheet wins.
    A missing or unreadable overrides file never blocks the bio update.
    """
    try:
        with open(path, encoding='utf-8') as f:
            overrides = json.load(f)
    except FileNotFoundError:
        print(f"No overrides file at {path}; skipping birth-date overrides")
        return
    except (OSError, ValueError) as e:
        print(f"Warning: could not read {path} ({e}); skipping birth-date overrides")
        return

    by_name = {r['PLAYER']: r for r in records}
    applied = skipped = unchanged = 0
    for o in overrides:
        name, wrong, correct = o.get('name'), o.get('wrong_value'), o.get('correct_value')
        rec = by_name.get(name)
        if rec is None:
            skipped += 1
            print(f"  skip {name}: not in sheet")
        elif rec['BIRTHDAY'] != wrong:
            skipped += 1
            print(f"  skip {name}: sheet has {rec['BIRTHDAY']!r}, expected {wrong!r}")
        elif rec['BIRTHDAY'] == correct:
            # Pinned entry (wrong_value == correct_value): nothing to change
            unchanged += 1
        else:
            rec['BIRTHDAY'] = correct
            applied += 1
    print(f"Birth-date overrides: applied {applied}, skipped {skipped}")
    if unchanged:
        print(f"Birth-date overrides: {unchanged} already at correct_value (no change)")


def main():
    print(f"Fetching bio data from Google Sheet {SHEET_ID} (gid={GID})...")
    csv_text = fetch_google_sheet_csv(SHEET_ID, GID)
    print(f"Fetched {len(csv_text)} bytes")

    records = parse_sheet_records(csv_text)
    print(f"Parsed {len(records)} records")

    if not records:
        raise RuntimeError("No records parsed; refusing to write bio.json")

    apply_birthdate_overrides(records)

    with open(OUTPUT_PATH, 'w', encoding='utf-8') as f:
        json.dump(records, f, ensure_ascii=False, separators=(',', ':'))
    print(f"Successfully wrote {OUTPUT_PATH} with {len(records)} records")
    print(f"Sample: {records[0]}")


if __name__ == '__main__':
    main()
