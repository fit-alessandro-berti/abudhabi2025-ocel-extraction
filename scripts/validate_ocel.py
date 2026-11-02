"""Fail-closed structural, source-fidelity, temporal and independent-reader checks."""
import gzip
import hashlib
import json
import math
import re
from collections import Counter, defaultdict
from datetime import timedelta

import jsonschema

from extract_ocel import ROOT, LOG_NAME, EPOCH, dt, build, encode, load_sources

EXPECTED = {"sessions": 1, "drivers": 20, "laps": 1156, "pit": 27, "stints": 47,
            "race_control": 109, "weather": 154, "session_result": 20}


def values(item, static=False):
    return {a["name"]: a["value"] for a in item["attributes"] if not static or a.get("time") == EPOCH}


def validate_structure(log):
    schema = json.loads((ROOT / "schemas/ocel20-extraction.schema.json").read_text())
    jsonschema.Draft7Validator(schema, format_checker=jsonschema.FormatChecker()).validate(log)
    objects = {o["id"]: o for o in log["objects"]}
    assert len(objects) == len(log["objects"]), "duplicate object ID"
    assert len({e["id"] for e in log["events"]}) == len(log["events"]), "duplicate event ID"
    assert not set(objects) & {e["id"] for e in log["events"]}, "overlapping ID domains"
    seen = set()
    for item_key, declaration_key in [("objects", "objectTypes"), ("events", "eventTypes")]:
        declarations = {t["name"]: {a["name"]: a["type"] for a in t["attributes"]} for t in log[declaration_key]}
        assert len(declarations) == len(log[declaration_key]), "duplicate type"
        for t in log[declaration_key]:
            assert len(declarations[t["name"]]) == len(t["attributes"]), "duplicate attribute declaration"
        for item in log[item_key]:
            fields = declarations[item["type"]]
            attr_keys = [(a["name"], a.get("time")) for a in item["attributes"]]
            assert len(attr_keys) == len(set(attr_keys)), "duplicate attribute/time"
            for a in item["attributes"]:
                kind, v = fields[a["name"]], a["value"]
                allowed = {"string": (str,), "time": (str,), "integer": (int,), "float": (float, int), "boolean": (bool,)}
                assert type(v) in allowed[kind], (item["id"], a)
                if isinstance(v, float):
                    assert math.isfinite(v)
                if kind == "time":
                    dt(v)
                if "time" in a:
                    dt(a["time"])
            if "time" in item:
                dt(item["time"])
            for r in item["relationships"]:
                assert r["objectId"] in objects, (item["id"], "dangling reference", r)
                assert r["objectId"] != item["id"], "self relationship"
                if item_key == "events":
                    seen.add(r["objectId"])
    assert seen == set(objects), "objects with no event participation"
    times = [dt(e["time"]) for e in log["events"]]
    assert times == sorted(times), "unsorted events"


