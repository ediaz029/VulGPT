#!/usr/bin/env python3
"""Clone repositories and check out minimal versions listed in the filtered manifest.

Given the output from ``filter_minimal_sets.py`` this script will:

1. Clone each repository (once) under a shared ``repos`` directory.
2. Attempt to resolve the minimal versions to git tags/refs.
3. Create git worktrees for the resolved versions under ``worktrees``.
4. Emit a manifest capturing the resolution status for downstream processing.

Example usage::

    PYTHONPATH=src uv run --project src/backend/api python src/backend/tasks/checkout_repos.py \
        --input src/backend/api/package_minimal_sets_filtered.json \
        --checkout-root data/repositories \
        --manifest-output data/checkout_manifest.json \
        --max-repos 50

The resulting ``checkout_manifest.json`` can then be fed into the scanning stage.
"""
from __future__ import annotations

import argparse
import json
import logging
import shutil
import subprocess
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Dict, Iterable, List, Optional

LOG = logging.getLogger(__name__)


@dataclass
class VersionResult:
    version: str
    status: str
    ref: Optional[str] = None
    commit: Optional[str] = None
    path: Optional[str] = None
    message: Optional[str] = None


@dataclass
class PackageResult:
    package: str
    ecosystem: str
    repo_url: str
    repo_path: str
    versions: List[VersionResult] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)


def build_argparser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Clone repositories and check out minimal versions")
    parser.add_argument("--input", type=Path, required=True, help="Path to filtered minimal sets JSON")
    parser.add_argument(
        "--checkout-root",
        type=Path,
        default=Path("data/repositories"),
        help="Base directory where repos and worktrees will be stored",
    )
    parser.add_argument(
        "--manifest-output",
        type=Path,
        default=Path("data/checkout_manifest.json"),
        help="Path to write the checkout manifest JSON",
    )
    parser.add_argument("--max-repos", type=int, default=None, help="Optional cap on number of packages to process")
    parser.add_argument("--force-reclone", action="store_true", help="Remove existing repo directories before cloning")
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Logging verbosity",
    )
    parser.add_argument(
        "--skip-worktree",
        action="store_true",
        help="Resolve commits only without creating git worktrees",
    )
    return parser


def sanitize_segment(segment: str) -> str:
    cleaned = segment.replace("/", "_").replace("\\", "_").replace(" ", "-")
    if not cleaned:
        cleaned = "unknown"
    return cleaned


def read_filtered_packages(path: Path) -> Dict[str, dict]:
    try:
        return json.loads(path.read_text())
    except FileNotFoundError as exc:
        raise SystemExit(f"Filtered package file not found: {path}") from exc


def run_git(cwd: Path, *args: str, check: bool = True, capture_output: bool = False) -> subprocess.CompletedProcess:
    cwd_path = cwd if cwd.is_absolute() else cwd.resolve()
    cmd = ["git", *args]
    LOG.debug("Running git command: %s (cwd=%s)", " ".join(cmd), cwd_path)
    return subprocess.run(
        cmd,
        cwd=str(cwd_path),
        check=check,
        text=True,
        capture_output=capture_output,
    )


def clone_or_update_repo(repo_url: str, dest: Path, force_reclone: bool) -> None:
    dest = dest if dest.is_absolute() else dest.resolve()

    if dest.exists():
        if force_reclone:
            LOG.info("Removing existing repo directory %s", dest)
            shutil.rmtree(dest)
        else:
            LOG.info("Updating existing repository %s", dest)
            try:
                run_git(dest, "fetch", "--all", "--tags", "--prune")
            except subprocess.CalledProcessError as exc:
                LOG.warning("Failed to fetch repo %s: %s", repo_url, exc)
            return

    dest.parent.mkdir(parents=True, exist_ok=True)
    LOG.info("Cloning %s into %s", repo_url, dest)
    try:
        run_git(dest.parent, "clone", repo_url, str(dest))
    except subprocess.CalledProcessError as exc:
        raise RuntimeError(f"Failed to clone {repo_url}: {exc}") from exc


def load_tags(repo_dir: Path) -> List[str]:
    try:
        result = run_git(repo_dir, "tag", "--list", capture_output=True)
    except subprocess.CalledProcessError as exc:
        LOG.warning("Unable to list tags in %s: %s", repo_dir, exc)
        return []
    tags = [line.strip() for line in (result.stdout or "").splitlines() if line.strip()]
    LOG.debug("Found %d tags in %s", len(tags), repo_dir)
    return tags


def resolve_ref_from_tags(tags: Iterable[str], version: str) -> Optional[str]:
    candidates = [version, f"v{version}", f"release-{version}", f"{version}-release"]
    tags_list = list(tags)

    for candidate in candidates:
        if candidate in tags_list:
            return candidate

    # Fallback: find first tag that ends with the version string.
    for tag in tags_list:
        normalized = tag.lower().lstrip("v")
        if normalized == version.lower():
            return tag

    partial_matches = [tag for tag in tags_list if version in tag]
    if partial_matches:
        return partial_matches[0]
    return None


def remove_path(path: Path) -> None:
    if path.exists():
        LOG.debug("Removing existing path %s", path)
        shutil.rmtree(path)


def add_worktree(repo_dir: Path, commit: str, worktree_path: Path) -> None:
    worktree_path.parent.mkdir(parents=True, exist_ok=True)
    if worktree_path.exists():
        remove_path(worktree_path)
    run_git(repo_dir, "worktree", "add", "--force", "--detach", str(worktree_path), commit)


