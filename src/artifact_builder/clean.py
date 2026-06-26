from __future__ import annotations

import shutil
from pathlib import Path


BUNDLE_MARKERS = {"artifact-map.json", "privacy-report.json"}


def plan_clean(root: Path = Path(".artifacts")) -> dict:
    root = root.expanduser().resolve()
    bundles = _find_bundles(root)
    return {
        "root": str(root),
        "exists": root.exists(),
        "bundle_count": len(bundles),
        "bundles": [str(path) for path in bundles],
    }


def apply_clean(root: Path = Path(".artifacts")) -> dict:
    plan = plan_clean(root)
    removed: list[str] = []
    for bundle in plan["bundles"]:
        path = Path(bundle)
        if not _is_safe_bundle(path, Path(plan["root"])):
            continue
        shutil.rmtree(path)
        removed.append(bundle)
    plan["removed"] = removed
    return plan


def render_clean_text(plan: dict, applied: bool = False) -> str:
    action = "Removed" if applied else "Would remove"
    lines = [
        f"Artifacts root: {plan['root']}",
        f"Bundles found: {plan['bundle_count']}",
    ]
    for bundle in plan["bundles"]:
        lines.append(f"- {action}: {bundle}")
    if not applied:
        lines.append("Dry run only. Rerun with --apply to remove these bundle directories.")
    return "\n".join(lines)


def _find_bundles(root: Path) -> list[Path]:
    if not root.exists() or not root.is_dir():
        return []
    bundles: list[Path] = []
    for path in sorted(root.rglob("*")):
        if path.is_dir() and any((path / marker).exists() for marker in BUNDLE_MARKERS):
            bundles.append(path)
    return bundles


def _is_safe_bundle(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
    except ValueError:
        return False
    return path.is_dir() and any((path / marker).exists() for marker in BUNDLE_MARKERS)

