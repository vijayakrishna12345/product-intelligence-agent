"""Groq judge/simulator wrapper. Never default to OpenAI."""

from __future__ import annotations

import time

from pia.settings import get_settings


def _json_payload(text: str) -> str:
    stripped = (text or "").strip()
    if stripped.startswith("```"):
        stripped = stripped.strip("`")
        if stripped[:4].lower() == "json":
            stripped = stripped[4:].strip()
    start_obj = stripped.find("{")
    start_arr = stripped.find("[")
    starts = [index for index in (start_obj, start_arr) if index >= 0]
    if not starts:
        return stripped
    start = min(starts)
    end = max(stripped.rfind("}"), stripped.rfind("]"))
    if end > start:
        return stripped[start : end + 1]
    return stripped


class GroqJudge:
    """Thin DeepEvalBaseLLM adapter constructed only when Groq is configured."""

    @staticmethod
    def build(model: str | None = None):
        from deepeval.models import DeepEvalBaseLLM
        from groq import Groq, RateLimitError

        settings = get_settings()
        model_name = model or settings.groq_simulator_model

        class _Judge(DeepEvalBaseLLM):
            def __init__(self) -> None:
                self._client = Groq(api_key=settings.groq_api_key)
                self._model = model_name

            def load_model(self):
                return self._client

            def generate(self, prompt: str) -> str:
                last: Exception | None = None
                for attempt in range(6):
                    try:
                        completion = self._client.chat.completions.create(
                            model=self._model,
                            messages=[{"role": "user", "content": prompt}],
                            extra_body={"include_reasoning": False},
                        )
                        return _json_payload(completion.choices[0].message.content or "")
                    except RateLimitError as exc:
                        last = exc
                        time.sleep(2 * (attempt + 1))
                raise last or RuntimeError("Groq judge failed")

            async def a_generate(self, prompt: str) -> str:
                return self.generate(prompt)

            def get_model_name(self) -> str:
                return self._model

        return _Judge()
