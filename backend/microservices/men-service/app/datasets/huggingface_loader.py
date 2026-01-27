"""
Loader para datasets de Hugging Face.

Carga y transforma datasets externos al formato de entrenamiento del experto documental.
Datasets soportados:
- dariolopez/justicio-rag-embedding-qa: 815 ejemplos de derecho español
- dariolopez/justicio-BOE-A-1978-31229-constitucion-by-articles-qa: 515 ejemplos sobre la Constitución Española

Uso:
    from app.datasets.huggingface_loader import load_huggingface_datasets, AVAILABLE_DATASETS

    # Cargar todos los datasets disponibles
    examples = load_huggingface_datasets()

    # Cargar solo datasets específicos
    examples = load_huggingface_datasets(datasets=["justicio-rag"])
"""

import logging
from typing import List, Dict, Optional, Callable
from functools import lru_cache

logger = logging.getLogger(__name__)

# Definición de datasets disponibles de Hugging Face
AVAILABLE_DATASETS = {
    "justicio-rag": {
        "name": "dariolopez/justicio-rag-embedding-qa",
        "description": "Q&A sobre derecho español (vivienda, salud pública)",
        "rows": 815,
        "category": "legal_general",
        "fields": {
            "input": "question",
            "context": "context",
            "output": "answer"
        }
    },
    "justicio-constitucion": {
        "name": "dariolopez/justicio-BOE-A-1978-31229-constitucion-by-articles-qa",
        "description": "Q&A sobre la Constitución Española por artículos",
        "rows": 515,
        "category": "legal_constitutional",
        "fields": {
            "input": "question",
            "context": "context",
            "output": "answer",
            "article": "number"
        }
    }
}


def _transform_justicio_rag(row: dict) -> Dict[str, str]:
    """
    Transforma un ejemplo del dataset justicio-rag-embedding-qa.

    El dataset tiene formato: {question, context, answer}
    Lo transformamos a: {input, output} incluyendo contexto en la respuesta.
    """
    question = row.get("question", "").strip()
    context = row.get("context", "").strip()
    answer = row.get("answer", "").strip()

    # Si no hay pregunta o respuesta válida, saltar
    if not question or not answer:
        return None

    # Construir output enriquecido con contexto legal
    if context and len(context) > 50:
        output = f"{answer}\n\n**Base Legal:**\n{context[:500]}..."
    else:
        output = answer

    return {
        "input": question,
        "output": output,
        "source": "huggingface/justicio-rag",
        "category": "legal_general"
    }


def _transform_justicio_constitucion(row: dict) -> Dict[str, str]:
    """
    Transforma un ejemplo del dataset justicio-BOE-A-1978-31229-constitucion-by-articles-qa.

    El dataset tiene formato: {number, context, question, answer}
    Lo transformamos incluyendo referencia al artículo constitucional.
    """
    article_num = row.get("number", "")
    question = row.get("question", "").strip()
    context = row.get("context", "").strip()
    answer = row.get("answer", "").strip()

    # Si no hay pregunta o respuesta válida, saltar
    if not question or not answer:
        return None

    # Enriquecer con referencia constitucional
    if article_num:
        output = f"{answer}\n\n**Referencia:** Artículo {article_num} de la Constitución Española de 1978."
    else:
        output = answer

    if context and len(context) > 50:
        output += f"\n\n**Texto del artículo:**\n{context[:600]}..."

    return {
        "input": question,
        "output": output,
        "source": "huggingface/justicio-constitucion",
        "category": "legal_constitutional"
    }


# Mapeo de transformadores por dataset
_TRANSFORMERS: Dict[str, Callable] = {
    "justicio-rag": _transform_justicio_rag,
    "justicio-constitucion": _transform_justicio_constitucion,
}


