# Emma AI - Arquitectura Voice-First de Producción

## Resumen Ejecutivo

Emma evoluciona de un chatbot de texto a un **Asistente de Voz empresarial** con:

- **Voice-First Design**: Conversación por voz en tiempo real como modo principal
- **Modelo Propio (vLLM)**: Único motor de inferencia, sin dependencias de terceros para LLM
- **Gemini Pro TTS**: Síntesis de voz para respuestas habladas
- **Whisper STT**: Reconocimiento de voz (local o API)
- **Streaming Bidireccional**: Latencia mínima en conversación

```
┌─────────────────────────────────────────────────────────────────┐
│                     EMMA VOICE ASSISTANT                         │
│                                                                  │
│   🎤 Usuario habla → STT → vLLM (modelo propio) → TTS → 🔊      │
│                                                                  │
│   "Analiza el contrato"  →  [Procesamiento]  →  "He encontrado  │
│                                                    3 riesgos..." │
└─────────────────────────────────────────────────────────────────┘
```

---

## 1. Arquitectura Voice-First

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         FRONTEND (Next.js)                                   │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                    EmmaVoiceChat Component                           │   │
│  │                                                                      │   │
│  │  ┌───────────────┐  ┌───────────────┐  ┌───────────────────────┐   │   │
│  │  │ 🎤 Mic Input  │  │ 🔊 Speaker    │  │ 💬 Text (fallback)    │   │   │
│  │  │ WebRTC/Media  │  │ Audio Output  │  │ Para accesibilidad    │   │   │
│  │  └───────┬───────┘  └───────▲───────┘  └───────────────────────┘   │   │
│  │          │                  │                                       │   │
│  │          │    WebSocket (bidireccional)                            │   │
│  │          │    Audio chunks ↕ Text ↕ Events                         │   │
│  └──────────┼──────────────────┼──────────────────────────────────────┘   │
└─────────────┼──────────────────┼──────────────────────────────────────────┘
              │                  │
              ▼                  │
┌─────────────────────────────────────────────────────────────────────────────┐
│                    VOICE GATEWAY (FastAPI + WebSocket)                       │
│                                                                              │
│  ┌──────────────────────────────────────────────────────────────────────┐  │
│  │                     VoiceSessionManager                               │  │
│  │                                                                       │  │
│  │  • WebSocket connection handler (1 per user session)                  │  │
│  │  • Audio buffer & chunking (16kHz, 16-bit PCM)                       │  │
│  │  • Voice Activity Detection (VAD) - detecta inicio/fin de habla      │  │
│  │  • Interrupt handling - usuario puede interrumpir respuesta          │  │
│  │  • Session state (tenant_id, user_id, conversation_context)          │  │
│  └──────────────────────────────────────────────────────────────────────┘  │
│                                    │                                        │
│         ┌──────────────────────────┼──────────────────────────┐            │
│         ▼                          ▼                          ▼            │
│  ┌─────────────────┐    ┌─────────────────────┐    ┌─────────────────┐    │
│  │   STT Service   │    │    EMMA CORE        │    │   TTS Service   │    │
│  │   (Whisper)     │    │    (vLLM)           │    │  (Gemini Pro)   │    │
│  │                 │    │                     │    │                 │    │
│  │  Audio → Text   │───▶│  Text → Response    │───▶│  Text → Audio   │    │
│  │                 │    │  + Agent Actions    │    │                 │    │
│  │  Local o Cloud  │    │  Streaming output   │    │  Streaming MP3  │    │
│  └─────────────────┘    └─────────────────────┘    └─────────────────┘    │
│                                    │                                        │
└────────────────────────────────────┼────────────────────────────────────────┘
                                     │
                                     ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                         vLLM ENGINE (Único LLM)                              │
