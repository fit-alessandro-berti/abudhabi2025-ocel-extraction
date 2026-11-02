# Extraction model and data dictionary

This is a retrospective, single-race OCEL 2.0 extraction. It preserves the complete eight-endpoint OpenF1 snapshot, including pre-race weather and race-control messages and post-race messages. It does not crop data to the session's scheduled start/end fields. The exact event range is reported in the release manifest. No telemetry, positions, starting grid, overtakes or team-radio data were requested or added.

## Objects and identities

| Type | Count | ID pattern | Meaning |
|---|---:|---|---|
| RaceSession | 1 | `session:9839` | Race-level context and weather observations |
| Team | 10 | `team:9839:<slug>` | Distinct source team names in this session |
| Driver | 20 | `driver:9839:<number>` | Source driver profile, scoped to this race |
| RaceEntry | 20 | `entry:9839:<number>` | A driver's participation; recommended leading object |
| Lap | 1,156 | `lap:9839:<number>:<lap>` | One driver's numbered lap |
| TyreStint | 47 | `stint:9839:<number>:<stint>` | Source stint with inclusive lap range |
| PitStop | 27 | `pit:9839:<number>:<reported-lap>` | One reported pit observation |

Driver numbers and teams are scoped to this session, not asserted to be globally permanent identities. A stint is not a uniquely identified physical tyre set; no tyre serial numbers are available. The same compound can occur in successive stints (Norris: HARD → HARD), which must not be merged.

Object-to-object relationships preserve entry/session, entry/driver, entry/team, driver/team, team/session, lap/entry, lap/stint, stint/entry, and pit/entry/lap/outgoing-stint/incoming-stint connections. These are directed and are not redundantly mirrored. All 1,281 objects participate in at least one event.

## Event mapping

| Activity family | Count | Timestamp | Principal relations |
|---|---:|---|---|
| Lap completed | 1,156 | `laps.date_start + lap_duration` | Entry, driver, team, lap, lap-range stint |
| Last recorded lap completed | 20 | Same derived time as that driver's final recorded lap | Same objects as final lap |
| Stint first lap started | 47 | `date_start` of the stint's first lap | Entry, driver, team, stint, first lap |
| Pit stop recorded | 27 | `pit.date`, unchanged in meaning | Entry, driver, team, pit, reported pit lap, outgoing and incoming stints |
| Weather sampled | 154 | `weather.date` | Session only |
| Race-control activities | 109 | `race_control.date` | Session, explicitly named entries/drivers, affected lap for deletion notices |

The twenty final-lap markers are derived process milestones, not result-publication events or additional laps. Consumers needing only measured lap completions can filter them out. No event is synthesized at the scheduled session end. Actual session-start/finish messages remain race-control events. A driver's final lap can finish after the session-finished message; the message is not used to truncate traces.

OpenF1 documents lap start times as approximate. Adding the reported duration therefore produces an **approximate completion time**; the values are not rounded, snapped to adjacent starts, or silently corrected. In this snapshot, next-lap-start minus derived previous completion ranges from -0.971 to +1.052 seconds. Small overlaps are source uncertainty, not evidence of physically overlapping laps. Tied timestamps have no prescribed causal order; sorting by ID gives deterministic serialization only.

