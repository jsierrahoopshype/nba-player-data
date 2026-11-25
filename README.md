# nba-player-data

Data files behind the HoopsMatic comparison tools and games. Most are rebuilt daily from Google Sheets by the workflows in `.github/workflows/`.

## Known issue: title rows in the Awards sheet

The Awards sheet's TEAM column is wrong for many "NBA Champion" rows: it often names a team the player was on in another season (for example, Gary Payton II's 2022 title was listed under Boston). The sheet itself has not been corrected.

`scripts/update-awards.py` fixes this after every fetch. `fix_title_teams()` sets each title row's TEAM to that season's champion from `data/champions.json`, so `awards.json` is correct even though the sheet is not. Add the new champion to `data/champions.json` each June.

## Known issue: wrong years in the Awards sheet

A few Awards sheet rows have the wrong YEAR, for example Wilt Chamberlain's 1960 All-Star MVP is listed as 1950 (six All-Star MVP rows were a decade off). The sheet itself has not been corrected.

`scripts/update-awards.py` fixes these after every fetch too. `fix_award_years()` changes each row listed in `data/award-year-corrections.json` (player, award, wrong year, right year and the reason) to the right year. To fix another row, add it to that file.

## Birth dates: overrides and placeholders

`scripts/update-bio.py` applies `data/bio_birthdate_overrides.json` after every fetch: each entry replaces the sheet's BIRTHDAY with `correct_value` while the sheet still holds `wrong_value`, and says where the date came from (`source`, `reason`). The sources are NBA.com (www.nba.com/player/<id>) and Wikidata. `data/bio_birthdate_review.json` lists the cases a person should look at.

NBA.com fills an unknown birth date with January 1, or with a date in 1905. Such a date is a placeholder (`scripts/birthdate_rules.py`): when the same player's Wikidata item has one different full date, that date is used (Ray Corley 1/14/1928, Herm Hedderick 1/10/1930, Jimmy Jones 1/4/1945); otherwise NBA.com's date is kept and listed in the review file as `nba_placeholder`. `update-bio.py` prints any placeholder-looking date that is not in the review file yet. Tests: `python scripts/test_birthdate_rules.py`.
