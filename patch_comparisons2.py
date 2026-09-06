import json

with open('comparisons.json', encoding='utf-8') as f:
    data = json.load(f)

# Step 1: Remove the misplaced "Hustle Award" from YEARS RECEIVING VOTES
# (it's sitting at the top of that section before "Years with MVP votes")
current_section = None
to_remove = None
for i, row in enumerate(data):
    cp = row.get('Comparison points', '')
    if not row.get('Who wins?') and not row.get('Wheres the data?'):
        current_section = cp
    if current_section == 'YEARS RECEIVING VOTES' and cp == 'Hustle Award':
        to_remove = i
        break

if to_remove is not None:
    data.pop(to_remove)
    print(f"Removed misplaced Hustle Award at index {to_remove}")
else:
    print("Hustle Award not found in YEARS RECEIVING VOTES - nothing to remove")

# Step 2: Add "Hustle Award" to BEST AWARDS RANKING (after Clutch Player of the Year)
current_section = None
clutch_in_bar = None
for i, row in enumerate(data):
    cp = row.get('Comparison points', '')
    if not row.get('Who wins?') and not row.get('Wheres the data?'):
        current_section = cp
    if current_section == 'BEST AWARDS RANKING' and cp == 'Clutch Player of the Year':
        clutch_in_bar = i
        break

if clutch_in_bar is not None:
    data.insert(clutch_in_bar + 1, {
        'Comparison points': 'Hustle Award',
        'Who wins?': 'Least',
        'Wheres the data?': 'Award-Votes.csv'
    })
    print(f"Added Hustle Award to BEST AWARDS RANKING at index {clutch_in_bar + 1}")
else:
    print("Clutch Player of the Year not found in BEST AWARDS RANKING")

# Step 3: Add "Years with Hustle Award votes" to end of YEARS RECEIVING VOTES
# Find "Years with Clutch Player votes" and insert after it
current_section = None
clutch_votes = None
for i, row in enumerate(data):
    cp = row.get('Comparison points', '')
    if not row.get('Who wins?') and not row.get('Wheres the data?'):
        current_section = cp
    if current_section == 'YEARS RECEIVING VOTES' and cp == 'Years with Clutch Player votes':
        clutch_votes = i
        break

if clutch_votes is not None:
    data.insert(clutch_votes + 1, {
        'Comparison points': 'Years with Hustle Award votes',
        'Who wins?': 'Most',
        'Wheres the data?': 'Award-Votes.csv'
    })
    print(f"Added Years with Hustle Award votes at index {clutch_votes + 1}")
else:
    print("Years with Clutch Player votes not found")

with open('comparisons.json', 'w', encoding='utf-8') as f:
    json.dump(data, f, ensure_ascii=False, indent=2)
print('Done. Total records:', len(data))
