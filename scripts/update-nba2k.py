#!/usr/bin/env python3
"""
Fetches the NBA 2K ratings sheet and regenerates nba2k.json.

v2 changes:
  - Points at the current tab (gid 1324366970), which carries 2K00 through 2k27.
  - Editions extended through 2K27 (was capped at 2K26, which silently dropped
    any newer column).
  - Header cells are stripped, so trailing spaces like "2K00 " still match.
  - Uses /export?format=csv instead of the gviz endpoint. gviz infers headers
    and, because A1 on this tab is blank, it was swallowing the first two data
    rows (Alaa Abdelnaby and Mahmoud Abdul-Rauf) into the header. The export
    endpoint returns raw rows, so nothing is lost even if A1 stays empty.
  - If the first header cell is blank, column 0 is treated as Full Name.

Regenerates the file completely each run: the sheet is the source of truth.
"""

import csv
import json
import re
from io import StringIO

import requests

SHEET_ID = '1giIJWPabo6vgiY8R1rapcWl3h8VgqOlS4zTTiR-bdpo'
GID = '1324366970'
OUTPUT_PATH = 'nba2k.json'

# Canonical edition keys, all uppercase K: 2K00, 2K01, ... 2K27.
EDITIONS = ['2K%02d' % n for n in range(0, 28)]
EDITION_RE = re.compile(r'^2K(\d{2})$', re.IGNORECASE)


def fetch_sheet_csv(sheet_id, gid):
    url = ('https://docs.google.com/spreadsheets/d/%s/export?format=csv&gid=%s'
           % (sheet_id, gid))
    res = requests.get(url, timeout=90, headers={'User-Agent': 'Mozilla/5.0'})
    res.raise_for_status()
    return res.text


def canon_edition(header_cell):
    """'2k27 ' -> '2K27'.  Returns None if the cell is not an edition column."""
    m = EDITION_RE.match(str(header_cell).strip())
    if not m:
        return None
    return '2K' + m.group(1)


def parse_records(csv_text):
    rows = list(csv.reader(StringIO(csv_text)))
    if not rows:
        return []

    header = [str(c).strip() for c in rows[0]]
    upper = [h.upper() for h in header]

    def find(label, default=None):
        try:
            return upper.index(label)
        except ValueError:
            return default

    # A1 is blank on this tab, so fall back to column 0 for the full name.
    i_full = find('FULL NAME', 0)
    i_first = find('FIRST NAME', 1)
    i_last = find('LAST NAME', 2)

    edition_cols = {}
    for idx, cell in enumerate(header):
        key = canon_edition(cell)
        if key and key in EDITIONS:
            edition_cols[idx] = key

    print('  header row: %d columns, %d edition columns (%s .. %s)'
          % (len(header), len(edition_cols),
             min(edition_cols.values()) if edition_cols else '-',
             max(edition_cols.values()) if edition_cols else '-'))

    if not edition_cols:
        raise RuntimeError('No 2K edition columns found; header was: %s' % header[:8])

    def cell(row, i):
        return row[i].strip() if i is not None and i < len(row) else ''

    records = []
    for row in rows[1:]:
        full = cell(row, i_full)
        if not full:
            continue
        rec = {
            'Full Name': full,
            'First Name': cell(row, i_first),
            'Last Name': cell(row, i_last),
        }
        for key in EDITIONS:
            rec[key] = ''
        for idx, key in edition_cols.items():
            rec[key] = cell(row, idx)
        records.append(rec)
    return records


def rating_count(rec):
    return sum(1 for k in EDITIONS if rec.get(k, '') != '')


def dedupe(records):
    """One record per player; keep whichever row carries the most ratings."""
    best = {}
    for rec in records:
        key = rec['Full Name'].strip().lower()
        if key not in best or rating_count(rec) > rating_count(best[key]):
            best[key] = rec
    return list(best.values())


def main():
    print('Fetching NBA 2K ratings (sheet %s, gid %s) ...' % (SHEET_ID, GID))
    csv_text = fetch_sheet_csv(SHEET_ID, GID)
    print('  fetched %d bytes' % len(csv_text))

    records = parse_records(csv_text)
    print('  parsed %d rows' % len(records))

    records = dedupe(records)
    print('  %d players after dedupe' % len(records))

    if not records:
        raise RuntimeError('No records parsed; refusing to overwrite nba2k.json')

    with_ratings = sum(1 for r in records if rating_count(r) > 0)
    print('  %d players have at least one rating' % with_ratings)
    if with_ratings == 0:
        raise RuntimeError('Every record is empty; refusing to overwrite nba2k.json')

    for key in ('2K25', '2K26', '2K27'):
        n = sum(1 for r in records if r.get(key, '') != '')
        print('  %s: %d ratings' % (key, n))

    records.sort(key=lambda r: r['Full Name'].lower())

    with open(OUTPUT_PATH, 'w', encoding='utf-8') as f:
        json.dump(records, f, ensure_ascii=False)

    print('Wrote %s with %d records' % (OUTPUT_PATH, len(records)))
    for probe in ('Nikola Jokic', 'Shai Gilgeous-Alexander', 'Alaa Abdelnaby'):
        hit = next((r for r in records if r['Full Name'] == probe), None)
        if hit:
            print('  %-24s 2K26=%s  2K27=%s'
                  % (probe, hit.get('2K26', ''), hit.get('2K27', '')))
        else:
            print('  %-24s (not found)' % probe)


if __name__ == '__main__':
    main()
