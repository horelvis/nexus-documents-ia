"""
Expert Training Module.

Provides LoRA fine-tuning for creating tenant-specific experts
using either custom training data or synthetic examples.

Training uses 4-bit quantization + LoRA for memory efficiency,
allowing training on consumer GPUs (8GB+ VRAM).
"""

import logging
import os
from typing import Dict, List, Optional

import torch

logger = logging.getLogger(__name__)

# Training status tracking
_training_status: Dict[str, dict] = {}


def get_training_status(task_id: str) -> Optional[dict]:
    """Get status of a training task."""
    return _training_status.get(task_id)


def set_training_status(task_id: str, status: dict) -> None:
    """Update training task status."""
    _training_status[task_id] = status


async def train_expert_async(
    tenant_id: str,
    domain: str,
    training_data: Optional[List[Dict[str, str]]] = None,
    use_synthetic: bool = True,
    num_epochs: int = 3,
    num_synthetic_samples: int = 200
) -> str:
    """
    Train a LoRA adapter for domain expertise.

    This function runs asynchronously in background.

    Args:
        tenant_id: Tenant to create expert for
        domain: Domain specialization
        training_data: Custom training examples [{input, output}, ...]
        use_synthetic: Generate synthetic examples if no training_data
        num_epochs: Training epochs
        num_synthetic_samples: Number of synthetic examples to generate

    Returns:
        Path to trained adapter
    """
    task_id = f"{tenant_id}:{domain}"

    try:
        set_training_status(task_id, {
            "status": "starting",
            "progress": 0.0,
            "message": "Initializing training..."
        })

        # Get training data
        if training_data:
            examples = training_data
            logger.info(f"Using {len(examples)} custom training examples")
        elif use_synthetic:
            from .synthetic_generator import generate_synthetic_data
            examples = generate_synthetic_data(domain, num_synthetic_samples)
            logger.info(f"Generated {len(examples)} synthetic examples")
        else:
            raise ValueError("No training data provided and use_synthetic=False")

        set_training_status(task_id, {
            "status": "preparing",
            "progress": 0.1,
            "message": f"Preparing {len(examples)} training examples..."
        })

        # Run training
        adapter_path = train_lora_adapter(
            tenant_id=tenant_id,
            domain=domain,
            examples=examples,
            num_epochs=num_epochs,
            task_id=task_id
        )

        set_training_status(task_id, {
            "status": "completed",
            "progress": 1.0,
            "message": "Training completed successfully",
            "adapter_path": adapter_path
        })

        # Register expert
        from . import get_men_system
        men_system = get_men_system()
        if men_system.tenant_manager:
            men_system.tenant_manager.register_expert(
                tenant_id=tenant_id,
                domain=domain,
                path=adapter_path,
                document_types=[]
            )

        return adapter_path

    except Exception as e:
        logger.error(f"Training failed: {e}", exc_info=True)
        set_training_status(task_id, {
            "status": "failed",
            "progress": 0.0,
            "message": str(e)
        })
        raise


