"""
Training API — Sector QA Embedding Fine-Tuning

Provides endpoints to:
- Get training status for each sector (model exists, QA concepts count)
- Start training for a sector (runs in background thread)
- Get training progress
"""

import asyncio
import logging
import os
import time
from enum import Enum
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.core.config import settings

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/training", tags=["training"])

def _find_project_root() -> str:
    """Find project root (directory containing both 'app/' and 'config/')."""
    current = os.path.dirname(os.path.abspath(__file__))
    for _ in range(10):
        if os.path.isdir(os.path.join(current, "app")) and os.path.isdir(os.path.join(current, "config")):
            return current
        current = os.path.dirname(current)
    return os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))


_PROJECT_ROOT = _find_project_root()
MODELS_DIR = os.path.join(_PROJECT_ROOT, "models")
CONFIG_DIR = os.path.join(_PROJECT_ROOT, "config", "sector_qa")


# ============================================================================
# Models
# ============================================================================

class TrainingSectorStatus(BaseModel):
    sector: str
    has_trained_model: bool
    model_path: Optional[str] = None
    qa_concepts_count: int
    qa_questions_count: int


class TrainingStatusResponse(BaseModel):
    active_sector: str
    sectors: list[TrainingSectorStatus]
    training_in_progress: Optional[str] = None
    training_progress: Optional[dict] = None


class TrainingRequest(BaseModel):
    sector: str
    hf_dataset: Optional[str] = None
    epochs: int = 3
    batch_size: int = 16


class TrainingStartResponse(BaseModel):
    status: str
    message: str
    sector: str


# ============================================================================
# Training State (in-memory, single instance)
# ============================================================================

_training_state = {
    "in_progress": None,  # sector name or None
    "progress": {},       # {stage, epoch, total_epochs, started_at, ...}
    "last_error": None,
}


def _count_qa_data(sector: str) -> tuple[int, int]:
    """Count concepts and questions in sector QA YAML."""
    import yaml
    yaml_path = os.path.join(CONFIG_DIR, f"{sector}_qa.yaml")
    if not os.path.exists(yaml_path):
        return 0, 0
    with open(yaml_path) as f:
        data = yaml.safe_load(f)
    concepts = data.get("concepts", [])
    questions = sum(len(c.get("questions", [])) for c in concepts)
    return len(concepts), questions


def _has_trained_model(sector: str) -> tuple[bool, Optional[str]]:
    """Check if a fine-tuned model exists for sector."""
    model_path = os.path.join(MODELS_DIR, sector)
    if os.path.isdir(model_path):
        # Check it has actual model files
        has_files = any(
            f.endswith((".bin", ".safetensors", ".json"))
            for f in os.listdir(model_path)
        )
        if has_files:
            return True, model_path
    return False, None


def _run_training_sync(sector: str, hf_dataset: Optional[str], epochs: int, batch_size: int):
    """Run training in a sync context (called from background thread)."""
    import yaml
    from sentence_transformers import InputExample, SentenceTransformer, losses
    from torch.utils.data import DataLoader

    BASE_MODEL = "sentence-transformers/all-MiniLM-L6-v2"

    _training_state["progress"] = {
        "stage": "loading_model",
        "message": "Cargando modelo base...",
        "started_at": time.time(),
    }

    model = SentenceTransformer(BASE_MODEL)

    # Load YAML training data
    _training_state["progress"]["stage"] = "loading_data"
    _training_state["progress"]["message"] = "Cargando datos de entrenamiento..."

    yaml_path = os.path.join(CONFIG_DIR, f"{sector}_qa.yaml")
    with open(yaml_path) as f:
        data = yaml.safe_load(f)

    examples = []
    for concept in data["concepts"]:
        desc = concept.get("description", "")
        for question in concept["questions"]:
            if desc:
                examples.append(InputExample(texts=[question, desc], label=1.0))
            for other_q in concept["questions"]:
                if other_q != question:
                    examples.append(InputExample(texts=[question, other_q], label=0.9))

    _training_state["progress"]["yaml_examples"] = len(examples)

    # Load HuggingFace dataset if provided
    if hf_dataset:
        _training_state["progress"]["stage"] = "loading_hf_dataset"
        _training_state["progress"]["message"] = f"Descargando dataset {hf_dataset}..."
        try:
            from datasets import load_dataset
            ds = load_dataset(hf_dataset, split="train")
            for row in ds:
                q = row.get("question", "")
                a = row.get("answer", "")
                ctx = row.get("context", "")
                if q and a:
                    examples.append(InputExample(texts=[q, a], label=1.0))
                if q and ctx:
                    examples.append(InputExample(texts=[q, ctx[:512]], label=0.8))
            _training_state["progress"]["hf_examples"] = len(examples) - _training_state["progress"]["yaml_examples"]
        except Exception as e:
            logger.warning(f"Failed to load HF dataset {hf_dataset}: {e}")
            _training_state["progress"]["hf_error"] = str(e)

    _training_state["progress"]["total_examples"] = len(examples)

    # Train
    _training_state["progress"]["stage"] = "training"
    _training_state["progress"]["message"] = f"Entrenando ({len(examples)} ejemplos, {epochs} epochs)..."
    _training_state["progress"]["epoch"] = 0
    _training_state["progress"]["total_epochs"] = epochs

    dataloader = DataLoader(examples, shuffle=True, batch_size=batch_size)
    loss = losses.CosineSimilarityLoss(model)

    output_path = os.path.join(MODELS_DIR, sector)
    os.makedirs(output_path, exist_ok=True)

    model.fit(
        train_objectives=[(dataloader, loss)],
        epochs=epochs,
        warmup_steps=int(len(dataloader) * 0.1),
        output_path=output_path,
        show_progress_bar=False,
    )

    # Invalidate QA index cache so it reloads with new model
    _training_state["progress"]["stage"] = "reloading_index"
    _training_state["progress"]["message"] = "Recargando índice QA con nuevo modelo..."

    try:
        from app.agents.langgraph.sectors.qa_index import _indices
        if sector in _indices:
            del _indices[sector]
    except Exception:
        pass

    elapsed = time.time() - _training_state["progress"]["started_at"]
    _training_state["progress"] = {
        "stage": "completed",
        "message": f"Entrenamiento completado en {elapsed:.1f}s",
        "total_examples": len(examples),
        "epochs": epochs,
        "elapsed_seconds": elapsed,
        "model_path": output_path,
    }


