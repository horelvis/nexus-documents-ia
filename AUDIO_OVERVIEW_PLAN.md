# Audio Overview Feature - Implementation Plan

## Overview

Implement a "Google NotebookLM-style" Audio Overview feature that generates podcast-style audio summaries from documents using VibeVoice 1.5B multi-speaker TTS.

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        FRONTEND                                  │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │  Document View → "Generate Audio Overview" Button        │    │
│  │  ├── Select documents (1-5)                              │    │
│  │  ├── Choose style: Deep Dive | Debate | Summary | Q&A    │    │
│  │  ├── Select language (es-ES, en-US, etc.)                │    │
│  │  ├── Optional: Upload custom voice WAV                   │    │
│  │  └── Progress indicator + Audio player                   │    │
│  └─────────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                      BACKEND API                                 │
│  POST /api/v1/audio-overview/generate                           │
│  ├── document_ids: list[str]                                    │
│  ├── style: "deep_dive" | "debate" | "summary" | "qa"           │
│  ├── language: str                                              │
│  ├── host_a_voice: str (optional, for voice cloning)            │
│  └── host_b_voice: str (optional, for voice cloning)            │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                   WEAVIATE SERVICE (Emma)                        │
│  1. Retrieve document content via RAG                           │
│  2. Extract key topics, facts, quotes                           │
│  3. Generate structured summary for podcast script              │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                      vLLM (Qwen3-8B)                             │
│  Generate podcast script in format:                             │
│  Speaker 1: "Welcome to today's deep dive..."                   │
│  Speaker 2: "Thanks! Today we're exploring..."                  │
│  Speaker 1: "The document mentions that..."                     │
│  ...                                                            │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                   TTS SERVICE (VibeVoice 1.5B)                   │
│  POST /api/v1/tts/synthesize-podcast                            │
│  ├── script: str (multi-speaker format)                         │
│  ├── speaker_voices: {"Speaker 1": "en-Carter_man", ...}        │
│  └── voice_samples: {"Speaker 1": base64_wav, ...} (optional)   │
│                                                                  │
│  Returns: audio/wav (full podcast, ~5-15 minutes)               │
└─────────────────────────────────────────────────────────────────┘
```

## Phase 1: Migrate TTS to VibeVoice 1.5B

### 1.1 Update TTS Service Configuration

**File: `backend/microservices/tts-service/app/core/config.py`**
```python
vibevoice_model_path: str = Field(
    default="microsoft/VibeVoice-1.5B",  # Changed from Realtime-0.5B
    alias="VIBEVOICE_MODEL_PATH"
)
```

### 1.2 Update Docker Compose

**File: `backend/docker/docker-compose.yml`**
- Allocate more memory for 1.5B model (~7GB VRAM)
- Mount voices directory for custom WAV files
- Add volume for voice uploads

### 1.3 Create Multi-Speaker Service

**File: `backend/microservices/tts-service/app/services/vibevoice_multispeaker.py`**

Key methods:
- `synthesize_podcast(script, speaker_voices, voice_samples)`
- `parse_script(text) -> List[Tuple[speaker, text]]`
- `load_voice_sample(wav_bytes) -> voice_embedding`

### 1.4 Voice Format

Available preset voices:
- English: `en-Alice_woman`, `en-Carter_man`, `en-Frank_man`, `en-Mary_woman`, `en-Maya_woman`
- Spanish: `sp-Spk0_woman`, `sp-Spk1_man`
- Custom: Upload WAV (10-30 seconds recommended)

## Phase 2: Podcast Script Generation

### 2.1 Script Styles

**Deep Dive** (default):
```
Speaker 1: Welcome to today's deep dive! We're exploring [topic].
Speaker 2: This is fascinating material. Let me highlight the key points...
Speaker 1: The document states that [quote]...
Speaker 2: What's interesting here is [analysis]...
```

**Debate**:
```
Speaker 1: I'll argue in favor of [position A]...
Speaker 2: I respectfully disagree. The evidence shows [position B]...
```

**Summary**:
```
Speaker 1: Here's a quick overview of [document]...
Speaker 2: The main takeaways are...
```

**Q&A**:
```
Speaker 1: [Question about the document]
Speaker 2: [Answer based on content]
```

### 2.2 LLM Prompt Template

```yaml
# File: config/prompts/podcast_prompts.yaml

