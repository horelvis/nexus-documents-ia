#!/usr/bin/env python3
"""
SLM Router Fine-Tuning Script

Fine-tunes Qwen2-0.5B for TOON route classification using LoRA.
Requires ~2-4GB VRAM, can run on same GPU as SGLang if done offline.

Usage:
    # 1. Export training data from running system:
    curl -X GET "http://localhost:8007/slm/training/my-tenant" \
        -H "X-API-Key: YOUR_KEY" > training_data.json

    # 2. Run fine-tuning (stop SGLang first to free GPU memory):
    docker compose stop sglang tgi-slm
    python scripts/finetune_slm.py --data training_data.json --output ./slm-finetuned

    # 3. Deploy finetuned model:
    # Update TGI to use the new model path

Requirements:
    pip install torch transformers peft datasets accelerate bitsandbytes

Version 1.0 - January 2026
"""

import argparse
import json
import logging
import os
from pathlib import Path
from typing import Dict, List, Any

import torch
from datasets import Dataset
from transformers import (
    AutoModelForCausalLM,
    AutoTokenizer,
    TrainingArguments,
    Trainer,
    DataCollatorForLanguageModeling
)
from peft import (
    LoraConfig,
    get_peft_model,
    prepare_model_for_kbit_training,
    TaskType
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# =============================================================================
# CONFIGURATION
# =============================================================================

DEFAULT_MODEL = "Qwen/Qwen2-0.5B-Instruct"
ROUTES = ["GRAPH_ONLY", "VECTOR_ONLY", "HYBRID", "ASK_CLARIFY"]

SYSTEM_PROMPT = """You are a query routing assistant. Classify queries into routes:
- GRAPH_ONLY: counts, lists, existence checks (cuántos, lista, hay)
- VECTOR_ONLY: semantic search, content meaning, legal knowledge
- HYBRID: need both structure and content
- ASK_CLARIFY: ambiguous queries

Output ONLY the route name."""

# =============================================================================
# DATA PROCESSING
# =============================================================================

def load_training_data(data_path: str) -> List[Dict[str, Any]]:
    """Load training data from exported JSON."""
    with open(data_path, 'r') as f:
        data = json.load(f)

    # Handle both direct list and API response format
    if isinstance(data, dict) and 'examples' in data:
        examples = data['examples']
    elif isinstance(data, list):
        examples = data
    else:
        raise ValueError("Invalid training data format")

    logger.info(f"Loaded {len(examples)} training examples")
    return examples


def prepare_dataset(examples: List[Dict[str, Any]], tokenizer) -> Dataset:
    """Convert training examples to HuggingFace Dataset."""

    def format_example(example: Dict[str, Any]) -> str:
        """Format as chat-style prompt for training."""
        query = example.get('query', '')
        route = example.get('route', 'VECTOR_ONLY')

        # ChatML format for Qwen
        prompt = f"""<|im_start|>system
{SYSTEM_PROMPT}<|im_end|>
<|im_start|>user
Query: {query}

Route:<|im_end|>
<|im_start|>assistant
{route}<|im_end|>"""
        return prompt

    # Format all examples
    formatted = [format_example(ex) for ex in examples]

    # Tokenize
    def tokenize_function(examples):
        return tokenizer(
            examples['text'],
            truncation=True,
            max_length=512,
            padding='max_length',
            return_tensors='pt'
        )

    dataset = Dataset.from_dict({'text': formatted})
    dataset = dataset.map(
        lambda x: tokenizer(x['text'], truncation=True, max_length=512, padding='max_length'),
        batched=True,
        remove_columns=['text']
    )

    logger.info(f"Prepared dataset with {len(dataset)} examples")
    return dataset


def augment_data(examples: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Augment training data with variations."""
    augmented = []

    # Spanish query variations
    graph_patterns = [
        ("cuántos", "GRAPH_ONLY"),
        ("cuantos", "GRAPH_ONLY"),
        ("lista de", "GRAPH_ONLY"),
        ("listar", "GRAPH_ONLY"),
        ("muestra los", "GRAPH_ONLY"),
        ("hay algún", "GRAPH_ONLY"),
        ("existe", "GRAPH_ONLY"),
        ("total de", "GRAPH_ONLY"),
    ]

    vector_patterns = [
        ("qué dice la ley", "VECTOR_ONLY"),
        ("según la normativa", "VECTOR_ONLY"),
        ("contenido de", "VECTOR_ONLY"),
        ("información sobre", "VECTOR_ONLY"),
        ("explica", "VECTOR_ONLY"),
        ("resumen de", "VECTOR_ONLY"),
    ]

    hybrid_patterns = [
        ("cumple con", "HYBRID"),
        ("compara", "HYBRID"),
        ("verifica si", "HYBRID"),
        ("analiza el contrato", "HYBRID"),
    ]

    # Add original examples
    augmented.extend(examples)

    # Generate synthetic examples based on patterns
    entities = ["ACME", "Juan García", "Proyecto Alpha", "Cliente Beta"]
    doc_types = ["contratos", "expedientes", "facturas", "informes"]

    for pattern, route in graph_patterns:
        for entity in entities:
            for doc_type in doc_types:
                augmented.append({
                    'query': f"¿{pattern} {doc_type} tiene {entity}?",
                    'route': route
                })

    for pattern, route in vector_patterns:
        topics = ["vacaciones", "despido", "contrato laboral", "indemnización"]
        for topic in topics:
            augmented.append({
                'query': f"¿{pattern} {topic}?",
                'route': route
            })

    for pattern, route in hybrid_patterns:
        for entity in entities:
            augmented.append({
                'query': f"¿{pattern} el contrato de {entity} la normativa?",
                'route': route
            })

    logger.info(f"Augmented from {len(examples)} to {len(augmented)} examples")
    return augmented


# =============================================================================
# MODEL SETUP
# =============================================================================

def setup_model_and_tokenizer(model_name: str, use_4bit: bool = True):
    """Load model with LoRA configuration."""

    logger.info(f"Loading model: {model_name}")

    # Tokenizer
    tokenizer = AutoTokenizer.from_pretrained(
        model_name,
        trust_remote_code=True,
        padding_side='right'
    )
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    # Model with optional 4-bit quantization
    if use_4bit:
        from transformers import BitsAndBytesConfig

        bnb_config = BitsAndBytesConfig(
            load_in_4bit=True,
            bnb_4bit_quant_type="nf4",
            bnb_4bit_compute_dtype=torch.float16,
            bnb_4bit_use_double_quant=True
        )

        model = AutoModelForCausalLM.from_pretrained(
            model_name,
            quantization_config=bnb_config,
            device_map="auto",
            trust_remote_code=True
        )
        model = prepare_model_for_kbit_training(model)
    else:
        model = AutoModelForCausalLM.from_pretrained(
            model_name,
            torch_dtype=torch.float16,
            device_map="auto",
            trust_remote_code=True
        )

    # LoRA configuration
    lora_config = LoraConfig(
        r=16,  # Rank
        lora_alpha=32,
        lora_dropout=0.05,
        target_modules=["q_proj", "k_proj", "v_proj", "o_proj"],
        bias="none",
        task_type=TaskType.CAUSAL_LM
    )

    model = get_peft_model(model, lora_config)
    model.print_trainable_parameters()

    return model, tokenizer


# =============================================================================
# TRAINING
# =============================================================================

def train(
    model,
    tokenizer,
    train_dataset: Dataset,
    output_dir: str,
    epochs: int = 3,
    batch_size: int = 4,
    learning_rate: float = 2e-4
):
    """Run LoRA fine-tuning."""

    training_args = TrainingArguments(
        output_dir=output_dir,
        num_train_epochs=epochs,
        per_device_train_batch_size=batch_size,
        gradient_accumulation_steps=4,
        learning_rate=learning_rate,
        weight_decay=0.01,
        warmup_ratio=0.1,
        logging_steps=10,
        save_steps=100,
        save_total_limit=2,
        fp16=True,
        optim="paged_adamw_8bit",
        lr_scheduler_type="cosine",
        report_to="none",  # Disable wandb
    )

    data_collator = DataCollatorForLanguageModeling(
        tokenizer=tokenizer,
        mlm=False
    )

    trainer = Trainer(
        model=model,
        args=training_args,
        train_dataset=train_dataset,
        data_collator=data_collator,
    )

    logger.info("Starting training...")
    trainer.train()

    # Save the LoRA adapter
    logger.info(f"Saving model to {output_dir}")
    model.save_pretrained(output_dir)
    tokenizer.save_pretrained(output_dir)

    return trainer


def merge_and_save(
    base_model_name: str,
    adapter_path: str,
    output_path: str
):
    """Merge LoRA adapter with base model for deployment."""
    from peft import PeftModel

    logger.info("Loading base model for merging...")
    base_model = AutoModelForCausalLM.from_pretrained(
        base_model_name,
        torch_dtype=torch.float16,
        device_map="auto",
        trust_remote_code=True
    )

    logger.info("Loading and merging LoRA adapter...")
    model = PeftModel.from_pretrained(base_model, adapter_path)
    model = model.merge_and_unload()

    logger.info(f"Saving merged model to {output_path}")
    model.save_pretrained(output_path)

    tokenizer = AutoTokenizer.from_pretrained(adapter_path)
    tokenizer.save_pretrained(output_path)

    logger.info("Done! Model ready for deployment.")


# =============================================================================
# MAIN
# =============================================================================

def main():
    parser = argparse.ArgumentParser(description="Fine-tune SLM Router model")
    parser.add_argument(
        "--data", "-d",
        required=True,
        help="Path to training data JSON"
    )
    parser.add_argument(
        "--output", "-o",
        default="./slm-finetuned",
        help="Output directory for finetuned model"
    )
    parser.add_argument(
        "--model", "-m",
        default=DEFAULT_MODEL,
        help="Base model to finetune"
    )
    parser.add_argument(
        "--epochs", "-e",
        type=int,
        default=3,
        help="Number of training epochs"
    )
    parser.add_argument(
        "--batch-size", "-b",
        type=int,
        default=4,
        help="Training batch size"
    )
    parser.add_argument(
        "--augment",
        action="store_true",
        help="Augment training data with synthetic examples"
    )
    parser.add_argument(
        "--merge",
        action="store_true",
        help="Merge LoRA adapter into base model after training"
    )
    parser.add_argument(
        "--no-4bit",
        action="store_true",
        help="Disable 4-bit quantization (uses more VRAM)"
    )

    args = parser.parse_args()

    # Load data
    examples = load_training_data(args.data)

    if args.augment:
        examples = augment_data(examples)

    # Setup model
    model, tokenizer = setup_model_and_tokenizer(
        args.model,
        use_4bit=not args.no_4bit
    )

    # Prepare dataset
    dataset = prepare_dataset(examples, tokenizer)

    # Train
    output_dir = Path(args.output)
    adapter_dir = output_dir / "adapter"
    adapter_dir.mkdir(parents=True, exist_ok=True)

    train(
        model=model,
        tokenizer=tokenizer,
        train_dataset=dataset,
        output_dir=str(adapter_dir),
        epochs=args.epochs,
        batch_size=args.batch_size
    )

    # Optionally merge
    if args.merge:
        merged_dir = output_dir / "merged"
        merge_and_save(
            base_model_name=args.model,
            adapter_path=str(adapter_dir),
            output_path=str(merged_dir)
        )
        logger.info(f"\nMerged model saved to: {merged_dir}")
        logger.info("To deploy, update TGI MODEL_ID to point to this directory.")
    else:
        logger.info(f"\nLoRA adapter saved to: {adapter_dir}")
        logger.info("Run with --merge to create deployable model.")


if __name__ == "__main__":
    main()
