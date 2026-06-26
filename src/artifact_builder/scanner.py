from __future__ import annotations

import fnmatch
import json
import os
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

from .models import (
    Component,
    DeploymentClue,
    EntryPoint,
    GitMetadata,
    PublicClaim,
    Risk,
    ScanResult,
    SkippedFile,
    SourceRef,
    StackItem,
    Workflow,
)

IGNORE_DIRS = {
    ".git",
    ".claude",
    ".codex",
    ".cursor",
    ".hg",
    ".idea",
    ".svn",
    ".venv",
    "venv",
    "node_modules",
    "dist",
    "build",
    "target",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    ".artifacts",
    "artifacts",
}

TEXT_SUFFIXES = {
    ".md",
    ".txt",
    ".py",
    ".js",
    ".jsx",
    ".ts",
    ".tsx",
    ".json",
    ".toml",
    ".yaml",
    ".yml",
    ".ini",
    ".cfg",
    ".env",
    ".example",
    ".sh",
    ".Dockerfile",
    ".gradle",
}

ASSET_SUFFIXES = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg"}
DEFAULT_MAX_TEXT_BYTES = 80_000
DEFAULT_MAX_TEXT_FILES = 160
MAX_SKIPPED_REPORTS = 250


@dataclass(frozen=True)
class ScannerConfig:
    include: tuple[str, ...] = ()
    exclude: tuple[str, ...] = ()
    max_text_bytes: int = DEFAULT_MAX_TEXT_BYTES
    max_text_files: int = DEFAULT_MAX_TEXT_FILES
    skipped_report_limit: int = MAX_SKIPPED_REPORTS


def resolve_repo(repo: str, work_dir: Path) -> tuple[Path, str]:
    ssh_github_prefix = "git" + "@github.com:"
    if repo.startswith(("https://github.com/", ssh_github_prefix)):
        work_dir.mkdir(parents=True, exist_ok=True)
        target = work_dir / _repo_name_from_url(repo)
        subprocess.run(
            ["git", "clone", "--depth", "1", repo, str(target)],
            check=True,
            capture_output=True,
            text=True,
        )
        return target, repo

    path = Path(repo).expanduser().resolve()
    if not path.exists() or not path.is_dir():
        raise FileNotFoundError(f"Repository path does not exist: {repo}")
    return path, str(path)


def scan_repo(repo_path: Path, source: str, config: ScannerConfig | None = None) -> ScanResult:
    config = config or ScannerConfig()
    files: list[Path] = []
    text_files: dict[str, str] = {}
    assets: list[str] = []
    skipped: list[SkippedFile] = []

    for root, dirs, names in os.walk(repo_path):
        root_path = Path(root)
        relative_root = root_path.relative_to(repo_path)
        pruned: list[str] = []
        for dirname in sorted(dirs):
            relative_dir = relative_root / dirname if relative_root != Path(".") else Path(dirname)
            reason = _skip_reason(relative_dir, config, is_dir=True)
            if reason:
                _record_skip(skipped, relative_dir.as_posix(), reason, config)
            else:
                pruned.append(dirname)
        dirs[:] = pruned

        for name in sorted(names):
            path = root_path / name
            relative = path.relative_to(repo_path)
            reason = _skip_reason(relative, config, is_dir=False)
            if reason:
                _record_skip(skipped, relative.as_posix(), reason, config)
                continue
            files.append(relative)
            if path.suffix.lower() in ASSET_SUFFIXES:
                assets.append(relative.as_posix())
            if _is_text_candidate(path):
                if len(text_files) >= config.max_text_files:
                    _record_skip(skipped, relative.as_posix(), "text file limit reached", config)
                    continue
                text = _read_text(path, config.max_text_bytes)
                if text is None:
                    _record_skip(skipped, relative.as_posix(), "text file too large or unreadable", config)
                else:
                    text_files[relative.as_posix()] = text

    return ScanResult(
        repo_path=repo_path,
        project_name=_detect_project_name(repo_path, text_files),
        source=source,
        files=files,
        text_files=text_files,
        assets=assets,
        git=_read_git_metadata(repo_path),
        skipped_files=skipped,
    )


