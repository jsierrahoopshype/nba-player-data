#!/usr/bin/env python3
"""Tests for the birth-date placeholder rule (scripts/birthdate_rules.py) and
for the committed data it shaped: data/bio_birthdate_overrides.json,
data/bio_birthdate_review.json and bio.json.

Run from the repo root:  python scripts/test_birthdate_rules.py
Offline. Exits 1 on the first failing test.
"""
import importlib.util
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import birthdate_rules as R  # noqa: E402

_spec = importlib.util.spec_from_file_location('update_bio', os.path.join(HERE, 'update-bio.py'))
update_bio = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(update_bio)


def _load(rel):
    with open(os.path.join(ROOT, rel), encoding='utf-8') as f:
        return json.load(f)


def test_placeholder_dates():
    for v in ('1/1/1928', '1928-01-01', '4/5/1905', '1905-12-31', '1/1/2000'):
        assert R.is_nba_placeholder(v), v
    for v in ('1/14/1928', '1/2/1930', '12/31/1904', '2/1/1906', '', 'n/a', '1928'):
        assert not R.is_nba_placeholder(v), v


def test_choose_wikidata_for_a_placeholder():
    # Ray Corley: NBA.com 1/1/1928, Wikidata both 1/1/1928 and 1/14/1928
    assert R.choose('1928-01-01', ['1928-01-01', '1928-01-14']) == ('1/14/1928', 'wikidata')
    # Herm Hedderick
    assert R.choose('1/1/1930', ['1930-01-10', '1930-01-01']) == ('1/10/1930', 'wikidata')
    # a 1905 date is a placeholder whatever the day
    assert R.choose('4/5/1905', ['1922-01-01']) == ('1/1/1922', 'wikidata')


def test_choose_keeps_a_placeholder_wikidata_cannot_replace():
    assert R.choose('1/1/1986', ['1986-01-01']) == ('1/1/1986', R.KIND_PLACEHOLDER)
    assert R.choose('1/1/1986', []) == ('1/1/1986', R.KIND_PLACEHOLDER)
    # two different Wikidata days: no pick
    assert R.choose('1/1/1950', ['1950-03-03', '1950-04-04']) == ('1/1/1950', R.KIND_PLACEHOLDER)


def test_choose_nba_wins_when_not_a_placeholder():
    assert R.choose('2/26/1955', ['1955-02-28']) == ('2/26/1955', 'nba.com')
    assert R.choose('1/2/1960', ['1960-05-05']) == ('1/2/1960', 'nba.com')


def test_known_cases_switched_to_wikidata():
    by = {o['name']: o for o in _load('data/bio_birthdate_overrides.json')}
    for name, date in (('Ray Corley', '1/14/1928'), ('Herm Hedderick', '1/10/1930'),
                       ('Jimmy Jones', '1/4/1945')):
        o = by[name]
        assert o['correct_value'] == date and o['source'] == 'wikidata', o
        assert 'placeholder' in o['reason'], o


def test_no_nba_com_override_is_an_unlisted_placeholder():
    review = {e['name']: e for e in _load('data/bio_birthdate_review.json')['entries']}
    for o in _load('data/bio_birthdate_overrides.json'):
        if o.get('source') == 'nba.com' and R.is_nba_placeholder(o['correct_value']):
            e = review.get(o['name'])
            assert e and e['kind'] == R.KIND_PLACEHOLDER, o['name']


def test_every_placeholder_in_bio_json_is_reviewed():
    review = {e['name']: e for e in _load('data/bio_birthdate_review.json')['entries']}
    for r in _load('bio.json'):
        if R.is_nba_placeholder(r['BIRTHDAY']):
            assert r['PLAYER'] in review, r
    for e in review.values():
        if e['kind'] == R.KIND_PLACEHOLDER:
            assert e['chosen_source'] == 'nba.com' and R.is_nba_placeholder(e['chosen']), e
            # the rule says keep it only when Wikidata has no single other full date
            wd = [v for w in e['wikidata'] for v in w['values']]
            assert R.choose(e['chosen'], wd)[1] == R.KIND_PLACEHOLDER, e['name']


def test_bio_json_carries_the_overrides():
    bio = {r['PLAYER']: r['BIRTHDAY'] for r in _load('bio.json')}
    assert bio['Ray Corley'] == '1/14/1928'
    assert bio['Jimmy Jones'] == '1/4/1945'
    assert 'Herm Hedderick' not in bio   # not in the sheet


def test_update_bio_applies_and_reports():
    import io
    import contextlib
    recs = [{'PLAYER': 'Ray Corley', 'BIRTHDAY': '1/1/1928'},
            {'PLAYER': 'Somebody New', 'BIRTHDAY': '1/1/1999'}]
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        update_bio.apply_birthdate_overrides(recs, os.path.join(ROOT, update_bio.OVERRIDES_PATH))
        new = update_bio.report_placeholders(recs, os.path.join(ROOT, update_bio.REVIEW_PATH))
    assert recs[0]['BIRTHDAY'] == '1/14/1928'
    assert new == ['Somebody New'], new


def main():
    tests = [(n, f) for n, f in globals().items() if n.startswith('test_') and callable(f)]
    for name, fn in tests:
        try:
            fn()
        except AssertionError as e:
            print(f'FAIL {name}: {e}')
            return 1
        print(f'PASS {name}')
    print(f'all {len(tests)} birth-date rule tests PASS')
    return 0


if __name__ == '__main__':
    sys.exit(main())
