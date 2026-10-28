#!/usr/bin/env python3
"""
Builds data/stats/rs-stats.csv and data/stats/po-stats.csv: the "RS Stats" and
"PO Stats" tabs of the All-Time Database, without the spreadsheet.

Why: in Oct 2026 the All-Time Database grew too big for Google to export, and the
jobs that read these two tabs failed daily. Past seasons never change, so they are
frozen from the last good copies; only the season in progress is rebuilt, every day,
from NBA's public storage bucket (the box scores behind cdn.nba.com, which blocks
servers; no key needed).

  data/stats/rs-frozen.csv      RS Stats through 2025-26: salary-season-finder's copy
                                of the tab (Oct 16 2026, 2025-26 final), byte for byte,
                                including the tab's trailing empty rows
  data/stats/po-frozen.csv      PO Stats through the 2026 playoffs, from poStats.json
  data/stats/rs-season-YYYY.csv one season built from box scores (rows only; YYYY is
  data/stats/po-season-YYYY.csv the season's end year, as in the YEAR column). Only the
                                current season's file is rewritten; earlier ones stay.
  data/stats/rs-stats.csv       what the readers use: header + frozen rows + season
  data/stats/po-stats.csv       files in order (+ the RS tab's empty rows at the end)

Every rebuilt row matches the tab's layout and formats (checked against 2025-26):
  - one row per player per season; TEAM is the team of his latest game; CODE is
    "PLAYER TEAM YEAR", RG CODE is empty, NB CODE is NBA's own spelling of his name
  - PLAYER is the HoopsHype spelling: the light sheet's "HM Codes" table, then
    "Jr." -> "Jr"
  - MIN to one decimal (half up, no ".0"); FG%/3P%/FT% as percents to one decimal;
    per-game columns and the second FG%/3P%/FT% to two decimals (half up)
  - RS only: the tab's columns headed TOV / G, STL / G, BLK / G hold steals, blocks
    and turnovers per game, in that order. The tab has them that way; so does this.
  - AGE (Feb 1) is the age on Feb 8 of the YEAR, which is what the tab computes, from
    bio.json's birthdays (the Bio Data tab with data/bio_birthdate_overrides.json's
    corrections applied; since Oct 2026, accepting the few ages the corrections move)
  - RAT (RS) is left empty: its formula is unknown and no reader uses it
  - PO RESULT: First Round / Conf Semis / Conf Finalist / Finalist / Champion from
    the series results; empty while the team is still playing
Known, accepted differences from the old tab: minutes can differ by 0.1 (NBA rounds
each game), and a stat NBA corrects after the game may not reach the box score.

Safety, before anything is written (exit 1 leaves every file as committed):
  - every box score of a finished game must download
  - past seasons: the new rs-stats.csv / po-stats.csv minus the current season must be
    byte-identical to the committed files minus the current season
  - games played never go down: every player in the committed current-season file is
    still there (by NB CODE) with at least as many games
  - neither file may end up with fewer rows than the committed one

Usage: python scripts/build_season_stats.py
"""

import csv
import io
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from decimal import Decimal, ROUND_HALF_UP

BUCKET = 'https://nba-prod-us-east-1-mediaops-stats.s3.amazonaws.com/NBA'
SCHEDULE_URL = BUCKET + '/staticData/scheduleLeagueV2.json'
BOX_URL = BUCKET + '/liveData/boxscore/boxscore_{}.json'
# The light HoopsMatic spreadsheet's "HM Codes" tab: NBA name -> HoopsHype name.
HM_CODES_URL = ('https://docs.google.com/spreadsheets/d/1Wxqb2qD848ZEb0jVpVkJfN4-XzKy5qhOmdWMeFTe1ow'
                '/export?format=csv&gid=1892686525')
# Birthdays for AGE (Feb 1): update-bio.py's output, corrections applied.
BIO_PATH = 'bio.json'

