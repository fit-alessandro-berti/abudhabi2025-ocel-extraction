"""Deterministic OpenF1 snapshot -> OCEL 2.0; see MODEL.md for semantics."""
import argparse
import gzip
import hashlib
import json
import re
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EPOCH = "1970-01-01T00:00:00Z"
SESSION = "session:9839"
LOG_NAME = "abudhabi-2025-race.ocel.json.gz"


def dt(value):
    result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if result.tzinfo is None:
        raise ValueError(f"Naive timestamp: {value}")
    return result.astimezone(timezone.utc)


def iso(value):
    return (dt(value) if isinstance(value, str) else value).isoformat(timespec="microseconds").replace("+00:00", "Z")


def load_sources(directory=ROOT / "data/raw"):
    manifest = json.loads((directory / "manifest.json").read_text())
    result = {}
    for name, source in manifest["sources"].items():
        data = (directory / source["file"]).read_bytes()
        assert hashlib.sha256(data).hexdigest() == source["sha256_gzip"], name
        payload = gzip.decompress(data)
        assert hashlib.sha256(payload).hexdigest() == source["sha256_response"], name
        result[name] = json.loads(payload)
        assert len(result[name]) == source["records"], name
    return result


def rel(oid, qualifier):
    return {"objectId": oid, "qualifier": qualifier}


def oid(kind, driver, number=None):
    return f"{kind}:9839:{driver}" + (f":{number}" if number is not None else "")


def scalar(value):
    # OCEL scalar values only. Preserve arrays losslessly as JSON text.
    return json.dumps(value, separators=(",", ":")) if isinstance(value, (list, dict)) else value


def attrs(values, time=None):
    return [dict(name=k, value=scalar(v), **({"time": time} if time else {}))
            for k, v in sorted(values.items()) if v is not None]


def provenance(endpoint, index):
    return {"source_endpoint": endpoint, "source_row": index, "source_session_key": 9839}


def classify_control(row):
    message = row["message"]
    for phrase, activity in [
        ("PENALTY SERVED", "Penalty served reported"),
        ("TIME PENALTY FOR", "Time penalty announced"),
        ("DELETED - TRACK LIMITS", "Lap time deleted"),
        ("NO FURTHER", "Investigation closed"),
        ("UNDER INVESTIGATION", "Investigation opened"),
        ("NOTED", "Incident noted"),
    ]:
        if phrase in message:
            return activity
    if row["category"] == "SessionStatus":
        return "Session status: " + message
    if row.get("flag"):
        return "Flag: " + row["flag"]
    if row["category"] == "Drs":
        return "DRS status reported"
    return "Race control message"


def mentioned_drivers(row, drivers):
    """Only explicit number/acronym pairs; never infer drivers from bare numbers."""
    found = set()
    if row.get("driver_number") is not None:
        if row["driver_number"] not in drivers:
            raise ValueError("Unknown structured race-control driver")
        found.add(row["driver_number"])
    for number, acronym in re.findall(r"(?<![\d:])(\d{1,2}) \(([A-Z]{3})\)", row["message"]):
        number = int(number)
        if number not in drivers or drivers[number]["name_acronym"] != acronym:
            raise ValueError(f"Unresolved driver mention: {number} ({acronym})")
        found.add(number)
    return sorted(found)


def declarations(items):
    types = defaultdict(dict)
    for item in items:
        fields = types[item["type"]]
        for a in item["attributes"]:
            value = a["value"]
            t = {bool: "boolean", int: "integer", float: "float", str: "string"}[type(value)]
            if a["name"] in ("date", "date_start", "date_end"):
                dt(value)
                t = "time"
            if a["name"] in fields and fields[a["name"]] != t:
                if {fields[a["name"]], t} <= {"integer", "float"}:
                    t = "float"
                else:
                    raise ValueError(f"Mixed type {item['type']}.{a['name']}")
            fields[a["name"]] = t
    return [{"name": name, "attributes": [{"name": k, "type": v} for k, v in sorted(fields.items())]}
            for name, fields in sorted(types.items())]