def process_package(
    package_key: str,
    package_info: dict,
    repos_dir: Path,
    worktrees_dir: Path,
    force_reclone: bool,
    create_worktrees: bool,
) -> PackageResult:
    repo_meta = package_info.get("repo_metadata") or {}
    repo_url = repo_meta.get("repo_url")
    if not repo_url:
        raise ValueError(f"Package {package_key} is missing repo metadata")

    owner = sanitize_segment(repo_meta.get("owner", "unknown-owner"))
    name = sanitize_segment(repo_meta.get("name", "unknown-repo"))
    repo_dir = repos_dir / owner / name

    try:
        clone_or_update_repo(repo_url, repo_dir, force_reclone)
    except RuntimeError as exc:
        result = PackageResult(
            package=package_key,
            ecosystem=package_info.get("ecosystem", ""),
            repo_url=repo_url,
            repo_path=str(repo_dir),
            versions=[VersionResult(version=v, status="clone_failed", message=str(exc)) for v in package_info.get("minimal_versions", [])],
            notes=[str(exc)],
        )
        return result

    tags = load_tags(repo_dir)

    pkg_result = PackageResult(
        package=package_key,
        ecosystem=package_info.get("ecosystem", ""),
        repo_url=repo_url,
        repo_path=str(repo_dir),
    )

    for version in package_info.get("minimal_versions", []):
        version_result = checkout_version(
            repo_dir=repo_dir,
            version=version,
            tags=tags,
            package_key=package_key,
            worktrees_dir=worktrees_dir,
            create_worktrees=create_worktrees,
        )
        pkg_result.versions.append(version_result)
    return pkg_result


def checkout_version(
    repo_dir: Path,
    version: str,
    tags: List[str],
    package_key: str,
    worktrees_dir: Path,
    create_worktrees: bool,
) -> VersionResult:
    ref = resolve_ref_from_tags(tags, version)
    if not ref:
        return VersionResult(version=version, status="tag_not_found", message="No matching tag found")

    try:
        commit_proc = run_git(repo_dir, "rev-list", "-n", "1", ref, capture_output=True)
    except subprocess.CalledProcessError as exc:
        return VersionResult(version=version, status="resolve_failed", ref=ref, message=str(exc))

    commit = (commit_proc.stdout or "").strip()
    checkout_path = worktrees_dir / sanitize_segment(package_key) / sanitize_segment(version)

    if create_worktrees:
        try:
            add_worktree(repo_dir, commit, checkout_path)
            status = "checked_out"
            message = ""
        except subprocess.CalledProcessError as exc:
            status = "worktree_failed"
            message = str(exc)
            checkout_path = None
    else:
        status = "resolved"
        message = ""
        checkout_path = None

    return VersionResult(
        version=version,
        status=status,
        ref=ref,
        commit=commit,
        path=str(checkout_path) if checkout_path else None,
        message=message or None,
    )


def summarize_results(package_results: List[PackageResult]) -> Dict[str, int]:
    stats: Dict[str, int] = {}
    for pkg in package_results:
        for version in pkg.versions:
            stats[version.status] = stats.get(version.status, 0) + 1
    return stats


def write_manifest(path: Path, package_results: List[PackageResult]) -> None:
    payload = {
        "packages": [
            {
                "package": pkg.package,
                "ecosystem": pkg.ecosystem,
                "repo_url": pkg.repo_url,
                "repo_path": pkg.repo_path,
                "notes": pkg.notes,
                "versions": [asdict(v) for v in pkg.versions],
            }
            for pkg in package_results
        ],
        "stats": summarize_results(package_results),
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2))
    LOG.info("Wrote checkout manifest to %s", path)
    LOG.info("Status counts: %s", payload["stats"])


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_argparser()
    args = parser.parse_args(argv)

    logging.basicConfig(level=getattr(logging, args.log_level.upper()), format="%(levelname)s:%(name)s:%(message)s")

    input_path = args.input.expanduser().resolve()
    checkout_root = args.checkout_root.expanduser().resolve()
    manifest_output = args.manifest_output.expanduser().resolve()

    packages = read_filtered_packages(input_path)
    repos_dir = checkout_root / "repos"
    worktrees_dir = checkout_root / "worktrees"

    package_results: List[PackageResult] = []

    for idx, (package_key, package_info) in enumerate(packages.items(), start=1):
        if args.max_repos and idx > args.max_repos:
            break
        LOG.info("[%d] Processing %s", idx, package_key)
        try:
            result = process_package(
                package_key=package_key,
                package_info=package_info,
                repos_dir=repos_dir,
                worktrees_dir=worktrees_dir,
                force_reclone=args.force_reclone,
                create_worktrees=not args.skip_worktree,
            )
        except Exception as exc:  # pylint: disable=broad-except
            LOG.exception("Failed to process package %s", package_key)
            result = PackageResult(
                package=package_key,
                ecosystem=package_info.get("ecosystem", ""),
                repo_url=(package_info.get("repo_metadata") or {}).get("repo_url", ""),
                repo_path=str(repos_dir / sanitize_segment(package_key)),
                versions=[VersionResult(version=v, status="error", message=str(exc)) for v in package_info.get("minimal_versions", [])],
                notes=[str(exc)],
            )
        package_results.append(result)

    write_manifest(manifest_output, package_results)
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
