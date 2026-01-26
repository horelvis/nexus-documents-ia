"""
Outline Generator

Uses LLM (via vLLM) to generate presentation outlines from document content.
"""
import json
import logging
import re
from typing import List, Optional, Dict, Any

import httpx

from app.core.config import settings
from app.schemas import SlideOutline, SourceInfo, PresentationConfig

logger = logging.getLogger(__name__)


class OutlineGenerator:
    """Generates presentation outlines using LLM."""

    def __init__(self):
        self.vllm_base_url = settings.vllm_base_url
        self.model = settings.vllm_model
        self.max_tokens = settings.vllm_max_tokens
        self.temperature = settings.vllm_temperature

    async def generate_outline(
        self,
        sources: List[SourceInfo],
        config: PresentationConfig,
    ) -> List[SlideOutline]:
        """
        Generate a presentation outline from source documents.

        Args:
            sources: List of source documents with content
            config: Presentation configuration

        Returns:
            List of slide outlines
        """
        # Prepare content summary for the LLM
        content_text = self._prepare_content(sources)

        # Build the prompt
        prompt = self._build_prompt(content_text, config)

        logger.info(f"Generating outline with {len(sources)} sources, max {config.max_slides} slides")

        try:
            # Call vLLM
            response = await self._call_llm(prompt)

            # Parse the response into slide outlines
            outlines = self._parse_response(response, config.max_slides)

            logger.info(f"Generated {len(outlines)} slide outlines")
            return outlines

        except Exception as e:
            logger.error(f"Failed to generate outline: {e}")
            raise

    def _prepare_content(self, sources: List[SourceInfo]) -> str:
        """Prepare document content for the prompt."""
        content_parts = []

        for source in sources:
            # Truncate content if too long (keep first 5000 chars per source)
            content = source.content[:5000] if len(source.content) > 5000 else source.content
            content_parts.append(f"=== {source.title} ===\n{content}")

        return "\n\n".join(content_parts)

    def _build_prompt(self, content: str, config: PresentationConfig) -> str:
        """Build the LLM prompt for outline generation."""
        language_instructions = {
            "es-ES": "Genera el contenido en español.",
            "en-US": "Generate the content in English.",
            "pt-BR": "Gere o conteudo em portugues.",
        }

        lang_instruction = language_instructions.get(
            config.language,
            language_instructions["es-ES"]
        )

        focus_text = ""
        if config.focus_topics:
            focus_text = f"\nEnfocate especialmente en estos temas: {', '.join(config.focus_topics)}"

        notes_instruction = ""
        if config.include_speaker_notes:
            notes_instruction = '\n- "speaker_notes": Notas para el presentador (1-2 oraciones explicativas)'

        prompt = f"""Eres un experto en crear presentaciones profesionales. Tu tarea es crear un esquema de presentacion PowerPoint basado en el siguiente contenido.

{lang_instruction}
{focus_text}

INSTRUCCIONES:
1. Crea exactamente {config.max_slides} diapositivas
2. Cada diapositiva debe tener un titulo claro y conciso
3. Incluye 3-5 puntos clave por diapositiva (bullet points)
4. Los puntos deben ser concisos (maximo 10-15 palabras cada uno)
5. La primera diapositiva debe ser una introduccion/titulo
6. La ultima diapositiva debe ser un resumen o conclusiones

FORMATO DE RESPUESTA (JSON):
Responde SOLO con un array JSON valido, sin texto adicional:
[
  {{
    "slide_number": 1,
    "title": "Titulo de la diapositiva",
    "bullet_points": ["Punto 1", "Punto 2", "Punto 3"]{notes_instruction}
  }}
]

CONTENIDO DEL DOCUMENTO:
{content}

RESPUESTA (solo JSON):"""

        return prompt

    async def _call_llm(self, prompt: str) -> str:
        """Call the vLLM API."""
        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.post(
                f"{self.vllm_base_url}/chat/completions",
                json={
                    "model": self.model,
                    "messages": [
                        {
                            "role": "system",
                            "content": "Eres un asistente experto en crear presentaciones profesionales. Responde siempre en formato JSON valido."
                        },
                        {
                            "role": "user",
                            "content": prompt
                        }
                    ],
                    "max_tokens": self.max_tokens,
                    "temperature": self.temperature,
                },
            )
            response.raise_for_status()
            data = response.json()

            return data["choices"][0]["message"]["content"]

    def _parse_response(self, response: str, max_slides: int) -> List[SlideOutline]:
        """Parse the LLM response into slide outlines."""
        # Clean up the response - remove markdown code blocks if present
        response = response.strip()
        if response.startswith("```"):
            # Remove markdown code blocks
            response = re.sub(r"^```(?:json)?\s*", "", response)
            response = re.sub(r"\s*```$", "", response)

        # Try to extract JSON from the response
        try:
            # Find JSON array in response
            json_match = re.search(r'\[[\s\S]*\]', response)
            if json_match:
                response = json_match.group()

            slides_data = json.loads(response)
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse LLM response as JSON: {e}")
            logger.debug(f"Raw response: {response}")
            # Return a fallback single slide
            return [
                SlideOutline(
                    slide_number=1,
                    title="Resumen del Documento",
                    bullet_points=["Error al generar el esquema detallado", "Por favor intente nuevamente"],
                    speaker_notes=None,
                )
            ]

        # Convert to SlideOutline objects
        outlines = []
        for i, slide in enumerate(slides_data[:max_slides], start=1):
            outline = SlideOutline(
                slide_number=i,
                title=slide.get("title", f"Diapositiva {i}"),
                bullet_points=slide.get("bullet_points", []),
                speaker_notes=slide.get("speaker_notes"),
            )
            outlines.append(outline)

        return outlines

    async def health_check(self) -> bool:
        """Check if vLLM is available."""
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(f"{self.vllm_base_url}/models")
                return response.status_code == 200
        except Exception:
            return False
