"""
SLM Client: Small Language Model Client for TOON Plan Generation

This module provides a dedicated client for the SLM (Small Language Model)
that generates TOON plans. The SLM is optimized for:
1. Structured output generation (YAML/JSON)
2. Low latency (~5-15ms on CPU, ~2-5ms on GPU)
3. Deterministic routing decisions (temperature 0.0-0.2)

Supported backends:
- vLLM (secondary server, recommended for production)
- Local transformers (CPU/GPU, good for development)
- Ollama (lightweight local inference)
- Main vLLM server with small model (shared GPU)

Version 1.0 - January 2026
"""

import asyncio
import logging
import time
from typing import Optional, Dict, Any, List
from abc import ABC, abstractmethod
import httpx
from pydantic import BaseModel

from .toon_schema import TOONPlan, TOONParser, TOONRoute, TOONGuardrails

logger = logging.getLogger(__name__)


# =============================================================================
# CONFIGURATION
# =============================================================================

class SLMConfig(BaseModel):
    """Configuration for the SLM client."""

    # Provider selection
    provider: str = "tgi"  # tgi, vllm, litellm, transformers, ollama

    # TGI settings (recommended for dedicated SLM on GPU)
    tgi_base_url: str = "http://tgi-slm:80"
    tgi_model: str = "Qwen/Qwen2-0.5B-Instruct"  # For logging only, TGI uses loaded model

    # vLLM settings (can be same server as main or separate)
    vllm_base_url: str = "http://vllm:8000/v1"
    vllm_model: str = "Qwen/Qwen2-0.5B"  # Small model for routing

    # LiteLLM Gateway settings (optional, requires PostgreSQL)
    litellm_base_url: str = "http://litellm:4000/v1"
    litellm_model: str = "slm/qwen2-0.5b"  # Model alias in LiteLLM config
    litellm_api_key: str = ""  # Optional API key for LiteLLM

    # Ollama settings (lightweight alternative)
    ollama_base_url: str = "http://genai-ollama:11434"
    ollama_model: str = "qwen2:0.5b"

    # Local transformers settings
    local_model: str = "Qwen/Qwen2-0.5B"
    local_device: str = "cpu"  # cpu or cuda

    # Inference settings
    max_tokens: int = TOONGuardrails.SLM["max_tokens"]
    temperature: float = TOONGuardrails.SLM["temperature"]["default"]
    timeout_ms: int = TOONGuardrails.SLM["timeout_ms"]

    # Retry settings
    max_retries: int = 2
    retry_delay_ms: int = 100


# =============================================================================
# PROMPT TEMPLATES
# =============================================================================

SLM_SYSTEM_PROMPT = """You are a query planning assistant. Generate TOON plans in YAML format.

## Context
{tenant_schema}

History: {conversation_history}
Previous plan: {last_toon_plan}

## Routes
- GRAPH_ONLY: counts, lists, existence ("cuántos", "listar", "hay")
- VECTOR_ONLY: semantic search, content lookup
- HYBRID: structure + content
- ASK_CLARIFY: ambiguous query

## Graph Operations
- COUNT: "cuántos", "how many"
- LIST: "listar", "mostrar", "show"
- EXISTS: "hay", "existe"

## Graph Labels
- Entity: clients, persons, companies
- structural_document: documents, contracts, invoices
- structural_folder: folders, cases (expedientes)

## Example 1 - Count query:
Query: "¿Cuántos contratos tiene ACME?"
```yaml
route: GRAPH_ONLY
confidence: 0.9
entities:
  - name: ACME
    type: client
    graph_label: Entity
  - name: contrato
    type: document_type
    graph_label: structural_document
graph:
  enabled: true
  operation: COUNT
  cypher_template: |
    MATCH (c:Entity {{name: $client_name}})<-[:BELONGS_TO]-(d:structural_document)
    WHERE d.semantic_type = $doc_type
    RETURN count(d) as total
  params:
    client_name: ACME
    doc_type: contract
  limit: 1
  hops: 2
```

## Example 2 - List query:
Query: "Lista los expedientes de Legal"
```yaml
route: GRAPH_ONLY
confidence: 0.85
entities:
  - name: Legal
    type: department
    graph_label: Entity
  - name: expediente
    type: folder_type
    graph_label: structural_folder
graph:
  enabled: true
  operation: LIST
  cypher_template: |
    MATCH (d:Entity {{name: $department}})<-[:BELONGS_TO]-(f:structural_folder)
    RETURN f.name as name, f.id as id
  params:
    department: Legal
  limit: 50
  hops: 2
```

## Example 3 - Semantic search:
Query: "Busca información sobre cláusulas de confidencialidad"
```yaml
route: VECTOR_ONLY
confidence: 0.9
entities:
  - name: cláusulas de confidencialidad
    type: concept
vector:
  enabled: true
  operation: SEMANTIC_SEARCH
  query: cláusulas de confidencialidad
  top_k: 5
```

Output ONLY valid YAML, no explanations."""

