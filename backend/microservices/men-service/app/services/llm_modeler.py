"""
LLM Modeler - Response Synthesis with Conversational Memory.

Uses a medium LLM (Qwen2.5-3B @ 4-bit) to synthesize final responses
combining expert data with conversational context.

VRAM: ~2.5 GB
Always loaded: Yes
Key feature: Maintains conversation history per session
"""

import logging
from typing import Dict, List, Optional

import torch
from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig

logger = logging.getLogger(__name__)


class LLMModeler:
    """
    Response synthesis model with conversational memory.

    Responsibilities:
    1. Maintain conversation history per session
    2. Combine expert data with user context
    3. Generate fluent, contextual responses

    The modeler is always loaded in memory (~2.5 GB VRAM)
    and provides the final response synthesis for every query.
    """

    # System prompt template
    SYSTEM_PROMPT_BASE = """Eres Emma, una asistente especializada en gestión documental empresarial.

Tu rol es proporcionar respuestas precisas, profesionales y útiles sobre documentos, contratos, normativas y procesos empresariales.

Directrices:
- Responde de forma clara y concisa
- Si tienes información técnica del experto, úsala para fundamentar tu respuesta
- Mantén coherencia con la conversación previa
- Si no tienes información suficiente, indícalo claramente
- Usa un tono profesional pero accesible"""

    def __init__(
        self,
        model_name: str = "Qwen/Qwen2.5-3B-Instruct",
        max_history_turns: int = 5,
        max_tokens: int = 500,
        temperature: float = 0.7
    ):
        """
        Initialize the LLM Modeler.

        Args:
            model_name: HuggingFace model ID for response synthesis
            max_history_turns: Maximum conversation turns to keep in memory
            max_tokens: Maximum tokens for response generation
            temperature: Sampling temperature for generation
        """
        self.model_name = model_name
        self.max_history_turns = max_history_turns
        self.max_tokens = max_tokens
        self.temperature = temperature

        self.model = None
        self.tokenizer = None
        self._loaded = False

        # Conversational memory: {session_id: [{role, content}, ...]}
        self._history: Dict[str, List[dict]] = {}

    def load(self) -> None:
        """
        Load the modeler with 4-bit quantization.

        Uses bitsandbytes for memory-efficient inference,
        reducing VRAM from ~6GB to ~2.5GB.
        """
        if self._loaded:
            logger.info("LLM Modeler already loaded")
            return

        logger.info(f"Loading LLM Modeler: {self.model_name} (4-bit)")

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

        logger.info(f"LLM Modeler loaded successfully (~2.5 GB VRAM)")

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
        logger.info("LLM Modeler unloaded")

    def generate_response(
        self,
        user_input: str,
        session_id: str = "default",
        expert_data: Optional[str] = None,
        tenant_context: Optional[str] = None
    ) -> str:
        """
        Generate a synthesized response.

        Combines:
        - User's current query
        - Expert data (if available)
        - Conversation history
        - Tenant context

        Args:
            user_input: Current user query
            session_id: Session identifier for memory
            expert_data: Technical data from expert (optional)
            tenant_context: Tenant-specific context (optional)

        Returns:
            Generated response string
        """
        if not self._loaded:
            self.load()

        # Build dynamic system prompt
        system_parts = [self.SYSTEM_PROMPT_BASE]

        if tenant_context:
            system_parts.append(f"\nContexto del cliente: {tenant_context}")

        if expert_data:
            system_parts.append(
                f"\nInformación técnica relevante (usa esto para fundamentar tu respuesta):\n{expert_data}"
            )

        system_prompt = "\n".join(system_parts)

        # Get or create session history
        if session_id not in self._history:
            self._history[session_id] = []

        history = self._history[session_id]

        # Add current user message
        history.append({"role": "user", "content": user_input})

        # Build messages with history (limited to max_history_turns)
        messages = [{"role": "system", "content": system_prompt}]

        # Include last N turns (user + assistant pairs)
        history_slice = history[-(self.max_history_turns * 2):]
        messages.extend(history_slice)

        # Generate response
        text = self.tokenizer.apply_chat_template(
            messages,
            tokenize=False,
            add_generation_prompt=True
        )
        inputs = self.tokenizer(text, return_tensors="pt").to(self.model.device)

        with torch.no_grad():
            outputs = self.model.generate(
                **inputs,
                max_new_tokens=self.max_tokens,
                temperature=self.temperature,
                top_p=0.9,
                do_sample=True,
                pad_token_id=self.tokenizer.eos_token_id
            )

        # Decode response
        response = self.tokenizer.decode(
            outputs[0][inputs['input_ids'].shape[1]:],
            skip_special_tokens=True
        ).strip()

        # Save response to history
        history.append({"role": "assistant", "content": response})

        # Trim history if too long
        if len(history) > self.max_history_turns * 2:
            self._history[session_id] = history[-(self.max_history_turns * 2):]

        logger.debug(
            f"Generated response for session {session_id} "
            f"({len(response)} chars, {len(history)} messages in history)"
        )

        return response

    def clear_history(self, session_id: str) -> bool:
        """
        Clear conversation history for a session.

        Args:
            session_id: Session identifier

        Returns:
            True if history was cleared, False if session not found
        """
        if session_id in self._history:
            del self._history[session_id]
            logger.info(f"Cleared history for session: {session_id}")
            return True
        return False

    def get_history(self, session_id: str) -> List[dict]:
        """
        Get conversation history for a session.

        Args:
            session_id: Session identifier

        Returns:
            List of message dicts [{role, content}, ...]
        """
        return self._history.get(session_id, []).copy()

    def get_all_sessions(self) -> List[str]:
        """Get all active session IDs."""
        return list(self._history.keys())

    def get_session_count(self) -> int:
        """Get number of active sessions."""
        return len(self._history)

    @property
    def is_loaded(self) -> bool:
        """Check if model is loaded."""
        return self._loaded
