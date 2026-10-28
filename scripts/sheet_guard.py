#!/usr/bin/env python3
"""
Guards for the jobs that read the All-Time Database Google Sheet.

In Oct 2026 the sheet got close to Google's 10M-cell limit and its CSV export
started timing out, answering HTTP 400, or answering a short HTML error page in
place of the CSV. A run must then fail clearly and leave the committed data file
as it is, never replace it with an empty or partial one.

fetch_checked() wraps a script's own fetch function (the URL it reads is not
changed): any fetch error, an empty answer or an HTML page instead of a CSV ends
the run with a ::error:: line naming the tab and the file that is being kept.
check_data_file.py is the second line, run by each workflow before it commits.
"""

import sys

MIN_LINES = 10   # every tab these jobs read has thousands of rows


def fail(label, output_path, message):
    print(f"::error::{label}: {message}. {output_path} is left as committed.")
    sys.exit(1)


def check_csv_text(text, label, output_path):
    """Exit 1 unless text looks like the tab's CSV."""
    if not text or not text.strip():
        fail(label, output_path, 'Google answered an empty file')
    head = text.lstrip()[:1000].lower()
    if head.startswith('<') or '<html' in head or '<!doctype' in head:
        fail(label, output_path, f'Google answered a web page ({len(text)} bytes), not the CSV')
    lines = text.count('\n') + 1
    if lines < MIN_LINES:
        fail(label, output_path, f'Google answered only {lines} lines')


def fetch_checked(label, output_path, fetch, *args, **kwargs):
    """Call the script's own fetch function; exit 1 on any failure or a non-CSV answer."""
    try:
        text = fetch(*args, **kwargs)
    except Exception as e:   # timeouts, HTTP 400/5xx, connection errors
        fail(label, output_path, f'fetch failed: {type(e).__name__}: {e}')
    check_csv_text(text, label, output_path)
    return text
