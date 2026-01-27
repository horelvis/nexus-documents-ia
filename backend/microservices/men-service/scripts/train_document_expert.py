#!/usr/bin/env python3
"""
Script para entrenar el Experto Documental.

Este script entrena un adaptador LoRA sobre Qwen2.5-0.5B usando
el dataset de gestión documental.

Uso:
    python scripts/train_document_expert.py --epochs 3 --output trained_experts/_generic_/document

Requisitos:
    - GPU con al menos 8GB VRAM
    - PyTorch, transformers, peft, bitsandbytes instalados
"""

import argparse
import json
import logging
import os
import sys
from datetime import datetime
from pathlib import Path

# Add app to path
sys.path.insert(0, str(Path(__file__).parent.parent))

import torch
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

from app.datasets.document_expert_dataset import (
    ALL_DOCUMENT_EXPERT_EXAMPLES,
    get_document_expert_examples,
    DATASET_STATS,
)
from app.datasets.huggingface_loader import (
    load_huggingface_datasets,
    get_huggingface_stats,
    convert_to_training_format,
    AVAILABLE_DATASETS,
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def parse_args():
    parser = argparse.ArgumentParser(
        description="Entrena el Experto Documental con LoRA"
    )
    parser.add_argument(
        "--base-model",
        type=str,
        default="Qwen/Qwen2.5-0.5B-Instruct",
        help="Modelo base para fine-tuning"
    )
    parser.add_argument(
        "--output",
        type=str,
        default="trained_experts/_generic_/document_expert",
        help="Directorio de salida para el adaptador LoRA"
    )
    parser.add_argument(
        "--epochs",
        type=int,
        default=3,
        help="Número de epochs de entrenamiento"
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=4,
        help="Batch size por dispositivo"
    )
    parser.add_argument(
        "--learning-rate",
        type=float,
        default=2e-4,
        help="Learning rate"
    )
    parser.add_argument(
        "--lora-r",
        type=int,
        default=16,
        help="Rango de LoRA"
    )
    parser.add_argument(
        "--lora-alpha",
        type=int,
        default=32,
        help="Alpha de LoRA"
    )
    parser.add_argument(
        "--max-length",
        type=int,
        default=1024,
        help="Longitud máxima de secuencia"
    )
    parser.add_argument(
        "--categories",
        type=str,
        nargs="+",
        default=None,
        help="Categorías a incluir (None = todas)"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Solo mostrar estadísticas, no entrenar"
    )
    parser.add_argument(
        "--augment-huggingface",
        action="store_true",
        help="Aumentar dataset con ejemplos de HuggingFace (dariolopez/justicio-*)"
    )
    parser.add_argument(
        "--hf-max-examples",
        type=int,
        default=200,
        help="Máximo de ejemplos por dataset de HuggingFace"
    )
    parser.add_argument(
        "--hf-datasets",
        type=str,
        nargs="+",
        default=None,
        help=f"Datasets de HuggingFace a usar. Opciones: {list(AVAILABLE_DATASETS.keys())}"
    )
    return parser.parse_args()


def format_example(example: dict, tokenizer) -> dict:
    """Formatea un ejemplo para entrenamiento."""
    # Formato de chat para Qwen
    messages = [
        {"role": "system", "content": "Eres un experto en gestión documental empresarial. Responde de forma técnica, precisa y detallada."},
        {"role": "user", "content": example["input"]},
        {"role": "assistant", "content": example["output"]}
    ]

    text = tokenizer.apply_chat_template(
        messages,
        tokenize=False,
        add_generation_prompt=False
    )
    return {"text": text}


def main():
    args = parse_args()

    logger.info("=" * 60)
    logger.info("Entrenamiento de Experto Documental")
    logger.info("=" * 60)

    # Mostrar estadísticas del dataset
    logger.info(f"\nEstadísticas del Dataset:")
    logger.info(f"  Total ejemplos: {DATASET_STATS['total_examples']}")
    logger.info(f"  Categorías:")
    for cat, count in DATASET_STATS['categories'].items():
        logger.info(f"    - {cat}: {count} ejemplos")
    logger.info(f"  Longitud promedio input: {DATASET_STATS['avg_input_length']} chars")
    logger.info(f"  Longitud promedio output: {DATASET_STATS['avg_output_length']} chars")

    # Obtener ejemplos locales
    examples = get_document_expert_examples(categories=args.categories)
    logger.info(f"\nEjemplos locales: {len(examples)}")

    # Aumentar con HuggingFace si se solicita
    if args.augment_huggingface:
        logger.info(f"\n--- Aumentando con datasets de HuggingFace ---")
        hf_stats = get_huggingface_stats()
        logger.info(f"Datasets disponibles:")
        for key, info in hf_stats["datasets_info"].items():
            logger.info(f"  - {key}: {info['description']} ({info['rows']} filas)")

        try:
            hf_examples = load_huggingface_datasets(
                datasets=args.hf_datasets,
                max_examples_per_dataset=args.hf_max_examples
            )
            # Convertir al formato de entrenamiento
            hf_training = convert_to_training_format(hf_examples, include_source=False)
            examples.extend(hf_training)
            logger.info(f"  ✓ Añadidos {len(hf_training)} ejemplos de HuggingFace")
        except Exception as e:
            logger.warning(f"  ⚠ Error cargando HuggingFace: {e}")
            logger.warning(f"    Continuando solo con dataset local...")

    logger.info(f"\nTotal ejemplos para entrenamiento: {len(examples)}")

    if args.dry_run:
        logger.info("\n[DRY RUN] Mostrando primeros 3 ejemplos:")
        for i, ex in enumerate(examples[:3]):
            logger.info(f"\n--- Ejemplo {i+1} ---")
            logger.info(f"Input: {ex['input'][:100]}...")
            logger.info(f"Output: {ex['output'][:200]}...")
        return

    # Verificar GPU
    if not torch.cuda.is_available():
        logger.error("GPU no disponible. Este script requiere CUDA.")
        sys.exit(1)

    logger.info(f"\nGPU detectada: {torch.cuda.get_device_name(0)}")
    logger.info(f"VRAM disponible: {torch.cuda.get_device_properties(0).total_memory / 1e9:.1f} GB")

    # Configuración de cuantización 4-bit
    logger.info(f"\nCargando modelo base: {args.base_model}")
    bnb_config = BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_quant_type="nf4",
        bnb_4bit_compute_dtype=torch.bfloat16,
        bnb_4bit_use_double_quant=True,
    )

    # Cargar tokenizer
    tokenizer = AutoTokenizer.from_pretrained(
        args.base_model,
        trust_remote_code=True
    )
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    # Cargar modelo
    model = AutoModelForCausalLM.from_pretrained(
        args.base_model,
        quantization_config=bnb_config,
        device_map="auto",
        trust_remote_code=True,
    )

    # Preparar para entrenamiento k-bit
    model = prepare_model_for_kbit_training(model)

    # Configurar LoRA
    logger.info(f"\nConfigurando LoRA: r={args.lora_r}, alpha={args.lora_alpha}")
    lora_config = LoraConfig(
        r=args.lora_r,
        lora_alpha=args.lora_alpha,
        target_modules=["q_proj", "v_proj", "k_proj", "o_proj", "gate_proj", "up_proj", "down_proj"],
        lora_dropout=0.05,
        bias="none",
        task_type="CAUSAL_LM",
    )

    model = get_peft_model(model, lora_config)
    model.print_trainable_parameters()

    # Preparar dataset
    logger.info("\nPreparando dataset...")
    formatted_examples = [format_example(ex, tokenizer) for ex in examples]
    dataset = Dataset.from_list(formatted_examples)

    def tokenize(example):
        return tokenizer(
            example["text"],
            truncation=True,
            max_length=args.max_length,
            padding="max_length",
        )

    tokenized_dataset = dataset.map(tokenize, remove_columns=["text"])
    logger.info(f"Dataset tokenizado: {len(tokenized_dataset)} ejemplos")

    # Crear directorio de salida
    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Configurar entrenamiento
    logger.info(f"\nConfigurando entrenamiento:")
    logger.info(f"  Epochs: {args.epochs}")
    logger.info(f"  Batch size: {args.batch_size}")
    logger.info(f"  Learning rate: {args.learning_rate}")
    logger.info(f"  Output: {args.output}")

    training_args = TrainingArguments(
        output_dir=str(output_dir),
        num_train_epochs=args.epochs,
        per_device_train_batch_size=args.batch_size,
        gradient_accumulation_steps=4,
        learning_rate=args.learning_rate,
        warmup_steps=10,
        logging_steps=10,
        save_strategy="epoch",
        fp16=True,
        optim="paged_adamw_8bit",
        report_to="none",
        save_total_limit=2,
    )

    data_collator = DataCollatorForLanguageModeling(
        tokenizer=tokenizer,
        mlm=False,
    )

    # Crear trainer
    trainer = Trainer(
        model=model,
        args=training_args,
        train_dataset=tokenized_dataset,
        data_collator=data_collator,
    )

    # Entrenar
    logger.info("\n" + "=" * 60)
    logger.info("Iniciando entrenamiento...")
    logger.info("=" * 60)

    trainer.train()

    # Guardar modelo
    logger.info("\nGuardando adaptador LoRA...")
    model.save_pretrained(str(output_dir))
    tokenizer.save_pretrained(str(output_dir))

    # Guardar metadatos
    metadata = {
        "domain": "document",
        "base_model": args.base_model,
        "num_examples": len(examples),
        "categories": args.categories or list(DATASET_STATS['categories'].keys()),
        "num_epochs": args.epochs,
        "lora_r": args.lora_r,
        "lora_alpha": args.lora_alpha,
        "trained_at": datetime.now().isoformat(),
        "document_types": [
            "contratos", "facturas", "expedientes", "actas",
            "informes", "correspondencia", "normativas"
        ],
        "huggingface_augmented": args.augment_huggingface,
        "huggingface_datasets": args.hf_datasets if args.augment_huggingface else None,
    }

    with open(output_dir / "expert_metadata.json", "w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=2, ensure_ascii=False)

    logger.info(f"\n✓ Entrenamiento completado")
    logger.info(f"✓ Adaptador guardado en: {args.output}")
    logger.info(f"✓ Metadatos guardados en: {args.output}/expert_metadata.json")

    # Limpiar
    del model
    del trainer
    torch.cuda.empty_cache()

    logger.info("\n" + "=" * 60)
    logger.info("¡Experto Documental entrenado exitosamente!")
    logger.info("=" * 60)


if __name__ == "__main__":
    main()
