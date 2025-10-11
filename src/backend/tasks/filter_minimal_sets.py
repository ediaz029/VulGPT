#!/usr/bin/env python3
"""Filter the generated minimal version sets down to a manageable subset.

This script reads the consolidated minimal version JSON (as produced by
``vulnerability_repo_mapper.py``), enriches each package with repository
metadata, and writes out a filtered JSON containing only the repositories that
match the desired criteria (language, repo size, stars, etc.). The metadata is
pulled from Neo4j when available and otherwise fetched from the GitHub API.

Example:
    uv run python -m src.backend.tasks.filter_minimal_sets \
        --input package_minimal_sets_OSV_20251009_185832.json \
        --output package_minimal_sets_filtered.json \
        --languages Python JavaScript TypeScript \
        --max-repo-size-mb 50

Environment:
    * ``GITHUB_TOKEN`` (optional) – increases the GitHub rate limit.
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional

import requests
from packageurl import PackageURL

# Local imports
PROJECT_SRC = Path(__file__).resolve().parents[2]
if str(PROJECT_SRC) not in sys.path:
    sys.path.append(str(PROJECT_SRC))

from backend.api.osv.neo4j_connection import get_neo4j_driver  # type: ignore  # noqa: E402

LOG = logging.getLogger(__name__)

HTTPS_PREFIX = "https://"
GITHUB_API = f"{HTTPS_PREFIX}api.github.com"


@dataclass
class RepoMetadata:
    repo_url: str
    owner: str
    name: str
    primary_language: str | None
    languages: dict[str, int]
    size_kb: int
    stars: int

    @property
    def size_mb(self) -> float:
        return self.size_kb / 1024.0

    @property
    def dominant_languages(self) -> list[str]:
        if not self.languages:
            return [lang for lang in [self.primary_language] if lang]
        return [lang for lang, _ in Counter(self.languages).most_common(3)]


class RepositoryMetadataFetcher:
    def __init__(self, github_token: str | None = None) -> None:
        self._github_session = requests.Session()
        if github_token:
            self._github_session.headers["Authorization"] = f"token {github_token}"
        self._driver = get_neo4j_driver()

    def close(self) -> None:
        if self._driver:
            self._driver.close()
        self._github_session.close()

    def get_metadata(self, package_name: str, ecosystem: str, purl: str) -> Optional[RepoMetadata]:
        meta = self._fetch_from_neo4j(package_name, ecosystem)
        if meta:
            return meta

        repo_full_name = self._repo_from_purl(purl)
        if not repo_full_name:
            LOG.debug("Unable to resolve repo from purl %s", purl)
            return None

        meta = self._fetch_from_github(repo_full_name)
        if meta and self._driver:
            self._store_in_neo4j(package_name, ecosystem, meta)
        return meta

    # ------------------------------------------------------------------
    # Neo4j helpers
    def _fetch_from_neo4j(self, package_name: str, ecosystem: str) -> Optional[RepoMetadata]:
        if not self._driver:
            return None

        query = """
        MATCH (p:Package {name: $name, ecosystem: $ecosystem})-[:HAS_REPO_METADATA]->(m:RepoMetadata)
        RETURN m.repo_url AS repo_url,
               m.owner AS owner,
               m.name AS name,
               m.primary_language AS primary_language,
               m.languages AS languages,
               m.size_kb AS size_kb,
               m.stars AS stars
        LIMIT 1
        """
        with self._driver.session() as session:
            record = session.run(query, name=package_name, ecosystem=ecosystem).single()
        if not record:
            return None

        languages = record.get("languages") or {}
        if isinstance(languages, str):
            try:
                languages = json.loads(languages)
            except Exception:
                languages = {}

        return RepoMetadata(
            repo_url=record["repo_url"],
            owner=record["owner"],
            name=record["name"],
            primary_language=record.get("primary_language"),
            languages={k: int(v) for k, v in languages.items()},
            size_kb=int(record.get("size_kb", 0) or 0),
            stars=int(record.get("stars", 0) or 0),
        )

    def _store_in_neo4j(self, package_name: str, ecosystem: str, meta: RepoMetadata) -> None:
        if not self._driver:
            return
        query = """
        MERGE (p:Package {name: $name, ecosystem: $ecosystem})
        MERGE (m:RepoMetadata {repo_url: $repo_url})
        SET m.owner = $owner,
            m.name = $repo_name,
            m.primary_language = $primary_language,
            m.languages = $languages_json,
            m.size_kb = $size_kb,
            m.stars = $stars
        MERGE (p)-[:HAS_REPO_METADATA]->(m)
        """
        owner = meta.owner or "unknown"
        repo_name = meta.name or owner
        primary_language = meta.primary_language or "unknown"
        languages_json = json.dumps(meta.languages)
        size_kb = int(meta.size_kb or 0)
        stars = int(meta.stars or 0)
        params = {
            "name": package_name,
            "ecosystem": ecosystem,
            "repo_url": meta.repo_url,
            "repo_name": repo_name,
            "primary_language": primary_language,
            "languages_json": languages_json,
            "size_kb": size_kb,
            "stars": stars,
            "owner": owner,
        }
        with self._driver.session() as session:
            session.run(query, **params)

    # ------------------------------------------------------------------
    # GitHub helpers
    def _repo_from_purl(self, purl_str: str) -> Optional[str]:
        if not purl_str:
            return None
        try:
            purl = PackageURL.from_string(purl_str)
        except ValueError:
            return None

        if purl.type in {"github", "gitlab", "bitbucket"} and purl.namespace and purl.name:
            return f"{purl.namespace}/{purl.name}"

        if purl.type == "composer" and purl.namespace and purl.name:
            return f"{purl.namespace}/{purl.name}"

        if purl.type in {"npm", "pypi", "python"}:
            # The purl itself does not have repo info; try to infer via registry API.
            repo_url = self._repo_url_from_registry(purl)
            if repo_url:
                return self._extract_repo_full_name(repo_url)
            return None

        return None

    def _repo_url_from_registry(self, purl: PackageURL) -> Optional[str]:
        if purl.type == "npm":
            return self._npm_repo_url(purl)
        if purl.type in {"pypi", "python"}:
            return self._pypi_repo_url(purl)
        return None

    def _npm_repo_url(self, purl: PackageURL) -> Optional[str]:
        name = f"{purl.namespace}/{purl.name}" if purl.namespace else purl.name
        resp = self._github_session.get(f"https://registry.npmjs.org/{name}", timeout=15)
        if resp.status_code != 200:
            return None
        repo = (resp.json() or {}).get("repository") or {}
        raw_url = repo.get("url", "")
        return self._normalize_git_url(raw_url)

    def _pypi_repo_url(self, purl: PackageURL) -> Optional[str]:
        resp = self._github_session.get(f"https://pypi.org/pypi/{purl.name}/json", timeout=15)
        if resp.status_code != 200:
            return None
        info = (resp.json() or {}).get("info") or {}
        project_urls = info.get("project_urls") or {}
        raw = project_urls.get("Source") or project_urls.get("Homepage") or info.get("home_page", "")
        return self._normalize_git_url(raw)

    def _normalize_git_url(self, raw_url: str | None) -> Optional[str]:
        if not raw_url:
            return None
        url = raw_url.strip()
        url = url.removeprefix("git+")
        if url.startswith("git@"):
            host, path = url[len("git@") :].split(":", 1)
            return f"https://{host}/{path}"
        if url.startswith("ssh://git@"):
            rest = url[len("ssh://git@") :]
            return f"https://{rest}"
        if url.startswith("git://"):
            rest = url[len("git://") :]
            return f"https://{rest}"
        if url.startswith("http://") or url.startswith(HTTPS_PREFIX):
            return url
        return None

    def _extract_repo_full_name(self, repo_url: str | None) -> Optional[str]:
        if not repo_url:
            return None
        cleaned = repo_url.rstrip("/").removesuffix(".git")
        if cleaned.startswith(HTTPS_PREFIX):
            cleaned = cleaned[len(HTTPS_PREFIX) :]
        github_prefix = "github.com/"
        gitlab_prefix = "gitlab.com/"
        bitbucket_prefix = "bitbucket.org/"
        if cleaned.startswith(github_prefix):
            return cleaned[len(github_prefix) :]
        if cleaned.startswith(gitlab_prefix):
            return cleaned[len(gitlab_prefix) :]
        if cleaned.startswith(bitbucket_prefix):
            return cleaned[len(bitbucket_prefix) :]
        return None

    def _fetch_from_github(self, full_name: str) -> Optional[RepoMetadata]:
        repo_resp = self._github_session.get(f"{GITHUB_API}/repos/{full_name}", timeout=20)
        if repo_resp.status_code != 200:
            LOG.warning("GitHub repo lookup failed for %s: %s", full_name, repo_resp.status_code)
            return None
        repo_data = repo_resp.json()

        languages_resp = self._github_session.get(f"{GITHUB_API}/repos/{full_name}/languages", timeout=20)
        languages = languages_resp.json() if languages_resp.status_code == 200 else {}

        return RepoMetadata(
            repo_url=repo_data.get("html_url", f"https://github.com/{full_name}"),
            owner=repo_data.get("owner", {}).get("login", full_name.split("/", 1)[0]),
            name=repo_data.get("name", full_name.split("/", 1)[1]),
            primary_language=repo_data.get("language"),
            languages={k: int(v) for k, v in (languages or {}).items()},
            size_kb=int(repo_data.get("size", 0)),
            stars=int(repo_data.get("stargazers_count", 0)),
        )


def filter_minimal_sets(
    input_path: Path,
    output_path: Path,
    desired_languages: Iterable[str],
    max_repo_size_mb: float,
    min_stars: int,
    limit: Optional[int] = None,
) -> dict[str, dict]:
    LOG.info("Loading minimal sets from %s", input_path)
    data = json.loads(input_path.read_text())

    token = os.getenv("GITHUB_TOKEN")
    fetcher = RepositoryMetadataFetcher(token)
    desired_languages_normalized = {lang.lower() for lang in desired_languages}
    max_repo_size_kb = max_repo_size_mb * 1024

    filtered: dict[str, dict] = {}
    stats = Counter()

    try:
        for pkg_name, pkg_info in data.items():
            if limit and len(filtered) >= limit:
                break

            ecosystem = pkg_info.get("ecosystem", "")
            purl = pkg_info.get("purl", "")

            meta = fetcher.get_metadata(pkg_name, ecosystem, purl)
            if not meta:
                stats["missing_metadata"] += 1
                continue

            stats["considered"] += 1

            languages_lower = {lang.lower() for lang in meta.dominant_languages if lang}
            if desired_languages_normalized and not languages_lower.intersection(desired_languages_normalized):
                stats["language_mismatch"] += 1
                continue

            if meta.size_kb > max_repo_size_kb:
                stats["too_large"] += 1
                continue

            if meta.stars < min_stars:
                stats["too_few_stars"] += 1
                continue

            filtered[pkg_name] = {
                **pkg_info,
                "repo_metadata": {
                    "repo_url": meta.repo_url,
                    "owner": meta.owner,
                    "name": meta.name,
                    "primary_language": meta.primary_language,
                    "languages": meta.languages,
                    "size_kb": meta.size_kb,
                    "stars": meta.stars,
                },
            }
            stats["accepted"] += 1
    finally:
        fetcher.close()

    LOG.info("Filtering stats: %s", dict(stats))
    output_path.write_text(json.dumps(filtered, indent=2))
    LOG.info("Wrote %d filtered packages to %s", len(filtered), output_path)

    return filtered


def build_argparser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Filter minimal version sets to manageable repositories")
    parser.add_argument("--input", type=Path, required=True, help="Path to package_minimal_sets JSON file")
    parser.add_argument("--output", type=Path, required=True, help="Destination for filtered JSON")
    parser.add_argument("--languages", nargs="*", default=["Python", "JavaScript", "TypeScript"], help="Accepted languages")
    parser.add_argument("--max-repo-size-mb", type=float, default=50.0, help="Maximum repository size (MiB)")
    parser.add_argument("--min-stars", type=int, default=0, help="Minimum GitHub stars required")
    parser.add_argument("--limit", type=int, default=None, help="Optional maximum number of packages to keep")
    parser.add_argument("--log-level", default="INFO", help="Logging level")
    return parser


def main(argv: Optional[list[str]] = None) -> int:
    parser = build_argparser()
    args = parser.parse_args(argv)

    logging.basicConfig(level=getattr(logging, args.log_level.upper(), logging.INFO), format="%(levelname)s:%(name)s:%(message)s")

    try:
        filter_minimal_sets(
            input_path=args.input,
            output_path=args.output,
            desired_languages=args.languages,
            max_repo_size_mb=args.max_repo_size_mb,
            min_stars=args.min_stars,
            limit=args.limit,
        )
    except Exception as exc:
        LOG.exception("Filtering failed: %s", exc)
        return 1
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
