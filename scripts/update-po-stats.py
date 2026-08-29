#!/usr/bin/env python3
"""
Fetches PO (Playoff) Stats from Google Sheets and converts to poStats.json format.
Playoff analog of update-rs-stats.py. Used by GitHub Actions to keep playoff
stats up-to-date automatically.

Source: All-Time Database Google Sheet, "PO Stats" tab.
Output: poStats.json (one record per player-season-team, full history).

Note on the '3P' column: an earlier export of poStats.json stored the
three-point-makes column under the key "3:00 PM" (Google Sheets auto-formatted
the "3PM" header into a time on CSV export). The comparison tools read this
column as "3P", so this script normalizes it back to "3P".
"""

import json
import pandas as pd
import requests
from io import StringIO

# Google Sheet configuration (All-Time Database, PO Stats tab)
SHEET_ID = '1ZrDfzqiC31Hu3YCtxT4aZbZF4QVCVyGe6wBytR2LF30'
GID = '1591736011'  # PO Stats tab

def fetch_google_sheet_csv(sheet_id, gid):
    """Fetch data from published Google Sheet as CSV."""
    url = f'https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=csv&gid={gid}'
    response = requests.get(url, timeout=60, headers={'User-Agent': 'Mozilla/5.0'})
    response.raise_for_status()
    response.encoding = 'utf-8'
    return response.text

def safe_str(val, default=''):
    """Safely convert to string, stripping trailing .0 from integer-valued floats."""
    if pd.isna(val) or val is None:
        return default
    s = str(val).strip()
    if s.endswith('.0') and '.' not in s[:-2]:
        return s[:-2]
    return s

def calculate_per_game(total, gp):
    """Calculate per-game stat, returns '' when not computable."""
    try:
        total_f = float(total)
        gp_f = float(gp)
        if gp_f > 0:
            return round(total_f / gp_f, 2)
    except (ValueError, TypeError):
        pass
    return ''

def format_percentage(val):
    """Format percentage value (0.45 or 45 -> 0.45)."""
    try:
        num = float(val)
        # If > 1, assume it's already percentage points, divide by 100
        if num > 1:
            return f"{num / 100:.2f}"
        return f"{num:.2f}"
    except (ValueError, TypeError):
        return '0.00'

def get_col(row, *col_names):
    """Get value from row trying multiple candidate column names in order."""
    for name in col_names:
        if name in row.index and not pd.isna(row.get(name)):
            return row.get(name)
    return ''

