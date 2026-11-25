# nba-player-data

Data files behind the HoopsMatic comparison tools and games. Most are rebuilt daily from Google Sheets by the workflows in `.github/workflows/`.

## Known issue: title rows in the Awards sheet

The Awards sheet's TEAM column is wrong for many "NBA Champion" rows: it often names a team the player was on in another season (for example, Gary Payton II's 2022 title was listed under Boston). The sheet itself has not been corrected.

`scripts/update-awards.py` fixes this after every fetch. `fix_title_teams()` sets each title row's TEAM to that season's champion from `data/champions.json`, so `awards.json` is correct even though the sheet is not. Add the new champion to `data/champions.json` each June.
