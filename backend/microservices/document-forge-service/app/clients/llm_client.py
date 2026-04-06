"""Lightweight LLM client for direct SGLang communication (OpenAI-compatible)."""

import json
import logging
import re

import httpx

from app.core.config import get_settings

logger = logging.getLogger(__name__)


class ForgeLLMClient:
    """Direct HTTP client to SGLang for field analysis.

    Uses PLANNER-like parameters: low temperature, no thinking, structured JSON output.
    """

    def __init__(self):
        settings = get_settings()
        self.base_url = settings.sglang_base_url
        self.model = settings.sglang_model_name
        self.default_temperature = settings.llm_temperature
        self.default_max_tokens = settings.llm_max_tokens

    async def _raw_chat(
        self,
        messages: list[dict],
        temperature: float | None = None,
        max_tokens: int | None = None,
        disable_thinking: bool = False,
    ) -> dict:
        """Send a chat completion request and return the raw message dict."""
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature or self.default_temperature,
            "max_tokens": max_tokens or self.default_max_tokens,
        }
        # Disable SGLang reasoning parser for structured JSON output
        if disable_thinking:
            payload["chat_template_kwargs"] = {"enable_thinking": False}

        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.post(
                f"{self.base_url}/chat/completions",
                json=payload,
                headers={"Authorization": "Bearer not-needed"},
            )
            response.raise_for_status()
            data = response.json()
            return data["choices"][0]["message"]

    async def chat(
        self,
        messages: list[dict],
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> str:
        """Send a chat completion request and return the content string."""
        message = await self._raw_chat(messages, temperature, max_tokens)
        content = message.get("content") or ""

        # SGLang with --reasoning-parser separates thinking into
        # reasoning_content field. If content is empty, check there.
        if not content.strip():
            reasoning = message.get("reasoning_content") or ""
            if reasoning:
                logger.info("Content was empty, using reasoning_content as fallback")
                content = reasoning

        # Strip <think>...</think> tags if present (Qwen3 reasoning)
        if content:
            content = re.sub(r"<think>.*?</think>", "", content, flags=re.DOTALL).strip()
        return content or ""

    async def chat_json(
        self,
        messages: list[dict],
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> dict | list:
        """Send a chat completion and parse the response as JSON.

        Handles SGLang reasoning parser: tries content first, then
        reasoning_content. If both fail, retries once with stronger
        JSON-only instructions.
        """
        # First attempt: disable thinking for clean JSON output
        message = await self._raw_chat(
            messages, temperature, max_tokens, disable_thinking=True,
        )
        content = message.get("content") or ""
        reasoning = message.get("reasoning_content") or ""

        # Strip think tags from both
        if content:
            content = re.sub(r"<think>.*?</think>", "", content, flags=re.DOTALL).strip()
        if reasoning:
            reasoning = re.sub(r"<think>.*?</think>", "", reasoning, flags=re.DOTALL).strip()

        # Try to extract JSON from content first
        if content:
            try:
                return self._extract_json(content)
            except ValueError:
                logger.debug("No JSON in content, trying reasoning_content")

        # Try reasoning_content (SGLang may put the JSON response there)
        if reasoning:
            try:
                return self._extract_json(reasoning)
            except ValueError:
                logger.debug("No JSON in reasoning_content either")

        # Both failed — retry once with explicit JSON-only instruction
        logger.warning(
            "No JSON found in LLM response (content=%d chars, reasoning=%d chars). Retrying...",
            len(content), len(reasoning),
        )
        retry_messages = messages.copy()
        # Replace last user message to add stronger JSON emphasis
        if retry_messages and retry_messages[-1]["role"] == "user":
            retry_messages[-1] = {
                "role": "user",
                "content": retry_messages[-1]["content"]
                + "\n\nIMPORTANT: Respond ONLY with the JSON object. No explanations, no thinking, no markdown. Just the raw JSON.",
            }

        message2 = await self._raw_chat(
            retry_messages, temperature, max_tokens, disable_thinking=True,
        )
        content2 = message2.get("content") or ""
        reasoning2 = message2.get("reasoning_content") or ""

        # Strip think tags
        if content2:
            content2 = re.sub(r"<think>.*?</think>", "", content2, flags=re.DOTALL).strip()
        if reasoning2:
            reasoning2 = re.sub(r"<think>.*?</think>", "", reasoning2, flags=re.DOTALL).strip()

        # Try content2 first, then reasoning2
        combined = (content2 + "\n" + reasoning2).strip()
        return self._extract_json(combined)

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