SLM_USER_TEMPLATE = """Query: {query}

Generate TOON plan:"""


# =============================================================================
# ABSTRACT BASE CLIENT
# =============================================================================

class BaseSLMProvider(ABC):
    """Abstract base class for SLM providers."""

    @abstractmethod
    async def generate(
        self,
        system_prompt: str,
        user_prompt: str,
        max_tokens: int,
        temperature: float,
        timeout_ms: int
    ) -> str:
        """Generate text from the SLM."""
        pass

    @abstractmethod
    async def health_check(self) -> bool:
        """Check if the provider is available."""
        pass


# =============================================================================
# VLLM PROVIDER
# =============================================================================

class VLLMProvider(BaseSLMProvider):
    """
    vLLM-based SLM provider.

    Can use the same vLLM server as the main LLM or a dedicated smaller server.
    """

    def __init__(self, base_url: str, model: str):
        self.base_url = base_url.rstrip('/')
        self.model = model
        self._client: Optional[httpx.AsyncClient] = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=30.0)
        return self._client

    async def generate(
        self,
        system_prompt: str,
        user_prompt: str,
        max_tokens: int,
        temperature: float,
        timeout_ms: int
    ) -> str:
        client = await self._get_client()
        timeout_seconds = timeout_ms / 1000.0

        try:
            response = await client.post(
                f"{self.base_url}/chat/completions",
                json={
                    "model": self.model,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt}
                    ],
                    "max_tokens": max_tokens,
                    "temperature": temperature,
                    "stream": False
                },
                timeout=timeout_seconds
            )
            response.raise_for_status()
            data = response.json()
            return data["choices"][0]["message"]["content"]
        except httpx.TimeoutException:
            logger.warning(f"vLLM SLM timeout after {timeout_ms}ms")
            raise
        except Exception as e:
            logger.error(f"vLLM SLM error: {e}")
            raise

    async def health_check(self) -> bool:
        try:
            client = await self._get_client()
            response = await client.get(f"{self.base_url}/models", timeout=5.0)
            return response.status_code == 200
        except Exception:
            return False


# =============================================================================
# TGI PROVIDER (Direct connection to HuggingFace Text Generation Inference)
# =============================================================================

class TGIProvider(BaseSLMProvider):
    """
    TGI (Text Generation Inference) provider.

    Direct connection to HuggingFace TGI server.
    Uses TGI's native API format (different from OpenAI).
    Recommended for fast SLM inference on GPU.
    """

    def __init__(self, base_url: str, model: str = ""):
        self.base_url = base_url.rstrip('/')
        self.model = model  # For logging only, TGI serves one model
        self._client: Optional[httpx.AsyncClient] = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=30.0)
        return self._client

    async def generate(
        self,
        system_prompt: str,
        user_prompt: str,
        max_tokens: int,
        temperature: float,
        timeout_ms: int
    ) -> str:
        client = await self._get_client()
        timeout_seconds = timeout_ms / 1000.0

        # Use OpenAI-compatible API (supported in TGI 2.0+)
        try:
            response = await client.post(
                f"{self.base_url}/v1/chat/completions",
                json={
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt}
                    ],
                    "max_tokens": max_tokens,
                    "temperature": max(temperature, 0.01),  # TGI doesn't like 0.0
                    "stream": False
                },
                timeout=timeout_seconds
            )
            response.raise_for_status()
            data = response.json()
            return data["choices"][0]["message"]["content"]
        except httpx.TimeoutException:
            logger.warning(f"TGI SLM timeout after {timeout_ms}ms")
            raise
        except Exception as e:
            logger.error(f"TGI SLM error: {e}")
            raise

    async def health_check(self) -> bool:
        try:
            client = await self._get_client()
            response = await client.get(f"{self.base_url}/health", timeout=5.0)
            return response.status_code == 200
        except Exception:
            return False


