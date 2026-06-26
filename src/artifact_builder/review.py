from __future__ import annotations

import json
from pathlib import Path


REQUIRED_PUBLIC_OUTPUTS = {
    "artifact-map.json",
    "privacy-report.json",
    "leak-check.md",
    "case-study.md",
    "architecture.md",
    "README.rewrite.md",
    "linkedin-post.md",
    "portfolio-card.json",
    "screenshots-needed.md",
    "preview.html",
    "architecture.mmd",
    "request-flow.mmd",
    "data-flow.mmd",
}


def review_bundle(out_dir: Path) -> dict:
    privacy_report = _load_json(out_dir / "privacy-report.json")
    artifact_map = _load_json(out_dir / "artifact-map.json")
    existing = {path.name for path in out_dir.iterdir()} if out_dir.exists() else set()
    missing_outputs = sorted(REQUIRED_PUBLIC_OUTPUTS - existing)
    findings = privacy_report.get("findings", [])
    skipped = privacy_report.get("skipped_files", [])
    high_risk = int(privacy_report.get("high_risk_count", 0))
    status = privacy_report.get("status", "missing")
    screenshot_suggestions = _screenshot_suggestions(out_dir / "screenshots-needed.md")

    readiness = "ready"
    if status == "blocked" or high_risk > 0:
        readiness = "blocked"
    elif findings or skipped or missing_outputs:
        readiness = "needs-review"

    return {
        "project_name": artifact_map.get("project_name", out_dir.name),
        "readiness": readiness,
        "privacy_status": status,
        "finding_count": len(findings),
        "high_risk_count": high_risk,
        "finding_types": _counts(finding.get("type", "unknown") for finding in findings),
        "skipped_count": len(skipped),
        "skipped_reasons": _counts(item.get("reason", "unknown") for item in skipped),
        "missing_outputs": missing_outputs,
        "screenshot_suggestions": screenshot_suggestions,
    }


def render_review_text(review: dict) -> str:
    lines = [
        f"Project: {review['project_name']}",
        f"Readiness: {review['readiness']}",
        f"Privacy: {review['privacy_status']}",
        f"Findings: {review['finding_count']} total, {review['high_risk_count']} high risk",
        f"Skipped files: {review['skipped_count']}",
    ]
    if review["finding_types"]:
        lines.append("Finding types:")
        lines.extend(f"- {name}: {count}" for name, count in review["finding_types"].items())
    if review["skipped_reasons"]:
        lines.append("Skipped reasons:")
        lines.extend(f"- {name}: {count}" for name, count in review["skipped_reasons"].items())
    if review["missing_outputs"]:
        lines.append("Missing outputs:")
        lines.extend(f"- {name}" for name in review["missing_outputs"])
    if review["screenshot_suggestions"]:
        lines.append("Screenshots to gather:")
        lines.extend(f"- {item}" for item in review["screenshot_suggestions"])
    return "\n".join(lines)


def _load_json(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def _counts(values) -> dict:
    counts: dict[str, int] = {}
    for value in values:
        counts[str(value)] = counts.get(str(value), 0) + 1
    return dict(sorted(counts.items()))


def _screenshot_suggestions(path: Path) -> list[str]:
    if not path.exists():
        return []
    suggestions: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("- "):
            suggestions.append(line[2:])
    return suggestions