def detect_stack(scan: ScanResult) -> list[StackItem]:
    stack: list[StackItem] = []
    file_names = {path.as_posix() for path in scan.files}

    def add(name: str, category: str, confidence: float, path: str) -> None:
        if not any(item.name == name for item in stack):
            stack.append(
                StackItem(
                    name=name,
                    category=category,
                    confidence=confidence,
                    sources=[SourceRef(path=path, kind="file", confidence=confidence)],
                )
            )

    if "package.json" in file_names:
        add("Node.js", "runtime", 0.9, "package.json")
        package = _json_file(scan, "package.json")
        deps = {**package.get("dependencies", {}), **package.get("devDependencies", {})}
        for dep, label in {
            "@angular/core": "Angular",
            "@nestjs/core": "NestJS",
            "@remix-run/react": "Remix",
            "@sveltejs/kit": "SvelteKit",
            "@vue/runtime-core": "Vue",
            "astro": "Astro",
            "axios": "Axios",
            "drizzle-orm": "Drizzle ORM",
            "fastify": "Fastify",
            "graphql": "GraphQL",
            "hono": "Hono",
            "mongoose": "Mongoose",
            "react": "React",
            "next": "Next.js",
            "vite": "Vite",
            "express": "Express",
            "prisma": "Prisma",
            "svelte": "Svelte",
            "typescript": "TypeScript",
            "tailwindcss": "Tailwind CSS",
            "vue": "Vue",
        }.items():
            if dep in deps:
                add(label, "framework", 0.85, "package.json")
    if "pyproject.toml" in file_names:
        add("Python", "runtime", 0.9, "pyproject.toml")
        text = scan.text_files.get("pyproject.toml", "")
        for needle, label in {
            "typer": "Typer",
            "fastapi": "FastAPI",
            "django": "Django",
            "flask": "Flask",
            "sqlalchemy": "SQLAlchemy",
            "celery": "Celery",
            "rq": "RQ",
            "uvicorn": "Uvicorn",
            "gunicorn": "Gunicorn",
            "pytest": "pytest",
            "pydantic": "Pydantic",
        }.items():
            if needle in text.lower():
                add(label, "library", 0.8, "pyproject.toml")
    if "requirements.txt" in file_names:
        add("Python", "runtime", 0.75, "requirements.txt")
        text = scan.text_files.get("requirements.txt", "")
        for needle, label in {
            "fastapi": "FastAPI",
            "django": "Django",
            "flask": "Flask",
            "sqlalchemy": "SQLAlchemy",
            "celery": "Celery",
        }.items():
            if needle in text.lower():
                add(label, "library", 0.75, "requirements.txt")
    if "Cargo.toml" in file_names:
        add("Rust", "runtime", 0.9, "Cargo.toml")
    if "go.mod" in file_names:
        add("Go", "runtime", 0.9, "go.mod")
    if "Gemfile" in file_names:
        add("Ruby", "runtime", 0.85, "Gemfile")
        if "rails" in scan.text_files.get("Gemfile", "").lower():
            add("Rails", "framework", 0.8, "Gemfile")
    if "pom.xml" in file_names or "build.gradle" in file_names or "build.gradle.kts" in file_names:
        add("Java", "runtime", 0.8, "pom.xml")
    if "composer.json" in file_names:
        add("PHP", "runtime", 0.8, "composer.json")
        composer = _json_file(scan, "composer.json")
        deps = {**composer.get("require", {}), **composer.get("require-dev", {})}
        if "laravel/framework" in deps:
            add("Laravel", "framework", 0.8, "composer.json")
    if any(path.endswith("Dockerfile") or path == "Dockerfile" for path in file_names):
        add("Docker", "deployment", 0.85, "Dockerfile")
    if any(path.endswith((".yml", ".yaml")) and ".github/workflows/" in path for path in file_names):
        add("GitHub Actions", "ci", 0.85, ".github/workflows")

    return stack


def detect_components(scan: ScanResult) -> list[Component]:
    components: list[Component] = []
    dirs = {path.parts[0] for path in scan.files if len(path.parts) > 1}
    for dirname, description in {
        "src": "Primary application source code.",
        "app": "Application routes or runtime code.",
        "api": "API surface or service handlers.",
        "cli": "Command-line interface code.",
        "lib": "Shared library code.",
        "docs": "Project documentation.",
        "tests": "Automated tests and fixtures.",
        "scripts": "Operational or developer automation.",
    }.items():
        if dirname in dirs:
            components.append(
                Component(
                    name=dirname,
                    kind="directory",
                    description=description,
                    sources=[SourceRef(path=dirname, kind="directory", confidence=0.75)],
                )
            )
    return components


