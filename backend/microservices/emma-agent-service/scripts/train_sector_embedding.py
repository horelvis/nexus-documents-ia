"""
Train sector-specific QA embedding model.

Uses sentence-transformers fine-tuning with:
- Local QA pairs from config/sector_qa/{sector}_qa.yaml
- Optional HuggingFace datasets (e.g., justicio-rag-embedding-qa-tmp)

Usage:
    # Train with local YAML only
    python scripts/train_sector_embedding.py --sector legal

    # Train with YAML + HuggingFace dataset
    python scripts/train_sector_embedding.py --sector legal \
        --hf-dataset dariolopez/justicio-rag-embedding-qa-tmp

    # Train with custom epochs and batch size
    python scripts/train_sector_embedding.py --sector legal --epochs 5 --batch-size 32
"""

import argparse
import logging
import os

import yaml
from sentence_transformers import InputExample, SentenceTransformer, losses
from torch.utils.data import DataLoader

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

BASE_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
MODELS_DIR = os.path.join(os.path.dirname(__file__), "..", "models")


def load_qa_pairs_from_yaml(sector: str) -> list[InputExample]:
    """Load QA pairs from sector YAML as training examples."""
    yaml_path = os.path.join(
        os.path.dirname(__file__), "..", "config", "sector_qa", f"{sector}_qa.yaml"
    )
    with open(yaml_path) as f:
        data = yaml.safe_load(f)

    examples = []
    for concept in data["concepts"]:
        desc = concept.get("description", "")
        for question in concept["questions"]:
            # Positive pair: question <-> description
            if desc:
                examples.append(InputExample(texts=[question, desc], label=1.0))
            # Positive pair: question <-> question (same concept)
            for other_q in concept["questions"]:
                if other_q != question:
                    examples.append(InputExample(texts=[question, other_q], label=0.9))
    return examples


def load_hf_dataset(dataset_name: str) -> list[InputExample]:
    """Load QA pairs from HuggingFace dataset."""
    from datasets import load_dataset

    ds = load_dataset(dataset_name, split="train")
    examples = []
    for row in ds:
        q = row.get("question", "")
        a = row.get("answer", "")
        ctx = row.get("context", "")
        if q and a:
            examples.append(InputExample(texts=[q, a], label=1.0))
        if q and ctx:
            examples.append(InputExample(texts=[q, ctx[:512]], label=0.8))
    return examples


def train(sector: str, hf_dataset: str = None, epochs: int = 3, batch_size: int = 16):
    """Train embedding model for a sector."""
    model = SentenceTransformer(BASE_MODEL)

    examples = load_qa_pairs_from_yaml(sector)
    logger.info(f"Loaded {len(examples)} examples from YAML")

    if hf_dataset:
        hf_examples = load_hf_dataset(hf_dataset)
        logger.info(f"Loaded {len(hf_examples)} examples from HuggingFace: {hf_dataset}")
        examples.extend(hf_examples)

    logger.info(f"Training {sector} embedding with {len(examples)} total examples")

    dataloader = DataLoader(examples, shuffle=True, batch_size=batch_size)
    loss = losses.CosineSimilarityLoss(model)

    output_path = os.path.join(MODELS_DIR, sector)
    model.fit(
        train_objectives=[(dataloader, loss)],
        epochs=epochs,
        warmup_steps=int(len(dataloader) * 0.1),
        output_path=output_path,
        show_progress_bar=True,
    )
    logger.info(f"Model saved to {output_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Train sector QA embedding model")
    parser.add_argument("--sector", required=True, choices=["legal", "medical", "documental"])
    parser.add_argument("--hf-dataset", default=None, help="HuggingFace dataset name")
    parser.add_argument("--epochs", type=int, default=3)
    parser.add_argument("--batch-size", type=int, default=16)
    args = parser.parse_args()
    train(args.sector, args.hf_dataset, args.epochs, args.batch_size)
