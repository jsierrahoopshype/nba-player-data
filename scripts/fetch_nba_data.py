#!/usr/bin/env python3
"""
Fetches current NBA season data from Google Sheets and compiles into a single JSON file.
The season is worked out from today's UTC date (Oct 1 or later -> season starting this year),
so it rolls over automatically. Output: nba-<season>-data.json plus a fixed-name copy
nba-current-season-data.json that pages load. Past seasons' files are never touched.
Runs daily via GitHub Actions at 6 AM ET.
"""

import csv
import json
import re
import sys
import urllib.request
from io import StringIO
from datetime import datetime, timezone

# Google Sheets Configuration
SHEETS = {
    'allTime': '1ZrDfzqiC31Hu3YCtxT4aZbZF4QVCVyGe6wBytR2LF30',
    # Current-season sheet (same sheet every year; it rolls over to the new season itself)
    'currentSeason': '1JH2FUBIyQ1zEHzZBxgP8vHBZ7d8EtP5-fSVG3zMgCgg',
    'historical': '1nPSI-VVKHkGYW9IY2KDP-v_xW6qi9_L9WpCnUFKRi8A'
}

# Tab GIDs
TABS = {
    # All-Time Database tabs
    'rsStats': 576369994,
    'poStats': 1591736011,
    'teamStats': 1735540905,
    
    # Current Season tabs
    'current_advanced': 339737563,
    'current_scoring': 52077302,
    'current_shotLocation': 1205457990,
    'current_defense': 1957258468,
    'current_usage': 1415078232,
    'current_clutch': 10789411,
    'current_hustle': 439158060,
}

def get_sheet_url(sheet_id, gid):
    """Build Google Sheets CSV export URL"""
    return f"https://docs.google.com/spreadsheets/d/{sheet_id}/gviz/tq?tqx=out:csv&gid={gid}"

def parse_csv_line(line):
    """Parse a CSV line handling quoted fields"""
    result = []
    current = ''
    in_quotes = False
    for char in line:
        if char == '"':
            in_quotes = not in_quotes
        elif char == ',' and not in_quotes:
            result.append(current.strip().strip('"'))
            current = ''
        else:
            current += char
    result.append(current.strip().strip('"'))
    return result

def find_header_row(lines, known_headers):
    """Find the row index containing known header names"""
    for i, line in enumerate(lines):
        parsed = parse_csv_line(line)
        # Check if any known headers are in this row
        for header in known_headers:
            if header in parsed:
                return i
    return 0  # Default to first row

def fetch_csv(url, known_headers=None):
    """Fetch CSV data from URL and return as list of dicts"""
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=60) as response:
            content = response.read().decode('utf-8-sig')  # Handle BOM
            lines = content.strip().split('\n')
            
            if len(lines) < 2:
                print(f"  Warning: Not enough lines")
                return []
            
            # Find header row dynamically
            if known_headers:
                header_idx = find_header_row(lines, known_headers)
                print(f"  Found header row at index {header_idx}")
            else:
                header_idx = 0
            
            # Get headers
            headers = parse_csv_line(lines[header_idx])
            print(f"  Headers ({len(headers)}): {headers[:5]}...")
            
            # Parse data rows (everything after header row)
            result = []
            for line in lines[header_idx + 1:]:
                if not line.strip():
                    continue
                values = parse_csv_line(line)
                row = {}
                for j, header in enumerate(headers):
                    if header:  # Skip empty headers
                        row[header] = values[j] if j < len(values) else ''
                result.append(row)
            
            return result
    except Exception as e:
        print(f"Error fetching {url}: {e}")
        import traceback
        traceback.print_exc()
        return []

def clean_numeric(value):
    """Convert string to float/int where possible"""
    if value is None or value == '' or value == '-':
        return None
    try:
        cleaned = str(value).replace(',', '').replace('%', '').strip()
        if cleaned == '':
            return None
        if '.' in cleaned:
            return float(cleaned)
        return int(cleaned)
    except ValueError:
        return value

