# WTF: Weekly Underlying Gate Trace

## Problem

The weekly options screen already filters symbols through discovery, stock context, expiry selection, and contract quality, but the output does not preserve that reasoning as a first-class trace. Users can see the shortlist and skip list, yet still have to infer where each symbol fell out.

## User Or Operator

The operator is the solo researcher reviewing weekly options artifacts, debugging screen behavior, or syncing the run into Notion.

## Why Now

The weekly screen is already the primary teaching artifact in this repository. Adding gate trace now makes the existing workflow easier to trust, debug, and document without changing the screening rules.

## Evidence

- `weekly_options_screener.py` already contains distinct gate stages.
- HTML, JSON, and Notion outputs currently summarize the run but do not provide a stable per-symbol gate trail.
- The repo now treats the weekly screen as a product workflow rather than a loose experiment.

## Success Signal

Every symbol in a weekly run can be explained through a machine-readable gate trail and a human-readable summary in the weekly HTML and run-level Notion page.
