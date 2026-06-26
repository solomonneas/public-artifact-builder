from __future__ import annotations

import json
from pathlib import Path


POLICY_FILE = ".artifact-builder-privacy.json"
DENY_SEED_TYPES = {
    "custom-deny",
    "customer-name",
    "private-hostname",
    "screenshot-risk",
}


def init_policy(repo: Path, from_report: Path | None = None, force: bool = False) -> dict:
    repo_path = repo.expanduser().resolve()
    if not repo_path.exists() or not repo_path.is_dir():
        raise FileNotFoundError(f"Repository path does not exist: {repo}")

    policy_path = repo_path / POLICY_FILE
    if policy_path.exists() and not force:
        raise FileExistsError(f"Policy already exists: {policy_path}")

    report_path = from_report.expanduser().resolve() if from_report else find_latest_privacy_report(repo_path)
    deny = _deny_terms_from_report(report_path) if report_path else []
    policy = {
        "allow": [],
        "deny": deny,
    }
    policy_path.write_text(json.dumps(policy, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return {
        "path": str(policy_path),
        "from_report": str(report_path) if report_path else None,
        "deny_count": len(deny),
    }


def find_latest_privacy_report(repo_path: Path, search_root: Path | None = None) -> Path | None:
    candidates: list[Path] = []
    roots = [repo_path]
    if search_root:
        roots.append(search_root)
    roots.append(Path.cwd())

    seen: set[Path] = set()
    for root in roots:
        root = root.expanduser().resolve()
        if root in seen or not root.exists():
            continue
        seen.add(root)
        candidates.extend(root.glob(".artifacts/**/privacy-report.json"))

    if not candidates:
        return None
    return max(candidates, key=lambda path: path.stat().st_mtime)


def _deny_terms_from_report(report_path: Path) -> list[str]:
    try:
        report = json.loads(report_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    findings = report.get("findings", [])
    if not isinstance(findings, list):
        return []

    terms: set[str] = set()
    for finding in findings:
        if not isinstance(finding, dict):
            continue
        if finding.get("type") not in DENY_SEED_TYPES:
            continue
        evidence = finding.get("evidence")
        if isinstance(evidence, str) and _safe_policy_term(evidence):
            terms.add(evidence)
    return sorted(terms)


def _safe_policy_term(value: str) -> bool:
    if len(value) < 3 or len(value) > 120:
        return False
    if any(marker in value.lower() for marker in ("token", "secret", "password", "api_key", "sk-")):
        return False
    return True

