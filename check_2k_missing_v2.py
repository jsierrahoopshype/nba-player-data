"""
For each player present in the OLD nba2k.json but absent from the new one,
look for a near-match in the new data. Distinguishes real losses from
spelling variants and duplicated-name artifacts. Read-only.

    python check_2k_missing_v2.py

OLD_REF is set to HEAD~2 -- the version of nba2k.json from before the
2K27 rebuild (two commits back: the 2K commit, then the headshot commit).
If the history moves again, pass a different ref on the command line:

    python check_2k_missing_v2.py HEAD~5:nba2k.json
"""
import json
import subprocess
import sys
import unicodedata
import difflib

NEW = 'nba2k.json'
OLD_REF = sys.argv[1] if len(sys.argv) > 1 else 'HEAD~2:nba2k.json'


def norm(s):
    s = unicodedata.normalize('NFKD', str(s))
    s = ''.join(c for c in s if not unicodedata.combining(c))
    return ''.join(c for c in s if c.isalnum()).lower()


def dedupe_words(name):
    """'Anunoby Anunoby' -> 'Anunoby';  'Josh Primo Josh Primo' -> 'Josh Primo'"""
    w = str(name).split()
    half = len(w) // 2
    if len(w) % 2 == 0 and half and w[:half] == w[half:]:
        return ' '.join(w[:half])
    return name


def ratings(rec):
    return {k: v for k, v in rec.items()
            if k.upper().startswith('2K') and v not in ('', None)}


print('Comparing %s (new) against %s (old)\n' % (NEW, OLD_REF))

new = json.load(open(NEW, encoding='utf-8'))
raw = subprocess.run(['git', 'show', OLD_REF],
                     capture_output=True, text=True, encoding='utf-8').stdout
if not raw.strip():
    raise SystemExit('Could not read %s -- try another ref, e.g. HEAD~3:nba2k.json' % OLD_REF)
old = json.loads(raw)

print('old file: %d players    new file: %d players\n' % (len(old), len(new)))

new_by_norm = {}
for r in new:
    new_by_norm.setdefault(norm(r['Full Name']), r)

new_names = [r['Full Name'] for r in new]
missing = [r for r in old if norm(r['Full Name']) not in new_by_norm]

print('%d players in old but not in new\n' % len(missing))

real_loss = []
for rec in missing:
    name = rec['Full Name']
    old_n = len(ratings(rec))

    # 1. duplicated-word artifact?
    fixed = dedupe_words(name)
    if fixed != name and norm(fixed) in new_by_norm:
        hit = new_by_norm[norm(fixed)]
        print('%-28s -> ARTIFACT, present as "%s" (%d ratings)'
              % (name, hit['Full Name'], len(ratings(hit))))
        continue

    # 2. close spelling variant?
    close = difflib.get_close_matches(name, new_names, n=3, cutoff=0.82)
    if close:
        hit = new_by_norm[norm(close[0])]
        print('%-28s -> likely "%s" (%d ratings)   others: %s'
              % (name, close[0], len(ratings(hit)), ', '.join(close[1:]) or '-'))
        continue

    print('%-28s -> NO MATCH  (had %d ratings in old file)' % (name, old_n))
    if old_n:
        real_loss.append((name, old_n))

print()
if real_loss:
    print('Genuinely lost players WITH ratings (%d):' % len(real_loss))
    for name, n in real_loss:
        print('   %-28s %d ratings' % (name, n))
else:
    print('No player with ratings was lost.')
