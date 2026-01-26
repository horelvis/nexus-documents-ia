"""
Script Generator Service

Uses Qwen3-4B-Thinking to generate podcast scripts from document sources.
Implements a multi-stage pipeline:
1. Analyze sources -> Extract key points and themes
2. Generate outline -> Structure the podcast flow
3. Generate dialogue -> Create natural conversation between hosts
4. Refine script -> Add disfluencies and natural speech patterns
"""
import logging
import json
import re
from typing import List, Optional, Dict, Any
from uuid import UUID

import httpx

from app.core.config import settings
from app.schemas import (
    SourceInfo, SourceAnalysis, ScriptOutline,
    ScriptSegment, PodcastScript, AudioConfig, AudioTone, AudioLength,
)

logger = logging.getLogger(__name__)


# Prompts for each stage of generation
ANALYZE_SOURCES_SYSTEM = """Eres un analista experto que extrae información clave de documentos.
Tu tarea es analizar los textos proporcionados e identificar:
1. Temas principales (3-5 temas)
2. Datos o insights interesantes
3. Conexiones entre conceptos
4. Preguntas que un oyente tendría

Responde SOLO en formato JSON válido con esta estructura:
{
    "main_themes": ["tema1", "tema2", ...],
    "key_insights": ["insight1", "insight2", ...],
    "interesting_facts": ["dato1", "dato2", ...],
    "potential_questions": ["pregunta1", "pregunta2", ...],
    "connections": ["conexión1", "conexión2", ...]
}"""

GENERATE_OUTLINE_SYSTEM = """Eres un guionista de podcasts experto.
Crea un outline para un podcast basado en el análisis proporcionado.

El podcast debe tener:
- Una introducción atractiva que enganche al oyente
- Temas principales bien estructurados
- Una conclusión que resuma los puntos clave

Responde SOLO en formato JSON válido:
{
    "introduction": "Texto de la introducción...",
    "main_topics": ["Tema 1: descripción", "Tema 2: descripción", ...],
    "conclusion": "Texto de la conclusión...",
    "estimated_duration_seconds": 300
}"""

GENERATE_DIALOGUE_SYSTEM = """Eres un escritor de diálogos para podcasts.
Genera un diálogo natural entre dos presentadores:
- Emma (Speaker A): Host principal, experta y entusiasta
- Alex (Speaker B): Co-host curioso, hace preguntas del oyente

REGLAS IMPORTANTES:
1. Usa lenguaje conversacional natural
2. Incluye transiciones fluidas entre temas
3. Alex debe hacer preguntas que el oyente tendría
4. Emma debe explicar de forma clara y accesible
5. Mantén el tono {tone}
6. Duración aproximada: {duration}

Responde SOLO en formato JSON válido con esta estructura:
{{
    "title": "Título del episodio",
    "segments": [
        {{"speaker": "A", "text": "Texto de Emma...", "segment_id": 1}},
        {{"speaker": "B", "text": "Texto de Alex...", "segment_id": 2}},
        ...
    ]
}}"""

REFINE_SCRIPT_SYSTEM = """Eres un editor de scripts de podcast que hace el diálogo más natural.
Tu tarea es añadir elementos de habla natural al script:
- Muletillas ocasionales: "sabes", "bueno", "es que", "mira"
- Pausas naturales indicadas con "..."
- Risas ocasionales: "(risas)"
- Expresiones de acuerdo: "exacto", "totalmente", "claro"
- Interjecciones: "wow", "increíble", "interesante"

NO cambies el contenido sustancial, solo hazlo más natural.
Mantén el formato JSON con la misma estructura de entrada."""


