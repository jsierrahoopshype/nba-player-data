#!/usr/bin/env python3
"""The birth-date rules behind data/bio_birthdate_overrides.json.

Sources, in order: NBA.com (www.nba.com/player/<PERSON_ID>, career years
checked), then Wikidata P569 for the basketball player whose NBA.com ID
(P3647) and career match. See data/bio_birthdate_review.json for every case a
person should look at.

THE PLACEHOLDER RULE. NBA.com fills an unknown birth date with January 1 of a
year, or with a date in 1905. Such a date is a placeholder, not evidence:

  * if Wikidata has a different full date (day precision, 11) for the same
    person, Wikidata's date is used (source "wikidata");
  * otherwise NBA.com's date is kept, and the player is listed in the review
    file with kind "nba_placeholder".

When Wikidata carries more than one different full date, none is picked: the
NBA.com date is kept and listed. nba-career-map applies the same rule in
scripts/nba_birthdates.py.
"""
import datetime as dt
import re

PLACEHOLDER_YEAR = 1905
KIND_PLACEHOLDER = 'nba_placeholder'

_MDY = re.compile(r'^\s*(\d{1,2})/(\d{1,2})/(\d{4})\s*$')
_ISO = re.compile(r'^\s*(\d{4})-(\d{2})-(\d{2})\s*$')


def parse(value):
    """'1/14/1928' or '1928-01-14' -> date, or None when not a full date."""
    s = str(value or '')
    m = _MDY.match(s)
    if m:
        mo, d, y = (int(x) for x in m.groups())
    else:
        m = _ISO.match(s)
        if not m:
            return None
        y, mo, d = (int(x) for x in m.groups())
    try:
        return dt.date(y, mo, d)
    except ValueError:
        return None


def mdy(d):
    """date -> '1/14/1928', the BIRTHDAY format of bio.json."""
    return f'{d.month}/{d.day}/{d.year}'


def is_nba_placeholder(value):
    """Is this NBA.com birth date a placeholder (January 1, or any 1905 date)?"""
    d = parse(value)
    return bool(d) and ((d.month == 1 and d.day == 1) or d.year == PLACEHOLDER_YEAR)


def choose(nba_value, wikidata_full_dates):
    """(value, source) for one player, NBA.com first.

    `wikidata_full_dates` are the day-precision P569 values of the Wikidata
    item that passed the identity checks (any format parse() reads). Returns
    the value in bio.json's M/D/YYYY format and "nba.com", "wikidata" or
    KIND_PLACEHOLDER (NBA.com's placeholder kept: list it for review).
    """
    nba = parse(nba_value)
    wd = sorted({d for d in (parse(v) for v in wikidata_full_dates or []) if d})
    if nba is None:
        return (mdy(wd[0]), 'wikidata') if len(wd) == 1 else ('', 'unresolved')
    if not is_nba_placeholder(nba_value):
        return mdy(nba), 'nba.com'
    other = [d for d in wd if d != nba]
    if len(other) == 1:
        return mdy(other[0]), 'wikidata'
    return mdy(nba), KIND_PLACEHOLDER