def process_row(row):
    """Clean up a row of data"""
    return {k: clean_numeric(v) for k, v in row.items() if k}

def get_current_season(now=None):
    """Season label for a UTC date: Oct 1 or later -> starts this year, else started last year.
    e.g. 2026-10-27 -> '2026-27', 2027-03-15 -> '2026-27'."""
    now = now or datetime.now(timezone.utc)
    start = now.year if now.month >= 10 else now.year - 1
    return f"{start}-{(start + 1) % 100:02d}"

def filter_season(data, season, season_col='YEAR'):
    """Filter data to only the given season (YEAR may be '2026-27', '2027' or 2027)"""
    end_year = int(season[:4]) + 1
    return [row for row in data if row.get(season_col) in [season, str(end_year), end_year]]

def sheet_season_label(rows):
    """Read the 'Season: YYYY-YY' label the sheet puts in its first header cell, if any"""
    if not rows:
        return None
    for key in rows[0].keys():
        m = re.search(r'Season:\s*(\d{4}-\d{2})', key)
        if m:
            return m.group(1)
    return None

def main():
    season = get_current_season()
    print(f"Starting NBA data fetch at {datetime.now(timezone.utc).isoformat()}")
    print(f"Current season (from UTC date): {season}")
    
    nba_data = {
        'lastUpdated': datetime.now(timezone.utc).isoformat(),
        'season': season,
        'rsStats': [],
        'poStats': [],
        'teamStats': [],
        'advanced': [],
        'scoring': [],
        'shotLocation': [],
        'defense': [],
        'usage': [],
        'clutch': [],
        'hustle': []
    }
    
    # Fetch Regular Season Stats (filtered to current season)
    print("Fetching RS Stats...")
    url = get_sheet_url(SHEETS['allTime'], TABS['rsStats'])
    all_rs = fetch_csv(url, known_headers=['PLAYER', 'YEAR', 'TEAM', 'GP'])
    nba_data['rsStats'] = [process_row(r) for r in filter_season(all_rs, season)]
    print(f"  Found {len(nba_data['rsStats'])} players for {season}")
    
    # Fetch Playoff Stats (filtered to current season)
    print("Fetching PO Stats...")
    url = get_sheet_url(SHEETS['allTime'], TABS['poStats'])
    all_po = fetch_csv(url, known_headers=['PLAYER', 'YEAR', 'TEAM', 'GP'])
    nba_data['poStats'] = [process_row(r) for r in filter_season(all_po, season)]
    print(f"  Found {len(nba_data['poStats'])} players for {season}")
    
    # Fetch Team Stats (filtered to current season)
    print("Fetching Team Stats...")
    url = get_sheet_url(SHEETS['allTime'], TABS['teamStats'])
    all_teams = fetch_csv(url, known_headers=['TEAM', 'YEAR', 'W', 'L'])
    nba_data['teamStats'] = [process_row(r) for r in filter_season(all_teams, season)]
    print(f"  Found {len(nba_data['teamStats'])} teams for {season}")
    
    # Fetch current season Advanced Stats
    print("Fetching Advanced Stats...")
    url = get_sheet_url(SHEETS['currentSeason'], TABS['current_advanced'])
    nba_data['advanced'] = [process_row(r) for r in fetch_csv(url, known_headers=['PLAYER_NAME', 'PLAYER_ID', 'OFF_RATING'])]
    print(f"  Found {len(nba_data['advanced'])} players")
    
    # Fetch current season Scoring
    print("Fetching Scoring Stats...")
    url = get_sheet_url(SHEETS['currentSeason'], TABS['current_scoring'])
    nba_data['scoring'] = [process_row(r) for r in fetch_csv(url, known_headers=['PLAYER_NAME', 'PLAYER_ID', 'PTS_OFF_TOV'])]
    print(f"  Found {len(nba_data['scoring'])} players")
    
    # Fetch current season Shot Location
    print("Fetching Shot Location Stats...")
    url = get_sheet_url(SHEETS['currentSeason'], TABS['current_shotLocation'])
    nba_data['shotLocation'] = [process_row(r) for r in fetch_csv(url, known_headers=['PLAYER_NAME', 'PLAYER_ID', 'Mid-Range_FG_PCT'])]
    print(f"  Found {len(nba_data['shotLocation'])} players")
    
    # Fetch current season Defense
    print("Fetching Defense Stats...")
    url = get_sheet_url(SHEETS['currentSeason'], TABS['current_defense'])
    nba_data['defense'] = [process_row(r) for r in fetch_csv(url, known_headers=['PLAYER_NAME', 'D_FG_PCT', 'CLOSE_DEF_PERSON_ID'])]
    print(f"  Found {len(nba_data['defense'])} players")
    
    # Fetch current season Usage
    print("Fetching Usage Stats...")
    url = get_sheet_url(SHEETS['currentSeason'], TABS['current_usage'])
    nba_data['usage'] = [process_row(r) for r in fetch_csv(url, known_headers=['PLAYER_NAME', 'PLAYER_ID', 'USG_PCT'])]
    print(f"  Found {len(nba_data['usage'])} players")
    
    # Fetch current season Clutch
    print("Fetching Clutch Stats...")
    url = get_sheet_url(SHEETS['currentSeason'], TABS['current_clutch'])
    nba_data['clutch'] = [process_row(r) for r in fetch_csv(url, known_headers=['PLAYER_NAME', 'PLAYER_ID', 'FG_PCT'])]
    print(f"  Found {len(nba_data['clutch'])} players")
    
    # Fetch current season Hustle
    print("Fetching Hustle Stats...")
    url = get_sheet_url(SHEETS['currentSeason'], TABS['current_hustle'])
    nba_data['hustle'] = [process_row(r) for r in fetch_csv(url, known_headers=['PLAYER_NAME', 'PLAYER_ID', 'DEFLECTIONS'])]
    print(f"  Found {len(nba_data['hustle'])} players")
    
    # Debug: Print sample of first advanced player
    if nba_data['advanced']:
        print("\n=== SAMPLE DATA (first advanced player) ===")
        first = nba_data['advanced'][0]
        print(f"  Keys: {list(first.keys())[:10]}...")
        print(f"  PLAYER_NAME: {first.get('PLAYER_NAME', 'NOT FOUND')}")
        print(f"  OFF_RATING: {first.get('OFF_RATING', 'NOT FOUND')}")
    
    # Safety: nothing for this season yet (e.g. early October before opening night) -> write nothing
    if not nba_data['advanced']:
        print(f"\nNo players returned for {season} (season not started yet, or the sheet is unreachable/empty).")
        print("Nothing written. Existing files left as they are.")
        sys.exit(0)
    
    # Safety: the sheet still holds a different season (e.g. new season computed but sheet not rolled over yet)
    sheet_season = sheet_season_label(nba_data['advanced'])
    if sheet_season and sheet_season != season:
        print(f"\nSheet reports season {sheet_season}, but the current season is {season}.")
        print("Nothing written, so last season's numbers don't land in this season's file.")
        sys.exit(0)
    
    # Write to JSON files: the per-season file and a fixed-name copy for pages to load
    output_path = f'nba-{season}-data.json'
    for path in (output_path, 'nba-current-season-data.json'):
        with open(path, 'w') as f:
            json.dump(nba_data, f, indent=2)
    
    print(f"\n✓ Data saved to {output_path} (and nba-current-season-data.json)")
    print(f"  Total size: {len(json.dumps(nba_data)):,} bytes")
    
    # Summary
    print("\n=== SUMMARY ===")
    for key, value in nba_data.items():
        if isinstance(value, list):
            print(f"  {key}: {len(value)} records")

if __name__ == '__main__':
    main()