│                                                                              │
│  ┌──────────────────────────────────────────────────────────────────────┐  │
│  │                     Modelo Propio (fine-tuned)                        │  │
│  │                                                                       │  │
│  │   Base: Qwen2.5-7B / Ministral-8B / Custom                           │  │
│  │   Fine-tuning: Documentos legales españoles                          │  │
│  │   Especialización: Contratos, compliance, análisis                   │  │
│  │                                                                       │  │
│  │   Hardware: RTX 4090 (24GB VRAM)                                     │  │
│  │   Context: 32K tokens (extensible a 128K con YaRN)                   │  │
│  │   Throughput: ~50 tokens/s generación                                │  │
│  └──────────────────────────────────────────────────────────────────────┘  │
│                                                                              │
│  ┌──────────────────────────────────────────────────────────────────────┐  │
│  │                     Streaming Optimizations                           │  │
│  │                                                                       │  │
│  │   • Continuous batching (múltiples requests en paralelo)             │  │
│  │   • Speculative decoding (predicción de tokens)                      │  │
│  │   • KV-cache optimization (memoria eficiente)                        │  │
│  │   • First-token latency < 200ms                                      │  │
│  └──────────────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────────────┘
                                     │
                                     ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                      EMMA ORCHESTRATION (Simplificado)                       │
│                                                                              │
│  ┌──────────────────────────────────────────────────────────────────────┐  │
│  │                      Voice-Optimized Pipeline                         │  │
│  │                                                                       │  │
│  │   1. Conversational Check (YAML patterns) ────────┐                  │  │
│  │      └─ Saludos, despedidas → respuesta directa   │                  │  │
│  │                                                    │                  │  │
│  │   2. Intent Detection (fast, rule-based) ─────────┤                  │  │
│  │      └─ Detecta si necesita agentes o RAG simple  │                  │  │
│  │                                                    ▼                  │  │
│  │   3. Execution Strategy ────────────────────────────┐                │  │
│  │      │                                              │                │  │
│  │      ├─ FAST PATH: RAG simple (<2s)                │                │  │
│  │      │   └─ Búsqueda + respuesta streaming          │                │  │
│  │      │                                              │                │  │
│  │      └─ DEEP PATH: Agentes (2-30s)                 │                │  │
│  │          └─ PlanningFlow con progress streaming    │                │  │
│  │          └─ "Estoy analizando... encontré X..."    │                │  │
│  └──────────────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 2. Flujo de Voice Chat

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                        VOICE CONVERSATION FLOW                               │
└─────────────────────────────────────────────────────────────────────────────┘

Usuario                    Voice Gateway                 Emma Core
   │                            │                            │
   │  🎤 Empieza a hablar       │                            │
   │ ──────────────────────────▶│                            │
   │                            │ VAD detecta inicio         │
   │  Audio chunks (streaming)  │                            │
   │ ──────────────────────────▶│                            │
   │                            │                            │
   │  🎤 Deja de hablar         │                            │
   │ ──────────────────────────▶│                            │
   │                            │ VAD detecta fin            │
   │                            │                            │
   │                            │ STT (Whisper)              │
   │                            │ "Analiza el contrato"      │
   │                            │ ─────────────────────────▶ │
   │                            │                            │ Intent: document_analysis
   │                            │                            │ Strategy: DEEP PATH
   │                            │                            │
   │                            │ ◀───────────────────────── │ Stream token: "Voy"
   │                            │ TTS chunk                  │
   │ ◀──────────────────────────│                            │
   │  🔊 "Voy..."               │                            │
   │                            │ ◀───────────────────────── │ Stream: "a analizar"
   │                            │ TTS chunk                  │
   │ ◀──────────────────────────│                            │
   │  🔊 "...a analizar..."     │                            │
   │                            │                            │
   │                            │      [Agentes ejecutando]  │
   │                            │                            │
   │                            │ ◀───────────────────────── │ Stream: "He encontrado"
   │ ◀──────────────────────────│                            │
   │  🔊 "He encontrado..."     │                            │
   │                            │ ◀───────────────────────── │ Stream: "3 riesgos"
   │ ◀──────────────────────────│                            │
   │  🔊 "...3 riesgos..."      │                            │
   │                            │                            │
   │  🎤 INTERRUMPE             │                            │
   │ ──────────────────────────▶│ Cancel current TTS         │
   │                            │ ─────────────────────────▶ │ Interrupt signal
   │                            │                            │
   │  "¿Cuál es el más grave?"  │                            │
   │ ──────────────────────────▶│ New query                  │
   │                            │ ─────────────────────────▶ │
   │                            │                            │
