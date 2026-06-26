from __future__ import annotations

import json
import re
from pathlib import Path

from .models import ArtifactMap, PrivacyFinding
from .privacy import PrivacyScrubber
from .preview import render_preview_html


def write_artifacts(
    artifact_map: ArtifactMap,
    out_dir: Path,
    render_note: str | None = None,
    include_public_outputs: bool = True,
    include_sarif: bool = False,
) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    written.append(_write_json(out_dir / "artifact-map.json", artifact_map.model_dump(mode="json")))
    written.append(_write_json(out_dir / "privacy-report.json", render_privacy_report(artifact_map)))
    if include_sarif:
        written.append(_write_json(out_dir / "privacy-report.sarif", render_privacy_sarif(artifact_map)))
    written.append(_write_text(out_dir / "leak-check.md", render_leak_check(artifact_map, render_note)))
    if not include_public_outputs:
        return written

    markdown_outputs = {
        "case-study.md": render_case_study(artifact_map),
        "architecture.md": render_architecture(artifact_map),
        "README.rewrite.md": render_readme_rewrite(artifact_map),
        "linkedin-post.md": render_linkedin_post(artifact_map),
        "screenshots-needed.md": render_screenshots_needed(artifact_map),
    }
    for name, content in markdown_outputs.items():
        written.append(_write_text(out_dir / name, content))
    written.append(_write_text(out_dir / "preview.html", render_preview_html(artifact_map, markdown_outputs)))

    written.append(_write_json(out_dir / "portfolio-card.json", render_portfolio_card(artifact_map)))

    mermaid = render_mermaid_sources(artifact_map)
    for name, content in mermaid.items():
        written.append(_write_text(out_dir / name, content))
    return written


def render_case_study(artifact_map: ArtifactMap) -> str:
    return "\n".join(
        [
            f"# {artifact_map.project_name} Case Study",
            "",
            "## Summary",
            artifact_map.summary,
            "",
            "## Technical Focus",
            _bullets([claim.claim for claim in artifact_map.public_safe_claims]),
            "",
            "## Evidence",
            _claim_evidence(artifact_map),
            "",
            "## Stack",
            _bullets(
                [
                    f"{item.name} ({item.category}, confidence {item.confidence:.2f})"
                    for item in artifact_map.detected_stack
                ]
                or ["Stack detection needs manual review."]
            ),
            "",
            "## Notable Components",
            _bullets([f"{item.name}: {item.description}" for item in artifact_map.components] or ["No major components were detected."]),
            "",
            "## Review Notes",
            _bullets([risk.detail for risk in artifact_map.risks] or ["No structural review risks were detected."]),
            "",
        ]
    )


def render_architecture(artifact_map: ArtifactMap) -> str:
    return "\n".join(
        [
            f"# {artifact_map.project_name} Architecture",
            "",
            "## Overview",
            artifact_map.summary,
            "",
            "## Components",
            _architecture_groups(artifact_map),
            "",
            "## Entry Points",
            _bullets([f"{item.name}: {item.path}" for item in artifact_map.entrypoints] or ["No explicit entrypoints detected."]),
            "",
            "## Scan Coverage",
            _scan_coverage(artifact_map),
            "",
        ]
    )


def render_readme_rewrite(artifact_map: ArtifactMap) -> str:
    return "\n".join(
        [
            f"# {artifact_map.project_name}",
            "",
            artifact_map.summary,
            "",
            "## What It Shows",
            _bullets([claim.claim for claim in artifact_map.public_safe_claims]),
            "",
            "## Architecture",
            "See `architecture.md` and the generated Mermaid sources for a deterministic view of the project structure.",
            "",
            "## Privacy",
            "This public rewrite was generated from scrubbed repository metadata. Review `leak-check.md` before publishing.",
            "",
        ]
    )