def build(source):
    objects, events = {}, []

    def obj(key, kind, values, relationships=()):
        assert key not in objects, key
        objects[key] = {"id": key, "type": kind, "attributes": attrs(values, EPOCH),
                        "relationships": list(relationships)}

    def event(key, kind, time, values, relationships):
        events.append({"id": key, "type": kind, "time": iso(time),
                       "attributes": attrs(values), "relationships": list(relationships)})

    drivers = {r["driver_number"]: r for r in source["drivers"]}
    laps = {(r["driver_number"], r["lap_number"]): r for r in source["laps"]}
    stints = {(r["driver_number"], r["stint_number"]): r for r in source["stints"]}
    results = {r["driver_number"]: (i, r) for i, r in enumerate(source["session_result"])}
    teamids = {r["team_name"]: "team:9839:" + re.sub(r"[^a-z0-9]+", "-", r["team_name"].lower()).strip("-")
               for r in source["drivers"]}

    def driver_links(d):
        return [rel(oid("entry", d), "race_entry"), rel(oid("driver", d), "driver"),
                rel(teamids[drivers[d]["team_name"]], "team")]

    obj(SESSION, "RaceSession", {**source["sessions"][0], **provenance("sessions", 0)})
    for name, key in sorted(teamids.items()):
        obj(key, "Team", {"team_name": name, "identity_scope": "session:9839"}, [rel(SESSION, "participates_in")])
    for i, row in enumerate(source["drivers"]):
        d = row["driver_number"]
        obj(oid("driver", d), "Driver", {**row, **provenance("drivers", i)},
            [rel(teamids[row["team_name"]], "drives_for")])
        ri, result = results[d]
        # Final result is a retrospective snapshot, not an event at an invented time.
        result_values = {"result_" + k: v for k, v in result.items() if k not in ("meeting_key", "session_key", "driver_number", "gap_to_leader")}
        gap = result.get("gap_to_leader")
        result_values["result_gap_seconds" if isinstance(gap, (int, float)) else "result_gap_laps_text"] = gap
        obj(oid("entry", d), "RaceEntry", {"driver_number": d, "result_source_row": ri,
            "result_source_endpoint": "session_result", "result_timestamp_basis": "untimed_final_snapshot", **result_values},
            [rel(SESSION, "participates_in"), rel(oid("driver", d), "driven_by"), rel(teamids[row["team_name"]], "entered_by")])

    for i, row in enumerate(source["stints"]):
        d, n = row["driver_number"], row["stint_number"]
        sid = oid("stint", d, n)
        obj(sid, "TyreStint", {**row, **provenance("stints", i)}, [rel(oid("entry", d), "stint_of")])
        event("stint-first-lap:" + sid, "Stint first lap started", laps[d, row["lap_start"]]["date_start"],
              {**row, **provenance("stints", i), "timestamp_basis": "first_lap_date_start_approximate"},
              [*driver_links(d), rel(sid, "stint"), rel(oid("lap", d, row["lap_start"]), "first_lap")])
        objects[oid("entry", d)]["attributes"].extend(attrs({"lap_range_compound": row["compound"], "lap_range_stint_number": n},
                                                                iso(laps[d, row["lap_start"]]["date_start"])))

    pit_keys = {(r["driver_number"], r["lap_number"]) for r in source["pit"]}
    for i, row in enumerate(source["laps"]):
        d, n = row["driver_number"], row["lap_number"]
        matching = [s for (sd, _), s in stints.items() if sd == d and s["lap_start"] <= n <= s["lap_end"]]
        assert len(matching) == 1, (d, n, matching)
        stint = matching[0]
        sid, lid = oid("stint", d, stint["stint_number"]), oid("lap", d, n)
        derived = {"compound": stint["compound"], "stint_number": stint["stint_number"],
                   "is_pit_in_lap": (d, n) in pit_keys, "tyre_age_at_lap_start": stint["tyre_age_at_start"] + n - stint["lap_start"]}
        obj(lid, "Lap", {**row, **derived, **provenance("laps", i)},
            [rel(oid("entry", d), "lap_of"), rel(sid, "in_stint")])
        end = dt(row["date_start"]) + timedelta(seconds=row["lap_duration"])
        relationships = [*driver_links(d), rel(lid, "completed_lap"), rel(sid, "lap_range_stint")]
        event("lap-completed:" + lid, "Lap completed", end,
              {**row, **derived, **provenance("laps", i), "timestamp_basis": "lap_date_start_plus_duration_approximate"}, relationships)
        if n == results[d][1]["number_of_laps"]:
            event("last-lap:" + oid("entry", d), "Last recorded lap completed", end,
                  {"lap_number": n, **provenance("laps", i), "timestamp_basis": "lap_date_start_plus_duration_approximate"}, relationships)

    for i, row in enumerate(source["pit"]):
        d, n = row["driver_number"], row["lap_number"]
        before = [s for (sd, _), s in stints.items() if sd == d and s["lap_end"] == n]
        after = [s for (sd, _), s in stints.items() if sd == d and s["lap_start"] == n + 1]
        assert len(before) == len(after) == 1, row
        outgoing, incoming = oid("stint", d, before[0]["stint_number"]), oid("stint", d, after[0]["stint_number"])
        pid = oid("pit", d, n)
        relationships = [rel(oid("entry", d), "pit_of"), rel(outgoing, "outgoing_stint"), rel(incoming, "incoming_stint"), rel(oid("lap", d, n), "reported_pit_lap")]
        obj(pid, "PitStop", {**row, **provenance("pit", i)}, relationships)
        event("pit-recorded:" + pid, "Pit stop recorded", row["date"],
              {**row, **provenance("pit", i), "timestamp_basis": "api_pit_date_unspecified_phase", "outgoing_compound": before[0]["compound"], "incoming_compound": after[0]["compound"]},
              [*driver_links(d), rel(pid, "pit_stop"), *relationships[1:]])

    for i, row in enumerate(source["weather"]):
        event(f"weather:9839:{i:04}", "Weather sampled", row["date"],
              {**row, **provenance("weather", i), "timestamp_basis": "source_date"}, [rel(SESSION, "weather_context")])
        objects[SESSION]["attributes"].extend(attrs({"weather_" + k: row[k] for k in
            ("air_temperature", "track_temperature", "humidity", "pressure", "rainfall", "wind_speed", "wind_direction")}, iso(row["date"])))

    for i, row in enumerate(source["race_control"]):
        mentioned = mentioned_drivers(row, drivers)
        relationships = [rel(SESSION, "race_control_context")]
        for d in mentioned:
            qualifier = "structured_subject" if d == row.get("driver_number") else "mentioned_in_message"
            relationships.extend([rel(oid("entry", d), qualifier), rel(oid("driver", d), qualifier)])
        activity = classify_control(row)
        target_lap = None
        if activity == "Lap time deleted":
            match = re.search(r"\bLAP (\d+)\b", row["message"])
            assert match and len(mentioned) == 1, row
            target_lap = int(match[1])
            lid = oid("lap", mentioned[0], target_lap)
            assert lid in objects, row
            relationships.append(rel(lid, "deleted_lap_time"))
            # Repeated notifications remain distinct events and timed observations.
            change = attrs({"timing_deletion_reported": True}, iso(row["date"]))[0]
            objects[lid]["attributes"].append(change)
        event(f"race-control:9839:{i:04}", activity, row["date"],
              {**row, **provenance("race_control", i), "timestamp_basis": "source_message_date",
               "mentioned_driver_numbers_json": mentioned, "deleted_lap_number": target_lap}, relationships)

    objects = sorted(objects.values(), key=lambda o: o["id"])
    for o in objects:
        o["attributes"].sort(key=lambda a: (a["time"], a["name"]))
    events.sort(key=lambda e: (e["time"], e["id"]))
    return {"objectTypes": declarations(objects), "eventTypes": declarations(events), "objects": objects, "events": events}


def encode(log):
    return gzip.compress((json.dumps(log, ensure_ascii=False, separators=(",", ":"), allow_nan=False) + "\n").encode(), mtime=0)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw", type=Path, default=ROOT / "data/raw")
    parser.add_argument("--output", type=Path, default=ROOT / "data/ocel" / LOG_NAME)
    args = parser.parse_args()
    log = build(load_sources(args.raw))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(encode(log))
    print(f"{args.output}: {len(log['events'])} events, {len(log['objects'])} objects")


if __name__ == "__main__":
    main()
