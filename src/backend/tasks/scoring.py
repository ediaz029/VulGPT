"""Scoring utilities for vulnerability scan results.

This module orchestrates three steps after the primary Ollama scan finishes:

1. Fetch the ground-truth vulnerabilities for a package/version from OSV.
2. Forward each lead to an external ADK scoring service (with optional
   fallback to the local Ollama-based scorer) to obtain a binary score and
   supporting rationale.
3. Aggregate the per-lead judgments into precision/recall style metrics that
   mirror the eyeballvul paper.
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

import httpx

OSV_QUERY_URL = "https://api.osv.dev/v1/query"
LOG = logging.getLogger(__name__)


@dataclass
class ScoringConfig:
    """Configuration for the scoring pipeline."""

    enabled: bool
    endpoint: Optional[str]
    api_key: Optional[str]
    timeout: float = 60.0
    use_local_fallback: bool = True
    max_osv_retries: int = 3
    max_concurrency: int = 4


class RemoteScoringClient:
    """HTTP client for the external ADK scoring agent."""

    def __init__(self, base_url: str, api_key: Optional[str], timeout: float):
        self._client = httpx.AsyncClient(timeout=timeout)
        self._url = base_url.rstrip("/")
        self._api_key = api_key

    async def close(self) -> None:
        await self._client.aclose()

    async def score_lead(self, lead: Dict[str, Any], ground_truth: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
        headers = {"Content-Type": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"
        response = await self._client.post(
            self._url,
            json={"lead": lead, "ground_truth": list(ground_truth)},
            headers=headers,
        )
        response.raise_for_status()
        data = response.json()
        # Normalise the payload to the expected schema.
        return {
            "score": int(data.get("score", 0)),
            "reasoning": data.get("reasoning", ""),
            "corresponds_to": data.get("corresponds_to"),
            "source": "remote",
        }


class LocalScoringClient:
    """Fallback scorer that reuses the Ollama vulnerability scanner."""

    def __init__(self, scanner: Any):
        self._scanner = scanner

    async def score_lead(self, lead: Dict[str, Any], ground_truth: Sequence[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        response = await self._scanner.score_vulnerability(lead, list(ground_truth))
        if response is None:
            return None
        payload = response.model_dump()
        payload.update({"source": "local"})
        return payload


async def fetch_ground_truth(
    package: str,
    version: str,
    ecosystem: Optional[str],
    client: httpx.AsyncClient,
    retries: int,
    cache: Dict[Tuple[str, str, str], List[Dict[str, Any]]],
) -> List[Dict[str, Any]]:
    if not ecosystem:
        LOG.debug("No ecosystem metadata for %s; skipping OSV lookup", package)
        return []

    cache_key = (ecosystem, package, version)
    if cache_key in cache:
        return cache[cache_key]

    payload = {
        "package": {"name": package, "ecosystem": ecosystem},
        "version": version,
    }
    attempt = 0
    while attempt < max(1, retries):
        try:
            response = await client.post(OSV_QUERY_URL, json=payload)
            response.raise_for_status()
            data = response.json()
            vulns: List[Dict[str, Any]] = []
            for vuln in data.get("vulns", []):
                vuln_id = vuln.get("id")
                if not vuln_id:
                    continue
                vulns.append(
                    {
                        "id": vuln_id,
                        "summary": vuln.get("summary") or "",
                        "details": vuln.get("details") or "",
                        "aliases": vuln.get("aliases", []),
                    }
                )
            cache[cache_key] = vulns
            return vulns
        except httpx.HTTPError as exc:  # pragma: no cover - network failure path
            wait_seconds = 2 ** attempt
            LOG.warning(
                "OSV lookup failed for %s@%s (attempt %s/%s): %s",
                package,
                version,
                attempt + 1,
                retries,
                exc,
            )
            await asyncio.sleep(wait_seconds)
            attempt += 1
    LOG.error("Giving up on OSV lookup for %s@%s after %s attempts", package, version, retries)
    cache[cache_key] = []
    return []


async def score_leads_for_package(
    package_result: Dict[str, Any],
    ecosystem: Optional[str],
    ground_truth: List[Dict[str, Any]],
    remote_client: Optional[RemoteScoringClient],
    local_client: Optional[LocalScoringClient],
) -> Dict[str, Any]:
    leads = [
        lead
        for chunk in package_result.get("chunks", [])
        for lead in chunk.get("leads", [])
    ]
    evaluation: Dict[str, Any] = {
        "package": package_result.get("package"),
        "version": package_result.get("version"),
        "ecosystem": ecosystem,
        "ground_truth_count": len(ground_truth),
        "leads_evaluated": len(leads),
        "lead_scores": [],
        "errors": [],
    }

    if not leads:
        return evaluation

    for lead in leads:
        score_payload = None
        if remote_client:
            try:
                score_payload = await remote_client.score_lead(lead, ground_truth)
            except Exception as exc:  # pragma: no cover - network failure path
                LOG.warning("Remote scoring failed for %s: %s", evaluation["package"], exc)
                evaluation["errors"].append(f"remote_error: {exc}")
        if score_payload is None and local_client:
            score_payload = await local_client.score_lead(lead, ground_truth)
        if score_payload is None:
            evaluation["errors"].append("scoring_unavailable")
            continue

        score_payload.setdefault("reasoning", "")
        score_payload.setdefault("corresponds_to", None)
        evaluation["lead_scores"].append({**lead, **score_payload})

    return evaluation


def compute_metrics(evaluations: Iterable[Dict[str, Any]]) -> Dict[str, Any]:
    per_package: List[Dict[str, Any]] = []
    totals = {"true_positives": 0, "false_positives": 0, "false_negatives": 0}

    for evaluation in evaluations:
        truth_count = evaluation.get("ground_truth_count", 0)
        lead_scores = evaluation.get("lead_scores", [])
        matched_ids = {
            score.get("corresponds_to")
            for score in lead_scores
            if score.get("score") == 1 and score.get("corresponds_to")
        }
        tp = len(matched_ids)
        fp = sum(1 for score in lead_scores if score.get("score") == 0)
        fn = max(truth_count - tp, 0)
        precision = tp / (tp + fp) if (tp + fp) else None
        recall = tp / truth_count if truth_count else None

        per_package.append(
            {
                "package": evaluation.get("package"),
                "version": evaluation.get("version"),
                "ground_truth_count": truth_count,
                "true_positive_ids": sorted(matched_ids),
                "true_positive_count": tp,
                "false_positive_count": fp,
                "false_negative_count": fn,
                "precision": precision,
                "recall": recall,
            }
        )
        totals["true_positives"] += tp
        totals["false_positives"] += fp
        totals["false_negatives"] += fn

    totals_precision = None
    totals_recall = None
    if totals["true_positives"] or totals["false_positives"]:
        totals_precision = totals["true_positives"] / max(1, totals["true_positives"] + totals["false_positives"])
    if totals["true_positives"] or totals["false_negatives"]:
        totals_recall = totals["true_positives"] / max(1, totals["true_positives"] + totals["false_negatives"])

    return {
        "per_package": per_package,
        "totals": {
            **totals,
            "precision": totals_precision,
            "recall": totals_recall,
        },
    }


async def score_scan_results(
    scan_payload: Dict[str, Any],
    manifest_index: Dict[str, Dict[str, Any]],
    scoring_config: ScoringConfig,
    scanner: Any,
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    if not scoring_config.enabled:
        return [], {}

    remote_client = None
    if scoring_config.endpoint:
        remote_client = RemoteScoringClient(
            base_url=scoring_config.endpoint,
            api_key=scoring_config.api_key,
            timeout=scoring_config.timeout,
        )
    local_client = LocalScoringClient(scanner) if scoring_config.use_local_fallback else None

    evaluations: List[Dict[str, Any]] = []
    ground_truth_cache: Dict[Tuple[str, str, str], List[Dict[str, Any]]] = {}

    async with httpx.AsyncClient(timeout=scoring_config.timeout) as osv_client:
        for version_result in scan_payload.get("results", []):
            package_name = version_result.get("package")
            manifest_meta = manifest_index.get(package_name, {})
            ecosystem = manifest_meta.get("ecosystem")
            ground_truth = await fetch_ground_truth(
                package=package_name or "",
                version=version_result.get("version") or "",
                ecosystem=ecosystem,
                client=osv_client,
                retries=scoring_config.max_osv_retries,
                cache=ground_truth_cache,
            )
            evaluation = await score_leads_for_package(
                package_result=version_result,
                ecosystem=ecosystem,
                ground_truth=ground_truth,
                remote_client=remote_client,
                local_client=local_client,
            )
            evaluations.append(evaluation)

    if remote_client:
        await remote_client.close()

    metrics = compute_metrics(evaluations)
    return evaluations, metrics