def render_linkedin_post(artifact_map: ArtifactMap) -> str:
    stack = ", ".join(item.name for item in artifact_map.detected_stack[:4]) or "the application stack"
    return "\n".join(
        [
            f"I built {artifact_map.project_name} to solve a practical infrastructure-engineering problem with {stack}.",
            "",
            "The project emphasizes clear boundaries, repeatable workflows, and reviewable implementation details. The public artifact bundle includes a case study, architecture notes, Mermaid diagrams, and a privacy leak check so the work can be discussed without exposing private infrastructure.",
            "",
            "Key technical signals:",
            _bullets([claim.claim for claim in artifact_map.public_safe_claims[:3]]),
            "",
        ]
    )


def render_screenshots_needed(artifact_map: ArtifactMap) -> str:
    suggestions = [
        "A clean first-run CLI invocation with sensitive paths cropped or replaced.",
        "Generated artifact bundle directory showing only public-safe filenames.",
        "Architecture diagram rendered from `architecture.mmd`.",
    ]
    if artifact_map.assets:
        suggestions.append("Review existing screenshots/assets and replace any that show secrets, admin consoles, or internal hostnames.")
    return "# Screenshots Needed\n\n" + _bullets(suggestions) + "\n"


def render_leak_check(artifact_map: ArtifactMap, render_note: str | None = None) -> str:
    lines = [
        f"# Leak Check for {artifact_map.project_name}",
        "",
        f"Privacy mode: `{artifact_map.privacy.mode}`",
        f"Status: `{artifact_map.privacy.status}`",
        f"High-risk findings: `{artifact_map.privacy.high_risk_count}`",
        "",
    ]
    if render_note:
        lines.extend(["## Render Note", render_note, ""])
    if not artifact_map.privacy.findings:
        lines.extend(
            [
                "## Findings",
                "No privacy findings were detected by the deterministic scanner.",
                "",
                "## Scan Skips",
                _scan_coverage(artifact_map),
                "",
            ]
        )
        return "\n".join(lines)

    lines.append("## Findings")
    for finding in artifact_map.privacy.findings:
        lines.extend(_finding_lines(finding))
    lines.extend(["", "## Scan Skips", _scan_coverage(artifact_map), ""])
    return "\n".join(lines)


def render_privacy_report(artifact_map: ArtifactMap) -> dict:
    return {
        "schema_version": "1.0",
        "project_name": artifact_map.project_name,
        "mode": artifact_map.privacy.mode,
        "status": artifact_map.privacy.status,
        "high_risk_count": artifact_map.privacy.high_risk_count,
        "finding_count": len(artifact_map.privacy.findings),
        "findings": [finding.model_dump(mode="json") for finding in artifact_map.privacy.findings],
        "skipped_files": [skipped.model_dump(mode="json") for skipped in artifact_map.skipped_files],
    }


def render_privacy_sarif(artifact_map: ArtifactMap) -> dict:
    rules = {
        finding.type: {
            "id": finding.type,
            "name": finding.type,
            "shortDescription": {"text": finding.remediation},
        }
        for finding in artifact_map.privacy.findings
    }
    return {
        "$schema": "https://json.schemastore.org/sarif-2.1.0.json",
        "version": "2.1.0",
        "runs": [
            {
                "tool": {
                    "driver": {
                        "name": "public-artifact-builder",
                        "rules": list(rules.values()),
                    }
                },
                "results": [_sarif_result(finding) for finding in artifact_map.privacy.findings],
            }
        ],
    }


def render_portfolio_card(artifact_map: ArtifactMap) -> dict:
    return {
        "title": artifact_map.project_name,
        "summary": artifact_map.summary,
        "audience": artifact_map.audience,
        "stack": [item.name for item in artifact_map.detected_stack],
        "highlights": [claim.claim for claim in artifact_map.public_safe_claims[:3]],
        "artifacts": [
            "case-study.md",
            "architecture.md",
            "README.rewrite.md",
            "linkedin-post.md",
            "architecture.mmd",
            "request-flow.mmd",
            "data-flow.mmd",
            "leak-check.md",
            "preview.html",
        ],
    }


