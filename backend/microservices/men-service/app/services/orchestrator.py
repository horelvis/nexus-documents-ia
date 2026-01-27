"""
MEN Orchestrator - Domain Classification Component.

Uses a small LLM (Qwen2.5-1.5B @ 4-bit) to classify user queries
into domains and route them to the appropriate expert.

VRAM: ~1.5 GB
Always loaded: Yes
"""

import logging
from typing import List, Optional, Tuple

import torch
from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig

logger = logging.getLogger(__name__)


class Orchestrator:
    """
    Domain classifier for the MEN architecture.

    Responsibilities:
    1. Analyze user queries to determine domain
    2. Return confidence scores for routing decisions
    3. Support multi-domain classification

    The orchestrator is always loaded in memory (~1.5 GB VRAM)
    and provides fast domain classification for every query.
    """

    # Domain classification prompt template
    CLASSIFICATION_PROMPT = """Analiza la siguiente consulta del usuario y clasifica el dominio principal.

Dominios disponibles:
- legal: Consultas sobre leyes, normativas, jurisprudencia
- contract: Consultas sobre contratos, acuerdos, cláusulas
- compliance: Consultas sobre cumplimiento normativo, auditorías
- finance: Consultas sobre finanzas, presupuestos, contabilidad
- hr: Consultas sobre recursos humanos, empleados, nóminas
- technical: Consultas técnicas, documentación de sistemas
- general: Consultas generales que no encajan en otros dominios
- none: La consulta no requiere conocimiento especializado

Consulta del usuario: {query}

Responde SOLO con el nombre del dominio más apropiado (una palabra):"""

    def __init__(
        self,
        model_name: str = "Qwen/Qwen2.5-1.5B-Instruct",
        domains: Optional[List[str]] = None,
        confidence_threshold: float = 0.6
    ):
        """
        Initialize the Orchestrator.

        Args:
            model_name: HuggingFace model ID for the classifier
            domains: List of supported domains
            confidence_threshold: Minimum confidence for domain selection
        """
        self.model_name = model_name
        self.domains = domains or [
            "legal", "contract", "compliance", "finance",
            "hr", "technical", "general", "none"
        ]
        self.confidence_threshold = confidence_threshold

        self.model = None
        self.tokenizer = None
        self._loaded = False

    def load(self) -> None:
        """
        Load the orchestrator model with 4-bit quantization.

        Uses bitsandbytes for memory-efficient inference,
        reducing VRAM from ~3GB to ~1.5GB.
        """
        if self._loaded:
            logger.info("Orchestrator already loaded")
            return

        logger.info(f"Loading Orchestrator: {self.model_name} (4-bit)")

        # Configure 4-bit quantization
        bnb_config = BitsAndBytesConfig(
            load_in_4bit=True,
            bnb_4bit_quant_type="nf4",
            bnb_4bit_compute_dtype=torch.bfloat16,
            bnb_4bit_use_double_quant=True,
        )

        # Load tokenizer
        self.tokenizer = AutoTokenizer.from_pretrained(
            self.model_name,
            trust_remote_code=True
        )

        # Load model with quantization
        self.model = AutoModelForCausalLM.from_pretrained(
            self.model_name,
            quantization_config=bnb_config,
            device_map="auto",
            trust_remote_code=True,
            torch_dtype=torch.bfloat16,
        )
        self.model.eval()
        self._loaded = True

        logger.info(f"Orchestrator loaded successfully (~1.5 GB VRAM)")

    def unload(self) -> None:
        """Unload the model to free VRAM."""
        if self.model is not None:
            del self.model
            self.model = None
        if self.tokenizer is not None:
            del self.tokenizer
            self.tokenizer = None

        if torch.cuda.is_available():
            torch.cuda.empty_cache()

        self._loaded = False
        logger.info("Orchestrator unloaded")

    def route(self, query: str) -> List[str]:
        """
        Classify a query and return the most likely domain(s).

        Args:
            query: User's input query

        Returns:
            List of domain names, ordered by relevance.
            Usually returns single domain, but can return multiple
            if the query spans domains.
        """
        if not self._loaded:
            self.load()

        # Build classification prompt
        prompt = self.CLASSIFICATION_PROMPT.format(query=query)

        # Tokenize
        messages = [{"role": "user", "content": prompt}]
        text = self.tokenizer.apply_chat_template(
            messages,
            tokenize=False,
            add_generation_prompt=True
        )
        inputs = self.tokenizer(text, return_tensors="pt").to(self.model.device)

        # Generate classification
        with torch.no_grad():
            outputs = self.model.generate(
                **inputs,
                max_new_tokens=10,
                temperature=0.1,  # Low temperature for deterministic classification
                do_sample=False,
                pad_token_id=self.tokenizer.eos_token_id
            )

        # Decode response
        response = self.tokenizer.decode(
            outputs[0][inputs['input_ids'].shape[1]:],
            skip_special_tokens=True
        ).strip().lower()

        # Extract domain from response
        detected_domain = self._extract_domain(response)

        logger.debug(f"Query classified: '{query[:50]}...' -> {detected_domain}")

        return [detected_domain]

    def route_with_confidence(self, query: str) -> Tuple[str, float]:
        """
        Classify a query and return domain with confidence score.

        Args:
            query: User's input query

        Returns:
            Tuple of (domain_name, confidence_score)
        """
        domains = self.route(query)
        domain = domains[0] if domains else "none"

        # For now, return fixed confidence
        # TODO: Implement actual confidence scoring using logits
        confidence = 0.8 if domain != "none" else 0.5

        return domain, confidence

    def _extract_domain(self, response: str) -> str:
        """
        Extract domain name from model response.

        Handles various response formats and normalizes to valid domain.
        """
        response = response.strip().lower()

        # Direct match
        for domain in self.domains:
            if domain in response:
                return domain

        # Fuzzy matching for common variations
        domain_aliases = {
            "contratos": "contract",
            "contrato": "contract",
            "juridico": "legal",
            "jurídico": "legal",
            "cumplimiento": "compliance",
            "financiero": "finance",
            "finanzas": "finance",
            "recursos humanos": "hr",
            "rrhh": "hr",
            "técnico": "technical",
            "tecnico": "technical",
        }

        for alias, domain in domain_aliases.items():
            if alias in response:
                return domain

        # Default to general if no match
        return "general"

    @property
    def is_loaded(self) -> bool:
        """Check if model is loaded."""
        return self._loaded
