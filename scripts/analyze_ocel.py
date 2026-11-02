"""Reproducible descriptive process-mining analyses computed from the exported OCEL."""
import gzip
import hashlib
import json
from collections import Counter, defaultdict
from statistics import median

from extract_ocel import ROOT, LOG_NAME, dt
from validate_ocel import values


def summary(numbers):
    return {"n": len(numbers), "min": min(numbers), "median": median(numbers), "max": max(numbers)} if numbers else {"n": 0}


def main():
    path = ROOT / "data/ocel" / LOG_NAME
    log = json.loads(gzip.decompress(path.read_bytes()))
    objects = {o["id"]: o for o in log["objects"]}
    events = log["events"]
    by_type = defaultdict(list)
    for e in events:
        by_type[e["type"]].append(e)
    deleted = {r["objectId"] for e in by_type["Lap time deleted"] for r in e["relationships"] if r["qualifier"] == "deleted_lap_time"}
    rows, by_compound = [], defaultdict(list)
    for entry in sorted((o for o in objects.values() if o["type"] == "RaceEntry"), key=lambda o: values(o)["result_position"]):
        a = values(entry)
        number = a["driver_number"]
        driver = values(objects[f"driver:9839:{number}"])
        stints = sorted([values(o) for o in objects.values() if o["type"] == "TyreStint" and values(o)["driver_number"] == number], key=lambda x: x["stint_number"])
        pits = [values(e) for e in by_type["Pit stop recorded"] if values(e)["driver_number"] == number]
        laps = [values(e) for e in by_type["Lap completed"] if values(e)["driver_number"] == number]
        clean = [l for l in laps if l["lap_number"] > 1 and not l["is_pit_in_lap"] and not l["is_pit_out_lap"] and f"lap:9839:{number}:{l['lap_number']}" not in deleted]
        for lap in clean:
            by_compound[lap["compound"]].append(lap["lap_duration"])
        rows.append({"driver_number": number, "driver": driver["name_acronym"], "team": driver["team_name"],
            "result_position": a["result_position"], "laps": len(laps), "pit_stops": len(pits),
            "strategy": " → ".join(s["compound"] for s in stints),
            "stints": [{k: s[k] for k in ("stint_number", "compound", "lap_start", "lap_end", "tyre_age_at_start")} for s in stints],
            "pit_laps": [p["lap_number"] for p in pits], "lane_seconds_total": round(sum(p["lane_duration"] for p in pits), 3),
            "stationary_seconds_observed": [p["stop_duration"] for p in pits if "stop_duration" in p],
            "clean_lap_seconds": summary([l["lap_duration"] for l in clean])})
    traces = defaultdict(list)
    for e in events:
        for r in e["relationships"]:
            if objects[r["objectId"]]["type"] == "RaceEntry":
                traces[r["objectId"]].append(e)
    edges = Counter()
    # Exclude equal-time event pairs: the stable serialization order is not causality.
    tied_pairs = 0
    for trace in traces.values():
        for first, second in zip(trace, trace[1:]):
            if first["time"] == second["time"]:
                tied_pairs += 1
            else:
                edges[first["type"], second["type"]] += 1
    rc = [e for e in events if values(e)["source_endpoint"] == "race_control"]
    multi = [e for e in rc if sum(r["objectId"].startswith("entry:") for r in e["relationships"]) > 1]
    completed = {r["objectId"]: e for e in by_type["Lap completed"] for r in e["relationships"] if r["qualifier"] == "completed_lap"}
    delays = []
    for e in by_type["Lap time deleted"]:
        target = next(r["objectId"] for r in e["relationships"] if r["qualifier"] == "deleted_lap_time")
        delays.append((dt(e["time"]) - dt(completed[target]["time"])).total_seconds())
    weather = [values(e) for e in by_type["Weather sampled"]]
    report = {
        "log_sha256": hashlib.sha256(path.read_bytes()).hexdigest(), "drivers": rows,
        "strategy_variants": dict(Counter(r["strategy"] for r in rows)),
        "pit_stop_count_variants": dict(sorted(Counter(r["pit_stops"] for r in rows).items())),
        "pit_lane_seconds": summary([values(e)["lane_duration"] for e in by_type["Pit stop recorded"]]),
        "stationary_stop_seconds": summary([values(e)["stop_duration"] for e in by_type["Pit stop recorded"] if "stop_duration" in values(e)]),
        "filtered_lap_seconds_by_compound": {k: summary(v) for k, v in sorted(by_compound.items())},
        "lap_filter": "Exclude first lap, pit-in, pit-out, and every lap with a time-deletion notification anywhere in the snapshot. Retrospective descriptive filter, not causal or an online feature.",
        "lap_deletion_notifications": len(by_type["Lap time deleted"]), "distinct_deleted_laps": len(deleted),
        "deletion_notification_delay_seconds": summary(delays),
        "multi_driver_control_messages": len(multi),
        "race_control_messages_with_entry_link": sum(any(r["objectId"].startswith("entry:") for r in e["relationships"]) for e in rc),
        "time_penalties_announced": len(by_type["Time penalty announced"]), "penalty_served_notifications": len(by_type["Penalty served reported"]),
        "weather_samples": len(weather), "rainfall_values": sorted({w["rainfall"] for w in weather}),
        "track_temperature_celsius": summary([w["track_temperature"] for w in weather]),
        "race_entry_dfg_excluding_equal_timestamp_pairs": [{"from": a, "to": b, "count": c} for (a, b), c in edges.most_common()],
        "equal_timestamp_adjacent_pairs_excluded": tied_pairs,
    }
    (ROOT / "reports/insights.json").write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n")
    (ROOT / "reports/race-entry-traces.json").write_text(json.dumps({k: [e["id"] for e in v] for k, v in sorted(traces.items())}, indent=2) + "\n")
    text = ["# Process-mining findings", "", "Computed from the exported OCEL by `scripts/analyze_ocel.py`; see `insights.json` for exact values and `race-entry-traces.json` for the 20 event-ID traces.", "",
        f"The {len(rows)} drivers used {len(report['strategy_variants'])} compound-sequence variants. Thirteen drivers made one stop and seven made two. Norris's MEDIUM → HARD → HARD sequence retains two distinct hard-tyre stints; a compound-only state model would hide the second stop.", "",
        "| Strategy | Drivers |", "|---|---:|"]
    text += [f"| {k} | {v} |" for k, v in report["strategy_variants"].items()]
    lane, stop = report["pit_lane_seconds"], report["stationary_stop_seconds"]
    text += ["", f"Pit-lane duration across {lane['n']} observations: median {lane['median']:.3f} s, range {lane['min']:.3f}–{lane['max']:.3f} s. Stationary duration across {stop['n']} observations: median {stop['median']:.3f} s, range {stop['min']:.3f}–{stop['max']:.3f} s. The missing stationary duration (Hülkenberg, lap 7) stays missing. Pit-lane duration is not counterfactual race-time loss.", "",
        f"There are {len(deleted)} distinct deleted lap times in {report['lap_deletion_notifications']} notifications, {len(multi)} messages mentioning multiple drivers, six announced time penalties and two later 'penalty served' notifications. These are message timestamps, not the physical times of the underlying infringements or penalty service. The two Leclerc lap-52 deletion messages refer to the same lap and remain distinct notifications.", "",
        f"The OCEL exposes {report['race_control_messages_with_entry_link']} race-control messages on individual driver traces. The other messages remain session context. Global weather and flags are not copied onto all 20 drivers, avoiding artificial synchronization in the driver process model.", "",
        "| Finish | Driver | Strategy | Pit laps | Filtered laps | Median filtered lap (s) |",
        "|---:|---|---|---|---:|---:|"]
    for r in rows:
        text.append(f"| {r['result_position']} | {r['driver']} | {r['strategy']} | {', '.join(map(str, r['pit_laps']))} | {r['clean_lap_seconds']['n']} | {r['clean_lap_seconds']['median']:.3f} |")
    text += ["", "![Tyre strategies by classified position](strategy.png)", "",
        "Lap summaries exclude lap 1, pit-in laps, pit-out laps and retrospectively deleted times. Compound comparisons remain confounded by driver, fuel load, traffic, tyre age and race phase; these data do not prove an optimal strategy or a causal tyre effect. All drivers finished; this single race has no observed retirement pathway.", "",
        "For process discovery, select `RaceEntry` as the leading object type. `TyreStint` exposes lap progression and transitions; `Team` exposes two concurrent entries and should not be flattened as one sequential case. Pit events qualify outgoing and incoming stints, even when compounds match. `Lap` supports linking delayed deletion notifications to the affected lap.", "",
        "The PM4Py object-centric directly-follows graph and 20 flattened entry traces were computed successfully. The JSON report also provides a directly-follows summary excluding adjacent equal-timestamp pairs. Equal timestamps have no defined causal order; approximate lap-boundary timestamps may interleave with first-lap stint markers.", "",
        "For as-of state analysis, read the timed attributes in the OCEL JSON directly. PM4Py promotes the first value of each object attribute to its static table, including future deletion observations and final-result snapshots. Do not use those static values as pre-race prediction features.", ""]
    (ROOT / "reports/INSIGHTS.md").write_text("\n".join(text))
    plot(rows)
    print(json.dumps({k: v for k, v in report.items() if k not in ("drivers", "race_entry_dfg_excluding_equal_timestamp_pairs")}, indent=2, ensure_ascii=False))