def detect_services(scan: ScanResult) -> list[Component]:
    services: list[Component] = []
    for path, text in scan.text_files.items():
        lower = text.lower()
        if path.endswith(("docker-compose.yml", "docker-compose.yaml", "compose.yml")):
            for service in re.findall(r"(?m)^  ([a-zA-Z0-9_-]+):\s*$", text):
                services.append(
                    Component(
                        name=service,
                        kind="container",
                        description="Container service declared in Compose configuration.",
                        sources=[SourceRef(path=path, kind="compose", confidence=0.8)],
                    )
                )
        if "fastapi(" in lower:
            services.append(_source_component("FastAPI app", "api", path))
        if "flask(" in lower:
            services.append(_source_component("Flask app", "api", path))
        if "express()" in lower:
            services.append(_source_component("Express app", "api", path))
        if "fastify(" in lower:
            services.append(_source_component("Fastify app", "api", path))
        if "celery(" in lower or "celery_app" in lower:
            services.append(_source_component("Celery worker", "worker", path))
        if "mcp.server" in lower or "fastmcp" in lower:
            services.append(_source_component("MCP server", "integration", path))
    return _unique_components(services)


def detect_workflows(scan: ScanResult) -> list[Workflow]:
    workflows: list[Workflow] = []
    package = _json_file(scan, "package.json")
    scripts = package.get("scripts", {}) if isinstance(package.get("scripts", {}), dict) else {}
    for name, command in scripts.items():
        workflows.append(
            Workflow(
                name=f"npm {name}",
                trigger="developer command",
                steps=[str(command)],
                sources=[SourceRef(path="package.json", kind="script", confidence=0.85)],
            )
        )

    for path, text in scan.text_files.items():
        if ".github/workflows/" in path:
            workflow_name = _yaml_name(text) or Path(path).stem
            workflows.append(
                Workflow(
                    name=workflow_name,
                    trigger="GitHub Actions",
                    steps=_extract_yaml_steps(text),
                    sources=[SourceRef(path=path, kind="ci", confidence=0.8)],
                )
            )
        if re.search(r"\bagent\b|\bworkflow\b", text, re.IGNORECASE):
            workflows.append(
                Workflow(
                    name=f"{Path(path).stem} workflow",
                    trigger="detected in source",
                    steps=["Review source for agent or workflow orchestration details."],
                    sources=[SourceRef(path=path, kind="source", confidence=0.45)],
                )
            )
    return _unique_workflows(workflows)


def detect_data_stores(scan: ScanResult) -> list[Component]:
    found: list[Component] = []
    patterns = {
        "PostgreSQL": r"postgres|psycopg|pgvector",
        "SQLite": r"sqlite",
        "MySQL": r"\bmysql\b|pymysql|mysqlclient",
        "MariaDB": r"mariadb",
        "Redis": r"redis",
        "MongoDB": r"mongodb|mongoose",
        "Elasticsearch": r"elasticsearch",
        "OpenSearch": r"opensearch",
        "LanceDB": r"lancedb",
        "Qdrant": r"qdrant",
        "Pinecone": r"pinecone",
        "Chroma": r"chromadb|\bchroma\b",
        "S3-compatible object storage": r"\bs3\b|minio",
    }
    for path, text in scan.text_files.items():
        lower = text.lower()
        for name, pattern in patterns.items():
            if re.search(pattern, lower):
                found.append(
                    Component(
                        name=name,
                        kind="data_store",
                        description="Detected from project configuration or source references.",
                        sources=[SourceRef(path=path, kind="reference", confidence=0.65)],
                    )
                )
    return _unique_components(found)


def detect_entrypoints(scan: ScanResult) -> list[EntryPoint]:
    entrypoints: list[EntryPoint] = []
    package = _json_file(scan, "package.json")
    for key in ("main", "module", "bin"):
        value = package.get(key)
        if isinstance(value, str):
            entrypoints.append(EntryPoint(name=key, path=value, kind="package"))
        elif isinstance(value, dict):
            for name, path in value.items():
                entrypoints.append(EntryPoint(name=name, path=str(path), kind="package"))

    for candidate in (
        "src/main.py",
        "main.py",
        "app.py",
        "src/main.ts",
        "src/main.js",
        "src/index.ts",
        "src/index.js",
    ):
        if candidate in scan.text_files:
            entrypoints.append(EntryPoint(name=Path(candidate).stem, path=candidate))

    pyproject = scan.text_files.get("pyproject.toml", "")
    for match in re.findall(r"(?m)^([A-Za-z0-9_.-]+)\s*=\s*\"([A-Za-z0-9_.: -]+)\"$", pyproject):
        name, command = match
        if ":" in command:
            entrypoints.append(
                EntryPoint(name=name, path=command, command=name, kind="console_script")
            )
    return _unique_entrypoints(entrypoints)


