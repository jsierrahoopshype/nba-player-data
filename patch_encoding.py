"""
Adds an explicit UTF-8 response encoding to every update script in scripts/.

Why: none of them sets res.encoding after requests.get(), so requests guesses
the charset per response. When Google omits the charset header the guess is
latin-1 and every accented name gets mangled (Nene -> NenA~).

What it does: in each scripts/*.py, right after every line of the form
    <var>.raise_for_status()
inserts
    <var>.encoding = 'utf-8'
unless that line is already present. Idempotent -- safe to run twice.
Prints what it changed. Run from the nba-player-data repo root:

    python patch_encoding.py
"""
import glob
import re

PATTERN = re.compile(r'^(\s*)(\w+)\.raise_for_status\(\)\s*$')

changed = []
for path in sorted(glob.glob('scripts/*.py')):
    lines = open(path, encoding='utf-8').read().splitlines(keepends=True)
    out = []
    touched = False
    for i, line in enumerate(lines):
        out.append(line)
        m = PATTERN.match(line.rstrip('\r\n'))
        if not m:
            continue
        indent, var = m.group(1), m.group(2)
        enc_line = "%s%s.encoding = 'utf-8'" % (indent, var)
        nxt = lines[i + 1].rstrip('\r\n') if i + 1 < len(lines) else ''
        if nxt.strip() == enc_line.strip():
            continue  # already patched
        eol = '\r\n' if line.endswith('\r\n') else '\n'
        out.append(enc_line + eol)
        touched = True
    if touched:
        open(path, 'w', encoding='utf-8', newline='').write(''.join(out))
        changed.append(path)
        print('patched  ', path)
    else:
        print('unchanged', path)

print()
print('%d file(s) patched' % len(changed))
