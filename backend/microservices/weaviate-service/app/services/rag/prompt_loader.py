"""
Prompt Loader - Carga prompts desde archivos YAML externos

Permite editar los prompts de Emma sin modificar el código.
Los archivos se buscan en:
1. /app/config/prompts/ (dentro del contenedor Docker)
2. ./config/prompts/ (desarrollo local)
3. Fallback a prompts por defecto si no se encuentra el archivo
"""

import os
import logging
from pathlib import Path
from typing import Dict, Optional
import yaml

logger = logging.getLogger(__name__)

# Rutas donde buscar los archivos de prompts
PROMPT_PATHS = [
    Path("/app/config/prompts"),           # Docker container
    Path("./config/prompts"),              # Local development
    Path(__file__).parent.parent.parent.parent / "config" / "prompts",  # Relative to this file
]

# Cache de prompts cargados
_prompts_cache: Dict[str, Dict[str, str]] = {}
_cache_mtime: Dict[str, float] = {}


def _find_prompt_file(filename: str) -> Optional[Path]:
    """Encuentra el archivo de prompts en las rutas configuradas."""
    for base_path in PROMPT_PATHS:
        file_path = base_path / filename
        if file_path.exists():
            return file_path
    return None


def _load_yaml_file(file_path: Path) -> Dict[str, str]:
    """Carga un archivo YAML y retorna su contenido."""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = yaml.safe_load(f)
            if not isinstance(content, dict):
                logger.error(f"El archivo {file_path} no contiene un diccionario válido")
                return {}
            return content
    except yaml.YAMLError as e:
        logger.error(f"Error parseando YAML {file_path}: {e}")
        return {}
    except Exception as e:
        logger.error(f"Error leyendo archivo {file_path}: {e}")
        return {}


def load_prompts(filename: str = "emma_prompts.yaml", force_reload: bool = False) -> Dict[str, str]:
    """
    Carga los prompts desde un archivo YAML.

    Args:
        filename: Nombre del archivo de prompts
        force_reload: Forzar recarga aunque esté en cache

    Returns:
        Diccionario con los prompts cargados
    """
    global _prompts_cache, _cache_mtime

    file_path = _find_prompt_file(filename)

    if file_path is None:
        logger.warning(f"Archivo de prompts no encontrado: {filename}")
        return {}

    # Verificar si el archivo ha cambiado
    current_mtime = file_path.stat().st_mtime
    cache_key = str(file_path)

    if not force_reload and cache_key in _prompts_cache:
        if _cache_mtime.get(cache_key) == current_mtime:
            return _prompts_cache[cache_key]

    # Cargar y cachear
    logger.info(f"📄 Cargando prompts desde: {file_path}")
    prompts = _load_yaml_file(file_path)

    if prompts:
        _prompts_cache[cache_key] = prompts
        _cache_mtime[cache_key] = current_mtime
        logger.info(f"✅ Cargados {len(prompts)} prompts: {list(prompts.keys())}")

    return prompts


def get_prompt(intent: str, filename: str = "emma_prompts.yaml") -> Optional[str]:
    """
    Obtiene un prompt específico por su intent.

    Args:
        intent: Tipo de intent (base, analyze, compare, summarize, etc.)
        filename: Archivo de prompts

    Returns:
        El prompt correspondiente o None si no existe
    """
    prompts = load_prompts(filename)

    # Mapeo de QueryIntent enum a keys del YAML
    intent_mapping = {
        "QueryIntent.ANALYZE": "analyze",
        "QueryIntent.COMPARE": "compare",
        "QueryIntent.SUMMARIZE": "summarize",
        "QueryIntent.SEARCH": "search",
        "QueryIntent.EXTRACT": "extract",
        "QueryIntent.EXPLAIN": "explain",
        "QueryIntent.LIST": "search",  # Usa el mismo que search
        "QueryIntent.UNKNOWN": "base",
    }

    # Normalizar el intent
    if hasattr(intent, 'name'):
        intent_key = intent_mapping.get(str(intent), intent.name.lower())
    elif isinstance(intent, str):
        intent_key = intent_mapping.get(intent, intent.lower())
    else:
        intent_key = "base"

    return prompts.get(intent_key) or prompts.get("base")


def get_user_prompt_template(filename: str = "emma_prompts.yaml") -> str:
    """
    Obtiene el template del prompt de usuario.

    Returns:
        Template string con placeholders {doc_index}, {formatted_context}, {query}
    """
    prompts = load_prompts(filename)

    default_template = """## Documentos Disponibles
{doc_index}

---

{formatted_context}

---

## Consulta del Usuario
{query}

**Instrucciones:** Responde basándote únicamente en los documentos proporcionados. Usa citas **[1]**, **[2]**, etc. para referenciar los documentos. Formatea tu respuesta usando markdown."""

    return prompts.get("user_prompt_template", default_template)