```

---

## 3. Componentes Voice-Specific

### 3.1 Voice Session Manager

```python
# app/services/voice/voice_session.py

import asyncio
from dataclasses import dataclass, field
from typing import Optional, AsyncGenerator, Callable
from enum import Enum
import logging

logger = logging.getLogger(__name__)

class VoiceState(Enum):
    IDLE = "idle"                    # Esperando input
    LISTENING = "listening"          # Usuario hablando
    PROCESSING = "processing"        # STT + vLLM procesando
    SPEAKING = "speaking"            # TTS reproduciendo
    INTERRUPTED = "interrupted"      # Usuario interrumpió

@dataclass
class VoiceSession:
    """Estado de una sesión de voz."""
    session_id: str
    tenant_id: str
    user_id: str
    state: VoiceState = VoiceState.IDLE

    # Audio buffers
    input_buffer: bytes = b""       # Audio del usuario
    output_queue: asyncio.Queue = field(default_factory=asyncio.Queue)

    # Conversation context
    conversation_history: list = field(default_factory=list)
    current_document_id: Optional[str] = None

    # Control flags
    interrupt_requested: bool = False

class VoiceSessionManager:
    """
    Gestiona sesiones de voz con WebSocket.

    Responsabilidades:
    - Mantener conexión WebSocket por usuario
    - Buffer y chunking de audio
    - Detección de actividad vocal (VAD)
    - Coordinación STT → vLLM → TTS
    - Manejo de interrupciones
    """

    def __init__(
        self,
        stt_service: 'STTService',
        emma_core: 'EmmaService',
        tts_service: 'TTSService',
    ):
        self.stt = stt_service
        self.emma = emma_core
        self.tts = tts_service
        self.sessions: dict[str, VoiceSession] = {}

        # VAD settings
        self.vad_threshold = 0.5      # Sensibilidad
        self.silence_duration = 1.0    # Segundos de silencio para detectar fin

    async def handle_websocket(
        self,
        websocket: 'WebSocket',
        session_id: str,
        tenant_id: str,
        user_id: str,
    ):
        """Handler principal para conexión WebSocket de voz."""

        # Crear o recuperar sesión
        session = self._get_or_create_session(session_id, tenant_id, user_id)

        try:
            # Tasks paralelos para input y output
            input_task = asyncio.create_task(
                self._handle_input(websocket, session)
            )
            output_task = asyncio.create_task(
                self._handle_output(websocket, session)
            )

            await asyncio.gather(input_task, output_task)

        except Exception as e:
            logger.error(f"Voice session error: {e}")
        finally:
            self._cleanup_session(session_id)

    async def _handle_input(
        self,
        websocket: 'WebSocket',
        session: VoiceSession,
    ):
        """Procesa audio input del usuario."""

        async for message in websocket.iter_bytes():
            # Check for interrupt during TTS playback
            if session.state == VoiceState.SPEAKING:
                if self._detect_speech(message):
                    logger.info(f"🛑 Interrupt detected in session {session.session_id}")
                    session.interrupt_requested = True
                    session.state = VoiceState.INTERRUPTED
                    continue

            # Accumulate audio in buffer
            session.input_buffer += message

            # VAD: detect end of speech
            if session.state == VoiceState.LISTENING:
                if self._detect_silence(session.input_buffer):
                    await self._process_utterance(session)

            elif session.state == VoiceState.IDLE:
                if self._detect_speech(message):
                    session.state = VoiceState.LISTENING
                    logger.info(f"🎤 Speech started in session {session.session_id}")

    async def _process_utterance(self, session: VoiceSession):
        """Procesa un utterance completo del usuario."""
        session.state = VoiceState.PROCESSING

        try:
            # 1. STT: Audio → Text
            audio_data = session.input_buffer
            session.input_buffer = b""  # Clear buffer

            transcript = await self.stt.transcribe(audio_data)
            logger.info(f"📝 Transcribed: {transcript[:100]}...")

            if not transcript.strip():
                session.state = VoiceState.IDLE
                return

            # 2. Emma Core: Text → Response (streaming)
            session.state = VoiceState.SPEAKING

            async for text_chunk in self._get_emma_response_stream(
                session, transcript
            ):
                # Check for interrupt
                if session.interrupt_requested:
                    logger.info("🛑 Response interrupted, stopping")
                    session.interrupt_requested = False
                    break

                # 3. TTS: Text chunk → Audio chunk
                audio_chunk = await self.tts.synthesize_chunk(text_chunk)
                await session.output_queue.put(audio_chunk)

            # Signal end of response
            await session.output_queue.put(None)

        except Exception as e:
            logger.error(f"Utterance processing error: {e}")
        finally:
            session.state = VoiceState.IDLE

    async def _get_emma_response_stream(
        self,
        session: VoiceSession,
        query: str,
    ) -> AsyncGenerator[str, None]:
        """Obtiene respuesta de Emma como stream de texto."""

        # Build context with conversation history
        from app.schemas.emma import EmmaQuery

        emma_query = EmmaQuery(
            query=query,
            tenant_id=session.tenant_id,
            session_id=session.session_id,
            context={
                "document_id": session.current_document_id,
                "conversation_history": session.conversation_history[-5:],
                "voice_mode": True,  # Signal for shorter responses
            }
        )

        # Stream response from Emma
        async for event in self.emma.execute_query_stream(emma_query):
            if event.get("event") == "token":
                yield event.get("data", {}).get("text", "")
            elif event.get("event") == "complete":
                # Update conversation history
                session.conversation_history.append({
                    "role": "user",
                    "content": query,
                })
                session.conversation_history.append({
                    "role": "assistant",
                    "content": event.get("data", {}).get("answer", ""),
                })

    async def _handle_output(
        self,
        websocket: 'WebSocket',
        session: VoiceSession,
    ):
        """Envía audio output al cliente."""

        while True:
            audio_chunk = await session.output_queue.get()

            if audio_chunk is None:
                # End of current response
                await websocket.send_json({"event": "response_end"})
                continue

            if session.interrupt_requested:
                # Skip remaining audio if interrupted
                continue

            await websocket.send_bytes(audio_chunk)

    def _detect_speech(self, audio: bytes) -> bool:
        """Detecta si hay voz en el audio (VAD simple)."""
        # TODO: Implementar VAD real (webrtcvad, silero-vad)
        # Por ahora, basado en energía
        import struct
        samples = struct.unpack(f'{len(audio)//2}h', audio)
        energy = sum(abs(s) for s in samples) / len(samples)
        return energy > 500  # Threshold

    def _detect_silence(self, audio: bytes) -> bool:
        """Detecta silencio prolongado (fin de utterance)."""
        # Check last N samples for silence
        # TODO: Implementar con timestamps
        return False

    def _get_or_create_session(
        self,
        session_id: str,
        tenant_id: str,
        user_id: str,
    ) -> VoiceSession:
        """Obtiene o crea sesión de voz."""
        if session_id not in self.sessions:
            self.sessions[session_id] = VoiceSession(
                session_id=session_id,
                tenant_id=tenant_id,
                user_id=user_id,
            )
        return self.sessions[session_id]

    def _cleanup_session(self, session_id: str):
        """Limpia recursos de sesión."""
        if session_id in self.sessions:
            del self.sessions[session_id]