def validate_fidelity(log, raw):
    assert {k: len(v) for k, v in raw.items()} == EXPECTED
    objects = {o["id"]: o for o in log["objects"]}
    indexed_events, indexed_objects = defaultdict(list), defaultdict(list)
    for e in log["events"]:
        a = values(e)
        indexed_events[a["source_endpoint"], a["source_row"]].append(e)
    for o in log["objects"]:
        a = values(o, static=True)
        if "source_endpoint" in a:
            indexed_objects[a["source_endpoint"], a["source_row"]].append(o)
    # No invented source indices or endpoint labels.
    for endpoint, index in set(indexed_events) | set(indexed_objects):
        assert endpoint in raw and 0 <= index < len(raw[endpoint])
    for endpoint, rows in raw.items():
        for index, row in enumerate(rows):
            assert row["session_key"] == 9839 and row["meeting_key"] == 1276
            ev, ob = indexed_events[endpoint, index], indexed_objects[endpoint, index]
            if endpoint in ("sessions", "drivers"):
                assert len(ob) == 1 and not ev
            elif endpoint in ("stints", "pit"):
                assert len(ob) == len(ev) == 1
            elif endpoint == "laps":
                assert len(ob) == 1 and sum(e["type"] == "Lap completed" for e in ev) == 1
                assert len(ev) in (1, 2)
            elif endpoint in ("race_control", "weather"):
                assert len(ev) == 1 and not ob
            elif endpoint == "session_result":
                assert not ev and not ob
                entry = objects[f"entry:9839:{row['driver_number']}"]
                a = values(entry, static=True)
                assert a["result_source_row"] == index
                assert a["result_source_endpoint"] == "session_result"
                for k, v in row.items():
                    if k in ("driver_number", "meeting_key", "session_key"):
                        continue
                    key = "result_" + k
                    if k == "gap_to_leader":
                        key = "result_gap_seconds" if isinstance(v, (int, float)) else "result_gap_laps_text"
                    assert (key not in a) if v is None else (a[key] == v), (key, v)
                continue
            for item in ob + [e for e in ev if e["type"] != "Last recorded lap completed"]:
                a = values(item, static="time" not in item)
                for k, v in row.items():
                    if v is None:
                        assert k not in a, (endpoint, index, "imputed null", k)
                    else:
                        expected = json.dumps(v, separators=(",", ":")) if isinstance(v, (dict, list)) else v
                        assert a[k] == expected, (endpoint, index, k)
    drivers = {r["driver_number"] for r in raw["drivers"]}
    assert len(drivers) == 20
    laps = {(r["driver_number"], r["lap_number"]): r for r in raw["laps"]}
    assert len(laps) == 1156
    assert len({(r["driver_number"], r["lap_number"]) for r in raw["pit"]}) == 27
    assert len({(r["driver_number"], r["stint_number"]) for r in raw["stints"]}) == 47
    assert len({r["driver_number"] for r in raw["session_result"]}) == 20
    assert {r["position"] for r in raw["session_result"]} == set(range(1, 21))
    residuals, pit_offsets = [], []
    for r in raw["session_result"]:
        d = r["driver_number"]
        assert sorted(n for dd, n in laps if dd == d) == list(range(1, r["number_of_laps"] + 1))
        ss = sorted((s for s in raw["stints"] if s["driver_number"] == d), key=lambda s: s["stint_number"])
        assert [s["stint_number"] for s in ss] == list(range(1, len(ss) + 1))
        assert ss[0]["lap_start"] == 1 and ss[-1]["lap_end"] == r["number_of_laps"]
        assert all(a["lap_end"] + 1 == b["lap_start"] for a, b in zip(ss, ss[1:]))
    for index, lap in enumerate(raw["laps"]):
        d, n = lap["driver_number"], lap["lap_number"]
        assert d in drivers and lap["lap_duration"] > 0
        expected_time = dt(lap["date_start"]) + timedelta(seconds=lap["lap_duration"])
        matching = [s for s in raw["stints"] if s["driver_number"] == d and s["lap_start"] <= n <= s["lap_end"]]
        assert len(matching) == 1
        stint = matching[0]
        for e in indexed_events["laps", index]:
            assert dt(e["time"]) == expected_time
            assert {r["objectId"] for r in e["relationships"]} >= {
                f"entry:9839:{d}", f"lap:9839:{d}:{n}", f"stint:9839:{d}:{stint['stint_number']}"}
        a = values(next(e for e in indexed_events["laps", index] if e["type"] == "Lap completed"))
        assert a["compound"] == stint["compound"] and a["stint_number"] == stint["stint_number"]
        assert a["tyre_age_at_lap_start"] == stint["tyre_age_at_start"] + n - stint["lap_start"]
        assert a["is_pit_in_lap"] == any(p["driver_number"] == d and p["lap_number"] == n for p in raw["pit"])
        if (d, n + 1) in laps:
            residuals.append(round((dt(laps[d, n+1]["date_start"]) - expected_time).total_seconds(), 6))
    last_events = [e for e in log["events"] if e["type"] == "Last recorded lap completed"]
    assert len(last_events) == 20
    for e in last_events:
        a = values(e)
        lap = raw["laps"][a["source_row"]]
        assert a["lap_number"] == max(n for d, n in laps if d == lap["driver_number"])
    for i, s in enumerate(raw["stints"]):
        e = indexed_events["stints", i][0]
        assert dt(e["time"]) == dt(laps[s["driver_number"], s["lap_start"]]["date_start"])
        assert e["type"] == "Stint first lap started"
    for i, p in enumerate(raw["pit"]):
        d, n = p["driver_number"], p["lap_number"]
        e = indexed_events["pit", i][0]
        assert e["type"] == "Pit stop recorded" and dt(e["time"]) == dt(p["date"])
        assert p["lane_duration"] == p["pit_duration"] > 0
        if p["stop_duration"] is not None:
            assert 0 < p["stop_duration"] < p["lane_duration"]
        assert laps[d, n+1]["is_pit_out_lap"]
        for qualifier, boundary, value in [("outgoing_stint", "lap_end", n), ("incoming_stint", "lap_start", n+1)]:
            targets = [objects[r["objectId"]] for r in e["relationships"] if r["qualifier"] == qualifier]
            assert len(targets) == 1
            a = values(targets[0], static=True)
            assert a["driver_number"] == d and a[boundary] == value
        pit_offsets.append(round((dt(p["date"]) - dt(laps[d, n+1]["date_start"])).total_seconds(), 6))
    assert sum(x["is_pit_out_lap"] for x in raw["laps"]) == len(raw["pit"])
    # All explicit driver mentions, and only those mentions, receive entry relationships.
    for i, row in enumerate(raw["race_control"]):
        e = indexed_events["race_control", i][0]
        assert dt(e["time"]) == dt(row["date"])
        expected = {d["driver_number"] for d in raw["drivers"] if re.search(
            rf"(?<![\d:]){d['driver_number']} \({d['name_acronym']}\)", row["message"])}
        if row["driver_number"] is not None:
            expected.add(row["driver_number"])
        actual = {int(r["objectId"].split(":")[-1]) for r in e["relationships"] if r["objectId"].startswith("entry:")}
        assert actual == expected
        if "DELETED - TRACK LIMITS" in row["message"]:
            target = int(re.search(r"\bLAP (\d+)\b", row["message"])[1])
            assert len(expected) == 1
            assert [r["objectId"] for r in e["relationships"] if r["qualifier"] == "deleted_lap_time"] == [f"lap:9839:{next(iter(expected))}:{target}"]
    session = objects["session:9839"]
    for i, row in enumerate(raw["weather"]):
        assert dt(indexed_events["weather", i][0]["time"]) == dt(row["date"])
        for k in ("air_temperature", "track_temperature", "humidity", "pressure", "rainfall", "wind_speed", "wind_direction"):
            assert any(a["name"] == "weather_" + k and dt(a["time"]) == dt(row["date"]) and a["value"] == row[k] for a in session["attributes"])
    return {"raw_counts": EXPECTED, "lap_boundary_residual_seconds": {"min": min(residuals), "max": max(residuals),
            "absolute_over_one_second": sum(abs(x) > 1 for x in residuals), "negative": sum(x < 0 for x in residuals)},
            "pit_timestamp_seconds_after_next_lap_start": {"min": min(pit_offsets), "max": max(pit_offsets)},
            "source_nulls": {k: dict(Counter(field for r in rows for field, v in r.items() if v is None)) for k, rows in raw.items()}}