A stint marker denotes the first lap in the API's stint range. It does **not** identify tyre installation or pit-lane exit. All pit timestamps lie 19.649–27.288 seconds after the following out-lap's start. The upstream [pit ingestor](https://github.com/br-g/openf1/blob/d5cab5c9bc673611f31f829422088f9e287f21da/src/openf1/services/ingestor_livetiming/core/processing/collections/pit.py) uses message/timing observations with multiple fallbacks. The model therefore calls this activity “Pit stop recorded” and does not construct entry/exit events by adding or subtracting durations.

## Race-control interpretation

The original text, category, flag, scope, lap number and other non-null fields are preserved. A deterministic ordered phrase classifier produces these activities:

1. `PENALTY SERVED` → Penalty served reported.
2. `TIME PENALTY FOR` → Time penalty announced.
3. `DELETED - TRACK LIMITS` → Lap time deleted.
4. `NO FURTHER` → Investigation closed.
5. `UNDER INVESTIGATION` → Investigation opened.
6. `NOTED` → Incident noted.
7. Otherwise: session-status message, explicit flag, DRS category, or Race control message.

These labels classify notifications. They do not establish unique incident identities, assign blame to every named driver, or measure physical incident/penalty-service times. Twenty-five messages name multiple drivers; they share one event. No incident objects or inferred case matching are introduced.

Structured `driver_number` fields create `structured_subject` relationships. Explicit number/acronym pairs in message text, verified against driver records, create `mentioned_in_message` relationships. The parser excludes clock fragments such as `17:29:27 (PIT)`; bare numbers are never used to infer drivers. Ninety-five of 109 messages have entry links. Track-wide messages remain session context without invented driver participation.

For deletion notices only, the driver and explicit `LAP n` text identify the affected Lap object via `deleted_lap_time`. The structured race-control `lap_number` is retained as source context and is **not** substituted for this referenced lap. Forty notices affect 39 unique laps, including two notices for Leclerc lap 52. Both notices are retained; a timed `timing_deletion_reported=true` observation is attached to the lap at each message time. No false initial value is assumed, and no lap record is removed from the OCEL.

## Attributes, types and units

Source rows are copied as attributes wherever they have a direct event/object representation. `source_endpoint` and zero-based `source_row` identify the exact row in the archived, hash-verified API response; `source_session_key` is 9839. Stable source-index IDs for weather/control messages preserve repeated observations. Static Team identity is derived from driver profiles. RaceEntry result provenance uses `result_source_endpoint` and `result_source_row`.

The OCEL declares boolean, integer, float, string and time types. Source `date`, `date_start` and `date_end` attributes have type `time`; OCEL event and object-change timestamps are normalized to UTC. Mini-sector arrays are retained as JSON-encoded strings because OCEL attributes are scalar; parse these with `json.loads` when needed. `mentioned_driver_numbers_json` is likewise JSON text. Original values and arrays remain available unmodified in the raw files.

| Attribute | Unit / interpretation |
|---|---|
| `lap_duration`, `duration_sector_1/2/3` | Seconds |
| `lane_duration`, deprecated `pit_duration` | Seconds in pit lane; equal in this snapshot |
| `stop_duration` | Stationary seconds; one missing value remains absent |
| `i1_speed`, `i2_speed`, `st_speed` | km/h |
| `is_pit_in_lap` | Derived by matching driver's reported pit lap |
| `is_pit_out_lap` | Source boolean; all 27 correspond to the lap after a pit |
| `tyre_age_at_lap_start` | `tyre_age_at_start + lap_number - lap_start`, in laps |
| `compound`, `stint_number` on lap events/objects | Derived from the unique inclusive stint range |
| Weather temperature | °C |
| Weather pressure / humidity / wind | mbar / percent / m/s; direction in degrees |
| `rainfall` | Source rainfall indicator (0 in all 154 samples), not measured rainfall depth |
| `result_duration`, `result_gap_seconds` | Reported seconds; gaps for lapped drivers use `result_gap_laps_text` |
| `result_position`, `result_number_of_laps`, `result_points`, `result_dnf/dns/dsq` | Final source classification fields |

Static descriptive/snapshot attributes use the OCEL epoch convention, `1970-01-01T00:00:00Z`. This is a sentinel, **not** an observation time or a claim that final results were known before the race. In particular, final positions, durations, points and penalties must not be used as predictive pre-race features. There are no fabricated result events because the source has no publication timestamp.

Timed attributes carry actual observation/derivation times: seven `weather_*` attributes on RaceSession; `lap_range_compound` and `lap_range_stint_number` on RaceEntry at each first-lap marker; and lap-deletion observations. The `lap_range_*` names distinguish range classification from the unknown physical tyre-change instant. They do not track tyre installation state.

All source nulls are omitted from OCEL attribute lists rather than replaced by zero, false, “unknown,” or interpolated values. All raw rows and nulls remain in the archived responses. Missing result durations for four lapped drivers are not reconstructed. Snapshot fields on Lap and PitStop objects are retrospective descriptors; the corresponding event timestamps govern when to place the process observation.

## Validation and interpretation limits

The strict local JSON profile in `schemas/ocel20-extraction.schema.json` follows the [OCEL JSON specification](https://www.ocel-standard.org/specification/formats/json/). It is not the official downloadable schema: both official schema URLs tried during preparation returned 404. Semantic checks separately enforce typed values, declared names, uniqueness, referential integrity, source coverage, temporal arithmetic and boundary relations. PM4Py imports the actual gzip file and independently verifies event values, timestamps, qualified E2O/O2O relations, base object values and subsequent changes.

PM4Py 2.7.23.11 moves each attribute's first value into its static object table, even if its first timestamp is later than the epoch. In this log that affects 86 first observations. All 1,212 non-epoch attribute observations remain in the OCEL JSON; PM4Py exposes 1,126 subsequent changes. Use the original JSON for as-of queries requiring the first observation time.

The dataset supports descriptive object-centric discovery, strategy variants, lap/stint performance summaries, and notification workflows. It cannot establish causal strategy advantage, physical pit-entry/exit times, precise infringement times or effects of unobserved telemetry. `Team` contains concurrent driver processes; `RaceSession` is shared context. Flattening either as one sequential case can create artificial directly-follows relations. Source message delays, approximate lap clocks, snapshot attributes and equal timestamps should be considered before conformance or predictive analysis.
