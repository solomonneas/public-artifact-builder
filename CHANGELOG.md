# Changelog

All notable changes to Public Artifact Builder will be documented here.

This project follows human-readable release notes. Version numbers should be updated in `pyproject.toml` before tagging.

## 0.1.0 - Unreleased

### Added
- CLI-first artifact generation with `artifact-builder analyze`.
- Deterministic `artifact-map.json`, markdown outputs, Mermaid sources, and static `preview.html`.
- Strict privacy scanner with blocking behavior, leak check markdown, JSON privacy report, and optional SARIF.
- Review, policy initialization, and approval workflows.
- Publish readiness hashes for artifact map, privacy report, and optional reviewed policy.
- Dry-run-first generated artifact cleanup command.
- Environment doctor command.
- Pytest coverage for scanner behavior, privacy detection, schema shape, markdown snapshots, Mermaid generation, renderer abstraction, review, approval, doctor, and cleanup.

### Notes
- Image rendering is optional and uses a stub unless `OPENAI_API_KEY` is configured.
- `PAB_IMAGE_MODEL` can override the default image model.