```

### 3.2 STT Service (Whisper)

```python
# app/services/voice/stt_service.py

import logging
from typing import Optional
from dataclasses import dataclass

logger = logging.getLogger(__name__)

@dataclass
class STTConfig:
    """Configuración de Speech-to-Text."""
    # Whisper local (faster-whisper) o API
    use_local: bool = True
    model_size: str = "base"  # tiny, base, small, medium, large
    language: str = "es"

    # API fallback (Google, Azure, etc.)
    api_provider: Optional[str] = None
    api_key: Optional[str] = None

class STTService:
    """
    Speech-to-Text usando Whisper.

    Opciones:
    1. faster-whisper (local, GPU) - Recomendado
    2. OpenAI Whisper API (cloud)
    3. Google Speech-to-Text (cloud fallback)
    """

    def __init__(self, config: STTConfig):
        self.config = config
        self._model = None

    async def initialize(self):
        """Carga modelo Whisper local."""
        if self.config.use_local:
            try:
                from faster_whisper import WhisperModel

                # Use GPU if available
                self._model = WhisperModel(
                    self.config.model_size,
                    device="cuda",
                    compute_type="float16",
                )
                logger.info(f"✅ Whisper {self.config.model_size} loaded on GPU")
            except Exception as e:
                logger.warning(f"⚠️ Local Whisper failed: {e}, using API")
                self.config.use_local = False

    async def transcribe(
        self,
        audio_data: bytes,
        language: Optional[str] = None,
    ) -> str:
        """
        Transcribe audio a texto.

        Args:
            audio_data: PCM audio (16kHz, 16-bit, mono)
            language: Código de idioma (es, en, etc.)

        Returns:
            Texto transcrito
        """
        lang = language or self.config.language

        if self.config.use_local and self._model:
            return await self._transcribe_local(audio_data, lang)
        else:
            return await self._transcribe_api(audio_data, lang)

    async def _transcribe_local(
        self,
        audio_data: bytes,
        language: str,
    ) -> str:
        """Transcripción con faster-whisper local."""
        import io
        import numpy as np

        # Convert bytes to numpy array
        audio_array = np.frombuffer(audio_data, dtype=np.int16).astype(np.float32) / 32768.0

        # Transcribe
        segments, info = self._model.transcribe(
            audio_array,
            language=language,
            beam_size=5,
            vad_filter=True,
        )

        # Concatenate segments
        text = " ".join(segment.text for segment in segments)

        logger.debug(f"📝 Local STT: {text[:100]}... (lang={info.language})")
        return text.strip()

    async def _transcribe_api(
        self,
        audio_data: bytes,
        language: str,
    ) -> str:
        """Transcripción con API (OpenAI Whisper)."""
        import httpx

        async with httpx.AsyncClient() as client:
            response = await client.post(
                "https://api.openai.com/v1/audio/transcriptions",
                headers={"Authorization": f"Bearer {self.config.api_key}"},
                files={"file": ("audio.wav", audio_data, "audio/wav")},
                data={"model": "whisper-1", "language": language},
            )
            response.raise_for_status()
            return response.json()["text"]
