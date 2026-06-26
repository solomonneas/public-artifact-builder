from __future__ import annotations

from pathlib import Path

from .models import ArtifactMap
from .privacy import PrivacyScrubber
from .scanner import (
    ScannerConfig,
    build_public_claims,
    build_summary,
    detect_components,
    detect_data_stores,
    detect_deployment_clues,
    detect_entrypoints,
    detect_risks,
    detect_services,
    detect_stack,
    detect_workflows,
    resolve_repo,
    scan_repo,
)


def build_artifact_map(
    repo: str,
    audience: str,
    privacy_mode: str,
    work_dir: Path,
    scanner_config: ScannerConfig | None = None,
) -> ArtifactMap:
    repo_path, source = resolve_repo(repo, work_dir)
    scan = scan_repo(repo_path, source, scanner_config)
    stack = detect_stack(scan)
    privacy = PrivacyScrubber().analyze(scan, privacy_mode)
    return ArtifactMap(
        project_name=scan.project_name,
        source=scan.source,
        audience=audience,
        privacy=privacy,
        summary=build_summary(scan, stack),
        detected_stack=stack,
        components=detect_components(scan),
        services=detect_services(scan),
        workflows=detect_workflows(scan),
        data_stores=detect_data_stores(scan),
        entrypoints=detect_entrypoints(scan),
        deployment_clues=detect_deployment_clues(scan),
        risks=detect_risks(scan),
        public_safe_claims=build_public_claims(scan, stack),
        git=scan.git,
        assets=scan.assets,
        skipped_files=scan.skipped_files,
    )
