#!/usr/bin/env python
"""Batch-1 dry run: Arbeitnow + VisaSponsor.jobs.

Fills matching job-application forms and screenshots them, but never clicks
submit. Review logs/digest_<date>.txt and logs/screenshots/*.png afterward;
data/applied.json is the running ledger (dedupes across runs by URL+company+title).

Usage:
    py run_dry_run.py [--limit N]
"""
import argparse
import sys

from src.dry_run import run

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=None, help="override the daily cap for this run")
    args = parser.parse_args()

    kwargs = {}
    if args.limit is not None:
        kwargs["limit"] = args.limit

    try:
        run(**kwargs)
    except KeyboardInterrupt:
        sys.exit(1)