STATS_DIR = 'data/stats'
RS_FROZEN = f'{STATS_DIR}/rs-frozen.csv'
PO_FROZEN = f'{STATS_DIR}/po-frozen.csv'
RS_OUT = f'{STATS_DIR}/rs-stats.csv'
PO_OUT = f'{STATS_DIR}/po-stats.csv'
AGE_REF = (2, 8)   # month, day: the tab's "AGE (Feb 1)" is the age on Feb 8
CRLF = '\r\n'      # the tab's CSV export: CRLF, no line break after the last row
PO_ROUNDS = {1: 'First Round', 2: 'Conf Semis', 3: 'Conf Finalist', 4: 'Finalist'}
STATS = [('PTS', 'points'), ('FGM', 'fieldGoalsMade'), ('FGA', 'fieldGoalsAttempted'),
         ('3P', 'threePointersMade'), ('3PA', 'threePointersAttempted'),
         ('FTM', 'freeThrowsMade'), ('FTA', 'freeThrowsAttempted'),
         ('ORB', 'reboundsOffensive'), ('DRB', 'reboundsDefensive'), ('REB', 'reboundsTotal'),
         ('AST', 'assists'), ('STL', 'steals'), ('BLK', 'blocks'), ('TOV', 'turnovers'),
         ('PF', 'foulsPersonal')]


def fail(message):
    print(f'::error::Season stats: {message}. Nothing under {STATS_DIR}/ was changed.')
    sys.exit(1)


def get(url, tries=3):
    err = None
    for attempt in range(tries):
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            return urllib.request.urlopen(req, timeout=60).read()
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            err = e
            time.sleep(5 * (attempt + 1))
    raise RuntimeError(f'{url}: {err}')


# ── Formats (the tab's, see the docstring) ──

def dec(x):
    return Decimal(str(x))


def strip0(s):
    return s[:-2] if s.endswith('.0') else s


def fmt_min(seconds):
    return strip0(str((dec(seconds) / 60).quantize(Decimal('0.1'), rounding=ROUND_HALF_UP)))


def fmt_pct(made, att):
    """FG% as the tab writes it: percent, one decimal, no '.0'."""
    if not att:
        return '0'
    ratio = (dec(made) / dec(att)).quantize(Decimal('0.001'), rounding=ROUND_HALF_UP)
    return strip0(str((ratio * 100).quantize(Decimal('0.1'))))


def fmt_2(x, y):
    if not y:
        return '0.00'
    return str((dec(x) / dec(y)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP))


def age_on_ref(birthday, year):
    m = re.fullmatch(r'(\d{1,2})/(\d{1,2})/(\d{4})', birthday or '')
    if not m:
        return ''
    bm, bd, by = map(int, m.groups())
    return str(year - by - ((AGE_REF[0], AGE_REF[1]) < (bm, bd)))


# ── Files ──

def read(path):
    if not os.path.exists(path):
        return ''
    with open(path, encoding='utf-8', newline='') as f:
        return f.read()


def write(path, text):
    with open(path, 'w', encoding='utf-8', newline='') as f:
        f.write(text)


def lines_of(text):
    """The CSV's rows as raw lines (no field in these tabs spans lines; checked)."""
    if not text:
        return []
    lines = text.split(CRLF)
    if len(lines) != len(list(csv.reader(io.StringIO(text)))):
        fail('a stats file has a field that spans lines')
    return lines


def year_of(line):
    row = next(csv.reader([line]), [])
    return row[4].strip() if len(row) > 4 else ''


def to_line(row):
    out = io.StringIO()
    csv.writer(out, lineterminator='').writerow(row)
    return out.getvalue()


def season_files(kind):
    files = sorted(f for f in os.listdir(STATS_DIR) if re.fullmatch(rf'{kind}-season-\d{{4}}\.csv', f))
    return [f'{STATS_DIR}/{f}' for f in files]


def combine(frozen_text, kind, blocks):
    """header + frozen rows + every season block in year order + the frozen file's
    trailing empty rows (the RS tab has 512 of them)."""
    lines = lines_of(frozen_text)
    header, body = lines[0], lines[1:]
    tail = []
    while body and not year_of(body[-1]):
        tail.insert(0, body.pop())
    out = [header] + body
    for year in sorted(blocks):
        out += blocks[year]
    return CRLF.join(out + tail)


# ── Names and bios ──

def load_hm_codes():
    text = get(HM_CODES_URL).decode('utf-8')
    rows = list(csv.reader(io.StringIO(text)))
    if not rows or [c.strip() for c in rows[0][:2]] != ['NBA Name', 'HH Name'] or len(rows) < 100:
        fail('the HM Codes tab did not come back as its CSV')
    return {r[0].strip(): r[1].strip() for r in rows[1:] if len(r) > 1 and r[0].strip() and r[1].strip()}


def hh_name(nba_name, hm):
    name = hm.get(nba_name) or nba_name
    return re.sub(r' (Jr|Sr)\.$', r' \1', name)


