#!/usr/bin/env python3
"""
Fetches RS Stats from Google Sheets and converts to rsStats.json format.
Used by GitHub Actions to keep stats up-to-date automatically.
"""

import json
import pandas as pd
import requests
from io import StringIO

# Google Sheet configuration
SHEET_ID = '1ZrDfzqiC31Hu3YCtxT4aZbZF4QVCVyGe6wBytR2LF30'
GID = '0'  # RS Stats tab

def fetch_google_sheet_csv(sheet_id, gid):
    """Fetch data from published Google Sheet as CSV."""
    url = f'https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=csv&gid={gid}'
    response = requests.get(url, timeout=60)
    response.raise_for_status()
    response.encoding = 'utf-8'
    return response.text

def safe_float(val, default=''):
    """Safely convert to float, return default if invalid."""
    if pd.isna(val) or val == '' or val is None:
        return default
    try:
        return float(val)
    except (ValueError, TypeError):
        return default

def safe_str(val, default=''):
    """Safely convert to string."""
    if pd.isna(val) or val is None:
        return default
    s = str(val).strip()
    # Remove .0 from integers stored as floats
    if s.endswith('.0') and '.' not in s[:-2]:
        return s[:-2]
    return s

def calculate_per_game(total, gp):
    """Calculate per-game stat."""
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
    """Get value from row trying multiple column names."""
    for name in col_names:
        if name in row.index and not pd.isna(row.get(name)):
            return row.get(name)
    return ''

def convert_to_rs_stats_format(df):
    """Convert DataFrame to rsStats.json format."""
    
    records = []
    
    for _, row in df.iterrows():
        player = safe_str(get_col(row, 'PLAYER'))
        year = safe_str(get_col(row, 'YEAR'))
        team = safe_str(get_col(row, 'TEAM'))
        
        # Skip empty rows
        if not player or not year:
            continue
        
        # Get RS (Regular Season) stats - columns have " RS" suffix
        gp = safe_str(get_col(row, 'GP RS', 'GP'))
        min_rs = safe_str(get_col(row, 'MIN RS', 'MIN'))
        pts = safe_str(get_col(row, 'PTS RS', 'PTS'))
        fgm = safe_str(get_col(row, 'FGM RS', 'FGM'))
        fga = safe_str(get_col(row, 'FGA RS', 'FGA'))
        fg_pct = get_col(row, 'FG% RS', 'FG%')
        three_p = safe_str(get_col(row, '3P RS', '3P', '3PM'))
        three_pa = safe_str(get_col(row, '3PA RS', '3PA'))
        three_pct = get_col(row, '3P% RS', '3P%')
        ftm = safe_str(get_col(row, 'FTM RS', 'FTM'))
        fta = safe_str(get_col(row, 'FTA RS', 'FTA'))
        ft_pct = get_col(row, 'FT% RS', 'FT%')
        orb = safe_str(get_col(row, 'ORB RS', 'ORB', 'OREB'))
        drb = safe_str(get_col(row, 'DRB RS', 'DRB', 'DREB'))
        reb = safe_str(get_col(row, 'REB RS', 'REB'))
        ast = safe_str(get_col(row, 'AST RS', 'AST'))
        stl = safe_str(get_col(row, 'STL RS', 'STL'))
        blk = safe_str(get_col(row, 'BLK RS', 'BLK'))
        tov = safe_str(get_col(row, 'TOV RS', 'TOV', 'TO'))
        pf = safe_str(get_col(row, 'PF RS', 'PF'))
        age = safe_str(get_col(row, 'AGE (Feb 1)', 'AGE'))
        
        # Build the record
        record = {
            'CODE': f"{player} {team} {year}".strip(),
            'RG CODE': '',
            'NB CODE': player,
            'PLAYER': player,
            'YEAR': year,
            'TEAM': team,
            'GP': gp,
            'MIN': min_rs,
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
            'AGE (Feb 1)': age,
        }
        
        # Calculate per-game stats
        record['PTS / G'] = str(calculate_per_game(pts, gp)) if calculate_per_game(pts, gp) else ''
        record['REB / G'] = str(calculate_per_game(reb, gp)) if calculate_per_game(reb, gp) else ''
        record['AST / G'] = str(calculate_per_game(ast, gp)) if calculate_per_game(ast, gp) else ''
        record['STL / G'] = str(calculate_per_game(stl, gp)) if calculate_per_game(stl, gp) else ''
        record['BLK / G'] = str(calculate_per_game(blk, gp)) if calculate_per_game(blk, gp) else ''
        record['TOV / G'] = str(calculate_per_game(tov, gp)) if calculate_per_game(tov, gp) else ''
        
        records.append(record)
    
    return records

def main():
    print(f"Fetching data from Google Sheet {SHEET_ID}...")
    
    try:
        csv_data = fetch_google_sheet_csv(SHEET_ID, GID)
        print(f"Fetched {len(csv_data)} bytes")
        
        df = pd.read_csv(StringIO(csv_data))
        print(f"Parsed {len(df)} rows, columns: {list(df.columns)[:10]}...")
        
        records = convert_to_rs_stats_format(df)
        print(f"Converted to {len(records)} records")
        
        # Filter out empty records
        records = [r for r in records if r['PLAYER'] and r['YEAR']]
        print(f"After filtering: {len(records)} valid records")
        
        # Save to JSON
        with open('rsStats.json', 'w', encoding='utf-8') as f:
            json.dump(records, f, ensure_ascii=False)
        
        print(f"Successfully saved rsStats.json with {len(records)} records")
        
        # Print sample record
        if records:
            print(f"Sample record: {records[0]['PLAYER']} ({records[0]['YEAR']})")
        
    except Exception as e:
        print(f"Error: {e}")
        raise

if __name__ == '__main__':
    main()
