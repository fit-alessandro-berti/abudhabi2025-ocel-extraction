"""Fetch an immutable, checksummed OpenF1 snapshot (never overwrites by default)."""
import argparse
import gzip
import hashlib
import json
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENDPOINTS = ["sessions", "drivers", "laps", "pit", "stints", "race_control", "weather", "session_result"]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "data/raw")
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    manifest_path = args.output / "manifest.json"
    manifest = json.loads(manifest_path.read_text()) if manifest_path.exists() else {
        "provider": "OpenF1", "session_key": 9839, "meeting_key": 1276,
        "documentation": "https://openf1.org/docs/", "sources": {}}
    for endpoint in ENDPOINTS:
        path = args.output / f"{endpoint}.json.gz"
        if endpoint in manifest["sources"]:
            assert hashlib.sha256(path.read_bytes()).hexdigest() == manifest["sources"][endpoint]["sha256_gzip"]
            print(endpoint, "verified existing snapshot", flush=True)
            continue
        if path.exists():
            raise RuntimeError(f"Unmanifested file: {path}; inspect before resuming")
        url = f"https://api.openf1.org/v1/{endpoint}?session_key=9839"
        for attempt in range(5):
            try:
                req = urllib.request.Request(url, headers={"User-Agent": "abudhabi2025-ocel-research/1.0"})
                with urllib.request.urlopen(req, timeout=90) as response:
                    payload = response.read()
                records = json.loads(payload)
                assert isinstance(records, list) and records
                assert all(r["session_key"] == 9839 and r["meeting_key"] == 1276 for r in records)
                break
            except Exception:
                if attempt == 4:
                    raise
                time.sleep(3 * (attempt + 1))
        compressed = gzip.compress(payload, mtime=0)
        path.write_bytes(compressed)
        manifest["sources"][endpoint] = {
            "url": url, "retrieved_at_utc": datetime.now(timezone.utc).isoformat(),
            "records": len(records), "file": path.name,
            "sha256_response": hashlib.sha256(payload).hexdigest(),
            "sha256_gzip": hashlib.sha256(compressed).hexdigest()}
        manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")
        print(endpoint, len(records), flush=True)
        time.sleep(2.1)


if __name__ == "__main__":
    main()
