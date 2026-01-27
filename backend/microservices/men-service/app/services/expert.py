"""
MicroLLM Expert - Specialized Domain Knowledge.

Uses a tiny LLM (Qwen2.5-0.5B + LoRA @ 4-bit) fine-tuned on
domain-specific data to provide specialized knowledge.

VRAM: ~0.5 GB
Always loaded: No (dynamic loading/unloading)
Key feature: LoRA adapters for tenant-specific customization
"""

import logging
import os
from typing import Optional

import torch
from peft import PeftModel
from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig

logger = logging.getLogger(__name__)


class MicroLLMExpert:
    """
    Specialized expert model with LoRA fine-tuning.

    Responsibilities:
    1. Provide domain-specific knowledge
    2. Load/unload dynamically to save VRAM
    3. Support tenant-specific LoRA adapters

    Each expert is a small model (~0.5 GB) that can be loaded
    and unloaded as needed, keeping VRAM usage minimal.
    """

    # Expert query prompt template
    EXPERT_PROMPT = """Eres un experto en {domain}.

Proporciona información técnica precisa y específica sobre la siguiente consulta.
Responde de forma concisa pero completa, enfocándote en los detalles técnicos relevantes.

Consulta: {query}

Información técnica:"""

    def __init__(
        self,
        domain: str,
        model_path: Optional[str] = None,
        base_model: str = "Qwen/Qwen2.5-0.5B-Instruct",
        max_tokens: int = 300
    ):
        """
        Initialize a MicroLLM Expert.

        Args:
            domain: Domain specialization (e.g., "legal", "contract")
            model_path: Path to LoRA weights (optional)
            base_model: HuggingFace model ID for base model
            max_tokens: Maximum tokens for response
        """
        self.domain = domain
        self.model_path = model_path
        self.base_model = base_model
        self.max_tokens = max_tokens

        self.model = None
        self.tokenizer = None
        self._loaded = False
        self._has_lora = False

    def load(self) -> None:
        """
        Load the expert model with 4-bit quantization.

        If a LoRA path is provided, loads the base model and applies
        the LoRA adapter. Otherwise, loads just the base model.
        """
        if self._loaded:
            logger.info(f"Expert '{self.domain}' already loaded")
            return

        logger.info(f"Loading Expert '{self.domain}': {self.base_model} (4-bit)")

        # Configure 4-bit quantization
        bnb_config = BitsAndBytesConfig(
            load_in_4bit=True,
            bnb_4bit_quant_type="nf4",
            bnb_4bit_compute_dtype=torch.bfloat16,
            bnb_4bit_use_double_quant=True,
        )

        # Load tokenizer
        self.tokenizer = AutoTokenizer.from_pretrained(
            self.base_model,
            trust_remote_code=True
        )

        # Load base model
        self.model = AutoModelForCausalLM.from_pretrained(
            self.base_model,
            quantization_config=bnb_config,
            device_map="auto",
            trust_remote_code=True,
            torch_dtype=torch.bfloat16,
        )

        # Apply LoRA adapter if path provided and exists
        if self.model_path and os.path.exists(self.model_path):
            logger.info(f"Loading LoRA adapter from: {self.model_path}")
            try:
                self.model = PeftModel.from_pretrained(
                    self.model,
                    self.model_path,
                    is_trainable=False
                )
                self._has_lora = True
                logger.info(f"LoRA adapter loaded for expert '{self.domain}'")
            except Exception as e:
                logger.warning(f"Failed to load LoRA adapter: {e}. Using base model.")
                self._has_lora = False
        else:
            self._has_lora = False
            if self.model_path:
                logger.warning(f"LoRA path not found: {self.model_path}. Using base model.")

        self.model.eval()
        self._loaded = True

        vram_info = "with LoRA" if self._has_lora else "base only"
        logger.info(f"Expert '{self.domain}' loaded successfully ({vram_info}, ~0.5 GB VRAM)")

    def unload(self) -> None:
        """
        Unload the model to free VRAM.

        Called after query to keep memory footprint low.
        """
        if self.model is not None:
            del self.model
            self.model = None
        if self.tokenizer is not None:
            del self.tokenizer
            self.tokenizer = None

        if torch.cuda.is_available():
            torch.cuda.empty_cache()

        self._loaded = False
        self._has_lora = False
        logger.info(f"Expert '{self.domain}' unloaded")

    def query(self, user_query: str, max_tokens: Optional[int] = None) -> str:
        """
        Query the expert for domain-specific information.

        Args:
            user_query: User's question
            max_tokens: Override default max_tokens (optional)

        Returns:
            Expert's technical response
        """
        if not self._loaded:
            self.load()

        # Build expert prompt
        prompt = self.EXPERT_PROMPT.format(
            domain=self._get_domain_description(),
            query=user_query
        )

        # Tokenize
        messages = [{"role": "user", "content": prompt}]
        text = self.tokenizer.apply_chat_template(
            messages,
            tokenize=False,
            add_generation_prompt=True
        )
        inputs = self.tokenizer(text, return_tensors="pt").to(self.model.device)

        # Generate
        tokens = max_tokens or self.max_tokens
        with torch.no_grad():
            outputs = self.model.generate(
                **inputs,
                max_new_tokens=tokens,
                temperature=0.3,  # Lower temperature for factual responses
                top_p=0.9,
                do_sample=True,
                pad_token_id=self.tokenizer.eos_token_id
            )

        # Decode
        response = self.tokenizer.decode(
            outputs[0][inputs['input_ids'].shape[1]:],
            skip_special_tokens=True
        ).strip()

        logger.debug(f"Expert '{self.domain}' responded ({len(response)} chars)")

        return response

    def _get_domain_description(self) -> str:
        """Get human-readable domain description."""
        descriptions = {
            "legal": "derecho y legislación",
            "contract": "contratos y acuerdos comerciales",
            "compliance": "cumplimiento normativo y auditorías",
            "finance": "finanzas y contabilidad empresarial",
            "hr": "recursos humanos y gestión de personal",
            "technical": "documentación técnica y sistemas",
            "general": "gestión documental general",
        }
        return descriptions.get(self.domain, self.domain)

    @property
    def is_loaded(self) -> bool:
        """Check if model is loaded."""
        return self._loaded

    @property
    def has_lora_adapter(self) -> bool:
        """Check if LoRA adapter is loaded."""
        return self._has_lora
