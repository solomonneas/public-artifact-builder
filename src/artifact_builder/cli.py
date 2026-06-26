from __future__ import annotations

import json
import tempfile
from pathlib import Path
from typing import Annotated

import typer

from .approval import approve_bundle
from .clean import apply_clean, plan_clean, render_clean_text
from .doctor import render_doctor_text, run_doctor
from .generators import render_mermaid_sources, write_artifacts
from .pipeline import build_artifact_map
from .policy import init_policy as create_policy
from .renderers import render_images as render_diagram_images
from .review import render_review_text, review_bundle
from .scanner import ScannerConfig

app = typer.Typer(help="Build privacy-safe public project artifact bundles.")


@app.callback()
def main() -> None:
    """Build privacy-safe public project artifact bundles."""


@app.command()
def analyze(
    repo: Annotated[str, typer.Argument(help="Local repo path or GitHub URL.")],
    audience: Annotated[str, typer.Option(help="Target audience for generated artifacts.")] = "hiring-manager",
    privacy: Annotated[str, typer.Option(help="Privacy mode: standard or strict.")] = "strict",
    out: Annotated[Path, typer.Option(help="Output directory for generated artifacts.")] = Path("artifacts/project"),
    include: Annotated[
        list[str] | None,
        typer.Option("--include", help="Glob path to include. Can be passed multiple times."),
    ] = None,
    exclude: Annotated[
        list[str] | None,
        typer.Option("--exclude", help="Glob path to exclude. Can be passed multiple times."),
    ] = None,
    max_text_bytes: Annotated[
        int,
        typer.Option(help="Maximum bytes to read from any single text file."),
    ] = 80_000,
    max_text_files: Annotated[
        int,
        typer.Option(help="Maximum number of text files to inspect."),
    ] = 160,
    sarif: Annotated[bool, typer.Option(help="Write privacy-report.sarif.")] = False,
    output_format: Annotated[
        str,
        typer.Option("--format", help="Console output format: text or json."),
    ] = "text",
    quiet: Annotated[bool, typer.Option(help="Suppress non-error console output.")] = False,
    render_images: Annotated[bool, typer.Option(help="Render diagram images using the configured provider.")] = False,
    acknowledge_risks: Annotated[
        bool,
        typer.Option(
            "--acknowledge-risks",
            help="Allow public artifact generation even when strict privacy finds high-risk issues.",
        ),
    ] = False,
) -> None:
    if privacy not in {"standard", "strict"}:
        raise typer.BadParameter("privacy must be standard or strict")
    if output_format not in {"text", "json"}:
        raise typer.BadParameter("format must be text or json")

    with tempfile.TemporaryDirectory(prefix="artifact-builder-") as temp_dir:
        scanner_config = ScannerConfig(
            include=tuple(include or ()),
            exclude=tuple(exclude or ()),
            max_text_bytes=max_text_bytes,
            max_text_files=max_text_files,
        )
        artifact_map = build_artifact_map(repo, audience, privacy, Path(temp_dir), scanner_config)
        blocked = artifact_map.privacy.status == "blocked" and not acknowledge_risks
        render_note = None
        if render_images and not blocked:
            notes = render_diagram_images(artifact_map, out, render_mermaid_sources(artifact_map))
            render_note = "\n".join(notes)
        elif render_images and blocked:
            render_note = "Image rendering skipped because strict privacy mode is blocked."

        written = write_artifacts(
            artifact_map,
            out,
            render_note=render_note,
            include_public_outputs=not blocked,
            include_sarif=sarif,
        )

    summary = {
        "out": str(out),
        "written": len(written),
        "blocked": blocked,
        "privacy_status": artifact_map.privacy.status,
        "finding_count": len(artifact_map.privacy.findings),
        "high_risk_count": artifact_map.privacy.high_risk_count,
        "skipped_count": len(artifact_map.skipped_files),
    }
    if output_format == "json":
        typer.echo(json.dumps(summary, sort_keys=True))
    elif not quiet:
        typer.echo(f"Wrote {len(written)} artifact file(s) to {out}")
    if blocked:
        if not quiet:
            typer.echo(
                "Strict privacy mode found high-risk findings. Public artifact generation was blocked. "
                "Review leak-check.md or rerun with --acknowledge-risks.",
                err=True,
            )
        raise typer.Exit(code=2)