def render_mermaid_sources(artifact_map: ArtifactMap) -> dict[str, str]:
    scrubber = PrivacyScrubber()
    outputs = {
        "architecture.mmd": _architecture_mmd(artifact_map, scrubber),
        "request-flow.mmd": _request_flow_mmd(artifact_map, scrubber),
        "data-flow.mmd": _data_flow_mmd(artifact_map, scrubber),
    }
    if _has_agent_workflow(artifact_map):
        outputs["agent-workflow.mmd"] = _agent_workflow_mmd(artifact_map, scrubber)
    if artifact_map.privacy.findings or artifact_map.deployment_clues:
        outputs["threat-boundary.mmd"] = _threat_boundary_mmd(artifact_map, scrubber)
    return outputs


def _architecture_mmd(artifact_map: ArtifactMap, scrubber: PrivacyScrubber) -> str:
    lines = ["flowchart TD", f"  repo[{_label(artifact_map.project_name, scrubber)}]"]
    for index, component in enumerate(artifact_map.components[:12], start=1):
        node = f"c{index}"
        lines.append(f"  {node}[{_label(component.name, scrubber)}]")
        lines.append(f"  repo --> {node}")
    for index, service in enumerate(artifact_map.services[:8], start=1):
        node = f"s{index}"
        lines.append(f"  {node}(({_label(service.name, scrubber)}))")
        lines.append(f"  repo --> {node}")
    if len(lines) == 2:
        lines.append("  repo --> scan[Repository scan]")
    return "\n".join(lines) + "\n"


def _request_flow_mmd(artifact_map: ArtifactMap, scrubber: PrivacyScrubber) -> str:
    lines = ["sequenceDiagram", "  actor User", f"  participant Project as {_label(artifact_map.project_name, scrubber)}"]
    if artifact_map.entrypoints:
        for entrypoint in artifact_map.entrypoints[:6]:
            lines.append(f"  User->>Project: invoke {_label(entrypoint.name, scrubber)}")
    else:
        lines.append("  User->>Project: run or open project entrypoint")
    if artifact_map.services:
        for service in artifact_map.services[:4]:
            lines.append(f"  Project->>{_participant(service.name)}: call {_label(service.kind, scrubber)}")
    lines.append("  Project-->>User: return project behavior")
    return "\n".join(lines) + "\n"


def _data_flow_mmd(artifact_map: ArtifactMap, scrubber: PrivacyScrubber) -> str:
    lines = ["flowchart LR", "  input[Input]", f"  app[{_label(artifact_map.project_name, scrubber)}]", "  output[Output]", "  input --> app"]
    for index, store in enumerate(artifact_map.data_stores[:8], start=1):
        node = f"d{index}"
        lines.append(f"  app --> {node}[{_label(store.name, scrubber)}]")
    lines.append("  app --> output")
    return "\n".join(lines) + "\n"


def _agent_workflow_mmd(artifact_map: ArtifactMap, scrubber: PrivacyScrubber) -> str:
    lines = ["flowchart TD", "  trigger[Trigger]"]
    workflows = [item for item in artifact_map.workflows if re.search(r"agent|workflow", item.name, re.I)]
    for index, workflow in enumerate(workflows[:8], start=1):
        node = f"w{index}"
        lines.append(f"  {node}[{_label(workflow.name, scrubber)}]")
        lines.append(f"  trigger --> {node}")
    if len(lines) == 2:
        lines.append("  trigger --> review[Review workflow source]")
    return "\n".join(lines) + "\n"


def _threat_boundary_mmd(artifact_map: ArtifactMap, scrubber: PrivacyScrubber) -> str:
    lines = [
        "flowchart TD",
        "  public[Public artifact boundary]",
        "  repo[Repository facts]",
        "  scrub[Privacy scrubber]",
        "  outputs[Generated artifacts]",
        "  repo --> scrub --> public --> outputs",
    ]
    if artifact_map.privacy.findings:
        lines.append("  scrub --> findings[Leak-check findings]")
    for index, clue in enumerate(artifact_map.deployment_clues[:5], start=1):
        lines.append(f"  repo --> dep{index}[{_label(clue.name, scrubber)}]")
        lines.append(f"  dep{index} --> scrub")
    return "\n".join(lines) + "\n"