def train_lora_adapter(
    tenant_id: str,
    domain: str,
    examples: List[Dict[str, str]],
    num_epochs: int = 3,
    task_id: Optional[str] = None
) -> str:
    """
    Train a LoRA adapter using PEFT.

    Uses 4-bit quantization + LoRA for memory-efficient training.
    Requires ~6 GB VRAM for 0.5B base model.

    Args:
        tenant_id: Tenant identifier
        domain: Domain name
        examples: Training examples [{input, output}, ...]
        num_epochs: Number of training epochs
        task_id: Task ID for progress tracking

    Returns:
        Path to saved adapter
    """
    from ..core.config import settings

    # Import training dependencies
    try:
        from datasets import Dataset
        from peft import LoraConfig, get_peft_model, prepare_model_for_kbit_training
        from transformers import (
            AutoModelForCausalLM,
            AutoTokenizer,
            BitsAndBytesConfig,
            TrainingArguments,
            Trainer,
            DataCollatorForLanguageModeling,
        )
    except ImportError as e:
        logger.error(f"Training dependencies not installed: {e}")
        raise RuntimeError(
            "Training requires additional dependencies. "
            "Install with: pip install peft datasets trl"
        )

    # Output path
    output_dir = os.path.join(settings.experts_dir, tenant_id, f"{domain}_expert")
    os.makedirs(output_dir, exist_ok=True)

    logger.info(f"Training LoRA adapter: {domain} for tenant {tenant_id}")
    logger.info(f"  Base model: {settings.expert_base_model}")
    logger.info(f"  Output: {output_dir}")
    logger.info(f"  Examples: {len(examples)}")
    logger.info(f"  Epochs: {num_epochs}")

    # Update status
    if task_id:
        set_training_status(task_id, {
            "status": "loading_model",
            "progress": 0.2,
            "message": "Loading base model..."
        })

    # Configure quantization
    bnb_config = BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_quant_type="nf4",
        bnb_4bit_compute_dtype=torch.bfloat16,
        bnb_4bit_use_double_quant=True,
    )

    # Load tokenizer
    tokenizer = AutoTokenizer.from_pretrained(
        settings.expert_base_model,
        trust_remote_code=True
    )
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    # Load base model
    model = AutoModelForCausalLM.from_pretrained(
        settings.expert_base_model,
        quantization_config=bnb_config,
        device_map="auto",
        trust_remote_code=True,
    )

    # Prepare for k-bit training
    model = prepare_model_for_kbit_training(model)

    # Configure LoRA
    lora_config = LoraConfig(
        r=16,
        lora_alpha=32,
        target_modules=["q_proj", "v_proj", "k_proj", "o_proj"],
        lora_dropout=0.05,
        bias="none",
        task_type="CAUSAL_LM",
    )

    # Apply LoRA
    model = get_peft_model(model, lora_config)
    model.print_trainable_parameters()

    # Update status
    if task_id:
        set_training_status(task_id, {
            "status": "preparing_data",
            "progress": 0.3,
            "message": "Preparing training data..."
        })

    # Prepare dataset
    def format_example(example):
        text = f"### Pregunta:\n{example['input']}\n\n### Respuesta:\n{example['output']}"
        return {"text": text}

    dataset = Dataset.from_list([format_example(e) for e in examples])

    def tokenize(example):
        return tokenizer(
            example["text"],
            truncation=True,
            max_length=512,
            padding="max_length",
        )

    tokenized_dataset = dataset.map(tokenize, remove_columns=["text"])

    # Training arguments
    training_args = TrainingArguments(
        output_dir=output_dir,
        num_train_epochs=num_epochs,
        per_device_train_batch_size=4,
        gradient_accumulation_steps=4,
        learning_rate=2e-4,
        warmup_steps=10,
        logging_steps=10,
        save_strategy="epoch",
        fp16=True,
        optim="paged_adamw_8bit",
        report_to="none",
    )

    # Data collator
    data_collator = DataCollatorForLanguageModeling(
        tokenizer=tokenizer,
        mlm=False,
    )

    # Update status
    if task_id:
        set_training_status(task_id, {
            "status": "training",
            "progress": 0.4,
            "message": "Training in progress..."
        })

    # Create trainer
    trainer = Trainer(
        model=model,
        args=training_args,
        train_dataset=tokenized_dataset,
        data_collator=data_collator,
    )

    # Train
    trainer.train()

    # Update status
    if task_id:
        set_training_status(task_id, {
            "status": "saving",
            "progress": 0.9,
            "message": "Saving adapter..."
        })

    # Save adapter
    model.save_pretrained(output_dir)
    tokenizer.save_pretrained(output_dir)

    # Save metadata
    import json
    metadata = {
        "domain": domain,
        "tenant_id": tenant_id,
        "base_model": settings.expert_base_model,
        "num_examples": len(examples),
        "num_epochs": num_epochs,
    }
    with open(os.path.join(output_dir, "expert_metadata.json"), "w") as f:
        json.dump(metadata, f, indent=2)

    logger.info(f"LoRA adapter saved to: {output_dir}")

    # Cleanup
    del model
    del trainer
    if torch.cuda.is_available():
        torch.cuda.empty_cache()

    return output_dir