def reload_prompts(filename: str = "emma_prompts.yaml") -> bool:
    """
    Fuerza la recarga de prompts desde el archivo.

    Útil para aplicar cambios sin reiniciar el servicio.

    Returns:
        True si se cargaron correctamente
    """
    prompts = load_prompts(filename, force_reload=True)
    return len(prompts) > 0


def list_available_prompts(filename: str = "emma_prompts.yaml") -> list:
    """Lista los prompts disponibles en el archivo."""
    prompts = load_prompts(filename)
    return list(prompts.keys())


def get_agent_system_message(agent_name: str, fallback: str = "", filename: str = "emma_prompts.yaml") -> str:
    """
    Load agent system message from YAML configuration.

    This function retrieves the system message for AutoGen agents defined
    in the autogen_agents section of the YAML file.

    Args:
        agent_name: Name of the agent (e.g., "ContractAgent", "LaborAgent")
        fallback: Default message if agent not found in config
        filename: YAML file to load from

    Returns:
        System message string for the agent

    Example:
        >>> msg = get_agent_system_message("ContractAgent")
        >>> msg = get_agent_system_message("LaborAgent", fallback="You are a labor law expert...")
    """
    prompts = load_prompts(filename)

    # Get the autogen_agents section
    autogen_agents = prompts.get("autogen_agents", {})

    if not autogen_agents:
        logger.warning("No autogen_agents section found in prompts YAML")
        return fallback

    # Get the specific agent config
    agent_config = autogen_agents.get(agent_name, {})

    if not agent_config:
        # Use DEBUG level since using fallback is expected behavior for some agents
        # (e.g., EmmaCoordinator uses DEFAULT_EMMA_INSTRUCTIONS as its intended prompt)
        logger.debug(f"Agent '{agent_name}' not in autogen_agents config, using fallback")
        return fallback

    # Return the system message
    system_message = agent_config.get("system_message", fallback)

    if system_message and system_message != fallback:
        logger.debug(f"Loaded system message for {agent_name} ({len(system_message)} chars)")

    return system_message


def list_available_agents(filename: str = "emma_prompts.yaml") -> list:
    """
    List available AutoGen agents defined in the YAML config.

    Returns:
        List of agent names
    """
    prompts = load_prompts(filename)
    autogen_agents = prompts.get("autogen_agents", {})
    return list(autogen_agents.keys())


# Default analysis prompts (fallback if not in YAML)
_DEFAULT_ANALYSIS_PROMPTS = {
    "comprehensive": """Analyze this document following these steps:
1. First identify the DOCUMENT TYPE (invoice, contract, report, letter, etc.)
2. Provide analysis APPROPRIATE for that type:
   - For INVOICES: issuer, recipient, amount, date, concept
   - For CONTRACTS: parties, subject matter, obligations, deadlines, legal risks
   - For REPORTS: main topic, conclusions, relevant data
   - For other documents: summary and key points
3. DO NOT invent risks or problems where none exist. Be objective and concise.""",
    "risks": "Identify REAL risks in this document. For simple documents like invoices, state there are no significant risks.",
    "summary": "Summarize the main points of this document concisely and objectively.",
    "entities": "Extract important entities: people, organizations, dates, amounts, addresses.",
    "compliance": "Evaluate regulatory compliance if applicable. For simple documents, state basic requirements.",
    "obligations": "Extract obligations and commitments if they exist. For invoices, state the amount due and payment deadline.",
}


def get_analysis_prompt(analysis_type: str, filename: str = "emma_prompts.yaml") -> str:
    """
    Get analysis prompt for document analysis.

    Loads from 'document_analysis' section in YAML, falls back to defaults.

    Args:
        analysis_type: Type of analysis (comprehensive, risks, summary, entities, compliance, obligations)
        filename: YAML file to load from

    Returns:
        Analysis prompt string
    """
    prompts = load_prompts(filename)

    # Get the document_analysis section
    analysis_prompts = prompts.get("document_analysis", {})

    if analysis_prompts and analysis_type in analysis_prompts:
        return analysis_prompts[analysis_type]

    # Fallback to defaults
    return _DEFAULT_ANALYSIS_PROMPTS.get(analysis_type, _DEFAULT_ANALYSIS_PROMPTS["comprehensive"])
