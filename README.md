# Public Artifact Builder

Public Artifact Builder is a CLI for turning a local repository or GitHub URL into a publishable project artifact bundle for portfolio, blog, and social use. It favors deterministic structured extraction before any generative step, and it treats privacy scanning as a required gate.

## Install

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -e ".[dev]"
```

## Usage

Check the local environment:

```bash
artifact-builder doctor
```

Analyze a local repository:

```bash
artifact-builder analyze ./path/to/repo --audience hiring-manager --privacy strict --out ./.artifacts/my-project
```

Analyze a GitHub repository URL:

```bash
artifact-builder analyze https://github.com/example/project --audience hiring-manager --privacy strict --out ./.artifacts/project
```

Automation-friendly run with filters and JSON console output:

```bash
artifact-builder analyze ./path/to/repo --include "README.md" --include "src/**" --exclude "**/*.png" --format json --quiet --out ./.artifacts/project
```

Strict mode blocks public markdown and diagram generation when high-risk privacy findings are detected. It still writes `artifact-map.json` and `leak-check.md` so you can review the issue.

```bash
artifact-builder analyze ./path/to/repo --privacy strict --out ./.artifacts/review
```

If you intentionally accept the findings for a private review workflow, acknowledge them explicitly:

```bash
artifact-builder analyze ./path/to/repo --privacy strict --acknowledge-risks --out ./.artifacts/review
```

Review an existing bundle without exposing raw finding evidence:

```bash
artifact-builder review ./.artifacts/project
```

The review command reports `ready`, `needs-review`, or `blocked`, plus finding counts, finding types, skipped file reasons, missing outputs, and screenshot suggestions.

Initialize a repo-local privacy policy from a report:

```bash
artifact-builder init-policy ./path/to/repo --from-report ./.artifacts/project/privacy-report.json
```

The generated policy starts with an empty `allow` list and seeds `deny` only with stable non-credential candidate terms such as private hostnames, screenshot-risk names, customer-name findings, and existing custom-deny findings.

Approve a reviewed bundle:

```bash
artifact-builder approve ./.artifacts/project --policy ./path/to/repo/.artifact-builder-privacy.json
```

Approval writes `publish-readiness.json` with the bundle status and SHA-256 hashes for `artifact-map.json`, `privacy-report.json`, and the optional reviewed policy. A blocked report exits nonzero unless `--acknowledge-risks` is supplied.

Preview cleanup without deleting anything:

```bash
artifact-builder clean --root ./.artifacts
```

Apply cleanup:

```bash
artifact-builder clean --root ./.artifacts --apply
```

## Generated Artifacts

- `artifact-map.json`
- `privacy-report.json`
- `privacy-report.sarif`, when `--sarif` is enabled
- `case-study.md`
- `architecture.md`
- `README.rewrite.md`
- `linkedin-post.md`
- `portfolio-card.json`
- `preview.html`
- `screenshots-needed.md`
- `leak-check.md`
- `architecture.mmd`
- `request-flow.mmd`
- `data-flow.mmd`
- `agent-workflow.mmd`, when agent or workflow signals exist
- `threat-boundary.mmd`, when deployment or privacy boundary signals exist

`artifact-builder approve` also writes `publish-readiness.json`.

## Privacy Model

The scanner detects and flags:

- Internal IPs
- Private hostnames and domains
- Usernames, emails, and private filesystem paths
- Credential-like tokens, secrets, passwords, and API keys
- Sensitive environment variable names and assignments
- Customer or client names in obvious metadata patterns
- Infrastructure claims that expose private boundaries
- Screenshot or asset filenames likely to contain secrets

Public outputs are generated from `artifact-map.json`, not from arbitrary free-form source dumps. Mermaid diagrams are generated from detected structure and scrubbed labels. Image rendering is disabled by default and does not receive raw source files.

`privacy-report.json` is always written for automation. Use `--sarif` to also write `privacy-report.sarif` for code scanning integrations. The leak check includes scan skip summaries so large files, ignored directories, and include or exclude filters are visible during review.

### Project Privacy Policy

Repos can include `.artifact-builder-privacy.json` for project-specific privacy rules:

```json
{
  "allow": ["public@example.com"],
  "deny": ["ExamplePrivateTenant"]
}
```

Use `allow` only for exact public-safe false positives. Use `deny` for customer names, internal codenames, private service names, or other terms that must block strict-mode publishing even when they do not match the built-in detectors.

## Image Rendering Roadmap

The `--render-images` flag uses an `ImageRenderer` abstraction, prompt templates, and Mermaid-derived inputs. Without `OPENAI_API_KEY`, the renderer is a stub and no external API calls are made.

Set `OPENAI_API_KEY` to enable the OpenAI image renderer. The provider defaults to `gpt-image-1.5`, which is the current documented GPT Image model at the time this project was created. If GPT Image 2 is available to your account later, set `PAB_IMAGE_MODEL=gpt-image-2`.

```bash
OPENAI_API_KEY=... PAB_IMAGE_MODEL=gpt-image-2 artifact-builder analyze ./path/to/repo --privacy strict --render-images --out ./.artifacts/project
```

The renderer sends only scrubbed Mermaid source and artifact metadata. It refuses to render when strict privacy mode is blocked, and it writes rendered images next to the `.mmd` files.

Image generation must not invent architecture. Rendered images should visually represent the deterministic Mermaid sources produced from `artifact-map.json`.

## Roadmap

- Optional LLM rewrite provider behind an explicit privacy gate.
- Rendered diagram and social image providers.
- UI layer over the same scanner and generator services.
- More advanced project-specific allow and deny dictionaries.

## Release Notes

Release notes live in `CHANGELOG.md`. Before tagging a release, update the changelog, update the version in `pyproject.toml`, run tests, run a CLI smoke test, and confirm generated artifacts are not tracked by git.
