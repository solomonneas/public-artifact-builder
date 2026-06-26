from pathlib import Path

from artifact_builder.pipeline import build_artifact_map


FIXTURE = Path(__file__).parent / "fixtures" / "sample_repo"


def test_artifact_map_has_required_sections(tmp_path):
    artifact_map = build_artifact_map(str(FIXTURE), "hiring-manager", "strict", tmp_path)
    data = artifact_map.model_dump(mode="json")

    for key in [
        "project_name",
        "summary",
        "detected_stack",
        "components",
        "services",
        "workflows",
        "data_stores",
        "entrypoints",
        "deployment_clues",
        "risks",
        "public_safe_claims",
        "privacy",
    ]:
        assert key in data

    assert data["project_name"] == "sample-ops-dashboard"
    assert data["privacy"]["status"] == "pass"

