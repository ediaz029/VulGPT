"""FastAPI service that wraps the ADK agent for scoring vulnerability leads."""
from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from google.adk.runners import InMemoryRunner
from google.genai import types
from pydantic import BaseModel, Field

from .agent import root_agent

load_dotenv()

if not os.getenv("GOOGLE_API_KEY"):
    raise RuntimeError("GOOGLE_API_KEY is required for the ADK agent. Set it in the environment or .env file.")

app = FastAPI(title="ADK Vulnerability Scoring Service", version="0.1.0")

RUNNER_APP_NAME = "vuln-scoring-service"
SERVICE_USER_ID = "scoring-service"


class LeadModel(BaseModel):
    headline: Optional[str] = None
    analysis: Optional[str] = None
    cwe: Optional[str] = None
    function_names: Optional[List[str]] = None
    filenames: Optional[List[str]] = None


class GroundTruthModel(BaseModel):
    id: str
    summary: Optional[str] = None
    details: Optional[str] = None
    aliases: Optional[List[str]] = None


class ScoreRequest(BaseModel):
    lead: Dict[str, Any]
    ground_truth: List[Dict[str, Any]] = Field(default_factory=list)


class ScoreResponse(BaseModel):
    score: int
    reasoning: str
    corresponds_to: Optional[str] = None
    source: str = "adk"


@app.get("/health")
async def health() -> Dict[str, str]:
    return {"status": "ok"}


def build_prompt(lead: Dict[str, Any], ground_truth: List[Dict[str, Any]]) -> str:
    lead_lines = ["Lead candidate:"]
    for key, value in lead.items():
        lead_lines.append(f"  {key}: {value}")

    truth_lines = ["Ground truth vulnerabilities:"]
    if not ground_truth:
        truth_lines.append("  (none provided)")
    else:
        for vuln in ground_truth:
            truth_lines.append(
                "  - "
                + json.dumps(
                    {
                        "id": vuln.get("id"),
                        "summary": vuln.get("summary"),
                        "details": vuln.get("details"),
                        "aliases": vuln.get("aliases"),
                    },
                    ensure_ascii=False,
                )
            )

    prompt = "\n".join(
        [
            "You receive a candidate vulnerability lead and the list of ground-truth vulnerabilities.",
            "Return JSON with keys reasoning (string), score (0 or 1), and corresponds_to (nullable string).",
            "Only return JSON, do not include markdown fences or additional commentary.",
            *lead_lines,
            *truth_lines,
        ]
    )
    return prompt


def normalize_agent_output(raw_output: Any) -> Dict[str, Any]:
    if isinstance(raw_output, dict):
        return raw_output

    text = getattr(raw_output, "output", None)
    if text is None and hasattr(raw_output, "output_text"):
        text = raw_output.output_text
    if text is None:
        text = str(raw_output)

    text = text.strip()
    if text.startswith("```"):
        text = text.strip("`")
        text = text.split("\n", 1)[-1]

    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Agent did not return valid JSON: {text}") from exc


def _extract_text_from_parts(parts: List[types.Part]) -> Optional[str]:
    snippets: List[str] = []
    for part in parts:
        text = getattr(part, "text", None)
        if text:
            snippets.append(text)
    if not snippets:
        return None
    combined = "".join(snippets).strip()
    return combined or None


async def invoke_agent(prompt: str) -> Dict[str, Any]:
    runner = InMemoryRunner(agent=root_agent.clone(), app_name=RUNNER_APP_NAME)
    session = await runner.session_service.create_session(
        app_name=runner.app_name,
        user_id=SERVICE_USER_ID,
    )
    user_message = types.Content(
        role="user",
        parts=[types.Part(text=prompt)],
    )

    responses: List[str] = []
    async with runner:
        async for event in runner.run_async(
            user_id=session.user_id,
            session_id=session.id,
            new_message=user_message,
        ):
            if event.partial or not event.content or not event.content.parts:
                continue
            text = _extract_text_from_parts(event.content.parts)
            if text:
                responses.append(text)

    if not responses:
        raise ValueError("Agent returned no textual response")

    return normalize_agent_output(responses[-1])


@app.post("/score", response_model=ScoreResponse)
async def score_lead(request: ScoreRequest) -> ScoreResponse:
    prompt = build_prompt(request.lead, request.ground_truth)

    try:
        agent_output = await invoke_agent(prompt)
    except ValueError as exc:
        raise HTTPException(status_code=502, detail=str(exc))
    except Exception as exc:  # pragma: no cover - unexpected agent failure
        raise HTTPException(status_code=500, detail=f"Agent invocation failed: {exc}")

    score = int(agent_output.get("score", 0))
    reasoning = str(agent_output.get("reasoning", ""))
    corresponds_to = agent_output.get("corresponds_to")
    if corresponds_to is not None:
        corresponds_to = str(corresponds_to)

    if score not in {0, 1}:
        raise HTTPException(status_code=502, detail=f"Invalid score returned by agent: {score}")

    return ScoreResponse(score=score, reasoning=reasoning, corresponds_to=corresponds_to)
