"""Regression checks for observed source hazards and silent-corruption failure modes."""
import copy
import gzip
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from extract_ocel import ROOT, LOG_NAME, classify_control, mentioned_drivers
from validate_ocel import load_sources, validate_structure, validate_fidelity, values


class ExtractionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.log = json.loads(gzip.decompress((ROOT / "data/ocel" / LOG_NAME).read_bytes()))
        cls.raw = load_sources()
        cls.drivers = {r["driver_number"]: r for r in cls.raw["drivers"]}

    def test_message_timestamp_is_not_a_driver_mention(self):
        row = {"driver_number": None, "message": "CAR 55 (SAI) LAP DELETED - TRACK LIMITS AT TURN 1 LAP 18 17:29:27 (PIT)"}
        self.assertEqual(mentioned_drivers(row, self.drivers), [55])

    def test_two_driver_message_and_unknown_driver(self):
        row = {"driver_number": None, "message": "CARS 22 (TSU) AND 4 (NOR) NOTED"}
        self.assertEqual(mentioned_drivers(row, self.drivers), [4, 22])
        row["message"] = "CAR 99 (XYZ) NOTED"
        with self.assertRaises(ValueError):
            mentioned_drivers(row, self.drivers)

    def test_penalty_service_is_not_another_penalty(self):
        row = {"message": "FIA STEWARDS: PENALTY SERVED - 5 SECOND TIME PENALTY FOR CAR 30 (LAW)"}
        self.assertEqual(classify_control(row), "Penalty served reported")

    def test_null_stop_duration_not_imputed_and_lane_not_stationary(self):
        log = copy.deepcopy(self.log)
        event = next(e for e in log["events"] if e["type"] == "Pit stop recorded" and values(e)["driver_number"] == 27 and values(e)["lap_number"] == 7)
        self.assertNotIn("stop_duration", values(event))
        event["attributes"].append({"name": "stop_duration", "value": values(event)["lane_duration"]})
        with self.assertRaises(AssertionError):
            validate_fidelity(log, self.raw)

    def test_wrong_stint_relation_rejected(self):
        log = copy.deepcopy(self.log)
        event = next(e for e in log["events"] if e["type"] == "Pit stop recorded")
        relation = next(r for r in event["relationships"] if r["qualifier"] == "incoming_stint")
        relation["objectId"] = "stint:9839:1:1"
        with self.assertRaises(AssertionError):
            validate_fidelity(log, self.raw)

    def test_missing_source_event_rejected(self):
        log = copy.deepcopy(self.log)
        log["events"] = [e for e in log["events"] if e["id"] != "lap-completed:lap:9839:1:1"]
        with self.assertRaises(AssertionError):
            validate_fidelity(log, self.raw)

    def test_dangling_relationship_rejected(self):
        log = copy.deepcopy(self.log)
        log["events"][0]["relationships"][0]["objectId"] = "absent"
        with self.assertRaises(AssertionError):
            validate_structure(log)

    def test_same_compound_stints_and_repeated_deletions_retained(self):
        stints = [values(o) for o in self.log["objects"] if o["type"] == "TyreStint" and values(o)["driver_number"] == 4]
        self.assertEqual([s["compound"] for s in sorted(stints, key=lambda s: s["stint_number"])], ["MEDIUM", "HARD", "HARD"])
        deletions = [e for e in self.log["events"] if e["type"] == "Lap time deleted" and any(r["objectId"] == "lap:9839:16:52" for r in e["relationships"])]
        self.assertEqual(len(deletions), 2)


if __name__ == "__main__":
    unittest.main()
