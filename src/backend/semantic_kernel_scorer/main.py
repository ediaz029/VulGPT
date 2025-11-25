"""FastAPI service that wraps Semantic Kernel for scoring vulnerability leads."""
from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from semantic_kernel import Kernel
from semantic_kernel.connectors.ai.open_ai import AzureChatCompletion, OpenAIChatCompletion
from semantic_kernel.contents import ChatHistory
from semantic_kernel.connectors.ai.function_choice_behavior import FunctionChoiceBehavior
from semantic_kernel.connectors.ai.chat_completion_client_base import ChatCompletionClientBase

from .agent import get_scoring_prompt

load_dotenv()

# Determine which AI service to use based on environment variables
USE_AZURE = bool(os.getenv("AZURE_OPENAI_ENDPOINT"))
if USE_AZURE:
    if not all([
        os.getenv("AZURE_OPENAI_ENDPOINT"),
        os.getenv("AZURE_OPENAI_API_KEY"),
        os.getenv("AZURE_OPENAI_DEPLOYMENT_NAME")
    ]):
        raise RuntimeError(
            "Azure OpenAI requires: AZURE_OPENAI_ENDPOINT, AZURE_OPENAI_API_KEY, "
            "and AZURE_OPENAI_DEPLOYMENT_NAME in environment or .env file."
        )
else:
    if not os.getenv("OPENAI_API_KEY"):
        raise RuntimeError(
            "OpenAI API key required. Set OPENAI_API_KEY in environment or .env file. "
            "Alternatively, configure Azure OpenAI with AZURE_OPENAI_* variables."
        )

app = FastAPI(title="Semantic Kernel Vulnerability Scoring Service", version="0.1.0")


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
    source: str = "semantic_kernel"


def create_kernel() -> Kernel:
    """Initialize Semantic Kernel with appropriate AI service."""
    kernel = Kernel()
    
    if USE_AZURE:
        service_id = "azure_chat"
        kernel.add_service(
            AzureChatCompletion(
                service_id=service_id,
                endpoint=os.getenv("AZURE_OPENAI_ENDPOINT"),
                api_key=os.getenv("AZURE_OPENAI_API_KEY"),
                deployment_name=os.getenv("AZURE_OPENAI_DEPLOYMENT_NAME"),
            )
        )
    else:
        service_id = "openai_chat"
        # Default to gpt-4-turbo if not specified
        model_id = os.getenv("OPENAI_MODEL_ID", "gpt-4-turbo")
        kernel.add_service(
            OpenAIChatCompletion(
                service_id=service_id,
                ai_model_id=model_id,
                api_key=os.getenv("OPENAI_API_KEY"),
            )
        )
    
    return kernel


def build_user_message(lead: Dict[str, Any], ground_truth: List[Dict[str, Any]]) -> str:
    """Construct the user message with lead and ground truth data."""
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

    return "\n".join(lead_lines + truth_lines)


def parse_response(response_text: str) -> Dict[str, Any]:
    """Parse and validate the AI response."""
    text = response_text.strip()
    
    # Remove markdown code fences if present
    if text.startswith("```"):
        lines = text.split("\n")
        # Remove first line (```json or ```)
        lines = lines[1:]
        # Remove last line if it's just ```
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    
    try:
        data = json.loads(text)
        return data
    except json.JSONDecodeError as exc:
        raise ValueError(f"AI did not return valid JSON: {text}") from exc


async def invoke_kernel(kernel: Kernel, lead: Dict[str, Any], ground_truth: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Invoke Semantic Kernel to score the vulnerability lead."""
    chat_service = kernel.get_service(type=ChatCompletionClientBase)
    
    # Build chat history with system prompt and user message
    chat_history = ChatHistory()
    chat_history.add_system_message(get_scoring_prompt())
    chat_history.add_user_message(build_user_message(lead, ground_truth))
    
    # Get chat completion
    response = await chat_service.get_chat_message_content(
        chat_history=chat_history,
        settings=chat_service.get_prompt_execution_settings_class()(
            temperature=0.0,  # Deterministic for scoring
            max_tokens=500,
        ),
    )
    
    if not response or not response.content:
        raise ValueError("Semantic Kernel returned empty response")
    
    return parse_response(response.content)


@app.get("/health")
async def health() -> Dict[str, str]:
    """Health check endpoint."""
    return {"status": "ok", "service": "semantic_kernel"}


@app.post("/score", response_model=ScoreResponse)
async def score_lead(request: ScoreRequest) -> ScoreResponse:
    """Score a vulnerability lead against ground truth."""
    kernel = create_kernel()
    
    try:
        result = await invoke_kernel(kernel, request.lead, request.ground_truth)
    except ValueError as exc:
        raise HTTPException(status_code=502, detail=str(exc))
    except Exception as exc:  # pragma: no cover - unexpected failure
        raise HTTPException(status_code=500, detail=f"Kernel invocation failed: {exc}")
    
    score = int(result.get("score", 0))
    reasoning = str(result.get("reasoning", ""))
    corresponds_to = result.get("corresponds_to")
    if corresponds_to is not None:
        corresponds_to = str(corresponds_to)
    
    if score not in {0, 1}:
        raise HTTPException(status_code=502, detail=f"Invalid score returned: {score}")
    
    return ScoreResponse(
        score=score,
        reasoning=reasoning,
        corresponds_to=corresponds_to,
        source="semantic_kernel"
    )