def load_birthdays():
    with open(BIO_PATH, encoding='utf-8') as f:
        rows = json.load(f)
    if len(rows) < 1000:
        fail(f'{BIO_PATH} has only {len(rows)} players')
    out = {}
    for r in rows:
        out.setdefault((r.get('PLAYER') or '').strip(), (r.get('BIRTHDAY') or '').strip())
    return out


# ── Box scores ──

def seconds(minutes):
    m = re.fullmatch(r'PT(\d+)M([\d.]+)S', minutes or '')
    return int(m.group(1)) * 60 + float(m.group(2)) if m else 0.0


def load_boxscores(game_ids):
    def one(gid):
        return gid, json.loads(get(BOX_URL.format(gid)))['game']
    try:
        with ThreadPoolExecutor(8) as pool:
            games = dict(pool.map(one, game_ids))
    except Exception as e:   # noqa: BLE001 - any missing box score stops the run
        fail(f'a box score did not download ({e})')
    return games


def aggregate(games, order):
    """Per player (by NBA personId): totals, his latest name and team, game count."""
    players = {}
    for gid in order:
        g = games[gid]
        for side in ('homeTeam', 'awayTeam'):
            team = g[side]['teamTricode']
            for p in g[side]['players']:
                if p.get('played') != '1':
                    continue
                s = p['statistics']
                t = players.setdefault(p['personId'], {'GP': 0, 'SEC': 0.0, **{k: 0 for k, _ in STATS}})
                t['GP'] += 1
                t['SEC'] += seconds(s.get('minutes'))
                for k, src in STATS:
                    t[k] += int(s.get(src) or 0)
                t['NBA_NAME'], t['TEAM'] = p['name'], team
    return players


def base_row(t, year, hm, birthdays):
    player = hh_name(t['NBA_NAME'], hm)
    gp = t['GP']
    row = {'CODE': f"{player} {t['TEAM']} {year}", 'RG CODE': '', 'NB CODE': t['NBA_NAME'],
           'PLAYER': player, 'YEAR': str(year), 'TEAM': t['TEAM'], 'GP': str(gp),
           'MIN': fmt_min(t['SEC']), **{k: str(t[k]) for k, _ in STATS},
           'FG%': fmt_pct(t['FGM'], t['FGA']), '3P%': fmt_pct(t['3P'], t['3PA']),
           'FT%': fmt_pct(t['FTM'], t['FTA'])}
    per_game = {k: fmt_2(t[k], gp) for k in ('PTS', 'REB', 'AST', 'STL', 'BLK', 'TOV')}
    dup_pct = [fmt_2(t['FGM'], t['FGA']), fmt_2(t['3P'], t['3PA']), fmt_2(t['FTM'], t['FTA'])]
    return row, per_game, dup_pct, birthdays.get(player, '')


def counts(t):
    return [t[k] for k in ('PTS', 'FGM', 'FGA')]


def rs_rows(players, year, hm, birthdays):
    rows = []
    for t in players.values():
        r, pg, dup, bday = base_row(t, year, hm, birthdays)
        rows.append([r['CODE'], r['RG CODE'], r['NB CODE'], r['PLAYER'], r['YEAR'], r['TEAM'],
                     r['GP'], r['MIN'], r['PTS'], r['FGM'], r['FGA'], r['FG%'], r['3P'], r['3PA'],
                     r['3P%'], r['FTM'], r['FTA'], r['FT%'], r['ORB'], r['DRB'], r['REB'], r['AST'],
                     r['STL'], r['BLK'], r['TOV'], r['PF'], age_on_ref(bday, year),
                     pg['PTS'], pg['REB'], pg['AST'],
                     pg['STL'], pg['BLK'], pg['TOV'],   # under the tab's TOV / G, STL / G, BLK / G
                     *dup, ''])                          # RAT
    return sorted(rows, key=lambda r: r[3].casefold())


def po_results(games):
    wins, teams = {}, {}
    for gid, g in games.items():
        rnd, series = int(gid[7]), gid[8]
        home, away = g['homeTeam'], g['awayTeam']
        winner = home if home['score'] > away['score'] else away
        key = (rnd, series)
        wins.setdefault(key, {})
        wins[key][winner['teamTricode']] = wins[key].get(winner['teamTricode'], 0) + 1
        teams.setdefault(key, set()).update((home['teamTricode'], away['teamTricode']))
    result = {}
    for key, tms in teams.items():
        if max(wins[key].values()) < 4:
            continue                       # series still going
        for team in tms:
            if wins[key].get(team, 0) < 4:
                result[team] = PO_ROUNDS[key[0]]
            elif key[0] == 4:
                result[team] = 'Champion'
    return result