def detect_deployment_clues(scan: ScanResult) -> list[DeploymentClue]:
    clues: list[DeploymentClue] = []
    for path in scan.files:
        name = path.name
        path_text = path.as_posix()
        if name == "Dockerfile" or name.endswith("Dockerfile"):
            clues.append(DeploymentClue(name="Dockerfile", kind="container", path=path_text))
        elif name in {"docker-compose.yml", "docker-compose.yaml", "compose.yml"}:
            clues.append(DeploymentClue(name="Compose", kind="container", path=path_text))
        elif name in {"vercel.json", "netlify.toml", "fly.toml"}:
            clues.append(DeploymentClue(name=name, kind="platform", path=path_text))
        elif ".github/workflows/" in path_text:
            clues.append(DeploymentClue(name="GitHub Actions", kind="ci", path=path_text))
        elif path.suffix in {".tf", ".tfvars"}:
            clues.append(DeploymentClue(name="Terraform", kind="infrastructure", path=path_text))
        elif name == "helmfile.yaml" or "helm" in path_text.lower():
            clues.append(DeploymentClue(name="Helm", kind="infrastructure", path=path_text))
        elif path.suffix in {".yaml", ".yml"} and "k8s" in path_text.lower():
            clues.append(DeploymentClue(name="Kubernetes manifest", kind="infrastructure", path=path_text))
        elif name in {"serverless.yml", "serverless.yaml"}:
            clues.append(DeploymentClue(name="Serverless", kind="platform", path=path_text))
    return clues


def detect_risks(scan: ScanResult) -> list[Risk]:
    risks: list[Risk] = []
    if not any(path.name.lower().startswith("readme") for path in scan.files):
        risks.append(
            Risk(
                name="Missing README",
                severity="medium",
                detail="Public positioning may need manual context because no README was detected.",
            )
        )
    if not any(path.parts and path.parts[0] == "tests" for path in scan.files):
        risks.append(
            Risk(
                name="No tests detected",
                severity="low",
                detail="No tests directory was detected during repository scan.",
            )
        )
    return risks


def build_summary(scan: ScanResult, stack: list[StackItem]) -> str:
    readme = _first_readme(scan)
    if readme:
        heading = next((line.strip("# ").strip() for line in readme.splitlines() if line.startswith("#")), "")
        paragraph = next(
            (
                line.strip()
                for line in readme.splitlines()
                if line.strip() and not line.startswith("#") and len(line.strip()) > 30
            ),
            "",
        )
        if paragraph:
            return paragraph[:400]
        if heading:
            return f"{heading} is a software project with detectable source and configuration structure."
    stack_names = ", ".join(item.name for item in stack[:4]) or "application code"
    return f"{scan.project_name} is a repository built around {stack_names}."


def build_public_claims(scan: ScanResult, stack: list[StackItem]) -> list[PublicClaim]:
    claims = [
        PublicClaim(
            claim=f"Includes a structured {scan.project_name} codebase suitable for technical review.",
            confidence=0.7,
            sources=[SourceRef(path=".", kind="repository", confidence=0.7)],
        )
    ]
    if stack:
        claims.append(
            PublicClaim(
                claim="Uses a detectable application stack: "
                + ", ".join(item.name for item in stack[:5])
                + ".",
                confidence=0.8,
                sources=[source for item in stack[:5] for source in item.sources],
            )
        )
    if scan.git.available:
        claims.append(
            PublicClaim(
                claim="Maintains git history suitable for release and implementation review.",
                confidence=0.65,
                sources=[SourceRef(path=".git", kind="metadata", confidence=0.65)],
            )
        )
    return claims


def _is_ignored(relative: Path) -> bool:
    return any(part in IGNORE_DIRS for part in relative.parts)


def _skip_reason(relative: Path, config: ScannerConfig, is_dir: bool) -> str | None:
    path = relative.as_posix()
    path_for_dir = f"{path}/" if is_dir else path
    if _is_ignored(relative):
        return "ignored directory" if is_dir else "ignored path"
    if config.include and not _matches_any(path, config.include):
        return "not matched by include filters"
    if config.exclude and (_matches_any(path, config.exclude) or _matches_any(path_for_dir, config.exclude)):
        return "matched by exclude filters"
    return None


