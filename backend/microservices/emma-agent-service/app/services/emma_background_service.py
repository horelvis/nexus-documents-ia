"""Emma Background Service — Proactive LangGraph execution without HTTP.

This service allows Emma to run analyses triggered by events, schedules,
or background tasks — without requiring a user HTTP request.

It reuses the existing LangGraph graph and Emma service, providing
a simplified interface for background invocations.
"""
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from app.core.config import settings

logger = logging.getLogger(__name__)


class EmmaBackgroundService:
    """Orchestrates proactive Emma executions from background tasks."""

    async def analyze_document(
        self,
        document_id: str,
        tenant_id: str,
        prompt_template: Optional[str] = None,
        agent: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Run Emma analysis on a newly indexed document.

        Args:
            document_id: The document to analyze
            tenant_id: Tenant context
            prompt_template: Custom prompt (may use {document_title} etc.)
            agent: Specific specialist agent to use
            metadata: Additional context (title, collection, tags, etc.)
        """
        metadata = metadata or {}
        title = metadata.get("title", document_id)

        # Build the query
        if prompt_template:
            query = prompt_template.format(
                document_title=title,
                document_id=document_id,
                **metadata,
            )
        else:
            query = f"Analiza el documento '{title}' y proporciona un resumen con los puntos clave."

        return await self._execute_emma(
            query=query,
            tenant_id=tenant_id,
            agent=agent,
            context={
                "background_task": True,
                "document_id": document_id,
                "trigger_type": "document_analysis",
            },
        )

    async def generate_daily_summary(
        self,
        tenant_id: str,
        collections: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Generate a daily summary of recent activity for a tenant."""
        query = (
            "Genera un resumen ejecutivo de la actividad reciente: "
            "documentos nuevos, cambios importantes, y cualquier alerta relevante."
        )
        return await self._execute_emma(
            query=query,
            tenant_id=tenant_id,
            context={
                "background_task": True,
                "trigger_type": "daily_summary",
                "collections": collections or [],
            },
        )

    async def proactive_analysis(
        self,
        tenant_id: str,
        analysis_type: str,
        query: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Run a custom proactive analysis."""
        return await self._execute_emma(
            query=query,
            tenant_id=tenant_id,
            context={
                "background_task": True,
                "trigger_type": "proactive_analysis",
                "analysis_type": analysis_type,
                **(context or {}),
            },
        )

    async def channel_query(
        self,
        tenant_id: str,
        query: str,
        channel_type: str,
        user_id: str,
        is_group: bool = False,
        group_name: str = "",
        channel_config: Optional[Dict[str, Any]] = None,
        session_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Process a query from a social channel with conversational tone.

        This method:
        1. Executes the query through Emma
        2. Post-processes the response to make it more conversational
        3. Shortens long responses with a "see more in app" suggestion
        4. Includes location context for weather/news queries
        5. Maintains conversation memory using session_id
        """
        # Load location from channel config or use defaults
        location = self._get_channel_location(channel_config)

        # Build context with channel info + location
        context = {
            "background_task": True,
            "trigger_type": "channel_query",
            "channel_type": channel_type,
            "user_id": user_id,
            "is_group": is_group,
            "group_name": group_name,
            "response_style": "conversational",
            # Social channel mode: enables web search for general queries
            "social_channel_mode": True,
            # Location context
            "location": location,
        }

        # Execute through Emma with persistent session_id for conversation memory
        result = await self._execute_emma(
            query=query,
            tenant_id=tenant_id,
            context=context,
            session_id=session_id,  # Pass session_id for memory persistence
        )

        if not result.get("success"):
            return result

        # Apply light formatting for social channels (no LLM rewrite)
        original_answer = result.get("answer", "")
        formatted_answer = self._format_for_social(original_answer, channel_type)

        result["answer"] = formatted_answer
        result["original_answer_length"] = len(original_answer)

        return result

    def _format_for_social(self, answer: str, channel_type: str) -> str:
        """Light formatting for social channels without LLM rewrite.

        Just cleans up formatting and truncates if too long.
        """
        import re

        result = answer

        # Remove markdown headers (## Title)
        result = re.sub(r'^#{1,3}\s+', '', result, flags=re.MULTILINE)

        # Remove horizontal rules
        result = re.sub(r'^---+\s*$', '', result, flags=re.MULTILINE)

        # Clean up multiple newlines
        result = re.sub(r'\n{3,}', '\n\n', result)

        # Truncate if too long for chat
        max_length = 1500
        if len(result) > max_length:
            truncate_at = result.rfind('. ', 0, max_length)
            if truncate_at == -1:
                truncate_at = result.rfind('\n', 0, max_length)
            if truncate_at == -1:
                truncate_at = max_length

            result = result[:truncate_at + 1].strip()
            result += "\n\n📱 Para la respuesta completa, usa la app."

        # Safety check
        if self._contains_inappropriate_content(result):
            logger.warning("Blocked inappropriate content")
            return "Lo siento, hubo un problema generando la respuesta. ¿Puedes reformular tu pregunta?"

        return result.strip()

    # Palabras/frases prohibidas en respuestas
    BLOCKED_PHRASES = [
        "cállate", "callate", "calla", "shut up", "idiota", "estúpido", "estupido",
        "imbécil", "imbecil", "tonto", "pendejo", "gilipollas", "mierda", "joder",
        "fuck", "shit", "damn", "bastard", "asshole", "bitch",
    ]

    def _contains_inappropriate_content(self, text: str) -> bool:
        """Check if text contains inappropriate language."""
        text_lower = text.lower()
        return any(phrase in text_lower for phrase in self.BLOCKED_PHRASES)

    async def _make_conversational(
        self,
        answer: str,
        channel_type: str,
        original_query: str,
    ) -> str:
        """Convert a formal Emma response to a conversational one.

        Uses a quick LLM call to rewrite the response in a friendlier tone,
        or applies heuristics if LLM is unavailable.
        """
        # If already short and simple, return as-is with minor tweaks
        if len(answer) < 300:
            result = self._apply_conversational_heuristics(answer, channel_type)
            # Safety check
            if self._contains_inappropriate_content(result):
                logger.warning(f"Blocked inappropriate content in heuristic response")
                return answer  # Return original
            return result

        # For longer responses, use LLM to summarize and make conversational
        try:
            import httpx
            from app.agents.config import agent_config

            system_prompt = f"""Reescribe la siguiente respuesta para un chat de {channel_type}.

REGLAS CRÍTICAS:
- NUNCA uses lenguaje ofensivo, grosero o inapropiado
- NUNCA insultes al usuario
- Sé siempre respetuoso y profesional
- Mantén un tono amigable pero educado

REGLAS DE FORMATO:
- Mantén el contenido pero hazlo MÁS CONVERSACIONAL y BREVE
- Máximo 3-4 párrafos cortos
- Usa 1-2 emojis relevantes (no más)
- Tono cercano, como un colega experto
- Si la respuesta original es muy larga, resume los puntos clave
- Al final, si hay mucho detalle omitido, añade: "¿Quieres más detalles sobre algún punto?"
- Responde en el mismo idioma que la respuesta original
- NO uses markdown elaborado (tablas, headers ##), solo negritas y listas simples"""

            user_prompt = f"""Pregunta original: {original_query}

Respuesta a reescribir:
{answer[:3000]}

{"[...respuesta truncada por longitud]" if len(answer) > 3000 else ""}"""

            async with httpx.AsyncClient(timeout=15.0) as client:
                response = await client.post(
                    f"{agent_config.vllm_base_url}/chat/completions",
                    json={
                        "model": agent_config.vllm_model,
                        "messages": [
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": user_prompt}
                        ],
                        "max_tokens": 800,
                        "temperature": 0.4,
                    }
                )

                if response.status_code == 200:
                    data = response.json()
                    rewritten = data["choices"][0]["message"]["content"].strip()

                    # Clean thinking tokens if present
                    if "</think>" in rewritten:
                        rewritten = rewritten.split("</think>")[-1].strip()

                    # SAFETY CHECK: Block inappropriate content
                    if rewritten and self._contains_inappropriate_content(rewritten):
                        logger.warning(f"Blocked inappropriate LLM response, using original")
                        return self._apply_conversational_heuristics(answer, channel_type)

                    if rewritten:
                        return rewritten

        except Exception as e:
            logger.warning(f"Conversational rewrite failed, using heuristics: {e}")

        # Fallback: apply heuristics
        result = self._apply_conversational_heuristics(answer, channel_type)

        # Final safety check
        if self._contains_inappropriate_content(result):
            logger.warning(f"Blocked inappropriate heuristic response, using original")
            return answer

        return result

    def _apply_conversational_heuristics(self, answer: str, channel_type: str) -> str:
        """Apply simple heuristics to make response more conversational."""
        result = answer

        # Remove overly formal headers
        import re
        result = re.sub(r'^#{1,3}\s+', '', result, flags=re.MULTILINE)

        # Truncate if too long
        max_length = 1200
        if len(result) > max_length:
            # Find a good break point
            truncate_at = result.rfind('. ', 0, max_length)
            if truncate_at == -1:
                truncate_at = max_length

            result = result[:truncate_at + 1]
            result += "\n\n📱 Para ver la respuesta completa, usa la app de NouxCubeIA."

        # Add a friendly touch if no emoji present
        if not any(c in result for c in ['📄', '✅', '⚠️', '📋', '🔍', '💡', '👋']):
            # Add contextual emoji at start
            if any(word in answer.lower() for word in ['riesgo', 'alerta', 'problema', 'error']):
                result = "⚠️ " + result
            elif any(word in answer.lower() for word in ['encontré', 'documento', 'contrato']):
                result = "📄 " + result
            elif any(word in answer.lower() for word in ['hola', 'encantad']):
                result = "👋 " + result
            else:
                result = "💡 " + result

        return result

    def _get_channel_location(self, channel_config: Optional[Dict[str, Any]] = None) -> Dict[str, str]:
        """Get location configuration from channel config or defaults.

        Location can be configured per channel in config.location:
        {
            "location": {
                "city": "Molina de Segura",
                "region": "Murcia",
                "country": "España",
                "timezone": "Europe/Madrid"
            }
        }
        """
        try:
            import yaml
            from pathlib import Path

            # Load defaults from settings (environment variables)
            from app.core.config import settings
            defaults = {
                "city": settings.default_location_city,
                "region": settings.default_location_region,
                "country": settings.default_location_country,
                "timezone": settings.default_location_timezone,
            }

            # Override with channel-specific config
            if channel_config and channel_config.get("location"):
                channel_location = channel_config["location"]
                return {
                    "city": channel_location.get("city", defaults["city"]),
                    "region": channel_location.get("region", defaults["region"]),
                    "country": channel_location.get("country", defaults["country"]),
                    "timezone": channel_location.get("timezone", defaults["timezone"]),
                }

            return defaults

        except Exception as e:
            logger.warning(f"Could not load location config: {e}")
            # Fallback to hardcoded defaults if settings not available
            return {
                "city": "Molina de Segura",
                "region": "Región de Murcia",
                "country": "España",
                "timezone": "Europe/Madrid",
            }

    def _get_social_prompt(self, channel_type: str, location: Optional[Dict[str, str]] = None) -> str:
        """Load social channel prompt from emma_prompts.yaml with location context."""
        try:
            import yaml
            from pathlib import Path
            from datetime import datetime
            import pytz

            prompts_path = Path(__file__).parent.parent.parent / "config" / "prompts" / "emma_prompts.yaml"
            if prompts_path.exists():
                with open(prompts_path, "r", encoding="utf-8") as f:
                    prompts = yaml.safe_load(f)

                social_config = prompts.get("social_channels", {})
                system_prompt = social_config.get("system_prompt", "")

                # Get location (from param or defaults)
                loc = location or self._get_channel_location()

                # Get current datetime in the channel's timezone
                try:
                    tz = pytz.timezone(loc.get("timezone", "Europe/Madrid"))
                    current_dt = datetime.now(tz).strftime("%A %d de %B de %Y, %H:%M")
                except Exception:
                    current_dt = datetime.now().strftime("%A %d de %B de %Y, %H:%M")

                # Replace all placeholders
                return (
                    system_prompt
                    .replace("{channel_type}", channel_type)
                    .replace("{location_city}", loc.get("city", "Madrid"))
                    .replace("{location_region}", loc.get("region", "España"))
                    .replace("{location_country}", loc.get("country", "España"))
                    .replace("{timezone}", loc.get("timezone", "Europe/Madrid"))
                    .replace("{current_datetime}", current_dt)
                )

        except Exception as e:
            logger.warning(f"Could not load social prompt: {e}")

        # Fallback prompt
        return (
            f"Eres Emma, asistente de IA. Estás conversando por {channel_type}. "
            "Sé amigable y concisa. Responde en el idioma del usuario."
        )

    async def _execute_emma(
        self,
        query: str,
        tenant_id: str,
        agent: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None,
        session_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Execute a query through the LangGraph pipeline.

        Args:
            query: User query
            tenant_id: Tenant identifier
            agent: Optional specific agent to use
            context: Optional context dict
            session_id: Optional session ID for conversation memory persistence.
                        If not provided, generates a random one (no memory).
        """
        # Use provided session_id or generate random one (for backward compatibility)
        session_id = session_id or f"bg-{uuid.uuid4().hex[:12]}"
        logger.info(f"🧠 Executing Emma with session_id: {session_id}")

        try:
            from app.services.emma_service import emma_service
            from app.schemas.emma import EmmaQuery

            emma_query = EmmaQuery(
                query=query,
                tenant_id=tenant_id,
                session_id=session_id,
                context=context or {},
                enable_learning=False,
                enable_debug=False,
            )

            response = await emma_service.execute_query(emma_query)

            # Extract sources from data.sources or data.references if available
            sources = []
            if response and response.data:
                sources = response.data.get("sources", response.data.get("references", []))

            return {
                "success": True,
                "session_id": session_id,
                "answer": response.answer if response else "Sin respuesta",
                "confidence_score": response.confidence_score if response else None,
                "sources_count": len(sources) if sources else 0,
                "executed_at": datetime.now(timezone.utc).isoformat(),
            }

        except Exception as e:
            logger.error(f"Background Emma execution failed: {e}", exc_info=True)
            return {
                "success": False,
                "session_id": session_id,
                "error": str(e),
                "executed_at": datetime.now(timezone.utc).isoformat(),
            }


# Global singleton
emma_background_service = EmmaBackgroundService()