def plot(rows):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import Patch
    colors = {"SOFT": "#d83b44", "MEDIUM": "#e2bb36", "HARD": "#c2cbd4"}
    fig, ax = plt.subplots(figsize=(11, 7))
    for y, row in enumerate(rows):
        for s in row["stints"]:
            ax.barh(y, s["lap_end"] - s["lap_start"] + 1, left=s["lap_start"] - 0.5, height=.7,
                    color=colors[s["compound"]], edgecolor="white", linewidth=1.5)
        for lap in row["pit_laps"]:
            ax.plot(lap + .5, y, marker="|", color="#182d41", markersize=13, markeredgewidth=2)
    ax.set_yticks(range(len(rows)), [f"{r['result_position']:>2}. {r['driver']}" for r in rows])
    ax.invert_yaxis()
    ax.set(xlim=(.5, 58.5), xlabel="Lap number (inclusive stint ranges)")
    fig.suptitle("2025 Abu Dhabi race · tyre strategies", y=.985)
    ax.set_xticks([1, 10, 20, 30, 40, 50, 58])
    fig.legend(handles=[Patch(facecolor=c, label=k.capitalize()) for k, c in colors.items()], loc="upper center", bbox_to_anchor=(.5, .95), ncol=3, frameon=False)
    ax.spines[["top", "right", "left"]].set_visible(False)
    fig.text(.01, .015, "Source: OpenF1 session 9839 · Black marks: reported pit laps · Rows ordered by final classification", fontsize=9, color="#45576b")
    fig.tight_layout(rect=(0, .035, 1, .91))
    fig.savefig(ROOT / "reports/strategy.png", dpi=150, metadata={"Software": "Matplotlib"})
    plt.close(fig)


if __name__ == "__main__":
    main()