def load_huggingface_dataset(
    dataset_key: str,
    max_examples: Optional[int] = None,
    min_answer_length: int = 50
) -> List[Dict[str, str]]:
    """
    Carga y transforma un dataset específico de Hugging Face.

    Args:
        dataset_key: Clave del dataset (ej: "justicio-rag")
        max_examples: Número máximo de ejemplos a cargar (None = todos)
        min_answer_length: Longitud mínima de respuesta para filtrar

    Returns:
        Lista de ejemplos transformados con formato {input, output, source, category}
    """
    if dataset_key not in AVAILABLE_DATASETS:
        raise ValueError(f"Dataset '{dataset_key}' no disponible. Opciones: {list(AVAILABLE_DATASETS.keys())}")

    dataset_info = AVAILABLE_DATASETS[dataset_key]
    transformer = _TRANSFORMERS.get(dataset_key)

    if not transformer:
        raise ValueError(f"No hay transformador definido para '{dataset_key}'")

    try:
        # Importar datasets de Hugging Face (lazy import)
        from datasets import load_dataset

        logger.info(f"Cargando dataset: {dataset_info['name']}")

        # Cargar dataset
        hf_dataset = load_dataset(dataset_info["name"], split="train")

        examples = []
        skipped = 0

        for i, row in enumerate(hf_dataset):
            if max_examples and len(examples) >= max_examples:
                break

            # Transformar ejemplo
            transformed = transformer(row)

            if transformed is None:
                skipped += 1
                continue

            # Filtrar por longitud mínima
            if len(transformed.get("output", "")) < min_answer_length:
                skipped += 1
                continue

            examples.append(transformed)

        logger.info(f"  ✓ Cargados {len(examples)} ejemplos (omitidos: {skipped})")
        return examples

    except ImportError:
        logger.error("Módulo 'datasets' no instalado. Ejecuta: pip install datasets")
        return []
    except Exception as e:
        logger.error(f"Error cargando dataset {dataset_key}: {e}")
        return []


def load_huggingface_datasets(
    datasets: Optional[List[str]] = None,
    max_examples_per_dataset: Optional[int] = None,
    min_answer_length: int = 50
) -> List[Dict[str, str]]:
    """
    Carga múltiples datasets de Hugging Face.

    Args:
        datasets: Lista de claves de datasets a cargar (None = todos)
        max_examples_per_dataset: Máximo de ejemplos por dataset
        min_answer_length: Longitud mínima de respuesta

    Returns:
        Lista combinada de todos los ejemplos
    """
    if datasets is None:
        datasets = list(AVAILABLE_DATASETS.keys())

    all_examples = []

    for dataset_key in datasets:
        examples = load_huggingface_dataset(
            dataset_key=dataset_key,
            max_examples=max_examples_per_dataset,
            min_answer_length=min_answer_length
        )
        all_examples.extend(examples)

    logger.info(f"Total ejemplos cargados de HuggingFace: {len(all_examples)}")
    return all_examples


def get_huggingface_stats() -> Dict:
    """
    Retorna estadísticas de los datasets disponibles.
    """
    return {
        "available_datasets": list(AVAILABLE_DATASETS.keys()),
        "total_potential_examples": sum(d["rows"] for d in AVAILABLE_DATASETS.values()),
        "datasets_info": {
            key: {
                "name": info["name"],
                "description": info["description"],
                "rows": info["rows"],
                "category": info["category"]
            }
            for key, info in AVAILABLE_DATASETS.items()
        }
    }


# Cache para evitar descargas repetidas
@lru_cache(maxsize=4)
def get_cached_dataset(dataset_key: str, max_examples: int = 500) -> tuple:
    """
    Versión cacheada de load_huggingface_dataset.
    Retorna tupla para ser hasheable por lru_cache.
    """
    examples = load_huggingface_dataset(dataset_key, max_examples=max_examples)
    return tuple(tuple(sorted(ex.items())) for ex in examples)


def convert_to_training_format(
    examples: List[Dict[str, str]],
    include_source: bool = False
) -> List[Dict[str, str]]:
    """
    Convierte ejemplos al formato exacto de entrenamiento {input, output}.

    Args:
        examples: Lista de ejemplos con campos adicionales
        include_source: Si True, mantiene source/category en output

    Returns:
        Lista con solo {input, output}
    """
    training_examples = []

    for ex in examples:
        if "input" not in ex or "output" not in ex:
            continue

        if include_source and "source" in ex:
            output = f"{ex['output']}\n\n_Fuente: {ex['source']}_"
        else:
            output = ex["output"]

        training_examples.append({
            "input": ex["input"],
            "output": output
        })

    return training_examples


# Ejemplo de uso
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    print("=== Estadísticas de Datasets HuggingFace ===")
    stats = get_huggingface_stats()
    for key, info in stats["datasets_info"].items():
        print(f"\n{key}:")
        print(f"  Nombre: {info['name']}")
        print(f"  Descripción: {info['description']}")
        print(f"  Filas: {info['rows']}")
        print(f"  Categoría: {info['category']}")

    print(f"\nTotal potencial: {stats['total_potential_examples']} ejemplos")

    # Test de carga (descomentar para probar)
    # print("\n=== Cargando ejemplos de prueba ===")
    # examples = load_huggingface_datasets(max_examples_per_dataset=5)
    # for ex in examples[:3]:
    #     print(f"\nInput: {ex['input'][:80]}...")
    #     print(f"Output: {ex['output'][:150]}...")