# =============================================================================
# LITELLM PROVIDER (Gateway to TGI/vLLM)
# =============================================================================

class LiteLLMProvider(BaseSLMProvider):
    """
    LiteLLM Gateway-based SLM provider.

    Routes to TGI (CPU) for fast SLM inference via LiteLLM proxy.
    Uses OpenAI-compatible API.
    """

    def __init__(self, base_url: str, model: str, api_key: str = ""):
        self.base_url = base_url.rstrip('/')
        self.model = model
        self.api_key = api_key
        self._client: Optional[httpx.AsyncClient] = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            headers = {}
            if self.api_key:
                headers["Authorization"] = f"Bearer {self.api_key}"
            self._client = httpx.AsyncClient(timeout=30.0, headers=headers)
        return self._client

    async def generate(
        self,
        system_prompt: str,
        user_prompt: str,
        max_tokens: int,
        temperature: float,
        timeout_ms: int
    ) -> str:
        client = await self._get_client()
        timeout_seconds = timeout_ms / 1000.0

        try:
            response = await client.post(
                f"{self.base_url}/chat/completions",
                json={
                    "model": self.model,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt}
                    ],
                    "max_tokens": max_tokens,
                    "temperature": temperature,
                    "stream": False
                },
                timeout=timeout_seconds
            )
            response.raise_for_status()
            data = response.json()
            return data["choices"][0]["message"]["content"]
        except httpx.TimeoutException:
            logger.warning(f"LiteLLM SLM timeout after {timeout_ms}ms")
            raise
        except Exception as e:
            logger.error(f"LiteLLM SLM error: {e}")
            raise

    async def health_check(self) -> bool:
        try:
            client = await self._get_client()
            response = await client.get(f"{self.base_url}/health", timeout=5.0)
            return response.status_code == 200
        except Exception:
            return False


# =============================================================================
# OLLAMA PROVIDER
# =============================================================================

class OllamaProvider(BaseSLMProvider):
    """
    Ollama-based SLM provider.

    Lightweight local inference, good for development.
    """

    def __init__(self, base_url: str, model: str):
        self.base_url = base_url.rstrip('/')
        self.model = model
        self._client: Optional[httpx.AsyncClient] = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=60.0)
        return self._client

    async def generate(
        self,
        system_prompt: str,
        user_prompt: str,
        max_tokens: int,
        temperature: float,
        timeout_ms: int
    ) -> str:
        client = await self._get_client()
        timeout_seconds = timeout_ms / 1000.0

        try:
            response = await client.post(
                f"{self.base_url}/api/generate",
                json={
                    "model": self.model,
                    "prompt": f"{system_prompt}\n\n{user_prompt}",
                    "stream": False,
                    "options": {
                        "num_predict": max_tokens,
                        "temperature": temperature
                    }
                },
                timeout=timeout_seconds
            )
            response.raise_for_status()
            data = response.json()
            return data.get("response", "")
        except httpx.TimeoutException:
            logger.warning(f"Ollama SLM timeout after {timeout_ms}ms")
            raise
        except Exception as e:
            logger.error(f"Ollama SLM error: {e}")
            raise

    async def health_check(self) -> bool:
        try:
            client = await self._get_client()
            response = await client.get(f"{self.base_url}/api/tags", timeout=5.0)
            return response.status_code == 200
        except Exception:
            return False


# =============================================================================
# LOCAL TRANSFORMERS PROVIDER
# =============================================================================

