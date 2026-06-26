from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from .hashing import bundle_hashes


def approve_bundle(
    out_dir: Path,
    policy: Path | None = None,
    acknowledge_risks: bool = False,
) -> dict:
    artifact_map = _load_json(out_dir / "artifact-map.json")
    privacy_report = _load_json(out_dir / "privacy-report.json")
    high_risk = int(privacy_report.get("high_risk_count", 0))
    privacy_status = privacy_report.get("status", "missing")

    if privacy_status == "pass" and high_risk == 0:
        status = "approved"
    elif acknowledge_risks:
        status = "acknowledged"
    else:
        status = "blocked"

    readiness = {
        "schema_version": "1.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "project_name": artifact_map.get("project_name", out_dir.name),
        "status": status,
        "privacy_status": privacy_status,
        "finding_count": int(privacy_report.get("finding_count", 0)),
        "high_risk_count": high_risk,
        "acknowledged_risks": bool(acknowledge_risks and status == "acknowledged"),
        "hashes": bundle_hashes(out_dir, policy),
    }
    (out_dir / "publish-readiness.json").write_text(
        json.dumps(readiness, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return readiness


def _load_json(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}