```

### 3.3 TTS Service (Gemini Pro)

```python
# app/services/voice/tts_service.py

import logging
from typing import AsyncGenerator, Optional
from dataclasses import dataclass

logger = logging.getLogger(__name__)

@dataclass
class TTSConfig:
    """Configuración de Text-to-Speech."""
    provider: str = "gemini"  # gemini, elevenlabs, azure
    voice_id: str = "es-ES-Wavenet-B"  # Voz española
    speaking_rate: float = 1.0
    pitch: float = 0.0

    # API keys
    google_api_key: Optional[str] = None
    elevenlabs_api_key: Optional[str] = None

class TTSService:
    """
    Text-to-Speech usando Gemini Pro (Google).

    Features:
    - Streaming output (chunks de audio)
    - Múltiples voces
    - SSML support para entonación
    """

    def __init__(self, config: TTSConfig):
        self.config = config
        self._client = None

    async def initialize(self):
        """Inicializa cliente de TTS."""
        if self.config.provider == "gemini":
            from google.cloud import texttospeech_v1 as tts
            self._client = tts.TextToSpeechAsyncClient()
            logger.info("✅ Gemini TTS client initialized")

    async def synthesize(
        self,
        text: str,
        voice_id: Optional[str] = None,
    ) -> bytes:
        """
        Sintetiza texto completo a audio.

        Args:
            text: Texto a sintetizar
            voice_id: ID de voz a usar

        Returns:
            Audio en formato MP3
        """
        if self.config.provider == "gemini":
            return await self._synthesize_gemini(text, voice_id)
        elif self.config.provider == "elevenlabs":
            return await self._synthesize_elevenlabs(text, voice_id)
        else:
            raise ValueError(f"Unknown TTS provider: {self.config.provider}")

    async def synthesize_stream(
        self,
        text_stream: AsyncGenerator[str, None],
    ) -> AsyncGenerator[bytes, None]:
        """
        Sintetiza stream de texto a stream de audio.

        Optimización: agrupa tokens pequeños para reducir llamadas API.

        Args:
            text_stream: Generator de chunks de texto

        Yields:
            Chunks de audio MP3
        """
        buffer = ""
        min_chunk_size = 50  # Caracteres mínimos antes de sintetizar

        async for text_chunk in text_stream:
            buffer += text_chunk

            # Sintetizar cuando tenemos suficiente texto o hay puntuación
            if len(buffer) >= min_chunk_size or self._has_sentence_end(buffer):
                if buffer.strip():
                    audio_chunk = await self.synthesize(buffer)
                    yield audio_chunk
                    buffer = ""

        # Sintetizar resto del buffer
        if buffer.strip():
            audio_chunk = await self.synthesize(buffer)
            yield audio_chunk

    async def synthesize_chunk(self, text: str) -> bytes:
        """Sintetiza un chunk de texto."""
        return await self.synthesize(text)

    async def _synthesize_gemini(
        self,
        text: str,
        voice_id: Optional[str] = None,
    ) -> bytes:
        """Síntesis con Google Cloud TTS."""
        from google.cloud import texttospeech_v1 as tts

        voice = voice_id or self.config.voice_id

        # Parse voice ID (format: es-ES-Wavenet-B)
        parts = voice.split("-")
        language_code = f"{parts[0]}-{parts[1]}"

        request = tts.SynthesizeSpeechRequest(
            input=tts.SynthesisInput(text=text),
            voice=tts.VoiceSelectionParams(
                language_code=language_code,
                name=voice,
            ),
            audio_config=tts.AudioConfig(
                audio_encoding=tts.AudioEncoding.MP3,
                speaking_rate=self.config.speaking_rate,
                pitch=self.config.pitch,
            ),
        )

        response = await self._client.synthesize_speech(request)
        return response.audio_content

    async def _synthesize_elevenlabs(
        self,
        text: str,
        voice_id: Optional[str] = None,
    ) -> bytes:
        """Síntesis con ElevenLabs (alternativa)."""
        import httpx

        voice = voice_id or "21m00Tcm4TlvDq8ikWAM"  # Rachel

        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"https://api.elevenlabs.io/v1/text-to-speech/{voice}",
                headers={
                    "xi-api-key": self.config.elevenlabs_api_key,
                    "Content-Type": "application/json",
                },
                json={
                    "text": text,
                    "model_id": "eleven_multilingual_v2",
                    "voice_settings": {
                        "stability": 0.5,
                        "similarity_boost": 0.75,
                    }
                },
            )
            response.raise_for_status()
            return response.content

    def _has_sentence_end(self, text: str) -> bool:
        """Detecta fin de oración para chunking natural."""
        return any(text.rstrip().endswith(p) for p in [".", "!", "?", ":", ";"])