class LocalTransformersProvider(BaseSLMProvider):
    """
    Local transformers-based SLM provider.

    Loads model directly in Python for lowest latency.
    Best for development or when dedicated GPU memory is available.
    """

    def __init__(self, model_name: str, device: str = "cpu"):
        self.model_name = model_name
        self.device = device
        self._model = None
        self._tokenizer = None
        self._loaded = False

    async def _load_model(self):
        """Lazy load the model."""
        if self._loaded:
            return

        # Import here to avoid startup cost if not using this provider
        try:
            from transformers import AutoModelForCausalLM, AutoTokenizer
            import torch

            logger.info(f"Loading SLM model: {self.model_name} on {self.device}")

            self._tokenizer = AutoTokenizer.from_pretrained(
                self.model_name,
                trust_remote_code=True
            )
            self._model = AutoModelForCausalLM.from_pretrained(
                self.model_name,
                torch_dtype=torch.float16 if self.device == "cuda" else torch.float32,
                device_map=self.device if self.device == "cuda" else None,
                trust_remote_code=True
            )
            if self.device == "cpu":
                self._model = self._model.to("cpu")

            self._loaded = True
            logger.info(f"SLM model loaded successfully")
        except Exception as e:
            logger.error(f"Failed to load SLM model: {e}")
            raise

    async def generate(
        self,
        system_prompt: str,
        user_prompt: str,
        max_tokens: int,
        temperature: float,
        timeout_ms: int
    ) -> str:
        await self._load_model()

        # Run in executor to not block event loop
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None,
            self._generate_sync,
            system_prompt,
            user_prompt,
            max_tokens,
            temperature
        )

    def _generate_sync(
        self,
        system_prompt: str,
        user_prompt: str,
        max_tokens: int,
        temperature: float
    ) -> str:
        """Synchronous generation for use in executor."""
        import torch

        prompt = f"<|im_start|>system\n{system_prompt}<|im_end|>\n<|im_start|>user\n{user_prompt}<|im_end|>\n<|im_start|>assistant\n"

        inputs = self._tokenizer(prompt, return_tensors="pt")
        if self.device == "cuda":
            inputs = {k: v.cuda() for k, v in inputs.items()}

        with torch.no_grad():
            outputs = self._model.generate(
                **inputs,
                max_new_tokens=max_tokens,
                temperature=temperature if temperature > 0 else None,
                do_sample=temperature > 0,
                pad_token_id=self._tokenizer.eos_token_id
            )

        generated = self._tokenizer.decode(
            outputs[0][inputs['input_ids'].shape[1]:],
            skip_special_tokens=True
        )
        return generated

    async def health_check(self) -> bool:
        try:
            await self._load_model()
            return self._loaded
        except Exception:
            return False


# =============================================================================
# MAIN SLM CLIENT
# =============================================================================

