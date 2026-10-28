#!/usr/bin/env python3
"""
Fetches the awards tab from Google Sheets and regenerates awards.json.
Source: the light HoopsMatic spreadsheet (1Wxqb2qD...), Awards tab, gid 0. It was
the All-Time Database's Awards tab (gid 1456513900) until Oct 2026, when that
spreadsheet got too big to export.
The sheet is the source of truth — awards.json is fully regenerated each run.
"""

import csv
import json
from io import StringIO
import requests

import sheet_guard  # fail clearly and keep the committed file (scripts/sheet_guard.py)

SHEET_ID = '1Wxqb2qD848ZEb0jVpVkJfN4-XzKy5qhOmdWMeFTe1ow'
GID = '0'  # Awards
OUTPUT_PATH = 'awards.json'
REQUIRED_HEADERS = ('PLAYER / COACH', 'AWARD', 'YEAR', 'TEAM')


def fetch_google_sheet_csv(sheet_id, gid):
    url = f'https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=csv&gid={gid}'
    response = requests.get(url, timeout=sheet_guard.READ_TIMEOUT, headers={'User-Agent': 'Mozilla/5.0'})
    response.raise_for_status()
    response.encoding = 'utf-8'
    return response.text


def find_header_row(rows):
    for i, row in enumerate(rows):
        upper = [str(c).strip().upper() for c in row]
        if 'PLAYER / COACH' in upper and 'AWARD' in upper:
            return i
    return 0


def parse_sheet_records(csv_text):
    rows = list(csv.reader(StringIO(csv_text)))
    if not rows:
        return []
    header_idx = find_header_row(rows)
    headers = [str(h).strip() for h in rows[header_idx]]
    headers_upper = [h.upper() for h in headers]

    # Find column indices by name
    idx = {}
    for req in REQUIRED_HEADERS:
        try:
            idx[req] = headers_upper.index(req.upper())
        except ValueError:
            raise RuntimeError(f"Could not find column '{req}' in headers: {headers}")

    def cell(row, i):
        return row[i].strip() if i < len(row) else ''

    records = []
    for row in rows[header_idx + 1:]:
        player = cell(row, idx['PLAYER / COACH'])
        award = cell(row, idx['AWARD'])
        if not player or not award:
            continue
        records.append({
            'PLAYER / COACH': player,
            'AWARD': award,
            'YEAR': cell(row, idx['YEAR']),
            'TEAM': cell(row, idx['TEAM']),
        })
    return records


def main():
    print(f"Fetching awards from Google Sheet {SHEET_ID} (gid={GID})...")
    csv_text = sheet_guard.fetch_checked('Awards tab', 'awards.json', fetch_google_sheet_csv, SHEET_ID, GID)
    print(f"Fetched {len(csv_text)} bytes")

    records = parse_sheet_records(csv_text)
    print(f"Parsed {len(records)} records")

    if not records:
        raise RuntimeError("No records parsed; refusing to overwrite awards.json")

    with open(OUTPUT_PATH, 'w', encoding='utf-8') as f:
        json.dump(records, f, ensure_ascii=False)

    print(f"Successfully wrote {OUTPUT_PATH} with {len(records)} records")
    print(f"Sample: {records[0]}")


if __name__ == '__main__':
    main()
