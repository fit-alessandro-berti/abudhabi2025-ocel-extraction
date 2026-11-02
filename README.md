# 2025 Abu Dhabi Grand Prix — OCEL 2.0

A reproducible object-centric event log extracted from the public [OpenF1 API](https://openf1.org/docs/), race session **9839**, meeting **1276**, held on **7 December 2025** at Yas Marina. The archived API responses were retrieved on **2 November 2026**.

**Dataset:** [abudhabi-2025-race.ocel.json.gz](data/ocel/abudhabi-2025-race.ocel.json.gz) — **1,513 events, 1,281 objects, 21 event types, seven object types**. Gzip-compressed OCEL 2.0 JSON, with qualified event-to-object and object-to-object relationships and timed object attributes.

**Zenodo:** copy the title and description from [metadata/ZENODO.md](metadata/ZENODO.md). The corresponding [metadata/zenodo.json](metadata/zenodo.json) contains the descriptive fields; no deposit has been created. Upload the actual `.json.gz` file after `git lfs pull`, not the small Git LFS pointer shown in Git's object database. Include [MODEL.md](MODEL.md), [reports/QUALITY.md](reports/QUALITY.md), and [reports/INSIGHTS.md](reports/INSIGHTS.md) as companion documentation. The source snapshot and scripts may also be included for reproducibility.

| Source table | Records | Representation |
|---|---:|---|
| Drivers | 20 | Driver objects and race entries, associated with 10 teams |
| Laps | 1,156 | Lap objects and approximate completion events |
| Pit stops | 27 | PitStop objects and recorded-stop events |
| Tyre stints | 47 | TyreStint objects and first-lap-start markers |
| Race control | 109 | Timestamped, classified messages; explicit driver/lap links |
| Weather | 154 | Weather events and timed session attributes |
| Session results | 20 | Untimed final-result attributes on race entries |
| Session | 1 | RaceSession context object |

The 1,513 events include **20 derived last-recorded-lap markers** in addition to the lap-completion events. They do not represent additional observed laps. All input rows are accounted for. Null values remain absent in the OCEL; the raw snapshot preserves the original JSON nulls.

## Process-mining use

Start with **RaceEntry** as the leading object type. The [analysis report](reports/INSIGHTS.md) demonstrates five compound-sequence variants, 13 one-stop and seven two-stop strategies, pit-duration summaries, and delayed race-control notifications. It includes a tyre-strategy chart, 20 reproducible driver traces and an object-centric directly-follows discovery check with PM4Py. Distinct tyre stints remain separate even when the compound does not change.

Read [MODEL.md](MODEL.md) before performance or state analysis. Lap timestamps are approximate. A pit timestamp identifies an API observation with an unspecified physical phase; **pit-lane duration and stationary stop duration are separate measures**. Results are retrospective snapshots. Global weather and messages are linked to the session rather than copied onto every driver. Use qualified relationships and timed attributes to avoid conflating context with participation.

## Reproduce offline

Git LFS is configured for compressed source and OCEL files. It was initialized in this repository with `git lfs install --local`; new clones must install Git LFS and retrieve its objects:

```bash
git lfs install --local
git lfs pull
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-lock.txt
make reproduce
sha256sum -c SHA256SUMS
```

The release was tested with Python 3.13.5 and PM4Py 2.7.23.11. Dependency installation needs network access; extraction, validation and analysis use only the checked-in snapshot. `make reproduce` stops on a failed check and recreates the log, reports, chart, release manifest and checksums. The log is byte-reproducible in the pinned environment; gzip headers have a zero modification time. Run without Python's `-O` flag because integrity checks use assertions.

```python
import pm4py
ocel = pm4py.read_ocel2_json("data/ocel/abudhabi-2025-race.ocel.json.gz")
model = pm4py.discover_ocdfg(ocel)
driver_traces = pm4py.ocel_flattening(ocel, "RaceEntry")
```

Readers without gzip support can decompress with `gzip -dk data/ocel/abudhabi-2025-race.ocel.json.gz` and import the resulting JSON. PM4Py promotes the first value of each object attribute to its static table; use the original JSON for time-aware state analysis, especially deletion observations and final results.

## Audit and provenance

- [Source manifest](data/raw/manifest.json): exact query URLs, retrieval timestamps, record counts, and compressed/uncompressed response hashes.
- [Model and mapping](MODEL.md): object identities, activity derivation, qualifiers, timestamp and missing-data rules.
- [Quality report](reports/QUALITY.md) and [machine-readable validation](reports/validation.json): source reconciliation, temporal checks, strict JSON-profile validation, independent PM4Py import and regression tests.
- [Release manifest](data/ocel/manifest.json) and [checksums](SHA256SUMS): output counts and file integrity.
- [Source attribution and licensing](SOURCES.md): provider, specification and code/data distinction.

`make fetch` verifies and reuses the existing snapshot; it never silently refreshes it. To inspect a new API snapshot, use `python3 scripts/fetch_sources.py --output /tmp/openf1-new-snapshot`. The validator deliberately requires the counts and semantics of this published snapshot; a changed upstream response needs a reviewed new release.

Repository code uses the existing [GPL-3.0 license](LICENSE). Data attribution and the provider's separate license notice are recorded in [SOURCES.md](SOURCES.md).
