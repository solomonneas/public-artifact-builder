# Repository Guidance

## Definition of Done
```
./scripts/verify
```
It runs the full pytest suite, the `artifact-builder` doctor/analyze/review/approve smoke flow, and the untracked-bundle guard, in order, failing fast.

A change is done only when ALL of these pass from the repo root (use `.venv`, it exists; otherwise `python3 -m venv .venv && . .venv/bin/activate && python -m pip install -e ".[dev]"`):

```
pytest                            # full suite, 24 tests, must all pass
artifact-builder doctor --format json
artifact-builder analyze tests/fixtures/sample_repo --privacy strict --out .artifacts/ci-sample --format json
artifact-builder review .artifacts/ci-sample --format json
artifact-builder approve .artifacts/ci-sample --format json
test -z "$(git ls-files .artifacts artifacts .venv)"   # CI enforces this
```

These mirror `.github/workflows/ci.yml`. Report actual results, not expectations. If anything fails, report the failure verbatim and do not claim success.

## Project Shape
- Python 3.11+ Typer CLI (`artifact-builder`, entry `artifact_builder.cli:app` in `pyproject.toml`) that turns a local repo or GitHub URL into a privacy-gated publishable artifact bundle (case study, README rewrite, LinkedIn post, Mermaid diagrams, privacy report).
- Subcommands: `doctor`, `analyze`, `review`, `approve`, `init-policy`, `clean`.
- Flow: `scanner.py` walks the repo and runs privacy detection, `pipeline.py` builds `artifact-map.json`, `generators.py` writes all public outputs from that map. `privacy.py` holds detection rules, `policy.py` handles `.artifact-builder-privacy.json` allow/deny lists, `approval.py` writes `publish-readiness.json` with SHA-256 hashes.
- Image rendering (`renderers.py`) is a stub unless `OPENAI_API_KEY` is set. Model defaults to `gpt-image-1.5`, override with `PAB_IMAGE_MODEL`. The renderer only receives scrubbed Mermaid source and metadata.
- Tests in `tests/`, fixture repos in `tests/fixtures/`, golden markdown in `tests/snapshots/`.

## Snapshot Tests
- `test_markdown_snapshots` compares four generated files byte-for-byte (modulo trailing whitespace) against `tests/snapshots/*.md`: `case-study.md`, `architecture.md`, `README.rewrite.md`, `linkedin-post.md`.
- Intentional generator wording change: regenerate with `artifact-builder analyze tests/fixtures/sample_repo --privacy strict --out /tmp/snap --format json`, copy those four files into `tests/snapshots/`, re-run `pytest`, then read `git diff tests/snapshots/` and explain every changed line in your report. Commit snapshots and generator change together.
- Snapshot failure you did not intend: that is a bug in your change. Fix the code. Never regenerate snapshots to silence a failure you cannot explain.

## Privacy Gate (the product)
- The privacy gate is the product. Never weaken detection rules, redaction, or the privacy report to make output look cleaner or to make a test pass. If a rule seems wrong, report it as a finding and stop.
- Strict mode must keep blocking public markdown and diagram generation on high-risk findings, while still writing `artifact-map.json` and `leak-check.md` for review.
- Public outputs are generated only from `artifact-map.json` with scrubbed labels, never from raw source dumps. Do not add code paths that feed raw source into generators or renderers.
- `--acknowledge-risks` is the only sanctioned bypass for blocked strict runs. Do not add silent bypasses or new bypass flags.

## Hard Prohibitions
- Failing test: fix the cause. Never delete, skip, xfail, or loosen an assertion to get green.
- Generated bundles (`.artifacts/`, `artifacts/`) and `.venv/`: never `git add` them. CI fails if any are tracked.
- `/memory/` and `.brigade/` are local-only working state (gitignored). Never commit them.
- Never push with `--no-verify` if a pre-push hook exists. Hooks are part of the gate.
- Blocked (missing tool, ambiguous spec, failing baseline): report the exact blocker and stop. Do not work around it silently.

## Operational Rules
- Changing one module: run its test file first (`pytest tests/test_scanner.py`), then the full suite before reporting done.
- Writing a test that needs a repo input: use `tests/fixtures/`, never a live clone. Passing a GitHub URL to `analyze` shells out to `git clone` (see `scanner.py`).
- Running tests or reviews: leave `OPENAI_API_KEY` unset so image rendering stays a stub and makes no external API calls.
- Running CLI commands by hand: pytest imports `artifact_builder` via `pythonpath = ["src"]` without an install, but the `artifact-builder` command needs the editable install in `.venv`.
- Choosing an output dir: `analyze` defaults `--out` to `artifacts/project` (gitignored). Prefer `./.artifacts/<name>` as in the README.
- Cutting a release: update `CHANGELOG.md` and the version in `pyproject.toml`, run the Definition of Done commands, confirm generated artifacts are untracked, then tag.

## Memory Handoff
At the end of any substantial task, write a handoff note to `.claude/memory-handoffs/` using that directory's `TEMPLATE.md`. Record durable discoveries, gotchas, and decisions. Do not wait to be reminded.