```

---

## 4. API Endpoints para Voice

```python
# app/api/v1/voice.py

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends
from app.services.voice import VoiceSessionManager, STTService, TTSService
from app.services.emma_service import emma_service
from app.core.security import verify_ws_token

router = APIRouter(prefix="/voice", tags=["voice"])

# Global services (initialized at startup)
voice_manager: VoiceSessionManager = None

@router.websocket("/ws/{session_id}")
async def voice_websocket(
    websocket: WebSocket,
    session_id: str,
    token: str,  # JWT token in query param
):
    """
    WebSocket endpoint para Voice Chat.

    Protocol:
    - Client sends: audio chunks (binary) or JSON commands
    - Server sends: audio chunks (binary) or JSON events

    Commands (client → server):
    - {"type": "start"} - Start recording
    - {"type": "stop"} - Stop recording
    - {"type": "interrupt"} - Interrupt current response
    - {"type": "set_document", "document_id": "..."} - Set context

    Events (server → client):
    - {"event": "listening"} - Ready for input
    - {"event": "processing"} - Processing query
    - {"event": "speaking"} - Playing response
    - {"event": "response_end"} - Response complete
    - {"event": "error", "message": "..."} - Error occurred
    """
    # Verify token
    payload = verify_ws_token(token)
    tenant_id = payload.get("tenant_id")
    user_id = payload.get("user_id")

    await websocket.accept()

    try:
        await voice_manager.handle_websocket(
            websocket=websocket,
            session_id=session_id,
            tenant_id=tenant_id,
            user_id=user_id,
        )
    except WebSocketDisconnect:
        pass  # Normal disconnect
    except Exception as e:
        await websocket.send_json({"event": "error", "message": str(e)})

