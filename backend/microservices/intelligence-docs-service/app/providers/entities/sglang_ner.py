import json
import logging
import httpx

from app.providers.base import EntityProvider, Entity

logger = logging.getLogger(__name__)

NER_SYSTEM_PROMPT = """Extract named entities from the text. Return a JSON array of objects with "type" and "value" fields.
Entity types: PERSON, ORGANIZATION, DATE, AMOUNT, LOCATION.
Only return the JSON array, no other text. If no entities found, return [].
Example: [{"type":"PERSON","value":"Maria Lopez"},{"type":"DATE","value":"2024-03-15"}]"""


class SglangNerProvider(EntityProvider):
    """Extract entities via direct OpenAI-compatible API calls to SGLang."""

    name = "sglang"

    def __init__(self, base_url: str, model: str, timeout: int = 60):
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._timeout = timeout

    async def extract_entities(self, text: str, language: str = "es") -> list[Entity]:
        if not self._model:
            return []

        truncated = text[:4000] if len(text) > 4000 else text

        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.post(
                    f"{self._base_url}/chat/completions",
                    json={
                        "model": self._model,
                        "messages": [
                            {"role": "system", "content": NER_SYSTEM_PROMPT},
                            {"role": "user", "content": truncated},
                        ],
                        "temperature": 0.1,
                        "max_tokens": 1024,
                    },
                )
                response.raise_for_status()
                data = response.json()

            content = data["choices"][0]["message"]["content"].strip()
            start = content.find("[")
            end = content.rfind("]") + 1
            if start == -1 or end == 0:
                return []

            raw_entities = json.loads(content[start:end])
            return [
                Entity(
                    type=e.get("type", "UNKNOWN"),
                    value=e.get("value", ""),
                    provider="sglang",
                    confidence=e.get("confidence", 0.8),
                )
                for e in raw_entities
                if e.get("value")
            ]
        except (json.JSONDecodeError, KeyError) as e:
            logger.warning(f"Failed to parse SGLang NER response: {e}")
            return []
        except Exception as e:
            logger.warning(f"SGLang NER failed: {e}")
            return []

    async def is_available(self) -> bool:
        if not self._model:
            return False
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                resp = await client.get(f"{self._base_url}/models")
                return resp.status_code == 200
        except Exception:
            return False
