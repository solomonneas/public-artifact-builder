from pathlib import Path

from artifact_builder.scanner import (
    ScannerConfig,
    detect_components,
    detect_data_stores,
    detect_deployment_clues,
    detect_entrypoints,
    detect_services,
    detect_stack,
    detect_workflows,
    scan_repo,
)


FIXTURE = Path(__file__).parent / "fixtures" / "sample_repo"
FRAMEWORK_FIXTURE = Path(__file__).parent / "fixtures" / "framework_repo"


def test_scanner_detects_project_structure():
    scan = scan_repo(FIXTURE, str(FIXTURE))

    assert scan.project_name == "sample-ops-dashboard"
    assert "README.md" in scan.text_files
    assert "src/main.ts" in scan.text_files

    stack = detect_stack(scan)
    assert {item.name for item in stack} >= {"Node.js", "React", "Vite", "TypeScript"}

    components = detect_components(scan)
    assert {item.name for item in components} >= {"src"}

    services = detect_services(scan)
    assert {item.name for item in services} >= {"web", "redis"}

    workflows = detect_workflows(scan)
    assert any(workflow.name == "CI" for workflow in workflows)
    assert any(workflow.name == "npm test" for workflow in workflows)

    data_stores = detect_data_stores(scan)
    assert any(item.name == "Redis" for item in data_stores)

    entrypoints = detect_entrypoints(scan)
    assert any(item.path == "src/main.ts" for item in entrypoints)

    deployment = detect_deployment_clues(scan)
    assert any(item.name == "Compose" for item in deployment)
    assert any(item.name == "GitHub Actions" for item in deployment)


def test_scanner_detects_additional_frameworks_and_services():
    scan = scan_repo(FRAMEWORK_FIXTURE, str(FRAMEWORK_FIXTURE))

    stack = {item.name for item in detect_stack(scan)}
    assert stack >= {"NestJS", "SvelteKit", "Fastify", "Prisma", "Vue", "Flask", "SQLAlchemy", "Celery"}

    services = {item.name for item in detect_services(scan)}
    assert services >= {"Flask app", "Celery worker"}

    deployment = detect_deployment_clues(scan)
    assert any(item.name == "Kubernetes manifest" for item in deployment)


def test_scanner_include_exclude_and_skip_reporting():
    scan = scan_repo(
        FIXTURE,
        str(FIXTURE),
        ScannerConfig(include=("README.md", "package.json"), exclude=("package.json",)),
    )

    assert list(scan.text_files) == ["README.md"]
    assert any(item.path == "package.json" and item.reason == "matched by exclude filters" for item in scan.skipped_files)
    assert any(item.reason == "not matched by include filters" for item in scan.skipped_files)
