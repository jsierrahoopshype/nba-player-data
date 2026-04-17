import json
import re
import unicodedata
import urllib.request

# ========================================
# Manual alias table (Strategy G)
# ========================================
ALIASES = {
    # Nicknames vs full names (rsStats name -> headshot slug)
    "Metta World Peace": "ron-artest",
    "Metta Sandiford-Artest": "ron-artest",
    "Bill Walker": "henry-walker",
    "Herb Jones": "herbert-jones",
    "Carlton Carrington": "bub-carrington",
    "Sviatoslav Mykhailiuk": "svi-mykhailiuk",
    "Timothe Luwawu": "timothe-luwawu-cabarrot",
    "Juan Hernangomez": "juancho-hernangomez",
    "Hidayet Turkoglu": "hedo-turkoglu",
    "Jose Juan Barea": "jj-barea",
    "Enes Kanter": "enes-freedom",
    "Moe Harkless": "maurice-harkless",
    "Patrick Mills": "patty-mills",
    "Ishmael Smith": "ish-smith",
    "Radoslav Nesterovic": "rasho-nesterovic",
    "Predrag Stojakovic": "peja-stojakovic",
    "Tiny Archibald": "nate-archibald",
    "Walter Tavares": "edy-tavares",
    "Dee Brown (1968)": "dee-brown",
    "Ron Holland": "ronald-holland-ii",
    "Mike James (1975)": "mike-james",
}

# ========================================
# 1. Read rsStats.json
# ========================================
with open("rsStats.json", encoding="utf-8") as f:
    rs_data = json.load(f)

players = sorted(set(row["PLAYER"] for row in rs_data))
print(f"Unique players in rsStats.json: {len(players)}")

# ========================================
# 2. Fetch headshot filenames via Git Trees API (no 1000-file cap)
# ========================================
tree_url = "https://api.github.com/repos/jsierrahoopshype/nba-headshots/git/trees/main?recursive=1"
req = urllib.request.Request(tree_url, headers={"Accept": "application/vnd.github.v3+json"})
with urllib.request.urlopen(req) as resp:
    tree_data = json.loads(resp.read().decode())

filenames = []
for item in tree_data.get("tree", []):
    path = item["path"]
    if path.startswith("players/headshots/face/") and path.endswith(".png"):
        filenames.append(path.split("/")[-1])

print(f"Headshot files on GitHub: {len(filenames)}")

# ========================================
# 3. Build indexes from GitHub filenames
# ========================================
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

# Suffix-stripped index for fallback matching
stripped_to_basenames = {}
for slug, basename in slug_to_basename.items():
    stripped = SUFFIXES.sub("", slug)
    if stripped != slug:
        stripped_to_basenames.setdefault(stripped, []).append(basename)

# ========================================
# 4. Helpers
# ========================================
def make_slug(name):
    """Basic slug: lowercase, strip apostrophes/periods/punctuation, spaces to hyphens."""
    s = name.lower()
    s = s.replace("\u2019", "").replace("'", "")
    s = s.replace(".", "")
    s = re.sub(r"[^a-z0-9\s-]", "", s)
    s = s.strip()
    s = re.sub(r"\s+", "-", s)
    return s

def normalize_accent(s):
    """Strip all accents/diacritics: NFKD decompose then encode to ASCII."""
    return unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode("ascii")

def aggressive_normalize(name):
    """Strategy E: strip accents, suffixes, punctuation, lowercase."""
    s = normalize_accent(name).lower()
    s = s.replace("'", "").replace("\u2019", "").replace(".", "")
    s = re.sub(r"[^a-z0-9\s-]", "", s)
    s = s.strip()
    s = re.sub(r"\s+", "-", s)
    # Strip suffixes
    s = SUFFIXES.sub("", s)
    return s

def strip_suffix(slug):
    return SUFFIXES.sub("", slug)

def is_subsequence(short, long):
    """Check if 'short' is a subsequence of 'long' (chars appear in order)."""
    it = iter(long)
    return all(c in it for c in short)

def first_last_tokens(slug):
    """Extract first and last tokens from a hyphenated slug."""
    parts = slug.split("-")
    parts = [p for p in parts if p]  # filter empty
    if len(parts) >= 2:
        return (parts[0], parts[-1])
    elif len(parts) == 1:
        return (parts[0], parts[0])
    return None

