#!/usr/bin/env python3
"""
Guards for the jobs that read the All-Time Database Google Sheet.

In Oct 2026 the sheet got close to Google's 10M-cell limit and its CSV export
started timing out, answering HTTP 400, or answering a short HTML error page in
place of the CSV. A run must then fail clearly and leave the committed data file
as it is, never replace it with an empty or partial one.

fetch_checked() wraps a script's own fetch function (the URL it reads is not
changed): any fetch error, an empty answer or an HTML page instead of a CSV is
retried, and if every attempt fails the run ends with a ::error:: line naming the
tab and the file that is being kept. check_data_file.py is the second line, run
by each workflow before it commits.

Why retries: the export is slow and erratic rather than dead. On Oct 28 2026 the
same Awards tab export failed with HTTP 400 after 241 s at 11:33 UTC and came back
fine (3.5 MB) in 100 s at 12:43 UTC. Each attempt waits up to READ_TIMEOUT.
"""

import sys
import time

MIN_LINES = 10   # every tab these jobs read has thousands of rows

# Google gives up on the export itself after ~240 s ("unable to open the file", HTTP 400),
# so waiting longer than that buys nothing. Good exports took 20-160 s in Oct 2026.
READ_TIMEOUT = 240
ATTEMPTS = 3
BACKOFF_SECONDS = (30, 90)   # wait before attempt 2 and attempt 3


def fail(label, output_path, message):
    print(f"::error::{label}: {message}. {output_path} is left as committed.")
    sys.exit(1)


def csv_problem(text):
    """Why text is not the tab's CSV, or None if it looks right."""
    if not text or not text.strip():
        return 'Google answered an empty file'
    head = text.lstrip()[:1000].lower()
    if head.startswith('<') or '<html' in head or '<!doctype' in head:
        return f'Google answered a web page ({len(text)} bytes), not the CSV'
    lines = text.count('\n') + 1
    if lines < MIN_LINES:
        return f'Google answered only {lines} lines'
    return None


def check_csv_text(text, label, output_path):
    """Exit 1 unless text looks like the tab's CSV."""
    problem = csv_problem(text)
    if problem:
        fail(label, output_path, problem)


def fetch_checked(label, output_path, fetch, *args, **kwargs):
    """Call the script's own fetch function, retrying ATTEMPTS times with backoff;
    exit 1 if every attempt fails or answers something that is not the CSV."""
    for attempt in range(1, ATTEMPTS + 1):
        started = time.monotonic()
        try:
            text = fetch(*args, **kwargs)
            problem = csv_problem(text)
        except Exception as e:   # timeouts, HTTP 400/5xx, connection errors
            problem = f'fetch failed: {type(e).__name__}: {e}'
        took = round(time.monotonic() - started)
        if not problem:
            print(f"{label}: attempt {attempt}/{ATTEMPTS} OK in {took} s")
            return text
        if attempt == ATTEMPTS:
            fail(label, output_path, f'{problem} (attempt {attempt}/{ATTEMPTS}, {took} s)')
        wait = BACKOFF_SECONDS[attempt - 1]
        print(f"::warning::{label}: attempt {attempt}/{ATTEMPTS} failed after {took} s: {problem}. "
              f"Retrying in {wait} s.")
        time.sleep(wait)