def po_rows(players, year, hm, birthdays, results):
    rows = []
    for t in players.values():
        r, pg, dup, _ = base_row(t, year, hm, birthdays)
        rows.append([r['CODE'], r['RG CODE'], r['NB CODE'], r['PLAYER'], r['YEAR'], r['TEAM'],
                     r['GP'], r['MIN'], r['PTS'], r['FGM'], r['FGA'], r['FG%'], r['3P'], r['3PA'],
                     r['3P%'], r['FTM'], r['FTA'], r['FT%'], r['ORB'], r['DRB'], r['REB'], r['AST'],
                     r['STL'], r['BLK'], r['TOV'], r['PF'], '',
                     pg['PTS'], pg['REB'], pg['AST'], pg['STL'], pg['BLK'], pg['TOV'],
                     *dup, '', results.get(r['TEAM'], '')])
    return sorted(rows, key=lambda r: r[3].casefold())


# ── Safety checks ──

def without_year(text, year):
    return [ln for ln in lines_of(text) if year_of(ln) != str(year)]


def check(kind, old_out, new_out, old_block, new_block, year):
    if old_out and without_year(old_out, year) != without_year(new_out, year):
        fail(f'{kind}: a past season would change')
    old_gp = {}
    for ln in old_block:
        r = next(csv.reader([ln]))
        old_gp[r[2]] = int(r[6])
    new_gp = {next(csv.reader([ln]))[2]: int(next(csv.reader([ln]))[6]) for ln in new_block}
    lost = [n for n in old_gp if n not in new_gp]
    down = [f'{n} {old_gp[n]}->{new_gp[n]}' for n in old_gp if n in new_gp and new_gp[n] < old_gp[n]]
    if lost or down:
        fail(f'{kind} {year}: games played would go down ({", ".join((lost + down)[:10])})')
    if old_out and len(lines_of(new_out)) < len(lines_of(old_out)):
        fail(f'{kind}: {len(lines_of(old_out))} rows would become {len(lines_of(new_out))}')


def build(kind, frozen_path, out_path, year, new_rows):
    frozen = read(frozen_path)
    if not frozen:
        fail(f'{frozen_path} is missing')
    season_path = f'{STATS_DIR}/{kind}-season-{year}.csv'
    old_block = lines_of(read(season_path))
    new_block = [to_line(r) for r in new_rows]
    blocks = {int(re.search(r'(\d{4})\.csv$', p).group(1)): lines_of(read(p)) for p in season_files(kind)}
    if new_block:
        blocks[year] = new_block
    old_out, new_out = read(out_path), combine(frozen, kind, blocks)
    check(kind, old_out, new_out, old_block, new_block, year)
    return season_path, CRLF.join(new_block), new_out, len(new_block)


def main():
    schedule = json.loads(get(SCHEDULE_URL))['leagueSchedule']
    season = schedule['seasonYear']                      # '2026-27'
    year = int(season[:4]) + 1                           # the YEAR column: 2027
    final = [g for d in schedule['gameDates'] for g in d['games'] if g.get('gameStatus') == 3]
    final.sort(key=lambda g: (g['gameDateTimeUTC'], g['gameId']))
    rs_ids = [g['gameId'] for g in final if g['gameId'].startswith('002')]   # not preseason,
    po_ids = [g['gameId'] for g in final if g['gameId'].startswith('004')]   # play-in or Cup final
    print(f'{season}: {len(rs_ids)} regular-season and {len(po_ids)} playoff games final')

    hm, birthdays = load_hm_codes(), load_birthdays()
    games = load_boxscores(rs_ids + po_ids)
    rs = rs_rows(aggregate(games, rs_ids), year, hm, birthdays)
    po_games = {gid: games[gid] for gid in po_ids}
    po = po_rows(aggregate(games, po_ids), year, hm, birthdays, po_results(po_games))

    outputs = [build('rs', RS_FROZEN, RS_OUT, year, rs), build('po', PO_FROZEN, PO_OUT, year, po)]
    for (season_path, block, combined, n), out_path in zip(outputs, (RS_OUT, PO_OUT)):
        if n:
            write(season_path, block)
        write(out_path, combined)
        print(f'{out_path}: {len(lines_of(combined)) - 1} rows ({n} for {season})')


if __name__ == '__main__':
    main()
