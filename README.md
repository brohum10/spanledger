# SpanLedger

[![Checks](https://github.com/brohum10/spanledger/actions/workflows/ci.yml/badge.svg)](https://github.com/brohum10/spanledger/actions/workflows/ci.yml)

**Find where trace time goes without counting parallel work twice.**

SpanLedger is a local, dependency-free Python CLI for nested application spans. It calculates inclusive duration, direct-child interval union, exclusive/self duration, overlapping child time, per-service activity, and uncovered gaps within the trace window.

## Why overlap matters

A 100 ms request has two children: inventory runs from 10–70 ms and payment from 40–90 ms. Subtracting both durations gives a nonsense **−10 ms** self time. Their union is 10–90 ms, so the correct interval-based self time is **20 ms**. The included checkout trace demonstrates this case and a nested database call.

## Run

Python 3.11+; no API key or external service.

```sh
python3 spanledger.py examples/checkout.json
python3 -m unittest discover -s tests -v
```

Optional installation:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install .
.venv/bin/spanledger examples/checkout.json
```

Windows uses `.venv\Scripts\python.exe` and `.venv\Scripts\spanledger.exe`.

## Input contract

Input is a JSON array. Each span has `id`, `service`, `name`, `start_us`, and `end_us`; optional `parent` is another span ID or null. Timestamps must be nonnegative integer microseconds on one comparable clock. Intervals are half-open `[start_us, end_us)`. Zero-duration spans are valid. Multiple roots are allowed.

Duplicate IDs/JSON fields, unknown fields, missing parents, cycles, reversed intervals, and children outside their parent are rejected with exit code 2 and no partial report. Input order does not matter. This strict containment model intentionally rejects asynchronous children that outlive their parent and uncorrected clock skew.

## Architecture

`JSON → schema checks → parent validation/cycle detection → interval unions → deterministic JSON report`

The interval-union sweep sorts by start time and merges overlapping or touching ranges. Each span subtracts the union of **direct** children only, avoiding double subtraction of grandchildren. Parent-cycle detection is iterative so deeply nested input does not exhaust Python's recursion stack.

| Field | Meaning |
| --- | --- |
| `inclusive_us` | End minus start |
| `child_union_us` | Time covered by at least one direct child |
| `self_us` | Inclusive duration minus direct-child union |
| `child_overlap_us` | Sum of child durations minus their union; multiplicity-weighted excess, not simply time with overlap |
| `active_union_us` | Union of span intervals, globally or for a service |
| `sum_self_us` | Sum across service spans; may exceed wall time when spans run concurrently |
| `gaps` | Uncovered intervals between earliest start and latest end |

Rows are sorted by span ID and services by name. A parent spanning a wait still covers that time: a reported gap means **no recorded span covers it**, not CPU idle time. Self duration can include waits, uninstrumented work, and overhead; it is not CPU usage or exclusive ownership of a thread. Service unions overlap with one another and must not be summed as total latency.

## Tests and limits

The suite covers overlap, nesting, gaps, zero durations, input-order independence, service aggregation, malformed inputs, parent cycles, and a 2,000-level tree. A seeded **1,000-case** differential test compares interval union against an independent integer-time occupancy oracle. GitHub Actions checks Python 3.11 and 3.13 and smoke-tests the installed CLI.

This is an analysis utility, not an OpenTelemetry collector, critical-path solver, or causal bottleneck detector. It has no OTLP/Jaeger import yet, clock correction, sampling correction, or resource measurements. All data and output stay local; reports retain operation names and IDs, so sanitize before sharing.

Interval processing is O(n log n); the simple service aggregation scans rows per service, adding O(n × number of services). Memory is O(n). No production throughput or latency-improvement claims are made.

Next extensions: standardized trace import, per-service aggregation without repeated scans, optional event links for asynchronous tasks, and a timeline viewer that preserves these accounting definitions.

Built as a learning and portfolio project with AI assistance. MIT licensed.
