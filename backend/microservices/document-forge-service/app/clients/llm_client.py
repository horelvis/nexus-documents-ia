"""Lightweight LLM client for direct vLLM/SGLang communication (OpenAI-compatible)."""

import json
import logging
import re

import httpx

from app.core.config import get_settings

logger = logging.getLogger(__name__)


class ForgeLLMClient:
    """Direct HTTP client to vLLM/SGLang for field analysis.

    Uses PLANNER-like parameters: low temperature, no thinking, structured JSON output.
    """

    def __init__(self):
        settings = get_settings()
        self.base_url = settings.vllm_base_url
        self.model = settings.vllm_model_name
        self.default_temperature = settings.llm_temperature
        self.default_max_tokens = settings.llm_max_tokens

    async def chat(
        self,
        messages: list[dict],
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> str:
        """Send a chat completion request and return the content string."""
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature or self.default_temperature,
            "max_tokens": max_tokens or self.default_max_tokens,
        }

        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                f"{self.base_url}/chat/completions",
                json=payload,
                headers={"Authorization": "Bearer not-needed"},
            )
            response.raise_for_status()
            data = response.json()
            content = data["choices"][0]["message"]["content"]

        # Strip <think>...</think> tags if present (Qwen3 reasoning)
        content = re.sub(r"<think>.*?</think>", "", content, flags=re.DOTALL).strip()
        return content

    async def chat_json(
        self,
        messages: list[dict],
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> dict | list:
        """Send a chat completion and parse the response as JSON."""
        content = await self.chat(messages, temperature, max_tokens)
        # Try to extract JSON from the response
        return self._extract_json(content)

    @staticmethod
    def _extract_json(text: str) -> dict | list:
        """Extract JSON from LLM response, handling markdown code blocks."""
        # Try direct parse first
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

        # Try extracting from ```json ... ``` blocks
        match = re.search(r"```(?:json)?\s*\n?(.*?)\n?\s*```", text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(1))
            except json.JSONDecodeError:
                pass

        # Try finding first { or [ and matching to last } or ]
        for start_char, end_char in [("{", "}"), ("[", "]")]:
            start = text.find(start_char)
            end = text.rfind(end_char)
            if start != -1 and end > start:
                try:
                    return json.loads(text[start : end + 1])
                except json.JSONDecodeError:
                    continue

        raise ValueError(f"Could not parse JSON from LLM response: {text[:200]}...")


_client = None


def get_llm_client() -> ForgeLLMClient:
    global _client
    if _client is None:
        _client = ForgeLLMClient()
    return _client
