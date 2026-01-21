#!/usr/bin/env python3
"""
Fetches NBA 2025-26 season data from Google Sheets and compiles into a single JSON file.
Runs daily via GitHub Actions at 6 AM ET.
"""

import csv
import json
import urllib.request
from io import StringIO
from datetime import datetime, timezone

# Google Sheets Configuration
SHEETS = {
    'allTime': '1ZrDfzqiC31Hu3YCtxT4aZbZF4QVCVyGe6wBytR2LF30',
    'current2526': '1JH2FUBIyQ1zEHzZBxgP8vHBZ7d8EtP5-fSVG3zMgCgg',
    'historical': '1nPSI-VVKHkGYW9IY2KDP-v_xW6qi9_L9WpCnUFKRi8A'
}

# Tab GIDs
TABS = {
    # All-Time Database tabs
    'rsStats': 576369994,
    'poStats': 1591736011,
    'teamStats': 1735540905,
    
    # 2025-26 Season tabs
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

def fetch_csv(url):
    """Fetch CSV data from URL and return as list of dicts"""
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=30) as response:
            content = response.read().decode('utf-8')
            reader = csv.DictReader(StringIO(content))
            return list(reader)
    except Exception as e:
        print(f"Error fetching {url}: {e}")
        return []

def clean_numeric(value):
    """Convert string to float/int where possible"""
    if value is None or value == '' or value == '-':
        return None
    try:
        # Remove commas and percentage signs
        cleaned = str(value).replace(',', '').replace('%', '').strip()
        if '.' in cleaned:
            return float(cleaned)
        return int(cleaned)
    except ValueError:
        return value

def process_row(row):
    """Clean up a row of data"""
    return {k: clean_numeric(v) for k, v in row.items() if k}

def filter_2025_26_season(data, season_col='YEAR'):
    """Filter data to only 2025-26 season
    In All-Time Database, year is the END year: 2026 = 2025-26 season
    """
    return [row for row in data if row.get(season_col) in ['2025-26', '2026', 2026]]

def main():
    print(f"Starting NBA data fetch at {datetime.now(timezone.utc).isoformat()}")
    
    nba_data = {
        'lastUpdated': datetime.now(timezone.utc).isoformat(),
        'season': '2025-26',
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
    
    # Fetch Regular Season Stats (filtered to 2025-26)
    print("Fetching RS Stats...")
    url = get_sheet_url(SHEETS['allTime'], TABS['rsStats'])
    all_rs = fetch_csv(url)
    nba_data['rsStats'] = [process_row(r) for r in filter_2025_26_season(all_rs)]
    print(f"  Found {len(nba_data['rsStats'])} players")
    
    # Fetch Playoff Stats (filtered to 2025-26)
    print("Fetching PO Stats...")
    url = get_sheet_url(SHEETS['allTime'], TABS['poStats'])
    all_po = fetch_csv(url)
    nba_data['poStats'] = [process_row(r) for r in filter_2025_26_season(all_po)]
    print(f"  Found {len(nba_data['poStats'])} players")
    
    # Fetch Team Stats (filtered to 2025-26)
    print("Fetching Team Stats...")
    url = get_sheet_url(SHEETS['allTime'], TABS['teamStats'])
    all_teams = fetch_csv(url)
    nba_data['teamStats'] = [process_row(r) for r in filter_2025_26_season(all_teams)]
    print(f"  Found {len(nba_data['teamStats'])} teams")
    
    # Fetch 2025-26 Advanced Stats
    print("Fetching Advanced Stats...")
    url = get_sheet_url(SHEETS['current2526'], TABS['current_advanced'])
    nba_data['advanced'] = [process_row(r) for r in fetch_csv(url)]
    print(f"  Found {len(nba_data['advanced'])} players")
    
    # Fetch 2025-26 Scoring
    print("Fetching Scoring Stats...")
    url = get_sheet_url(SHEETS['current2526'], TABS['current_scoring'])
    nba_data['scoring'] = [process_row(r) for r in fetch_csv(url)]
    print(f"  Found {len(nba_data['scoring'])} players")
    
    # Fetch 2025-26 Shot Location
    print("Fetching Shot Location Stats...")
    url = get_sheet_url(SHEETS['current2526'], TABS['current_shotLocation'])
    nba_data['shotLocation'] = [process_row(r) for r in fetch_csv(url)]
    print(f"  Found {len(nba_data['shotLocation'])} players")
    
    # Fetch 2025-26 Defense
    print("Fetching Defense Stats...")
    url = get_sheet_url(SHEETS['current2526'], TABS['current_defense'])
    nba_data['defense'] = [process_row(r) for r in fetch_csv(url)]
    print(f"  Found {len(nba_data['defense'])} players")
    
    # Fetch 2025-26 Usage
    print("Fetching Usage Stats...")
    url = get_sheet_url(SHEETS['current2526'], TABS['current_usage'])
    nba_data['usage'] = [process_row(r) for r in fetch_csv(url)]
    print(f"  Found {len(nba_data['usage'])} players")
    
    # Fetch 2025-26 Clutch
    print("Fetching Clutch Stats...")
    url = get_sheet_url(SHEETS['current2526'], TABS['current_clutch'])
    nba_data['clutch'] = [process_row(r) for r in fetch_csv(url)]
    print(f"  Found {len(nba_data['clutch'])} players")
    
    # Fetch 2025-26 Hustle
    print("Fetching Hustle Stats...")
    url = get_sheet_url(SHEETS['current2526'], TABS['current_hustle'])
    nba_data['hustle'] = [process_row(r) for r in fetch_csv(url)]
    print(f"  Found {len(nba_data['hustle'])} players")
    
    # Write to JSON file
    output_path = 'nba-2025-26-data.json'
    with open(output_path, 'w') as f:
        json.dump(nba_data, f, indent=2)
    
    print(f"\n✓ Data saved to {output_path}")
    print(f"  Total size: {len(json.dumps(nba_data)):,} bytes")
    
    # Summary
    print("\n=== SUMMARY ===")
    for key, value in nba_data.items():
        if isinstance(value, list):
            print(f"  {key}: {len(value)} records")

if __name__ == '__main__':
    main()
