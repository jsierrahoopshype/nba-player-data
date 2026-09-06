import json

with open('comparisons.json', encoding='utf-8') as f:
    data = json.load(f)

accolades_clutch = None
best_ranking_end = None
years_votes_end = None
current_section = None

for i, row in enumerate(data):
    cp = row.get('Comparison points', '')
    if not row.get('Who wins?') and not row.get('Wheres the data?'):
        current_section = cp
    if current_section == 'ACCOLADES' and cp == 'Clutch Player of the Year':
        accolades_clutch = i
    if current_section == 'BEST AWARDS RANKING' and cp == 'Most Improved Player':
        best_ranking_end = i
    if current_section == 'YEARS RECEIVING VOTES' and cp == 'Years with MIP votes':
        years_votes_end = i

offset = 0
data.insert(accolades_clutch + 1 + offset, {'Comparison points': 'Hustle Award', 'Who wins?': 'Most', 'Wheres the data?': 'Awards.csv'})
offset += 1
data.insert(best_ranking_end + 1 + offset, {'Comparison points': 'Clutch Player of the Year', 'Who wins?': 'Least', 'Wheres the data?': 'Award-Votes.csv'})
offset += 1
data.insert(best_ranking_end + 2 + offset, {'Comparison points': 'Hustle Award', 'Who wins?': 'Least', 'Wheres the data?': 'Award-Votes.csv'})
offset += 1
data.insert(years_votes_end + 1 + offset, {'Comparison points': 'Years with Clutch Player votes', 'Who wins?': 'Most', 'Wheres the data?': 'Award-Votes.csv'})
offset += 1
data.insert(years_votes_end + 2 + offset, {'Comparison points': 'Years with Hustle Award votes', 'Who wins?': 'Most', 'Wheres the data?': 'Award-Votes.csv'})

with open('comparisons.json', 'w', encoding='utf-8') as f:
    json.dump(data, f, ensure_ascii=False, indent=2)
print('Done. Total records:', len(data))
