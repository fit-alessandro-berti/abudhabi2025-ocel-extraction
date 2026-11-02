"""Write a deterministic release manifest and checksums after successful validation."""
import gzip
import hashlib
import json

from extract_ocel import ROOT, LOG_NAME


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    path = ROOT / "data/ocel" / LOG_NAME
    log = json.loads(gzip.decompress(path.read_bytes()))
    validation = json.loads((ROOT / "reports/validation.json").read_text())
    insights = json.loads((ROOT / "reports/insights.json").read_text())
    assert validation["status"] == "passed"
    assert validation["sha256_gzip"] == insights["log_sha256"] == sha(path)
    manifest = {
        "version": "1.0.0", "format": "OCEL 2.0 JSON", "compression": "gzip", "file": LOG_NAME,
        "bytes": path.stat().st_size, "sha256_gzip": sha(path), "sha256_json": validation["sha256_json"],
        "events": len(log["events"]), "objects": len(log["objects"]), "event_types": len(log["eventTypes"]),
        "object_types": len(log["objectTypes"]), "event_time_min": log["events"][0]["time"], "event_time_max": log["events"][-1]["time"],
        "source_manifest": "data/raw/manifest.json", "source_manifest_sha256": sha(ROOT / "data/raw/manifest.json"),
        "software_sha256": {name: sha(ROOT / name) for name in [
            "scripts/fetch_sources.py", "scripts/extract_ocel.py", "scripts/validate_ocel.py", "scripts/analyze_ocel.py",
            "scripts/package_release.py", "schemas/ocel20-extraction.schema.json", "requirements-lock.txt"]},
        "metadata": "metadata/zenodo.json", "validation": "reports/validation.json", "model": "MODEL.md",
    }
    (ROOT / "data/ocel/manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    files = sorted([*ROOT.glob("data/raw/*"), *ROOT.glob("data/ocel/*"), *ROOT.glob("metadata/*"),
                    *ROOT.glob("reports/*"), ROOT / "MODEL.md", ROOT / "SOURCES.md"])
    (ROOT / "SHA256SUMS").write_text("".join(f"{sha(p)}  {p.relative_to(ROOT)}\n" for p in files if p.is_file()))
    print(f"Release manifest and checksums written: {LOG_NAME}, {manifest['bytes']} bytes")


if __name__ == "__main__":
    main()