class SLMClient:
    """
    Main SLM Client for TOON plan generation.

    This client:
    1. Manages provider selection and fallback
    2. Formats prompts with context
    3. Parses and validates TOON plans
    4. Handles errors with graceful fallbacks
    """

    def __init__(self, config: Optional[SLMConfig] = None):
        self.config = config or SLMConfig()
        self._provider: Optional[BaseSLMProvider] = None
        self._initialized = False

    async def initialize(self) -> bool:
        """Initialize the SLM provider."""
        if self._initialized:
            return True

        provider = self.config.provider.lower()

        try:
            if provider == "tgi":
                # Recommended: Direct TGI connection (GPU or CPU)
                self._provider = TGIProvider(
                    self.config.tgi_base_url,
                    self.config.tgi_model
                )
            elif provider == "litellm":
                # LiteLLM Gateway (requires PostgreSQL)
                self._provider = LiteLLMProvider(
                    self.config.litellm_base_url,
                    self.config.litellm_model,
                    self.config.litellm_api_key
                )
            elif provider == "vllm":
                self._provider = VLLMProvider(
                    self.config.vllm_base_url,
                    self.config.vllm_model
                )
            elif provider == "ollama":
                self._provider = OllamaProvider(
                    self.config.ollama_base_url,
                    self.config.ollama_model
                )
            elif provider == "transformers":
                self._provider = LocalTransformersProvider(
                    self.config.local_model,
                    self.config.local_device
                )
            else:
                logger.warning(f"Unknown SLM provider: {provider}, falling back to tgi")
                self._provider = TGIProvider(
                    self.config.tgi_base_url,
                    self.config.tgi_model
                )

            # Check health
            if await self._provider.health_check():
                self._initialized = True
                logger.info(f"SLM client initialized with provider: {provider}")
                return True
            else:
                logger.warning(f"SLM provider {provider} health check failed")
                return False

        except Exception as e:
            logger.error(f"Failed to initialize SLM client: {e}")
            return False

    async def generate_plan(
        self,
        query: str,
        tenant_schema: str = "",
        conversation_history: str = "",
        last_toon_plan: str = "",
        tenant_id: str = "",
        session_id: str = ""
    ) -> TOONPlan:
        """
        Generate a TOON plan for the given query.

        Args:
            query: The user's query
            tenant_schema: Formatted tenant schema context
            conversation_history: Formatted conversation history
            last_toon_plan: Previous TOON plan (for continuations)
            tenant_id: Tenant ID for isolation
            session_id: Session ID for tracking

        Returns:
            Validated TOONPlan
        """
        # Ensure initialized
        if not self._initialized:
            if not await self.initialize():
                logger.warning("SLM not initialized, returning fallback plan")
                return self._create_fallback_plan(query, tenant_id, session_id)

        # Format prompts
        system_prompt = SLM_SYSTEM_PROMPT.format(
            tenant_schema=tenant_schema or "No schema context available",
            conversation_history=conversation_history or "No history",
            last_toon_plan=last_toon_plan or "None"
        )
        user_prompt = SLM_USER_TEMPLATE.format(query=query)

        # Generate with retries
        start_time = time.time()
        last_error = None

        for attempt in range(self.config.max_retries + 1):
            try:
                raw_output = await self._provider.generate(
                    system_prompt=system_prompt,
                    user_prompt=user_prompt,
                    max_tokens=self.config.max_tokens,
                    temperature=self.config.temperature,
                    timeout_ms=self.config.timeout_ms
                )

                # Debug: log raw output at debug level
                logger.debug(f"SLM raw output: {repr(raw_output[:500]) if raw_output else 'empty'}")

                # Parse the output
                plan = TOONParser.parse(raw_output)
                plan.original_query = query
                plan.tenant_id = tenant_id
                plan.session_id = session_id

                elapsed_ms = (time.time() - start_time) * 1000
                logger.info(
                    f"TOON plan generated in {elapsed_ms:.1f}ms: "
                    f"route={plan.route.value}, confidence={plan.confidence:.2f}"
                )

                return plan

            except Exception as e:
                last_error = e
                logger.warning(f"SLM generation attempt {attempt + 1} failed: {e}")
                if attempt < self.config.max_retries:
                    await asyncio.sleep(self.config.retry_delay_ms / 1000.0)

        # All retries failed
        logger.error(f"SLM generation failed after {self.config.max_retries + 1} attempts: {last_error}")
        return self._create_fallback_plan(query, tenant_id, session_id)

    def _create_fallback_plan(
        self,
        query: str,
        tenant_id: str,
        session_id: str
    ) -> TOONPlan:
        """Create a fallback plan when SLM fails."""
        # Use simple heuristics for fallback routing
        query_lower = query.lower()

        route = TOONRoute.VECTOR_ONLY
        confidence = 0.5

        # Check for count/list patterns
        count_patterns = ['cuántos', 'cuantos', 'how many', 'count']
        list_patterns = ['lista', 'listar', 'muestra', 'show me', 'list']
        exists_patterns = ['hay', 'existe', 'is there', 'does exist']

        if any(p in query_lower for p in count_patterns + list_patterns + exists_patterns):
            route = TOONRoute.GRAPH_ONLY
            confidence = 0.6

        return TOONPlan(
            route=route,
            confidence=confidence,
            reasoning="Fallback plan due to SLM failure",
            original_query=query,
            tenant_id=tenant_id,
            session_id=session_id
        )

    async def health_check(self) -> Dict[str, Any]:
        """Check SLM client health."""
        if not self._provider:
            return {"status": "not_initialized", "provider": self.config.provider}

        try:
            is_healthy = await self._provider.health_check()
            return {
                "status": "healthy" if is_healthy else "unhealthy",
                "provider": self.config.provider,
                "model": getattr(self._provider, 'model', self.config.vllm_model)
            }
        except Exception as e:
            return {
                "status": "error",
                "provider": self.config.provider,
                "error": str(e)
            }

    async def close(self):
        """Close the client and release resources."""
        if self._provider and hasattr(self._provider, '_client') and self._provider._client:
            await self._provider._client.aclose()
        self._initialized = False


# =============================================================================
# SINGLETON INSTANCE
# =============================================================================

_slm_client: Optional[SLMClient] = None


def get_slm_client() -> SLMClient:
    """Get the singleton SLM client instance."""
    global _slm_client
    if _slm_client is None:
        _slm_client = SLMClient()
    return _slm_client


async def initialize_slm_client(config: Optional[SLMConfig] = None) -> SLMClient:
    """Initialize the singleton SLM client."""
    global _slm_client
    _slm_client = SLMClient(config)
    await _slm_client.initialize()
    return _slm_client
