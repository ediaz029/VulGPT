"""ADK agent definition for vulnerability lead scoring."""
from __future__ import annotations

from google.adk.agents.llm_agent import Agent

SCORING_INSTRUCTION = (
    "You are a security evaluation assistant. "
    "Given a candidate vulnerability lead plus the list of ground-truth vulnerabilities, "
    "determine whether the lead corresponds to one of the real issues. "
    "Respond strictly as JSON with the keys 'reasoning', 'score', and 'corresponds_to'. "
    "Set 'score' to 1 only if the lead clearly matches a specific ground-truth vulnerability; "
    "otherwise return 0. For score 1 include the matching vulnerability ID in 'corresponds_to', "
    "and use null when the score is 0."
)

root_agent = Agent(
    model="gemini-2.5-flash",
    name="vuln_scoring_agent",
    description="Scores vulnerability leads against OSV ground-truth entries",
    instruction=SCORING_INSTRUCTION,
    tools=[],
)
