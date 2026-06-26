from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


def run_doctor(out: Path = Path(".artifacts")) -> dict:
    checks = [
        _python_check(),
        _git_check(),
        _output_permission_check(out),
        _openai_image_check(),
        _mermaid_check(),
    ]
    if any(check["status"] == "fail" for check in checks):
        status = "fail"
    elif any(check["status"] == "warn" for check in checks):
        status = "warn"
    else:
        status = "pass"
    return {"status": status, "checks": checks}


def render_doctor_text(report: dict) -> str:
    lines = [f"Doctor status: {report['status']}"]
    for check in report["checks"]:
        lines.append(f"- {check['name']}: {check['status']} - {check['detail']}")
    return "\n".join(lines)


def _python_check() -> dict:
    version = sys.version_info
    status = "pass" if version >= (3, 11) else "fail"
    return {
        "name": "python",
        "status": status,
        "detail": f"{version.major}.{version.minor}.{version.micro}",
    }


def _git_check() -> dict:
    git = shutil.which("git")
    if not git:
        return {"name": "git", "status": "fail", "detail": "git executable not found"}
    try:
        result = subprocess.run(
            [git, "--version"],
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return {"name": "git", "status": "fail", "detail": "git did not run successfully"}
    return {"name": "git", "status": "pass", "detail": result.stdout.strip()}


def _output_permission_check(out: Path) -> dict:
    parent = out.expanduser().resolve().parent
    if not parent.exists():
        return {"name": "output", "status": "fail", "detail": f"parent does not exist: {parent}"}
    try:
        with tempfile.NamedTemporaryFile(prefix=".artifact-builder-doctor-", dir=parent, delete=True):
            pass
    except OSError as exc:
        return {"name": "output", "status": "fail", "detail": str(exc)}
    return {"name": "output", "status": "pass", "detail": f"writable parent: {parent}"}


def _openai_image_check() -> dict:
    if not os.environ.get("OPENAI_API_KEY"):
        return {
            "name": "openai-images",
            "status": "warn",
            "detail": "OPENAI_API_KEY not set, --render-images will use the stub provider",
        }
    model = os.environ.get("PAB_IMAGE_MODEL", "gpt-image-1.5")
    return {"name": "openai-images", "status": "pass", "detail": f"configured model: {model}"}


def _mermaid_check() -> dict:
    tool = shutil.which("mmdc") or shutil.which("mermaid")
    if not tool:
        return {
            "name": "mermaid",
            "status": "warn",
            "detail": "Mermaid renderer not found, source .mmd files will still be generated",
        }
    return {"name": "mermaid", "status": "pass", "detail": tool}