@router.post("/synthesize")
async def synthesize_text(
    text: str,
    voice_id: str = "es-ES-Wavenet-B",
    _: bool = Depends(verify_api_key),
):
    """
    Endpoint HTTP para TTS (para testing o fallback).

    Returns audio/mpeg
    """
    from fastapi.responses import Response

    audio = await voice_manager.tts.synthesize(text, voice_id)
    return Response(content=audio, media_type="audio/mpeg")
```

---

## 5. Optimizaciones para Latencia

### 5.1 vLLM Streaming

```python
# app/services/vllm_streaming.py

async def stream_vllm_response(
    prompt: str,
    config: dict,
) -> AsyncGenerator[str, None]:
    """
    Stream tokens desde vLLM con latencia mínima.

    Optimizaciones:
    - First token < 200ms
    - Streaming HTTP chunks
    - No buffering
    """
    import httpx

    async with httpx.AsyncClient() as client:
        async with client.stream(
            "POST",
            f"{config['vllm_base_url']}/chat/completions",
            json={
                "model": config["model"],
                "messages": [{"role": "user", "content": prompt}],
                "stream": True,
                "max_tokens": 1024,
                "temperature": 0.2,
            },
            timeout=None,  # Streaming, no timeout
        ) as response:
            async for line in response.aiter_lines():
                if line.startswith("data: "):
                    data = line[6:]
                    if data == "[DONE]":
                        break

                    import json
                    chunk = json.loads(data)
                    delta = chunk.get("choices", [{}])[0].get("delta", {})
                    content = delta.get("content", "")

                    if content:
                        yield content
```

### 5.2 Sentence-Level TTS Pipelining

```
Timeline optimizado:

vLLM:     [Token1][Token2][Token3][Token4][...][Sentence1 END][Token5][...]
                                                    │
TTS:                                    [Synth Sentence1]───────────────▶
                                                    │
Audio:                                              [Play]──────────────▶

Resultado: Audio empieza ~500ms después del primer token de la oración
```

---

## 6. Frontend Component (React)

```typescript
// components/EmmaVoiceChat.tsx

import { useState, useRef, useCallback, useEffect } from 'react';

interface VoiceState {
  status: 'idle' | 'listening' | 'processing' | 'speaking';
  transcript: string;
  response: string;
}