# ========================================
# 5. Build aggressive-normalized index for GitHub slugs (Strategy E)
# ========================================
aggressive_gh = {}  # aggressive_slug -> basename
for slug, basename in slug_to_basename.items():
    a = strip_suffix(normalize_accent(slug).lower())
    a = re.sub(r"[^a-z0-9-]", "", a)
    aggressive_gh.setdefault(a, basename)

# Build first+last token index for GitHub slugs (Strategy F)
fl_gh = {}  # (first, last) -> basename
for slug, basename in slug_to_basename.items():
    fl = first_last_tokens(strip_suffix(slug))
    if fl:
        fl_gh.setdefault(fl, basename)

# Build alias slug -> basename index (Strategy G)
alias_gh = {}
for alias_name, alias_slug in ALIASES.items():
    clean = alias_slug.replace(".", "").lower()
    # Find the GitHub basename that ends with this slug
    for slug, basename in slug_to_basename.items():
        if slug == alias_slug or slug == clean or strip_suffix(slug) == alias_slug or strip_suffix(slug) == clean:
            alias_gh[alias_name] = basename
            break

# ========================================
# 6. Match players to headshots
# ========================================
lookup = {}
unmatched_gh_slugs = dict(slug_to_basename)

def record_match(name, slug, basename):
    lookup[name] = basename
    unmatched_gh_slugs.pop(slug, None)

for name in players:
    if name in lookup:
        continue
    slug = make_slug(name)

    # Strategy A: exact slug match
    if slug in slug_to_basename:
        record_match(name, slug, slug_to_basename[slug])
        continue

    # Strategy B: rsStats name has no suffix but GitHub file does
    if slug in stripped_to_basenames:
        basename = stripped_to_basenames[slug][0]
        for gs, gb in list(unmatched_gh_slugs.items()):
            if gb == basename:
                del unmatched_gh_slugs[gs]
                break
        lookup[name] = basename
        continue

    # Strategy C: rsStats has suffix but GitHub doesn't
    slug_stripped = strip_suffix(slug)
    if slug_stripped != slug and slug_stripped in slug_to_basename:
        record_match(name, slug_stripped, slug_to_basename[slug_stripped])
        continue

    # Strategy E: aggressive normalization (strip accents + suffixes + punctuation)
    a_slug = aggressive_normalize(name)
    if a_slug in aggressive_gh:
        basename = aggressive_gh[a_slug]
        for gs, gb in list(unmatched_gh_slugs.items()):
            if gb == basename:
                del unmatched_gh_slugs[gs]
                break
        lookup[name] = basename
        continue

    # Strategy F: first + last token matching
    fl = first_last_tokens(strip_suffix(slug))
    if fl and fl in fl_gh:
        basename = fl_gh[fl]
        for gs, gb in list(unmatched_gh_slugs.items()):
            if gb == basename:
                del unmatched_gh_slugs[gs]
                break
        lookup[name] = basename
        continue

    # Strategy G: manual alias
    if name in alias_gh:
        basename = alias_gh[name]
        for gs, gb in list(unmatched_gh_slugs.items()):
            if gb == basename:
                del unmatched_gh_slugs[gs]
                break
        lookup[name] = basename
        continue

# Strategy D: subsequence matching for remaining diacritics
remaining_players = [p for p in players if p not in lookup]
remaining_gh = dict(unmatched_gh_slugs)

for gh_slug, gh_basename in list(remaining_gh.items()):
    for name in remaining_players:
        slug = make_slug(name)
        if len(gh_slug) >= len(slug) * 0.7 and is_subsequence(gh_slug, slug):
            lookup[name] = gh_basename
            remaining_players.remove(name)
            del remaining_gh[gh_slug]
            break

# ========================================
# 7. Report
# ========================================
used_headshots = len(filenames) - len(remaining_gh)
print(f"Matched: {len(lookup)} / {len(players)} players ({used_headshots} / {len(filenames)} headshots used)")
if remaining_gh:
    remaining_list = sorted(remaining_gh.values())
    print(f"Unmatched headshot files ({len(remaining_gh)}):")
    for b in remaining_list[:30]:
        print(f"  {b}")
    if len(remaining_list) > 30:
        print(f"  ... and {len(remaining_list) - 30} more")

# ========================================
# 8. Write output
# ========================================
with open("player-headshots.json", "w", encoding="utf-8") as f:
    json.dump(lookup, f, indent=2, ensure_ascii=False)

print(f"\nWrote player-headshots.json with {len(lookup)} entries")
