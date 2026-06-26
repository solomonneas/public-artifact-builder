import json
from pathlib import Path

from typer.testing import CliRunner

from artifact_builder.cli import app


FIXTURE = Path(__file__).parent / "fixtures" / "sample_repo"


def test_cli_generates_bundle(tmp_path):
    out = tmp_path / "sample"
    result = CliRunner().invoke(
        app,
        [
            "analyze",
            str(FIXTURE),
            "--audience",
            "hiring-manager",
            "--privacy",
            "strict",
            "--out",
            str(out),
        ],
    )

    assert result.exit_code == 0, result.output
    assert (out / "artifact-map.json").exists()
    assert (out / "privacy-report.json").exists()
    assert (out / "case-study.md").exists()
    assert (out / "architecture.mmd").exists()


def test_cli_blocks_public_outputs_on_strict_privacy(tmp_path):
    out = tmp_path / "private"
    private_fixture = _make_private_fixture(tmp_path)
    result = CliRunner().invoke(
        app,
        ["analyze", str(private_fixture), "--privacy", "strict", "--out", str(out)],
    )

    assert result.exit_code == 2
    assert (out / "artifact-map.json").exists()
    assert (out / "privacy-report.json").exists()
    assert (out / "leak-check.md").exists()
    assert not (out / "case-study.md").exists()


def test_cli_json_output_sarif_and_filters(tmp_path):
    out = tmp_path / "sample"
    result = CliRunner().invoke(
        app,
        [
            "analyze",
            str(FIXTURE),
            "--privacy",
            "strict",
            "--out",
            str(out),
            "--include",
            "README.md",
            "--include",
            "package.json",
            "--sarif",
            "--format",
            "json",
        ],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["privacy_status"] == "pass"
    assert payload["skipped_count"] > 0
    assert (out / "privacy-report.sarif").exists()


def test_cli_review_reports_ready_bundle(tmp_path):
    out = tmp_path / "sample"
    analyze = CliRunner().invoke(
        app,
        ["analyze", str(FIXTURE), "--privacy", "strict", "--out", str(out)],
    )
    assert analyze.exit_code == 0, analyze.output

    result = CliRunner().invoke(app, ["review", str(out), "--format", "json"])

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["readiness"] == "ready"
    assert payload["privacy_status"] == "pass"
    assert payload["screenshot_suggestions"]


def test_cli_review_reports_blocked_bundle(tmp_path):
    out = tmp_path / "private"
    private_fixture = _make_private_fixture(tmp_path)
    analyze = CliRunner().invoke(
        app,
        ["analyze", str(private_fixture), "--privacy", "strict", "--out", str(out)],
    )
    assert analyze.exit_code == 2

    result = CliRunner().invoke(app, ["review", str(out)])

    assert result.exit_code == 2
    assert "Readiness: blocked" in result.output
    assert "secret-assignment" in result.output


def test_cli_init_policy_from_report(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    report = tmp_path / "privacy-report.json"
    report.write_text(
        json.dumps(
            {
                "findings": [
                    {"type": "private-hostname", "evidence": ".".join(["api", "service", "internal"])},
                    {"type": "secret-assignment", "evidence": ("API" + "_KEY") + "=" + ("sk-" + "testsecret")},
                    {"type": "customer-name", "evidence": "Example Private Tenant"},
                ]
            }
        ),
        encoding="utf-8",
    )

    result = CliRunner().invoke(
        app,
        [
            "init-policy",
            str(repo),
            "--from-report",
            str(report),
            "--format",
            "json",
        ],
    )

    assert result.exit_code == 0, result.output
    policy = json.loads((repo / ".artifact-builder-privacy.json").read_text(encoding="utf-8"))
    assert policy["allow"] == []
    assert policy["deny"] == ["Example Private Tenant", ".".join(["api", "service", "internal"])]


def test_cli_approve_writes_publish_readiness_with_hashes(tmp_path):
    out = tmp_path / "sample"
    analyze = CliRunner().invoke(
        app,
        ["analyze", str(FIXTURE), "--privacy", "strict", "--out", str(out)],
    )
    assert analyze.exit_code == 0, analyze.output

    result = CliRunner().invoke(app, ["approve", str(out), "--format", "json"])

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    readiness = json.loads((out / "publish-readiness.json").read_text(encoding="utf-8"))
    assert payload["status"] == "approved"
    assert readiness["hashes"]["artifact_map_sha256"]
    assert readiness["hashes"]["privacy_report_sha256"]
    assert readiness["hashes"]["policy_sha256"] is None


def test_cli_approve_blocks_unacknowledged_high_risk_report(tmp_path):
    out = tmp_path / "private"
    private_fixture = _make_private_fixture(tmp_path)
    analyze = CliRunner().invoke(
        app,
        ["analyze", str(private_fixture), "--privacy", "strict", "--out", str(out)],
    )
    assert analyze.exit_code == 2

    blocked = CliRunner().invoke(app, ["approve", str(out)])
    acknowledged = CliRunner().invoke(app, ["approve", str(out), "--acknowledge-risks"])

    assert blocked.exit_code == 2
    assert acknowledged.exit_code == 0
    readiness = json.loads((out / "publish-readiness.json").read_text(encoding="utf-8"))
    assert readiness["status"] == "acknowledged"
    assert readiness["acknowledged_risks"] is True


def test_cli_doctor_json_reports_checks(tmp_path):
    result = CliRunner().invoke(
        app,
        ["doctor", "--out", str(tmp_path / "artifacts"), "--format", "json"],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["status"] in {"pass", "warn"}
    assert {check["name"] for check in payload["checks"]} >= {
        "python",
        "git",
        "output",
        "openai-images",
        "mermaid",
    }


def test_cli_clean_dry_run_and_apply(tmp_path):
    root = tmp_path / ".artifacts"
    bundle = root / "sample"
    bundle.mkdir(parents=True)
    (bundle / "artifact-map.json").write_text("{}", encoding="utf-8")
    (bundle / "case-study.md").write_text("# Sample\n", encoding="utf-8")

    dry_run = CliRunner().invoke(
        app,
        ["clean", "--root", str(root), "--format", "json"],
    )

    assert dry_run.exit_code == 0, dry_run.output
    assert bundle.exists()
    dry_payload = json.loads(dry_run.output)
    assert dry_payload["bundle_count"] == 1

    apply = CliRunner().invoke(
        app,
        ["clean", "--root", str(root), "--apply", "--format", "json"],
    )

    assert apply.exit_code == 0, apply.output
    apply_payload = json.loads(apply.output)
    assert apply_payload["removed"] == [str(bundle.resolve())]
    assert not bundle.exists()


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