def _write_text(path: Path, content: str) -> Path:
    path.write_text(content, encoding="utf-8")
    return path


def _write_json(path: Path, value: dict) -> Path:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def _bullets(items: list[str]) -> str:
    return "\n".join(f"- {item}" for item in items)


def _claim_evidence(artifact_map: ArtifactMap) -> str:
    lines: list[str] = []
    for claim in artifact_map.public_safe_claims:
        sources = ", ".join(source.path for source in claim.sources[:4]) or "repository scan"
        lines.append(f"- Confidence {claim.confidence:.2f}: {claim.claim} Sources: {sources}")
    return "\n".join(lines) if lines else "- No public-safe claims were generated."


def _architecture_groups(artifact_map: ArtifactMap) -> str:
    groups = [
        (
            "Application Code",
            [item for item in artifact_map.components if item.name in {"src", "app", "api", "cli", "lib"}],
        ),
        (
            "Operations",
            [item for item in artifact_map.components if item.name in {"docs", "tests", "scripts"}],
        ),
        ("Runtime Services", artifact_map.services),
        ("Data Stores", artifact_map.data_stores),
        ("Deployment Signals", artifact_map.deployment_clues),
    ]
    lines: list[str] = []
    for title, items in groups:
        if not items:
            continue
        lines.append(f"### {title}")
        for item in items:
            name = getattr(item, "name")
            kind = getattr(item, "kind", "")
            detail = getattr(item, "description", "") or getattr(item, "path", "")
            lines.append(f"- {name} ({kind})" + (f": {detail}" if detail else ""))
        lines.append("")
    return "\n".join(lines).strip() or "No architecture groups detected."


def _scan_coverage(artifact_map: ArtifactMap) -> str:
    if not artifact_map.skipped_files:
        return "No scan skips were recorded."
    reasons: dict[str, int] = {}
    for skipped in artifact_map.skipped_files:
        reasons[skipped.reason] = reasons.get(skipped.reason, 0) + 1
    lines = [f"- {reason}: {count}" for reason, count in sorted(reasons.items())]
    examples = ", ".join(skipped.path for skipped in artifact_map.skipped_files[:5])
    if examples:
        lines.append(f"- Examples: {examples}")
    return "\n".join(lines)


def _finding_lines(finding: PrivacyFinding) -> list[str]:
    location = finding.path if finding.line is None else f"{finding.path}:{finding.line}"
    return [
        f"- `{finding.severity}` `{finding.type}` at `{location}`",
        f"  Evidence: `{finding.evidence}`",
        f"  Remediation: {finding.remediation}",
    ]


def _sarif_result(finding: PrivacyFinding) -> dict:
    return {
        "ruleId": finding.type,
        "level": _sarif_level(finding.severity),
        "message": {"text": f"{finding.evidence}: {finding.remediation}"},
        "locations": [
            {
                "physicalLocation": {
                    "artifactLocation": {"uri": finding.path},
                    "region": {"startLine": finding.line or 1},
                }
            }
        ],
    }


def _sarif_level(severity: str) -> str:
    return {"high": "error", "medium": "warning", "low": "note"}.get(severity, "warning")


def _label(value: str, scrubber: PrivacyScrubber) -> str:
    cleaned = scrubber.sanitize_label(value)
    cleaned = re.sub(r"[\[\]{}|<>]", "", cleaned)
    return cleaned[:80] or "item"


def _participant(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_]", "", value.title())[:40] or "Service"


def _has_agent_workflow(artifact_map: ArtifactMap) -> bool:
    text = " ".join(workflow.name for workflow in artifact_map.workflows)
    return bool(re.search(r"agent|workflow", text, re.I))
