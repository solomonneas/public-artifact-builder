from __future__ import annotations

import base64
import json
import os
from dataclasses import dataclass
from pathlib import Path
from urllib import request

from .models import ArtifactMap


@dataclass(frozen=True)
class RenderRequest:
    diagram_name: str
    mermaid_source: str
    prompt: str
    output_path: Path


class ImageRenderer:
    name = "base"

    def render(self, request: RenderRequest) -> str:
        raise NotImplementedError


class StubImageRenderer(ImageRenderer):
    name = "stub"

    def render(self, request: RenderRequest) -> str:
        return (
            f"Skipped image render for {request.diagram_name}. "
            "Configure a real provider and API key to enable rendered images."
        )


class OpenAIImageRenderer(ImageRenderer):
    name = "openai"

    def __init__(self, api_key: str, model: str = "gpt-image-1.5"):
        self.api_key = api_key
        self.model = model

    def render(self, request_item: RenderRequest) -> str:
        payload = {
            "model": self.model,
            "prompt": request_item.prompt,
            "size": "1536x1024",
            "quality": "medium",
        }
        http_request = request.Request(
            "https://api.openai.com/v1/images/generations",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        with request.urlopen(http_request, timeout=120) as response:
            body = json.loads(response.read().decode("utf-8"))
        image_base64 = body["data"][0]["b64_json"]
        request_item.output_path.write_bytes(base64.b64decode(image_base64))
        return f"Rendered {request_item.output_path.name} with {self.model}."


def get_image_renderer() -> ImageRenderer:
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        return StubImageRenderer()
    model = os.environ.get("PAB_IMAGE_MODEL", "gpt-image-1.5")
    return OpenAIImageRenderer(api_key=api_key, model=model)


def build_image_prompt(artifact_map: ArtifactMap, diagram_name: str, mermaid_source: str) -> str:
    return "\n".join(
        [
            "Create a clean professional technical diagram image from the supplied Mermaid source.",
            "Do not add services, databases, networks, vendors, labels, icons, or architecture not present in the source.",
            "Use a restrained infrastructure-engineering visual style suitable for portfolio and blog use.",
            f"Project: {artifact_map.project_name}",
            f"Diagram: {diagram_name}",
            "Mermaid source:",
            mermaid_source,
        ]
    )


def render_images(artifact_map: ArtifactMap, out_dir: Path, mermaid_sources: dict[str, str]) -> list[str]:
    renderer = get_image_renderer()
    out_dir.mkdir(parents=True, exist_ok=True)
    notes: list[str] = []
    for name, source in mermaid_sources.items():
        request = RenderRequest(
            diagram_name=name,
            mermaid_source=source,
            prompt=build_image_prompt(artifact_map, name, source),
            output_path=out_dir / name.replace(".mmd", ".png"),
        )
        notes.append(renderer.render(request))
    return notes