deep_dive:
  system: |
    You are a podcast script writer. Create an engaging conversation between
    two hosts discussing the provided content. The conversation should:
    - Be natural and conversational
    - Include reactions, questions, and insights
    - Reference specific quotes and facts from the source
    - Last approximately 5-10 minutes when read aloud

  format: |
    Use this exact format:
    Speaker 1: [Host A dialogue]
    Speaker 2: [Host B dialogue]

    Do NOT include stage directions or emotions in brackets.
    Each speaker turn should be 1-3 sentences.
```

## Phase 3: Backend API

### 3.1 New Endpoint

**File: `backend/app/api/v1/audio_overview.py`**

```python
@router.post("/generate")
async def generate_audio_overview(
    request: AudioOverviewRequest,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user_async)
) -> AudioOverviewResponse:
    """
    Generate podcast-style audio from documents.

    This is a long-running operation (~2-5 minutes).
    Returns a job_id for polling status.
    """
```

### 3.2 Request/Response Models

```python
class AudioOverviewRequest(BaseModel):
    document_ids: List[str]
    style: Literal["deep_dive", "debate", "summary", "qa"] = "deep_dive"
    language: str = "es-ES"
    host_a_voice: Optional[str] = "sp-Spk1_man"
    host_b_voice: Optional[str] = "sp-Spk0_woman"
    custom_voice_a: Optional[str] = None  # base64 WAV
    custom_voice_b: Optional[str] = None  # base64 WAV
    max_duration_minutes: int = 10

class AudioOverviewResponse(BaseModel):
    job_id: str
    status: str  # "pending", "processing", "completed", "failed"
    audio_url: Optional[str] = None
    duration_seconds: Optional[int] = None
    script: Optional[str] = None  # The generated script
```

## Phase 4: Frontend UI

### 4.1 Audio Overview Button

Add to document view and chat:
- "🎙️ Generate Audio Overview" button
- Opens modal with options
- Shows progress during generation
- Audio player when complete

### 4.2 Component Structure

```
/components/audio-overview/
├── AudioOverviewButton.tsx      # Trigger button
├── AudioOverviewModal.tsx       # Configuration modal
├── AudioOverviewPlayer.tsx      # Audio player with transcript
├── AudioOverviewProgress.tsx    # Generation progress
└── VoiceSelector.tsx            # Voice selection/upload
```

## Resource Requirements

| Service | VRAM | RAM |
|---------|------|-----|
| vLLM (Qwen3-8B) | ~9GB | 16GB |
| VibeVoice 1.5B | ~7GB | 8GB |
| **Total** | **~16GB** | 24GB |
| **RTX 4090** | 24GB | ✅ Fits |

## Timeline Estimate

| Phase | Task | Effort |
|-------|------|--------|
| 1 | Migrate TTS to 1.5B | 2-3 hours |
| 2 | Podcast script prompts | 1-2 hours |
| 3 | Backend API | 3-4 hours |
| 4 | Frontend UI | 4-5 hours |
| **Total** | | **10-14 hours** |

## References

- [VibeVoice Community Fork](https://github.com/vibevoice-community/VibeVoice)
- [VibeVoice 1.5B on HuggingFace](https://huggingface.co/microsoft/VibeVoice-1.5B)
- [Google NotebookLM Audio Overview](https://blog.google/technology/ai/notebooklm-audio-overviews/)
- [KDnuggets VibeVoice Guide](https://www.kdnuggets.com/beginners-guide-to-vibevoice)
