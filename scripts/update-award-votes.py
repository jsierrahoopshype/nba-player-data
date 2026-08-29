#!/usr/bin/env python3
"""
Fetches the award votes tab from Google Sheets and updates awardVotes.json.
Source: All-Time Database, gid 578998874.
"""

import csv
import json
from io import StringIO
import requests

SHEET_ID = '1ZrDfzqiC31Hu3YCtxT4aZbZF4QVCVyGe6wBytR2LF30'
GID = '578998874'
OUTPUT_PATH = 'awardVotes.json'
REQUIRED_HEADERS = ('PLAYER', 'YEAR', 'AWARD', 'RNK')


def fetch_google_sheet_csv(sheet_id, gid):
    url = f'https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=csv&gid={gid}'
    response = requests.get(url, timeout=60, headers={'User-Agent': 'Mozilla/5.0'})
    response.raise_for_status()
    response.encoding = 'utf-8'
    return response.text


def find_header_row(rows):
    for i, row in enumerate(rows):
        upper = [str(c).strip().upper() for c in row]
        if 'PLAYER' in upper and 'YEAR' in upper:
            return i
    return 0


def parse_sheet_records(csv_text):
    rows = list(csv.reader(StringIO(csv_text)))
    if not rows:
        return []
    header_idx = find_header_row(rows)
    headers = [str(h).strip().upper() for h in rows[header_idx]]
    try:
        idx = {h: headers.index(h) for h in REQUIRED_HEADERS}
    except ValueError:
        raise RuntimeError(f"Could not locate required columns {REQUIRED_HEADERS} in: {headers}")
    def cell(row, i):
        return row[i].strip() if i < len(row) else ''
    records = []
    for row in rows[header_idx + 1:]:
        player = cell(row, idx['PLAYER'])
        year = cell(row, idx['YEAR'])
        if not player or not year:
            continue
        records.append({
            'PLAYER': player,
            'YEAR': year,
            'AWARD': cell(row, idx['AWARD']),
            'RNK': cell(row, idx['RNK']),
        })
    return records


def deduplicate(records):
    seen = set()
    out = []
    for r in records:
        key = (r.get('PLAYER'), r.get('YEAR'), r.get('AWARD'), r.get('RNK'))
        if key in seen:
            continue
        seen.add(key)
        out.append(r)
    return out


def main():
    print(f"Fetching award votes from Google Sheet {SHEET_ID} (gid={GID})...")
    csv_text = fetch_google_sheet_csv(SHEET_ID, GID)
    print(f"Fetched {len(csv_text)} bytes")
    new_records = parse_sheet_records(csv_text)
    print(f"Parsed {len(new_records)} records from the sheet")
    if not new_records:
        raise RuntimeError("No records parsed; refusing to modify awardVotes.json")
    with open(OUTPUT_PATH, encoding='utf-8') as f:
        existing = json.load(f)
    print(f"Loaded {len(existing)} existing records")
    combined = deduplicate(existing + new_records)
    added = len(combined) - len(existing)
    print(f"After merge + dedup: {len(combined)} total ({added} net new)")
    with open(OUTPUT_PATH, 'w', encoding='utf-8') as f:
        json.dump(combined, f, ensure_ascii=False, indent=2)
        f.write('\n')
    print(f"Successfully wrote {OUTPUT_PATH}")


if __name__ == '__main__':
    main()