@app.command()
def review(
    out: Annotated[Path, typer.Argument(help="Artifact output directory to review.")],
    output_format: Annotated[
        str,
        typer.Option("--format", help="Console output format: text or json."),
    ] = "text",
) -> None:
    if output_format not in {"text", "json"}:
        raise typer.BadParameter("format must be text or json")
    result = review_bundle(out)
    if output_format == "json":
        typer.echo(json.dumps(result, sort_keys=True))
    else:
        typer.echo(render_review_text(result))
    if result["readiness"] == "blocked":
        raise typer.Exit(code=2)
    if result["readiness"] == "needs-review":
        raise typer.Exit(code=1)


@app.command("init-policy")
def init_policy(
    repo: Annotated[Path, typer.Argument(help="Local repository path.")],
    from_report: Annotated[
        Path | None,
        typer.Option("--from-report", help="privacy-report.json to seed deny terms from."),
    ] = None,
    force: Annotated[bool, typer.Option(help="Overwrite an existing policy file.")] = False,
    output_format: Annotated[
        str,
        typer.Option("--format", help="Console output format: text or json."),
    ] = "text",
) -> None:
    if output_format not in {"text", "json"}:
        raise typer.BadParameter("format must be text or json")
    try:
        result = create_policy(repo, from_report=from_report, force=force)
    except FileExistsError as exc:
        raise typer.BadParameter(str(exc)) from exc
    if output_format == "json":
        typer.echo(json.dumps(result, sort_keys=True))
    else:
        source = result["from_report"] or "no report found"
        typer.echo(
            f"Wrote {result['path']} with {result['deny_count']} deny candidate(s). Source: {source}"
        )


@app.command()
def approve(
    out: Annotated[Path, typer.Argument(help="Artifact output directory to approve.")],
    policy: Annotated[
        Path | None,
        typer.Option("--policy", help="Reviewed .artifact-builder-privacy.json to hash into the approval."),
    ] = None,
    acknowledge_risks: Annotated[
        bool,
        typer.Option(
            "--acknowledge-risks",
            help="Write acknowledged readiness for a blocked report.",
        ),
    ] = False,
    output_format: Annotated[
        str,
        typer.Option("--format", help="Console output format: text or json."),
    ] = "text",
) -> None:
    if output_format not in {"text", "json"}:
        raise typer.BadParameter("format must be text or json")
    result = approve_bundle(out, policy=policy, acknowledge_risks=acknowledge_risks)
    if output_format == "json":
        typer.echo(json.dumps(result, sort_keys=True))
    else:
        typer.echo(
            f"Publish readiness: {result['status']} "
            f"({result['high_risk_count']} high-risk finding(s))"
        )
    if result["status"] == "blocked":
        raise typer.Exit(code=2)


@app.command()
def doctor(
    out: Annotated[
        Path,
        typer.Option(help="Output directory to use for permission checks."),
    ] = Path(".artifacts"),
    output_format: Annotated[
        str,
        typer.Option("--format", help="Console output format: text or json."),
    ] = "text",
) -> None:
    if output_format not in {"text", "json"}:
        raise typer.BadParameter("format must be text or json")
    report = run_doctor(out)
    if output_format == "json":
        typer.echo(json.dumps(report, sort_keys=True))
    else:
        typer.echo(render_doctor_text(report))
    if report["status"] == "fail":
        raise typer.Exit(code=2)


@app.command()
def clean(
    root: Annotated[
        Path,
        typer.Option(help="Artifacts root containing generated bundle directories."),
    ] = Path(".artifacts"),
    apply: Annotated[
        bool,
        typer.Option("--apply", help="Actually remove generated bundle directories."),
    ] = False,
    output_format: Annotated[
        str,
        typer.Option("--format", help="Console output format: text or json."),
    ] = "text",
) -> None:
    if output_format not in {"text", "json"}:
        raise typer.BadParameter("format must be text or json")
    result = apply_clean(root) if apply else plan_clean(root)
    if output_format == "json":
        typer.echo(json.dumps(result, sort_keys=True))
    else:
        typer.echo(render_clean_text(result, applied=apply))


if __name__ == "__main__":
    app()