async def _run_training_background(sector: str, hf_dataset: Optional[str], epochs: int, batch_size: int):
    """Run training in background thread."""
    loop = asyncio.get_event_loop()
    try:
        _training_state["in_progress"] = sector
        _training_state["last_error"] = None
        await loop.run_in_executor(
            None, _run_training_sync, sector, hf_dataset, epochs, batch_size
        )
    except Exception as e:
        logger.error(f"Training failed for {sector}: {e}")
        _training_state["last_error"] = str(e)
        _training_state["progress"] = {
            "stage": "error",
            "message": f"Error: {e}",
        }
    finally:
        _training_state["in_progress"] = None


# ============================================================================
# Endpoints
# ============================================================================

@router.get("/status", response_model=TrainingStatusResponse)
async def get_training_status():
    """Get training status for all sectors."""
    sectors = []
    for sector_name in ["legal", "medical", "documental"]:
        concepts, questions = _count_qa_data(sector_name)
        has_model, model_path = _has_trained_model(sector_name)
        sectors.append(TrainingSectorStatus(
            sector=sector_name,
            has_trained_model=has_model,
            model_path=model_path,
            qa_concepts_count=concepts,
            qa_questions_count=questions,
        ))

    return TrainingStatusResponse(
        active_sector=settings.active_sector,
        sectors=sectors,
        training_in_progress=_training_state["in_progress"],
        training_progress=_training_state["progress"] if _training_state["in_progress"] else None,
    )


@router.post("/start", response_model=TrainingStartResponse)
async def start_training(req: TrainingRequest):
    """Start sector embedding training (background)."""
    if req.sector not in ("legal", "medical", "documental"):
        raise HTTPException(status_code=400, detail=f"Sector inválido: {req.sector}")

    if _training_state["in_progress"]:
        raise HTTPException(
            status_code=409,
            detail=f"Entrenamiento en curso para '{_training_state['in_progress']}'. Espera a que termine.",
        )

    # Verify QA data exists
    concepts, questions = _count_qa_data(req.sector)
    if concepts == 0:
        raise HTTPException(
            status_code=400,
            detail=f"No hay datos QA para el sector '{req.sector}'. Configura config/sector_qa/{req.sector}_qa.yaml",
        )

    # Start in background
    asyncio.create_task(
        _run_training_background(req.sector, req.hf_dataset, req.epochs, req.batch_size)
    )

    return TrainingStartResponse(
        status="started",
        message=f"Entrenamiento iniciado para '{req.sector}' ({concepts} conceptos, {questions} preguntas)",
        sector=req.sector,
    )


@router.get("/progress")
async def get_training_progress():
    """Get current training progress."""
    return {
        "in_progress": _training_state["in_progress"],
        "progress": _training_state["progress"],
        "last_error": _training_state["last_error"],
    }
