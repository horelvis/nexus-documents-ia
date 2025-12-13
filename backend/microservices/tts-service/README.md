# TTS Service

Text-to-Speech microservice for NexusDocs360 using Microsoft VibeVoice for real-time streaming speech synthesis.

## Features

- **Real-time streaming TTS** with ~300ms latency to first audio
- **Multiple language support**: English, Spanish, and more
- **Dual provider support**: VibeVoice (primary) + Google Cloud TTS (fallback)
- **Audio caching** via Redis for frequently used phrases
- **WebSocket API** for streaming applications
- **REST API** for batch synthesis

## Architecture

```
┌─────────────────────────────────────────────────┐
│               TTS Service                        │
├─────────────────────────────────────────────────┤
│  FastAPI + WebSocket Server                     │
│  • POST /api/v1/tts/synthesize (batch)         │
│  • WS   /api/v1/tts/stream (realtime)          │
│  • GET  /api/v1/tts/voices                     │
├─────────────────────────────────────────────────┤
│  TTS Provider Factory                           │
│  ├── VibeVoice Provider (primary)              │
│  │   └── microsoft/VibeVoice-Realtime-0.5B     │
│  └── Google TTS Provider (fallback)            │
├─────────────────────────────────────────────────┤
│  Audio Cache (Redis)                            │
└─────────────────────────────────────────────────┘
```

## Requirements

- **GPU**: NVIDIA CUDA-capable GPU (RTX 4090 recommended)
- **VRAM**: ~2-3GB for VibeVoice model
- **Python**: 3.11+
- **Docker**: With NVIDIA Container Toolkit

## Configuration

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `TTS_PROVIDER` | `vibevoice` | TTS provider: `vibevoice` or `google` |
| `VIBEVOICE_MODEL_PATH` | `microsoft/VibeVoice-Realtime-0.5B` | HuggingFace model path |
| `VIBEVOICE_DEVICE` | `cuda` | Device: `cuda`, `cpu`, `mps` |
| `VIBEVOICE_DEFAULT_VOICE` | `Carter` | Default voice ID |
| `GOOGLE_TTS_ENABLED` | `false` | Enable Google TTS fallback |
| `GOOGLE_TTS_DEFAULT_VOICE` | `es-ES-Neural2-A` | Default Google voice |
| `MICROSERVICES_API_KEY` | - | API key for authentication |
| `HF_TOKEN` | - | HuggingFace token for model download |
| `REDIS_HOST` | `redis` | Redis host for caching |
| `CACHE_ENABLED` | `true` | Enable audio caching |

## API Endpoints

### REST Endpoints

#### GET /health
Simple health check (no auth required).

#### GET /api/v1/tts/voices
List available voices.

```bash
curl -H "X-API-Key: $API_KEY" http://localhost:8010/api/v1/tts/voices
```

#### POST /api/v1/tts/synthesize
Batch synthesis - generates complete audio.

```bash
curl -X POST http://localhost:8010/api/v1/tts/synthesize \
  -H "X-API-Key: $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"text": "Hello, this is a test.", "voice_id": "Carter", "language": "en-US"}'
```

Response:
```json
{
  "audio_base64": "UklGRi...",
  "format": "wav",
  "duration_ms": 2340,
  "sample_rate": 24000,
  "text_length": 24
}
```

### WebSocket Endpoint

#### WS /api/v1/tts/stream
Real-time streaming synthesis.

```javascript
const ws = new WebSocket('ws://localhost:8010/api/v1/tts/stream?api_key=YOUR_KEY');

ws.onopen = () => {
  ws.send(JSON.stringify({
    text: "Hello, this is streaming text.",
    voice_id: "Carter",
    language: "en-US",
    is_final: false
  }));
};

ws.onmessage = (event) => {
  const chunk = JSON.parse(event.data);
  if (chunk.audio_chunk) {
    // Play audio chunk
    playAudioChunk(atob(chunk.audio_chunk));
  }
  if (chunk.is_final) {
    console.log("Streaming complete");
  }
};
```

## Development

### Local Development

```bash
cd backend/microservices/tts-service

# Install dependencies
pip install -r requirements.txt

# Run server
python -m uvicorn app.main:app --reload --port 8000
```

### Docker Development

```bash
cd backend/docker

# Start TTS service with GPU
docker compose up tts-service
```

## Available Voices

### VibeVoice
| Voice ID | Language | Gender | Description |
|----------|----------|--------|-------------|
| Carter | en-US | Male | Default English voice |

### Google Cloud TTS
| Voice ID | Language | Gender |
|----------|----------|--------|
| es-ES-Neural2-A | es-ES | Female |
| es-ES-Neural2-B | es-ES | Male |
| es-MX-Neural2-A | es-MX | Female |
| es-MX-Neural2-B | es-MX | Male |
| en-US-Neural2-A | en-US | Male |
| en-US-Neural2-C | en-US | Female |

## Caching

Audio is cached in Redis with configurable TTL (default: 1 hour). Cache keys are generated from:
- Provider name
- Voice ID
- Language
- Speed
- Text hash (SHA-256)

## Known Limitations

1. **VibeVoice Spanish support** is experimental
2. **Single speaker** in realtime mode (no multi-speaker)
3. **Transformers version** must be exactly 4.51.3
4. **GPU required** for acceptable latency

## Troubleshooting

### Model not loading
- Ensure `HF_TOKEN` is set for HuggingFace authentication
- Check GPU availability with `nvidia-smi`
- Verify transformers version: `pip show transformers`

### High latency
- Enable Redis caching for repeated phrases
- Reduce text chunk size for streaming
- Check GPU utilization

### Audio quality issues
- Try different voice IDs
- Adjust speed parameter
- Consider Google TTS for Spanish
