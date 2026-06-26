from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

from .models import PrivacyFinding, PrivacyReport, ScanResult


class PrivacyScrubber:
    def analyze(self, scan: ScanResult, mode: str) -> PrivacyReport:
        policy = PrivacyPolicy.load(scan.repo_path)
        findings: list[PrivacyFinding] = []
        for path, text in scan.text_files.items():
            findings.extend(self._scan_text(path, text, policy))
        for asset in scan.assets:
            findings.extend(self._scan_asset_name(asset, policy))
        for path in scan.files:
            findings.extend(self._scan_path(path.as_posix(), policy))

        findings = _dedupe([finding for finding in findings if not policy.is_allowed(finding.evidence)])
        blocked = mode == "strict" and any(item.severity == "high" for item in findings)
        return PrivacyReport(mode=mode, status="blocked" if blocked else "pass", findings=findings)

    def sanitize_label(self, value: str) -> str:
        sanitized = value
        for pattern, replacement in SANITIZE_PATTERNS:
            sanitized = pattern.sub(replacement, sanitized)
        return sanitized

    def contains_high_risk(self, value: str) -> bool:
        return any(
            finding.severity == "high"
            for finding in self._scan_text("<generated>", value, PrivacyPolicy())
        )

    def _scan_text(self, path: str, text: str, policy: "PrivacyPolicy") -> list[PrivacyFinding]:
        findings: list[PrivacyFinding] = []
        for line_number, line in enumerate(text.splitlines(), start=1):
            for detector in DETECTORS:
                for match in detector.pattern.finditer(line):
                    evidence = _safe_evidence(match.group(0))
                    findings.append(
                        PrivacyFinding(
                            type=detector.name,
                            severity=detector.severity,
                            path=path,
                            line=line_number,
                            evidence=evidence,
                            remediation=detector.remediation,
                        )
                    )
            for term in policy.deny:
                if term.lower() in line.lower():
                    findings.append(_custom_deny_finding(path, line_number, term))
        return findings

    def _scan_asset_name(self, asset: str, policy: "PrivacyPolicy") -> list[PrivacyFinding]:
        findings: list[PrivacyFinding] = []
        if re.search(r"secret|token|credential|password|key|env|admin|console", asset, re.I):
            findings.append(
                PrivacyFinding(
                    type="screenshot-risk",
                    severity="high",
                    path=asset,
                    evidence=Path(asset).name,
                    remediation="Review or replace this screenshot before publishing.",
                )
            )
        for term in policy.deny:
            if term.lower() in asset.lower():
                findings.append(_custom_deny_finding(asset, None, term))
        return findings

    def _scan_path(self, path: str, policy: "PrivacyPolicy") -> list[PrivacyFinding]:
        findings: list[PrivacyFinding] = []
        if re.search(r"(^|/)\.env($|[./])", path):
            findings.append(
                PrivacyFinding(
                    type="env-file",
                    severity="high",
                    path=path,
                    evidence=Path(path).name,
                    remediation="Remove environment files from public artifacts.",
                )
            )
        if re.search(r"/(home|Users)/[^/\s]+/", path):
            findings.append(
                PrivacyFinding(
                    type="private-path",
                    severity="medium",
                    path=path,
                    evidence=path,
                    remediation="Replace private filesystem paths with generic paths.",
                )
            )
        for term in policy.deny:
            if term.lower() in path.lower():
                findings.append(_custom_deny_finding(path, None, term))
        return findings


@dataclass(frozen=True)
class PrivacyPolicy:
    allow: tuple[str, ...] = ()
    deny: tuple[str, ...] = ()

    @classmethod
    def load(cls, repo_path: Path) -> "PrivacyPolicy":
        path = repo_path / ".artifact-builder-privacy.json"
        if not path.exists():
            return cls()
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return cls(deny=("invalid .artifact-builder-privacy.json",))
        if not isinstance(data, dict):
            return cls(deny=("invalid .artifact-builder-privacy.json",))
        return cls(
            allow=_string_tuple(data.get("allow", [])),
            deny=_string_tuple(data.get("deny", [])),
        )

    def is_allowed(self, evidence: str) -> bool:
        return any(term.lower() in evidence.lower() for term in self.allow)


class Detector:
    def __init__(self, name: str, pattern: str, severity: str, remediation: str):
        self.name = name
        self.pattern = re.compile(pattern)
        self.severity = severity
        self.remediation = remediation


