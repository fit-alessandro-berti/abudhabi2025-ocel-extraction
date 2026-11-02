# Quality audit

The exported file passes the reproducible checks in `make reproduce`. Exact counts, hashes and measurements are recorded in [validation.json](validation.json); eight mutation/regression tests are in `tests/test_extraction.py`.

| Requirement | Evidence |
|---|---|
| Correct race and requested snapshot size | Every source row has session 9839 and meeting 1276. Counts: 20 drivers, 1,156 laps, 27 pits, 47 stints, 109 race-control messages, 154 weather records, 20 results, one session. |
| Complete source coverage | Every source row is matched to its expected event/object or result snapshot. Non-null fields are compared with the original response; original nulls must remain omitted. |
| OCEL structure and types | Strict locally authored JSON Schema profile, unique IDs/declarations, scalar types, valid timezone-bearing timestamps, qualified relationships, no dangling references or objects lacking event participation. |
| Lap/stint/pit consistency | Contiguous per-driver lap sequences and stint ranges; lap totals agree with all 20 results; each lap maps to exactly one stint; all 27 pits connect the correct outgoing/incoming stints and following out-laps. |
| Independent consumer | PM4Py 2.7.23.11 reads the compressed OCEL: 1,513 events, 1,281 objects, 6,847 E2O and 2,557 O2O relationships. Imported event values/timestamps, qualifiers and object values are checked. |
| Process-mining utility | PM4Py object-centric DFG discovery succeeds; RaceEntry flattening produces 20 traces and 1,370 rows. Descriptive strategy and notification analyses run against the exported OCEL. |
| Reproducibility | Source response and gzip SHA-256 checks; rebuilding from archived inputs yields identical gzip bytes. Dependency versions are pinned. |

## Source limitations retained

- One stationary pit duration is absent: Hülkenberg, lap 7. Its 21.6-second pit-lane duration is not substituted for it.
- Two lap sector-1 durations and 232 intermediate-1 speed observations are absent. Lap start times and full lap durations are present for every lap.
- Four lapped drivers have no result duration; their `+1 LAP` classification remains separate from numeric gaps.
- Driver country codes are absent for all 20 drivers; one profile image URL is absent.
- Ninety-three race-control rows lack structured driver numbers. Verified text mentions support links on 95 messages in total; global messages stay global.
- Forty deletion notices concern 39 laps. Duplicate targeting is preserved; it is not counted as 40 distinct deleted laps.

## Temporal review and changes to the initial model

Source inspection ruled out interpreting `pit.date` as pit entry or deriving an exit by adding the pit-lane duration. All 27 timestamps occur 19.649–27.288 seconds into the next out-lap. The final model uses “Pit stop recorded” with explicit timestamp-basis metadata.

Stint boundaries are inclusive lap ranges, not timestamps of tyre fitting. First-lap markers can precede pit observations. Norris's successive HARD stints are separate objects even though the compound stays the same.

Derived lap completion and the next approximate lap start differ by -0.971 to +1.052 seconds; 578 residuals are negative, and one has absolute magnitude above one second. No source timestamp is silently repaired. The 20 last-lap milestones share their timestamp with the corresponding lap completion; ties carry no causal order.

The snapshot includes final results without publication times. They are stored as final snapshot attributes with explicit provenance, rather than fabricated result-publication events. Weather and race control before the race and messages after racing are retained.

The independent-reader check exposed PM4Py's promotion of 86 first non-epoch attribute values to static attributes. This behavior is documented rather than hidden by adding invented initial values. Original JSON timestamps remain authoritative for as-of state analysis.

## Check scope

The official downloadable OCEL schema URLs returned 404, so validation uses a clearly identified local strict profile of the documented OCEL 2.0 JSON structure plus semantic checks and an independent reader. This report does not claim official-schema certification. The checks establish internal consistency and source fidelity, not that every upstream observation is physically exact or that descriptive strategy differences are causal.
