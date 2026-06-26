from pathlib import Path

from artifact_builder.privacy import PrivacyScrubber
from artifact_builder.scanner import scan_repo


POLICY_FIXTURE = Path(__file__).parent / "fixtures" / "policy_repo"


def test_privacy_detects_high_risk_findings_and_blocks_strict_mode(tmp_path):
    private_fixture = _make_private_fixture(tmp_path)
    scan = scan_repo(private_fixture, str(private_fixture))
    report = PrivacyScrubber().analyze(scan, "strict")

    assert report.status == "blocked"
    assert {finding.type for finding in report.findings} >= {
        "private-hostname",
        "private-ip",
        "secret-assignment",
        "screenshot-risk",
    }
    assert report.high_risk_count >= 4


def test_privacy_sanitizes_mermaid_labels():
    scrubber = PrivacyScrubber()
    host = ".".join(["api", "service", "internal"])
    private_ip = ".".join(["192", "168", "1", "10"])

    assert scrubber.sanitize_label(f"{host} at {private_ip}") == "[private-host] at [private-ip]"


def test_privacy_policy_allow_and_deny_terms():
    scan = scan_repo(POLICY_FIXTURE, str(POLICY_FIXTURE))
    report = PrivacyScrubber().analyze(scan, "strict")

    findings = {(finding.type, finding.evidence) for finding in report.findings}
    assert ("email", "public@example.com") not in findings
    assert ("custom-deny", "ExamplePrivateTenant") in findings
    assert report.status == "blocked"


def test_privacy_ignores_workspace_metadata_by_default(tmp_path):
    (tmp_path / "README.md").write_text("# Public Fixture\n", encoding="utf-8")
    metadata_dir = tmp_path / ".claude" / "memory-handoffs"
    metadata_dir.mkdir(parents=True)
    host = ".".join(["api", "service", "internal"])
    (metadata_dir / "private-note.md").write_text(
        f"Internal endpoint: {host}\n",
        encoding="utf-8",
    )

    scan = scan_repo(tmp_path, "sample")
    report = PrivacyScrubber().analyze(scan, "strict")

    assert report.status == "pass"
    assert not any(finding.path.startswith(".claude/") for finding in report.findings)


def _make_private_fixture(tmp_path: Path) -> Path:
    private_fixture = tmp_path / "private_repo"
    private_fixture.mkdir()
    host = ".".join(["api", "service", "internal"])
    private_ip = ".".join(["192", "168", "1", "10"])
    api_key_name = "API" + "_KEY"
    token_value = "sk-" + "testtokenvalue1234567890"
    email = "admin" + "@" + "example.com"
    (private_fixture / "README.md").write_text(
        "\n".join(
            [
                "# Private Fixture",
                "",
                f"Internal endpoint: {host}",
                f"Private IP: {private_ip}",
                f"Contact: {email}",
                f"{api_key_name}={token_value}",
                "",
            ]
        ),
        encoding="utf-8",
    )
    (private_fixture / "secret-console.png").write_text("placeholder", encoding="utf-8")
    return private_fixture