DETECTORS = [
    Detector(
        "private-ip",
        r"\b(?:10\.\d{1,3}\.\d{1,3}\.\d{1,3}|192\.168\.\d{1,3}\.\d{1,3}|172\.(?:1[6-9]|2\d|3[0-1])\.\d{1,3}\.\d{1,3}|127\.\d{1,3}\.\d{1,3}\.\d{1,3}|169\.254\.\d{1,3}\.\d{1,3})\b",
        "high",
        "Replace private IP addresses with public-safe placeholders.",
    ),
    Detector(
        "private-hostname",
        r"\b[a-zA-Z0-9][a-zA-Z0-9-]*(?:\.[a-zA-Z0-9-]+)*\.(?:local|lan|internal|corp|home|private)\b",
        "high",
        "Replace internal hostnames or private domains with generic labels.",
    ),
    Detector(
        "email",
        r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b",
        "medium",
        "Remove or generalize personal and customer email addresses.",
    ),
    Detector(
        "secret-assignment",
        r"(?i)\b(?:api[_-]?key|secret|token|password|passwd|client[_-]?secret)\b\s*[:=]\s*[\"']?[^\"'\s]{8,}",
        "high",
        "Remove credential-like values and publish only placeholder examples.",
    ),
    Detector(
        "token",
        r"\b(?:sk-[A-Za-z0-9_-]{16,}|ghp_[A-Za-z0-9_]{16,}|xox[baprs]-[A-Za-z0-9-]{10,}|[A-Za-z0-9_-]{32,}\.[A-Za-z0-9_-]{16,}\.[A-Za-z0-9_-]{16,})\b",
        "high",
        "Rotate exposed tokens and remove them from generated artifacts.",
    ),
    Detector(
        "env-var",
        r"\b[A-Z][A-Z0-9_]{2,}(?:SECRET|TOKEN|PASSWORD|API_KEY|PRIVATE_KEY|DATABASE_URL)[A-Z0-9_]*\b",
        "medium",
        "Mention configuration categories without exposing sensitive variable names when possible.",
    ),
    Detector(
        "private-path",
        r"(?:/home|/Users)/[A-Za-z0-9._-]+/[^\s\"']+",
        "medium",
        "Replace user-specific filesystem paths with generic paths.",
    ),
    Detector(
        "customer-name",
        r"(?i)\b(?:customer|client|tenant)\s+(?:name|account|org|organization)?\s*[:=]\s*[\"']?[A-Z][A-Za-z0-9 &.-]{2,}",
        "medium",
        "Remove customer or client names unless they are approved public references.",
    ),
    Detector(
        "infra-claim",
        r"(?i)\b(?:vpn|vpc|subnet|bastion|prod(?:uction)? cluster|private endpoint|internal load balancer)\b",
        "medium",
        "Describe infrastructure boundaries generically for public outputs.",
    ),
]

SANITIZE_PATTERNS = [
    (re.compile(r"\b(?:10\.\d{1,3}\.\d{1,3}\.\d{1,3}|192\.168\.\d{1,3}\.\d{1,3}|172\.(?:1[6-9]|2\d|3[0-1])\.\d{1,3}\.\d{1,3})\b"), "[private-ip]"),
    (re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"), "[email]"),
    (re.compile(r"\b[a-zA-Z0-9][a-zA-Z0-9-]*(?:\.[a-zA-Z0-9-]+)*\.(?:local|lan|internal|corp|home|private)\b"), "[private-host]"),
]


def _safe_evidence(value: str) -> str:
    if len(value) <= 80:
        return value
    return value[:36] + "...[redacted]..." + value[-12:]


def _dedupe(findings: list[PrivacyFinding]) -> list[PrivacyFinding]:
    seen: set[tuple[str, str, int | None, str]] = set()
    unique: list[PrivacyFinding] = []
    for finding in findings:
        key = (finding.type, finding.path, finding.line, finding.evidence)
        if key not in seen:
            unique.append(finding)
            seen.add(key)
    return unique


def _custom_deny_finding(path: str, line: int | None, term: str) -> PrivacyFinding:
    return PrivacyFinding(
        type="custom-deny",
        severity="high",
        path=path,
        line=line,
        evidence=_safe_evidence(term),
        remediation="Remove or generalize this project-specific sensitive term.",
    )


def _string_tuple(value: object) -> tuple[str, ...]:
    if not isinstance(value, list):
        return ()
    return tuple(item.strip() for item in value if isinstance(item, str) and item.strip())