export function EmmaVoiceChat({ sessionId, tenantId }: Props) {
  const [state, setState] = useState<VoiceState>({
    status: 'idle',
    transcript: '',
    response: '',
  });

  const wsRef = useRef<WebSocket | null>(null);
  const audioContextRef = useRef<AudioContext | null>(null);
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);

  // Initialize WebSocket
  useEffect(() => {
    const token = getAuthToken(); // JWT
    const ws = new WebSocket(
      `wss://api.nouxcubeia.app/voice/ws/${sessionId}?token=${token}`
    );

    ws.onopen = () => {
      console.log('Voice WebSocket connected');
    };

    ws.onmessage = async (event) => {
      if (event.data instanceof Blob) {
        // Audio data - play it
        await playAudioChunk(event.data);
      } else {
        // JSON event
        const data = JSON.parse(event.data);
        handleVoiceEvent(data);
      }
    };

    wsRef.current = ws;

    return () => ws.close();
  }, [sessionId]);

  // Start recording
  const startListening = async () => {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    const mediaRecorder = new MediaRecorder(stream, {
      mimeType: 'audio/webm;codecs=opus',
    });

    mediaRecorder.ondataavailable = (event) => {
      if (event.data.size > 0 && wsRef.current?.readyState === WebSocket.OPEN) {
        wsRef.current.send(event.data);
      }
    };

    mediaRecorder.start(100); // Send chunks every 100ms
    mediaRecorderRef.current = mediaRecorder;
    setState(s => ({ ...s, status: 'listening' }));
  };

  // Stop recording
  const stopListening = () => {
    mediaRecorderRef.current?.stop();
    setState(s => ({ ...s, status: 'processing' }));
  };

  // Interrupt Emma
  const interrupt = () => {
    wsRef.current?.send(JSON.stringify({ type: 'interrupt' }));
    setState(s => ({ ...s, status: 'idle' }));
  };

  // Play audio chunk
  const playAudioChunk = async (blob: Blob) => {
    if (!audioContextRef.current) {
      audioContextRef.current = new AudioContext();
    }

    const arrayBuffer = await blob.arrayBuffer();
    const audioBuffer = await audioContextRef.current.decodeAudioData(arrayBuffer);

    const source = audioContextRef.current.createBufferSource();
    source.buffer = audioBuffer;
    source.connect(audioContextRef.current.destination);
    source.start();
  };

  // Handle voice events
  const handleVoiceEvent = (event: any) => {
    switch (event.event) {
      case 'listening':
        setState(s => ({ ...s, status: 'listening' }));
        break;
      case 'processing':
        setState(s => ({ ...s, status: 'processing' }));
        break;
      case 'speaking':
        setState(s => ({ ...s, status: 'speaking' }));
        break;
      case 'transcript':
        setState(s => ({ ...s, transcript: event.text }));
        break;
      case 'response_text':
        setState(s => ({ ...s, response: s.response + event.text }));
        break;
      case 'response_end':
        setState(s => ({ ...s, status: 'idle', response: '' }));
        break;
    }
  };

  return (
    <div className="emma-voice-chat">
      {/* Voice visualization */}
      <VoiceVisualizer status={state.status} />

      {/* Controls */}
      <div className="controls">
        {state.status === 'idle' && (
          <button onClick={startListening}>
            🎤 Hablar con Emma
          </button>
        )}

        {state.status === 'listening' && (
          <button onClick={stopListening}>
            ⏹️ Terminar
          </button>
        )}

        {state.status === 'speaking' && (
          <button onClick={interrupt}>
            ✋ Interrumpir
          </button>
        )}
      </div>

      {/* Transcript display */}
      {state.transcript && (
        <div className="transcript">
          <strong>Tú:</strong> {state.transcript}
        </div>
      )}

      {state.response && (
        <div className="response">
          <strong>Emma:</strong> {state.response}
        </div>
      )}
    </div>
  );
}
```

---

## 7. Stack Tecnológico Simplificado

| Componente | Tecnología | Justificación |
|------------|------------|---------------|
| **LLM** | vLLM (modelo propio) | Único motor, sin dependencias |
| **STT** | faster-whisper (local) | GPU local, sin latencia API |
| **TTS** | Gemini Pro | Calidad + streaming + español |
| **Streaming** | WebSocket | Bidireccional, baja latencia |
| **VAD** | silero-vad | Ligero, preciso |
| **Audio Format** | PCM 16kHz | Universal, sin compresión |

---

## 8. Métricas de Latencia Objetivo

| Fase | Objetivo | Actual (estimado) |
|------|----------|-------------------|
| VAD detection | <50ms | TBD |
| STT (Whisper) | <500ms | ~300-500ms |
| vLLM first token | <200ms | ~150-300ms |
| TTS first chunk | <300ms | ~200-400ms |
| **End-to-end** | **<1.5s** | TBD |

---

## 9. Plan de Implementación

### Fase 1: STT + TTS Services (1 semana)
- [ ] Implementar STTService con faster-whisper
- [ ] Implementar TTSService con Gemini Pro
- [ ] Tests unitarios

### Fase 2: Voice Gateway (1-2 semanas)
- [ ] WebSocket endpoint
- [ ] VoiceSessionManager
- [ ] VAD integration
- [ ] Interrupt handling

### Fase 3: Frontend Component (1 semana)
- [ ] EmmaVoiceChat React component
- [ ] Audio recording/playback
- [ ] Visual feedback

### Fase 4: Optimizaciones (1 semana)
- [ ] Streaming pipeline
- [ ] Latency profiling
- [ ] Buffer tuning

### Fase 5: Testing & Polish (1 semana)
- [ ] Integration tests
- [ ] Load testing
- [ ] UX refinements

---

*Documento actualizado - Diciembre 2024*
*Enfoque: Voice-First con vLLM como único motor de inferencia*