def independent_reader(log, path):
    import pm4py
    ocel = pm4py.read_ocel2_json(str(path))
    assert len(ocel.events) == len(log["events"])
    assert len(ocel.objects) == len(log["objects"])
    declaration_types = {t["name"]: {a["name"]: a["type"] for a in t["attributes"]}
                         for t in log["objectTypes"] + log["eventTypes"]}
    imported_events = ocel.events.set_index("ocel:eid")
    for e in log["events"]:
        imported = imported_events.loc[e["id"]]
        assert imported["ocel:activity"] == e["type"]
        assert imported["ocel:timestamp"] == dt(e["time"])
        for a in e["attributes"]:
            expected = dt(a["value"]) if declaration_types[e["type"]][a["name"]] == "time" else a["value"]
            assert imported[a["name"]] == expected, (e["id"], a["name"])
    expected_e2o = {(e["id"], r["objectId"], r["qualifier"]) for e in log["events"] for r in e["relationships"]}
    actual_e2o = set(ocel.relations[["ocel:eid", "ocel:oid", "ocel:qualifier"]].itertuples(index=False, name=None))
    assert actual_e2o == expected_e2o
    expected_o2o = {(o["id"], r["objectId"], r["qualifier"]) for o in log["objects"] for r in o["relationships"]}
    assert set(ocel.o2o[["ocel:oid", "ocel:oid_2", "ocel:qualifier"]].itertuples(index=False, name=None)) == expected_o2o
    model = pm4py.discover_ocdfg(ocel)
    edges = model["edges"]["total_objects"]
    assert edges["RaceEntry"]
    flattened = pm4py.ocel_flattening(ocel, "RaceEntry")
    assert flattened["case:concept:name"].nunique() == 20
    # PM4Py promotes the first value of EACH attribute to its static object table,
    # even when that first observation has a non-epoch timestamp. Audit this
    # explicitly instead of inventing initial values to fit the reader.
    expected_changes, promoted = {}, 0
    base = ocel.objects.set_index("ocel:oid")
    for obj in log["objects"]:
        seen = set()
        for a in obj["attributes"]:
            if a["name"] not in seen:
                expected = dt(a["value"]) if declaration_types[obj["type"]][a["name"]] == "time" else a["value"]
                assert base.loc[obj["id"], a["name"]] == expected, (obj["id"], a["name"])
                promoted += a["time"] != EPOCH
                seen.add(a["name"])
            else:
                expected_changes[obj["id"], a["name"], dt(a["time"])] = a["value"]
    actual_changes = {(r['ocel:oid'], r['ocel:field'], r['ocel:timestamp'].to_pydatetime()): r[r['ocel:field']]
                      for r in ocel.object_changes.to_dict("records")}
    assert actual_changes == expected_changes
    return {"pm4py_version": pm4py.__version__, "events": len(ocel.events), "objects": len(ocel.objects),
            "e2o_relations": len(expected_e2o), "o2o_relations": len(expected_o2o), "object_changes": len(ocel.object_changes),
            "first_non_epoch_values_promoted_to_static_by_pm4py": promoted,
            "reader_caveat": "PM4Py stores first attribute values in its static object table, losing their initial effective timestamps there; use original JSON for as-of state analysis.",
            "race_entry_traces": 20, "flattened_race_entry_rows": len(flattened),
            "ocdfg_distinct_edges_by_object_type": {k: len(v) for k, v in sorted(edges.items())}}


def main():
    path = ROOT / "data/ocel" / LOG_NAME
    data = path.read_bytes()
    log = json.loads(gzip.decompress(data))
    raw = load_sources()
    validate_structure(log)
    report = validate_fidelity(log, raw)
    report["independent_reader"] = independent_reader(log, path)
    assert data == encode(build(raw)), "non-reproducible export"
    report.update({"status": "passed", "log_file": str(path.relative_to(ROOT)), "sha256_gzip": hashlib.sha256(data).hexdigest(),
                   "sha256_json": hashlib.sha256(gzip.decompress(data)).hexdigest(),
                   "byte_reproducible": True, "schema": "locally authored strict OCEL 2.0 profile; not official schema",
                   "event_types": dict(sorted(Counter(e["type"] for e in log["events"]).items())),
                   "object_types": dict(sorted(Counter(o["type"] for o in log["objects"]).items()))})
    (ROOT / "reports/validation.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