def convert_to_po_stats_format(df):
    """Convert DataFrame to poStats.json format."""

    records = []

    for _, row in df.iterrows():
        player = safe_str(get_col(row, 'PLAYER'))
        year = safe_str(get_col(row, 'YEAR'))
        team = safe_str(get_col(row, 'TEAM'))

        # Skip empty rows
        if not player or not year:
            continue

        # Stat columns. Try bare names first, then " PO" suffixed variants and
        # common aliases, so the script is robust to either a dedicated playoff
        # tab (bare headers) or the combined database (" PO" suffix).
        gp = safe_str(get_col(row, 'GP PO', 'GP'))
        min_po = safe_str(get_col(row, 'MIN PO', 'MIN'))
        pts = safe_str(get_col(row, 'PTS PO', 'PTS'))
        fgm = safe_str(get_col(row, 'FGM PO', 'FGM'))
        fga = safe_str(get_col(row, 'FGA PO', 'FGA'))
        fg_pct = get_col(row, 'FG% PO', 'FG%')
        # "3PM" can arrive as "3:00 PM" after Google Sheets CSV auto-formatting.
        three_p = safe_str(get_col(row, '3P PO', '3P', '3PM PO', '3PM', '3:00 PM'))
        three_pa = safe_str(get_col(row, '3PA PO', '3PA'))
        three_pct = get_col(row, '3P% PO', '3P%')
        ftm = safe_str(get_col(row, 'FTM PO', 'FTM'))
        fta = safe_str(get_col(row, 'FTA PO', 'FTA'))
        ft_pct = get_col(row, 'FT% PO', 'FT%')
        orb = safe_str(get_col(row, 'ORB PO', 'ORB', 'OREB'))
        drb = safe_str(get_col(row, 'DRB PO', 'DRB', 'DREB'))
        reb = safe_str(get_col(row, 'REB PO', 'REB'))
        ast = safe_str(get_col(row, 'AST PO', 'AST'))
        stl = safe_str(get_col(row, 'STL PO', 'STL'))
        blk = safe_str(get_col(row, 'BLK PO', 'BLK'))
        tov = safe_str(get_col(row, 'TOV PO', 'TOV', 'TO'))
        pf = safe_str(get_col(row, 'PF PO', 'PF'))

        # Identity / metadata columns: prefer values from the sheet, fall back
        # to constructing CODE the same way update-rs-stats.py does.
        code = safe_str(get_col(row, 'CODE')) or f"{player} {team} {year}".strip()
        rg_code = safe_str(get_col(row, 'RG CODE'))
        nb_code = safe_str(get_col(row, 'NB CODE'))
        result = safe_str(get_col(row, 'RESULT'))

        record = {
            'CODE': code,
            'RG CODE': rg_code,
            'NB CODE': nb_code,
            'PLAYER': player,
            'YEAR': year,
            'TEAM': team,
            'GP': gp,
            'MIN': min_po,
            'PTS': pts,
            'FGM': fgm,
            'FGA': fga,
            'FG%': format_percentage(fg_pct),
            '3P': three_p,
            '3PA': three_pa,
            '3P%': format_percentage(three_pct),
            'FTM': ftm,
            'FTA': fta,
            'FT%': format_percentage(ft_pct),
            'ORB': orb,
            'DRB': drb,
            'REB': reb,
            'AST': ast,
            'STL': stl,
            'BLK': blk,
            'TOV': tov,
            'PF': pf,
        }

        # Per-game stats (recomputed for consistency)
        record['PTS / G'] = str(calculate_per_game(pts, gp)) if calculate_per_game(pts, gp) != '' else ''
        record['REB / G'] = str(calculate_per_game(reb, gp)) if calculate_per_game(reb, gp) != '' else ''
        record['AST / G'] = str(calculate_per_game(ast, gp)) if calculate_per_game(ast, gp) != '' else ''
        record['STL / G'] = str(calculate_per_game(stl, gp)) if calculate_per_game(stl, gp) != '' else ''
        record['BLK / G'] = str(calculate_per_game(blk, gp)) if calculate_per_game(blk, gp) != '' else ''
        record['TOV / G'] = str(calculate_per_game(tov, gp)) if calculate_per_game(tov, gp) != '' else ''

        # Playoff result (e.g. First Round, Conf Semis, Conf Finalist, Finalist, Champion)
        record['RESULT'] = result

        records.append(record)

    return records

def main():
    print(f"Fetching PO data from Google Sheet {SHEET_ID} (gid={GID})...")

    try:
        csv_data = fetch_google_sheet_csv(SHEET_ID, GID)
        print(f"Fetched {len(csv_data)} bytes")

        df = pd.read_csv(StringIO(csv_data))
        print(f"Parsed {len(df)} rows, columns: {list(df.columns)[:12]}...")

        records = convert_to_po_stats_format(df)
        print(f"Converted to {len(records)} records")

        # Filter out empty records
        records = [r for r in records if r['PLAYER'] and r['YEAR']]
        print(f"After filtering: {len(records)} valid records")

        if not records:
            raise RuntimeError("No valid records produced; refusing to overwrite poStats.json")

        # Save to JSON (compact, ensure_ascii=False to match rsStats.json)
        with open('poStats.json', 'w', encoding='utf-8') as f:
            json.dump(records, f, ensure_ascii=False)

        print(f"Successfully saved poStats.json with {len(records)} records")

        if records:
            print(f"Sample record: {records[0]['PLAYER']} ({records[0]['YEAR']}) - {records[0].get('RESULT', '')}")

    except Exception as e:
        print(f"Error: {e}")
        raise

if __name__ == '__main__':
    main()
