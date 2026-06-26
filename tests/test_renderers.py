from pathlib import Path

from artifact_builder.pipeline import build_artifact_map
from artifact_builder.renderers import ImageRenderer, RenderRequest, render_images


FIXTURE = Path(__file__).parent / "fixtures" / "sample_repo"


class FakeRenderer(ImageRenderer):
    name = "fake"

    def render(self, request: RenderRequest) -> str:
        request.output_path.write_bytes(b"fake image")
        assert "Mermaid source:" in request.prompt
        assert request.mermaid_source in request.prompt
        assert "Do not add services" in request.prompt
        return f"rendered {request.output_path.name}"


def test_render_images_uses_provider_and_mermaid_prompt(monkeypatch, tmp_path):
    artifact_map = build_artifact_map(str(FIXTURE), "hiring-manager", "strict", tmp_path)
    mermaid_sources = {"architecture.mmd": "flowchart TD\n  a[A]\n"}

    monkeypatch.setattr("artifact_builder.renderers.get_image_renderer", lambda: FakeRenderer())
    notes = render_images(artifact_map, tmp_path / "images", mermaid_sources)

    assert notes == ["rendered architecture.png"]
    assert (tmp_path / "images" / "architecture.png").read_bytes() == b"fake image"