def _matches_any(path: str, patterns: tuple[str, ...]) -> bool:
    return any(fnmatch.fnmatch(path, pattern) for pattern in patterns)


def _record_skip(skipped: list[SkippedFile], path: str, reason: str, config: ScannerConfig) -> None:
    if len(skipped) < config.skipped_report_limit:
        skipped.append(SkippedFile(path=path, reason=reason))


def _is_text_candidate(path: Path) -> bool:
    return (
        path.name in {"Dockerfile", ".env", ".env.example", "Makefile"}
        or path.suffix.lower() in TEXT_SUFFIXES
    )


def _read_text(path: Path, max_text_bytes: int) -> str | None:
    try:
        if path.stat().st_size > max_text_bytes:
            return None
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None


def _detect_project_name(repo_path: Path, text_files: dict[str, str]) -> str:
    package = _json_from_text(text_files.get("package.json", ""))
    if isinstance(package.get("name"), str):
        return package["name"].split("/")[-1]
    pyproject = text_files.get("pyproject.toml", "")
    match = re.search(r"(?m)^name\s*=\s*\"([^\"]+)\"", pyproject)
    if match:
        return match.group(1)
    return repo_path.name


def _read_git_metadata(repo_path: Path) -> GitMetadata:
    def git(args: list[str]) -> str | None:
        try:
            result = subprocess.run(
                ["git", *args],
                cwd=repo_path,
                check=True,
                capture_output=True,
                text=True,
            )
            return result.stdout.strip()
        except (OSError, subprocess.CalledProcessError):
            return None

    inside = git(["rev-parse", "--is-inside-work-tree"])
    if inside != "true":
        return GitMetadata()
    top_level = git(["rev-parse", "--show-toplevel"])
    if top_level and Path(top_level).resolve() != repo_path.resolve():
        return GitMetadata()
    remotes = git(["remote", "-v"]) or ""
    hosts = sorted({match.group(1) for match in re.finditer(r"[@/]([^/:]+)[/:][^/\s]+/[^/\s]+", remotes)})
    return GitMetadata(
        available=True,
        current_branch=git(["branch", "--show-current"]),
        latest_commit=git(["rev-parse", "--short", "HEAD"]),
        latest_commit_date=git(["log", "-1", "--format=%cI"]),
        remote_hosts=hosts,
    )


def _repo_name_from_url(repo: str) -> str:
    name = repo.rstrip("/").split("/")[-1]
    return name.removesuffix(".git") or "repo"


def _json_file(scan: ScanResult, path: str) -> dict:
    return _json_from_text(scan.text_files.get(path, ""))


def _json_from_text(text: str) -> dict:
    try:
        parsed = json.loads(text)
        return parsed if isinstance(parsed, dict) else {}
    except json.JSONDecodeError:
        return {}


def _source_component(name: str, kind: str, path: str) -> Component:
    return Component(
        name=name,
        kind=kind,
        description="Detected from source code references.",
        sources=[SourceRef(path=path, kind="source", confidence=0.65)],
    )


def _unique_components(components: list[Component]) -> list[Component]:
    seen: set[tuple[str, str]] = set()
    unique: list[Component] = []
    for component in components:
        key = (component.name, component.kind)
        if key not in seen:
            unique.append(component)
            seen.add(key)
    return unique


def _unique_workflows(workflows: list[Workflow]) -> list[Workflow]:
    seen: set[tuple[str, str]] = set()
    unique: list[Workflow] = []
    for workflow in workflows:
        key = (workflow.name, workflow.trigger)
        if key not in seen:
            unique.append(workflow)
            seen.add(key)
    return unique


def _unique_entrypoints(entrypoints: list[EntryPoint]) -> list[EntryPoint]:
    seen: set[tuple[str, str]] = set()
    unique: list[EntryPoint] = []
    for entrypoint in entrypoints:
        key = (entrypoint.name, entrypoint.path)
        if key not in seen:
            unique.append(entrypoint)
            seen.add(key)
    return unique


def _first_readme(scan: ScanResult) -> str:
    for path, text in scan.text_files.items():
        if Path(path).name.lower().startswith("readme"):
            return text
    return ""


def _yaml_name(text: str) -> str:
    match = re.search(r"(?m)^name:\s*[\"']?([^\"'\n]+)", text)
    return match.group(1).strip() if match else ""


def _extract_yaml_steps(text: str) -> list[str]:
    steps = re.findall(r"(?m)^\s*-\s+name:\s*[\"']?([^\"'\n]+)", text)
    return steps[:8] or ["Review CI workflow definition."]
