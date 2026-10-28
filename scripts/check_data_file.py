#!/usr/bin/env python3
"""
Refuses a data file that is worse than the committed one. Each Google Sheets
workflow runs this after its update script and before it commits, so a run
that went wrong fails here and the committed file stays as it is.

    python scripts/check_data_file.py rsStats.json

Fails (exit 1, with a ::error:: line) when the new file is missing, is not a
JSON list, is empty, or has fewer than MIN_RATIO of the committed file's
records. An unchanged file passes.
"""

import json
import subprocess
import sys

MIN_RATIO = 0.9


def fail(path, message):
    print(f"::error::{path}: {message}. Not committing; {path} is left as committed.")
    sys.exit(1)


def main():
    if len(sys.argv) != 2:
        sys.exit('usage: check_data_file.py <file.json>')
    path = sys.argv[1]
    try:
        with open(path, encoding='utf-8') as f:
            new = json.load(f)
    except (OSError, ValueError) as e:
        fail(path, f'cannot read the new file ({type(e).__name__}: {e})')
    if not isinstance(new, list):
        fail(path, f'the new file is a {type(new).__name__}, not a list of records')
    if not new:
        fail(path, 'the new file has no records')

    try:
        old_text = subprocess.run(['git', 'show', f'HEAD:{path}'], capture_output=True,
                                  text=True, encoding='utf-8', check=True).stdout
        old = json.loads(old_text)
    except (subprocess.CalledProcessError, ValueError):
        print(f"{path}: no committed copy to compare with; {len(new)} records")
        return
    old_n = len(old) if isinstance(old, list) else 0
    print(f"{path}: {len(new)} records (committed: {old_n})")
    if old_n and len(new) < old_n * MIN_RATIO:
        fail(path, f'would shrink from {old_n} to {len(new)} records, '
                   f'more than {round((1 - MIN_RATIO) * 100)}% fewer')


if __name__ == '__main__':
    main()
