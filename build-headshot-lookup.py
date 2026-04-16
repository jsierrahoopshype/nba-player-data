import json
import re
import urllib.request

# 1. Read rsStats.json and extract unique player names
with open("rsStats.json", encoding="utf-8") as f:
    rs_data = json.load(f)

players = sorted(set(row["PLAYER"] for row in rs_data))
print(f"Unique players in rsStats.json: {len(players)}")

# 2. Fetch headshot filenames from GitHub API
url = "https://api.github.com/repos/jsierrahoopshype/nba-headshots/contents/players/headshots/face"
req = urllib.request.Request(url, headers={"Accept": "application/vnd.github.v3+json"})
with urllib.request.urlopen(req) as resp:
    gh_files = json.loads(resp.read().decode())

filenames = [f["name"] for f in gh_files if f["name"].endswith(".png")]
print(f"Headshot files on GitHub: {len(filenames)}")

# 3. Build indexes from GitHub filenames
# Filename format: "{nba_id}-{slug}.png" e.g. "2544-lebron-james.png"
slug_to_basename = {}
for fname in filenames:
    basename = fname.removesuffix(".png")
    hyphen_idx = basename.find("-")
    if hyphen_idx == -1:
        continue
    slug = basename[hyphen_idx + 1:]
    slug_to_basename[slug] = basename

SUFFIXES = re.compile(r"-(jr|sr|ii|iii|iv|v)$")

# Also build a suffix-stripped index for fallback matching
stripped_to_basenames = {}
for slug, basename in slug_to_basename.items():
    stripped = SUFFIXES.sub("", slug)
    if stripped != slug:
        stripped_to_basenames.setdefault(stripped, []).append(basename)

# 4. Slug generation
def make_slug(name):
    s = name.lower()
    s = s.replace("\u2019", "").replace("'", "")  # smart and straight apostrophes
    s = s.replace(".", "")
    s = re.sub(r"[^a-z0-9\s-]", "", s)
    s = s.strip()
    s = re.sub(r"\s+", "-", s)
    return s

def strip_suffix(slug):
    return SUFFIXES.sub("", slug)

def is_subsequence(short, long):
    """Check if 'short' is a subsequence of 'long' (chars appear in order)."""
    it = iter(long)
    return all(c in it for c in short)

# 5. Match players to headshots with multiple strategies
lookup = {}
unmatched_gh_slugs = dict(slug_to_basename)  # copy — remove as we match

for name in players:
    slug = make_slug(name)

    # Strategy 1: exact slug match
    if slug in slug_to_basename:
        lookup[name] = slug_to_basename[slug]
        unmatched_gh_slugs.pop(slug, None)
        continue

    # Strategy 2: rsStats name has no suffix but GitHub file does
    # e.g. "Kelly Oubre" -> "kelly-oubre" matches "kelly-oubre-jr"
    if slug in stripped_to_basenames:
        # Pick the first (there's usually only one)
        lookup[name] = stripped_to_basenames[slug][0]
        matched_slug = stripped_to_basenames[slug][0]
        # Find the original slug to remove from unmatched
        for gs, gb in list(unmatched_gh_slugs.items()):
            if gb == matched_slug:
                del unmatched_gh_slugs[gs]
                break
        continue

    # Strategy 3: rsStats has suffix but GitHub doesn't (unlikely but check)
    slug_stripped = strip_suffix(slug)
    if slug_stripped != slug and slug_stripped in slug_to_basename:
        lookup[name] = slug_to_basename[slug_stripped]
        unmatched_gh_slugs.pop(slug_stripped, None)
        continue

# Strategy 4: subsequence matching for diacritics (GitHub strips accents lossy)
# e.g. "Nikola Jokic" -> "nikola-jokic", GitHub has "nikola-joki" (from Jokić)
remaining_players = [p for p in players if p not in lookup]
remaining_gh = dict(unmatched_gh_slugs)

for gh_slug, gh_basename in list(remaining_gh.items()):
    for name in remaining_players:
        slug = make_slug(name)
        # The GitHub slug (diacritics removed) should be a subsequence of the
        # rsStats slug (anglicized), and lengths should be close
        if len(gh_slug) >= len(slug) * 0.7 and is_subsequence(gh_slug, slug):
            lookup[name] = gh_basename
            remaining_players.remove(name)
            del remaining_gh[gh_slug]
            break

print(f"Matched: {len(lookup)} / {len(players)} players ({len(filenames) - len(remaining_gh)} / {len(filenames)} headshots used)")
if remaining_gh:
    print(f"Unmatched headshot files ({len(remaining_gh)}):")
    for slug in sorted(remaining_gh):
        print(f"  {remaining_gh[slug]}")

# 6. Write output
with open("player-headshots.json", "w", encoding="utf-8") as f:
    json.dump(lookup, f, indent=2, ensure_ascii=False)

print(f"\nWrote player-headshots.json with {len(lookup)} entries")
