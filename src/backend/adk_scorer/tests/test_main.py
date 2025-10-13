"""Unit tests for the ADK scoring service helpers."""
from __future__ import annotations

import unittest
from types import SimpleNamespace

from backend.adk_scorer.main import (
    _extract_text_from_parts,
    build_prompt,
    normalize_agent_output,
)


class TestScoringHelpers(unittest.TestCase):
    def test_build_prompt_includes_lead_and_ground_truth(self) -> None:
        prompt = build_prompt(
            {"headline": "issue"},
            [{"id": "CVE-123", "summary": "test"}],
        )

        self.assertIn("headline: issue", prompt)
        self.assertIn('"id": "CVE-123"', prompt)
        self.assertIn("Ground truth vulnerabilities:", prompt)

    def test_normalize_agent_output_passthrough_dict(self) -> None:
        payload = {"score": 1}

        self.assertEqual(normalize_agent_output(payload), payload)

    def test_normalize_agent_output_parses_plain_json_string(self) -> None:
        result = normalize_agent_output('{"score": 0}')

        self.assertEqual(result["score"], 0)

    def test_normalize_agent_output_handles_code_fence(self) -> None:
        payload = '```json\n{"score": 1, "reasoning": "ok"}\n```'

        result = normalize_agent_output(payload)

        self.assertEqual(result["score"], 1)
        self.assertEqual(result["reasoning"], "ok")

    def test_normalize_agent_output_raises_on_invalid_json(self) -> None:
        with self.assertRaises(ValueError):
            normalize_agent_output("not-json")

    def test_extract_text_from_parts_concatenates_text(self) -> None:
        parts = [SimpleNamespace(text="Hello"), SimpleNamespace(text=" World")]

        self.assertEqual(_extract_text_from_parts(parts), "Hello World")

    def test_extract_text_from_parts_ignores_missing_text(self) -> None:
        parts = [SimpleNamespace(), SimpleNamespace(text="\t")]

        self.assertIsNone(_extract_text_from_parts(parts))


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
