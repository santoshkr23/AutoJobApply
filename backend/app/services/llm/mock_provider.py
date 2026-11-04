"""Offline sandbox provider. Clearly labelled: results are heuristic, not model-generated."""

import json

from app.schemas.ai import (
    LLMCoverLetter,
    LLMJobAnalysis,
    LLMMatchExplanation,
    LLMParsedResume,
    LLMTailoredResume,
)
from app.services import heuristics, mock_ai
from app.services.llm.base import LLMError, LLMProvider, LLMUsage, T


class MockProvider(LLMProvider):
    name = "mock"
    is_mock = True

    def complete(self, *, task: str, system: str, inputs: dict[str, str], schema: type[T], tier: str = "default"):
        if task == "parse_resume":
            data = heuristics.parse_resume_text(inputs["resume"])
            result = LLMParsedResume.model_validate(data)
        elif task == "analyze_job":
            data = heuristics.analyze_job_text(inputs.get("job_title", ""), inputs.get("job_description", ""))
            result = LLMJobAnalysis.model_validate(data)
        elif task == "tailor_resume":
            result = LLMTailoredResume.model_validate(
                mock_ai.mock_tailor(
                    json.loads(inputs["candidate_profile"]), json.loads(inputs["job_analysis"]), json.loads(inputs["job"])
                )
            )
        elif task == "cover_letter":
            result = LLMCoverLetter.model_validate(
                mock_ai.mock_cover_letter(
                    json.loads(inputs["candidate_profile"]), json.loads(inputs["job"]), json.loads(inputs["job_analysis"])
                )
            )
        elif task == "explain_match":
            result = LLMMatchExplanation.model_validate(mock_ai.mock_explain(json.loads(inputs["match"])))
        else:
            raise LLMError(f"Unknown task {task}")
        if not isinstance(result, schema):
            raise LLMError("Schema mismatch")
        return result, LLMUsage(provider=self.name, model="heuristic-v1")