class ScriptGenerator:
    """
    Generates podcast scripts using Qwen3-4B-Thinking LLM.

    The generation pipeline:
    1. analyze_sources() - Extract key points from documents
    2. generate_outline() - Create podcast structure
    3. generate_dialogue() - Write the actual conversation
    4. refine_script() - Add natural speech patterns
    """

    def __init__(self):
        self.vllm_url = settings.vllm_base_url
        self.model = settings.vllm_model
        self.client = httpx.AsyncClient(timeout=120.0)

    async def _call_llm(
        self,
        system_prompt: str,
        user_content: str,
        max_tokens: int = 4096,
        temperature: float = 0.7,
    ) -> str:
        """Call vLLM with the given prompts."""
        url = f"{self.vllm_url}/chat/completions"

        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content},
            ],
            "max_tokens": max_tokens,
            "temperature": temperature,
        }

        try:
            response = await self.client.post(url, json=payload)
            response.raise_for_status()
            result = response.json()

            content = result["choices"][0]["message"]["content"]

            # Remove Qwen3 thinking blocks first (handle various formats)
            content = re.sub(r'<think>[\s\S]*?</think>', '', content)
            content = re.sub(r'<thinking>[\s\S]*?</thinking>', '', content)
            content = content.strip()

            # Log first 200 chars for debugging
            logger.debug(f"LLM response (first 200 chars): {content[:200]}...")

            # Extract JSON from response (handle markdown code blocks)
            json_match = re.search(r'```(?:json)?\s*([\s\S]*?)\s*```', content)
            if json_match:
                extracted = json_match.group(1).strip()
                # Validate it's valid JSON
                try:
                    json.loads(extracted)
                    return extracted
                except json.JSONDecodeError:
                    logger.warning("Markdown block content is not valid JSON, continuing...")

            # Find the first complete JSON object by counting braces
            start_idx = content.find('{')
            if start_idx != -1:
                brace_count = 0
                end_idx = start_idx
                for i, char in enumerate(content[start_idx:], start_idx):
                    if char == '{':
                        brace_count += 1
                    elif char == '}':
                        brace_count -= 1
                        if brace_count == 0:
                            end_idx = i + 1
                            break

                if brace_count == 0 and end_idx > start_idx:
                    extracted = content[start_idx:end_idx]
                    try:
                        json.loads(extracted)
                        return extracted
                    except json.JSONDecodeError:
                        logger.warning(f"Extracted content is not valid JSON: {extracted[:100]}...")

            logger.warning(f"Could not extract valid JSON from response")
            return content

        except httpx.HTTPError as e:
            logger.error(f"vLLM request failed: {e}")
            raise RuntimeError(f"LLM request failed: {e}")

    async def analyze_sources(
        self,
        sources: List[SourceInfo],
    ) -> SourceAnalysis:
        """
        Analyze source documents to extract key information.

        Args:
            sources: List of source documents with full content or summaries

        Returns:
            SourceAnalysis with extracted themes, insights, etc.
        """
        logger.info(f"Analyzing {len(sources)} sources")

        # Compile source information
        source_text = "DOCUMENTOS A ANALIZAR:\n\n"
        total_words = 0

        for i, source in enumerate(sources, 1):
            source_text += f"=== Documento {i}: {source.title} ===\n"

            # Use full content if available (preferred), otherwise fall back to summary
            if source.content:
                # Truncate content if too long (keep first ~8000 chars per source for context window)
                content_preview = source.content[:8000]
                if len(source.content) > 8000:
                    content_preview += f"\n[... contenido truncado, {len(source.content)} caracteres total ...]"
                source_text += f"Contenido:\n{content_preview}\n"
                total_words += source.word_count or len(source.content.split())
            elif source.summary:
                source_text += f"Resumen: {source.summary}\n"
                if source.key_points:
                    source_text += f"Puntos clave: {', '.join(source.key_points)}\n"
                total_words += source.word_count

            source_text += f"Tipo: {source.source_type}\n\n"

        logger.info(f"Total content length for analysis: {len(source_text)} chars, ~{total_words} words")

        # Call LLM for analysis
        result = await self._call_llm(
            system_prompt=ANALYZE_SOURCES_SYSTEM,
            user_content=source_text,
            temperature=0.5,
        )

        try:
            analysis_data = json.loads(result)
            analysis_data["total_word_count"] = total_words
            return SourceAnalysis(**analysis_data)
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse analysis JSON: {e}")
            # Return minimal analysis
            return SourceAnalysis(
                main_themes=["Tema principal"],
                key_insights=["Información del documento"],
                total_word_count=total_words,
            )

    async def generate_outline(
        self,
        analysis: SourceAnalysis,
        config: AudioConfig,
    ) -> ScriptOutline:
        """
        Generate podcast outline from analysis.

        Args:
            analysis: Source analysis with themes and insights
            config: Audio configuration including length

        Returns:
            ScriptOutline with structure
        """
        logger.info("Generating podcast outline")

        # Determine target duration based on length setting
        duration_map = {
            AudioLength.SHORT: 240,      # 4 minutes
            AudioLength.STANDARD: 420,   # 7 minutes
            AudioLength.LONG: 720,       # 12 minutes
        }
        target_duration = duration_map.get(config.length, 420)

        user_content = f"""ANÁLISIS DE FUENTES:
Temas principales: {', '.join(analysis.main_themes)}
Insights clave: {', '.join(analysis.key_insights[:5])}
Datos interesantes: {', '.join(analysis.interesting_facts[:3])}
Preguntas potenciales: {', '.join(analysis.potential_questions[:3])}

CONFIGURACIÓN:
- Duración objetivo: {target_duration} segundos
- Tono: {config.tone.value}
- Idioma: {config.language}
{f'- Temas a enfocar: {", ".join(config.focus_topics)}' if config.focus_topics else ''}

Genera el outline del podcast."""

        result = await self._call_llm(
            system_prompt=GENERATE_OUTLINE_SYSTEM,
            user_content=user_content,
            temperature=0.6,
        )

        try:
            outline_data = json.loads(result)
            return ScriptOutline(**outline_data)
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse outline JSON: {e}")
            return ScriptOutline(
                introduction="Bienvenidos a este episodio especial",
                main_topics=analysis.main_themes[:3],
                conclusion="Gracias por escucharnos",
                estimated_duration_seconds=target_duration,
            )

    async def generate_dialogue(
        self,
        outline: ScriptOutline,
        analysis: SourceAnalysis,
        config: AudioConfig,
    ) -> List[ScriptSegment]:
        """
        Generate the actual dialogue between hosts.

        Args:
            outline: Podcast structure
            analysis: Source analysis for content
            config: Audio configuration

        Returns:
            List of dialogue segments
        """
        logger.info("Generating podcast dialogue")

        # Map tone to description
        tone_descriptions = {
            AudioTone.CONVERSATIONAL: "casual y amigable, como una charla entre amigos",
            AudioTone.FORMAL: "profesional y estructurado, pero accesible",
            AudioTone.EDUCATIONAL: "didáctico y explicativo, como una clase entretenida",
        }
        tone_desc = tone_descriptions.get(config.tone, tone_descriptions[AudioTone.CONVERSATIONAL])

        # Map length to description
        length_descriptions = {
            AudioLength.SHORT: "3-5 minutos, conciso y directo",
            AudioLength.STANDARD: "5-10 minutos, completo pero ágil",
            AudioLength.LONG: "10-15 minutos, profundo y detallado",
        }
        duration_desc = length_descriptions.get(config.length, length_descriptions[AudioLength.STANDARD])

        system_prompt = GENERATE_DIALOGUE_SYSTEM.format(
            tone=tone_desc,
            duration=duration_desc,
        )

        user_content = f"""OUTLINE DEL PODCAST:
Introducción: {outline.introduction}
Temas principales: {', '.join(outline.main_topics)}
Conclusión: {outline.conclusion}

CONTENIDO DISPONIBLE:
Temas: {', '.join(analysis.main_themes)}
Insights: {', '.join(analysis.key_insights)}
Datos interesantes: {', '.join(analysis.interesting_facts)}
Preguntas a responder: {', '.join(analysis.potential_questions)}
Conexiones: {', '.join(analysis.connections)}

HOSTS:
- Emma (A): Experta entusiasta, explica conceptos
- Alex (B): Curioso, hace preguntas del oyente

Genera el diálogo completo."""

        result = await self._call_llm(
            system_prompt=system_prompt,
            user_content=user_content,
            max_tokens=settings.vllm_max_tokens,
            temperature=settings.vllm_temperature,
        )

        try:
            dialogue_data = json.loads(result)
            segments = [ScriptSegment(**seg) for seg in dialogue_data.get("segments", [])]
            return segments
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse dialogue JSON: {e}")
            # Return minimal dialogue
            return [
                ScriptSegment(speaker="A", text=outline.introduction, segment_id=1),
                ScriptSegment(speaker="B", text="¡Qué interesante! Cuéntame más.", segment_id=2),
                ScriptSegment(speaker="A", text=outline.conclusion, segment_id=3),
            ]

    async def refine_script(
        self,
        segments: List[ScriptSegment],
    ) -> List[ScriptSegment]:
        """
        Refine the script to add natural speech patterns.

        Args:
            segments: Raw dialogue segments

        Returns:
            Refined segments with natural speech elements
        """
        logger.info("Refining script with natural speech patterns")

        # Convert segments to JSON for processing
        segments_json = json.dumps(
            {"segments": [seg.model_dump() for seg in segments]},
            ensure_ascii=False,
        )

        result = await self._call_llm(
            system_prompt=REFINE_SCRIPT_SYSTEM,
            user_content=f"Refina este script:\n{segments_json}",
            temperature=0.8,
        )

        try:
            refined_data = json.loads(result)
            return [ScriptSegment(**seg) for seg in refined_data.get("segments", [])]
        except json.JSONDecodeError:
            logger.warning("Failed to parse refined script, using original")
            return segments

    async def generate_full_script(
        self,
        sources: List[SourceInfo],
        config: AudioConfig,
    ) -> PodcastScript:
        """
        Generate a complete podcast script through the full pipeline.

        Args:
            sources: Source documents
            config: Audio configuration

        Returns:
            Complete PodcastScript ready for TTS
        """
        logger.info("Starting full script generation pipeline")

        # 1. Analyze sources
        analysis = await self.analyze_sources(sources)
        logger.info(f"Analysis complete: {len(analysis.main_themes)} themes found")

        # 2. Generate outline
        outline = await self.generate_outline(analysis, config)
        logger.info(f"Outline complete: {len(outline.main_topics)} topics")

        # 3. Generate dialogue
        segments = await self.generate_dialogue(outline, analysis, config)
        logger.info(f"Dialogue complete: {len(segments)} segments")

        # 4. Refine script
        refined_segments = await self.refine_script(segments)
        logger.info(f"Refinement complete: {len(refined_segments)} segments")

        # Estimate duration (rough estimate: 150 words per minute, avg 5 chars per word)
        total_chars = sum(len(seg.text) for seg in refined_segments)
        estimated_words = total_chars / 5
        estimated_ms = int((estimated_words / 150) * 60 * 1000)

        return PodcastScript(
            title=f"Podcast sobre {analysis.main_themes[0] if analysis.main_themes else 'temas diversos'}",
            outline=outline,
            segments=refined_segments,
            total_segments=len(refined_segments),
            estimated_duration_ms=estimated_ms,
        )

    async def close(self):
        """Close the HTTP client."""
        await self.client.aclose()
