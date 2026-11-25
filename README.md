# nba-player-data

Data files behind the HoopsMatic comparison tools and games. Most are rebuilt daily from Google Sheets by the workflows in `.github/workflows/`.

## Known issue: title rows in the Awards sheet

The Awards sheet's TEAM column is wrong for many "NBA Champion" rows: it often names a team the player was on in another season (for example, Gary Payton II's 2022 title was listed under Boston). The sheet itself has not been corrected.

`scripts/update-awards.py` fixes this after every fetch. `fix_title_teams()` sets each title row's TEAM to that season's champion from `data/champions.json`, so `awards.json` is correct even though the sheet is not. Add the new champion to `data/champions.json` each June.

## Known issue: wrong years in the Awards sheet

A few Awards sheet rows have the wrong YEAR, for example Wilt Chamberlain's 1960 All-Star MVP is listed as 1950 (six All-Star MVP rows were a decade off). The sheet itself has not been corrected.

`scripts/update-awards.py` fixes these after every fetch too. `fix_award_years()` changes each row listed in `data/award-year-corrections.json` (player, award, wrong year, right year and the reason) to the right year. To fix another row, add it to that file.
