from pathlib import Path

from artifact_builder.generators import (
    render_case_study,
    render_mermaid_sources,
    render_portfolio_card,
    write_artifacts,
)
from artifact_builder.pipeline import build_artifact_map


FIXTURE = Path(__file__).parent / "fixtures" / "sample_repo"


def test_markdown_and_portfolio_generation(tmp_path):
    artifact_map = build_artifact_map(str(FIXTURE), "hiring-manager", "strict", tmp_path)

    case_study = render_case_study(artifact_map)
    card = render_portfolio_card(artifact_map)

    assert "# sample-ops-dashboard Case Study" in case_study
    assert card["title"] == "sample-ops-dashboard"
    assert "React" in card["stack"]


def test_mermaid_generation_is_deterministic_and_safe(tmp_path):
    artifact_map = build_artifact_map(str(FIXTURE), "hiring-manager", "strict", tmp_path)
    mermaid = render_mermaid_sources(artifact_map)

    assert "architecture.mmd" in mermaid
    assert "flowchart TD" in mermaid["architecture.mmd"]
    assert "request-flow.mmd" in mermaid
    assert "data-flow.mmd" in mermaid
    assert "threat-boundary.mmd" in mermaid
    assert "192.168" not in "\n".join(mermaid.values())


def test_write_artifacts_creates_expected_files(tmp_path):
    artifact_map = build_artifact_map(str(FIXTURE), "hiring-manager", "strict", tmp_path)
    out = tmp_path / "bundle"
    written = write_artifacts(artifact_map, out)

    names = {path.name for path in written}
    assert {
        "artifact-map.json",
        "privacy-report.json",
        "case-study.md",
        "architecture.md",
        "README.rewrite.md",
        "linkedin-post.md",
        "portfolio-card.json",
        "screenshots-needed.md",
        "preview.html",
        "leak-check.md",
        "architecture.mmd",
        "request-flow.mmd",
        "data-flow.mmd",
    } <= names
    assert "<!doctype html>" in (out / "preview.html").read_text(encoding="utf-8")
    assert "Privacy: pass" in (out / "preview.html").read_text(encoding="utf-8")


def test_write_artifacts_can_emit_sarif(tmp_path):
    artifact_map = build_artifact_map(str(FIXTURE), "hiring-manager", "strict", tmp_path)
    out = tmp_path / "bundle"
    write_artifacts(artifact_map, out, include_sarif=True)

    assert (out / "privacy-report.sarif").exists()


def test_markdown_snapshots(tmp_path):
    artifact_map = build_artifact_map(str(FIXTURE), "hiring-manager", "strict", tmp_path)
    out = tmp_path / "bundle"
    write_artifacts(artifact_map, out)
    snapshot_dir = Path(__file__).parent / "snapshots"

    for name in [
        "case-study.md",
        "architecture.md",
        "README.rewrite.md",
        "linkedin-post.md",
    ]:
        actual = (out / name).read_text(encoding="utf-8").rstrip() + "\n"
        expected = (snapshot_dir / name).read_text(encoding="utf-8").rstrip() + "\n"
        assert actual == expected
