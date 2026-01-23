"""
NexusRouter Dataset Builder

Builds balanced training datasets from collected data:
1. Historical queries are mapped to intents
2. Synthetic queries are generated from document metadata
3. Manual examples provide coverage for edge cases
4. Dataset is balanced and split for training/evaluation

The builder ensures:
- Minimum examples per intent
- Balanced class distribution
- Train/eval split
- Quality filtering
"""

import logging
import random
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from .schemas import (
    Intent,
    TrainingExample,
    TrainingDataset,
    NexusRouterConfig,
)

logger = logging.getLogger(__name__)


# =============================================================================
# Synthetic Query Templates
# =============================================================================

# Templates for generating synthetic queries per intent
# {type} = document type, {entity} = entity name, {date} = date string

SYNTHETIC_TEMPLATES: Dict[Intent, List[str]] = {
    Intent.SEARCH: [
        "busca {type}",
        "encuentra {type}",
        "muéstrame {type}",
        "necesito {type}",
        "dame {type}",
        "quiero ver {type}",
        "buscar documentos de {type}",
        "documentos sobre {entity}",
        "archivos de {entity}",
        "información sobre {entity}",
        "busca {type} de {entity}",
        "encuentra documentos relacionados con {entity}",
        "mostrar {type} de {date}",
        "ver {type}",
        "obtener {type}",
    ],
    Intent.COUNT: [
        "cuántos {type} tengo",
        "cuántos {type} hay",
        "número de {type}",
        "total de {type}",
        "cantidad de {type}",
        "cuántos documentos de {type}",
        "cuántos {type} tiene {entity}",
        "cuántos {type} de {entity}",
        "cuenta los {type}",
        "total de {type} de {date}",
        "cuántos {type} este mes",
        "cuántos {type} en el sistema",
    ],
    Intent.LIST: [
        "lista de {type}",
        "listar {type}",
        "enumera {type}",
        "qué {type} tengo",
        "cuáles son los {type}",
        "muestra todos los {type}",
        "dame una lista de {type}",
        "listado de {type}",
        "todos los {type}",
        "qué {type} hay de {entity}",
        "listar {type} de {date}",
    ],
    Intent.ANALYZE: [
        "analiza el {type}",
        "analizar {type}",
        "revisa el {type}",
        "examina el {type}",
        "evalúa el {type}",
        "qué contiene el {type}",
        "detalles del {type}",
        "análisis del {type} de {entity}",
        "revisa las cláusulas del {type}",
        "examina los riesgos del {type}",
        "evalúa el {type} de {entity}",
    ],
    Intent.COMPARE: [
        "compara {type}",
        "comparar {type}",
        "diferencias entre {type}",
        "qué cambió en el {type}",
        "versiones del {type}",
        "comparativa de {type}",
        "compara el {type} con el anterior",
        "diferencias del {type} de {entity}",
        "cambios en {type}",
    ],
    Intent.SUMMARIZE: [
        "resume el {type}",
        "resumen del {type}",
        "sintetiza el {type}",
        "puntos clave del {type}",
        "principales puntos del {type}",
        "resumen ejecutivo del {type}",
        "resume los {type} de {entity}",
        "síntesis del {type}",
    ],
    Intent.EXTRACT: [
        "extrae datos del {type}",
        "extraer información del {type}",
        "saca los datos del {type}",
        "obtén las fechas del {type}",
        "extrae las cláusulas del {type}",
        "información de {entity} en el {type}",
        "datos de {entity} del {type}",
        "extrae las cifras del {type}",
    ],
    Intent.CHAT: [
        "hola",
        "buenos días",
        "buenas tardes",
        "gracias",
        "muchas gracias",
        "adiós",
        "hasta luego",
        "quién eres",
        "cómo te llamas",
        "qué puedes hacer",
        "ayuda",
        "cómo funciona esto",
        "qué hora es",
        "cómo estás",
        "bien",
        "ok",
        "vale",
        "entendido",
        "perfecto",
    ],
}

# Document type synonyms for variety
DOCUMENT_TYPE_SYNONYMS = {
    "contrato": ["contrato", "contratos", "acuerdo", "convenio"],
    "factura": ["factura", "facturas", "recibo", "comprobante"],
    "informe": ["informe", "informes", "reporte", "análisis"],
    "acta": ["acta", "actas", "minutas", "minuta"],
    "presupuesto": ["presupuesto", "presupuestos", "cotización", "oferta"],
    "nómina": ["nómina", "nóminas", "recibo de salario"],
    "documento": ["documento", "documentos", "archivo", "fichero"],
    "pdf": ["pdf", "pdfs", "documento pdf"],
    "excel": ["excel", "hoja de cálculo", "spreadsheet"],
    "word": ["word", "documento word", "doc"],
}


class DatasetBuilder:
    """
    Builds training datasets from collected data.

    Process:
    1. Map historical queries to intents
    2. Generate synthetic queries from document metadata
    3. Add manual examples for coverage
    4. Balance and split dataset
    """

    def __init__(self, config: Optional[NexusRouterConfig] = None):
        """
        Initialize the dataset builder.

        Args:
            config: Router configuration (uses defaults if not provided)
        """
        self.config = config or NexusRouterConfig()

    def build_dataset(
        self,
        collected_data: Dict[str, Any],
        include_synthetic: bool = True,
        include_manual: bool = True,
    ) -> TrainingDataset:
        """
        Build a complete training dataset from collected data.

        Args:
            collected_data: Output from DataCollector.collect_all()
            include_synthetic: Generate synthetic queries
            include_manual: Include manual baseline examples

        Returns:
            TrainingDataset ready for model training
        """
        examples = []

        # 1. Process historical queries
        historical_examples = self._process_historical_queries(
            collected_data.get("historical_queries", [])
        )
        examples.extend(historical_examples)
        logger.info(f"Added {len(historical_examples)} historical examples")

        # 2. Generate synthetic queries
        if include_synthetic:
            synthetic_examples = self._generate_synthetic_queries(
                documents=collected_data.get("documents", []),
                entities=collected_data.get("entities", []),
                doc_type_dist=collected_data.get("document_type_distribution", {}),
            )
            examples.extend(synthetic_examples)
            logger.info(f"Added {len(synthetic_examples)} synthetic examples")

        # 3. Add manual baseline examples
        if include_manual:
            manual_examples = self._get_manual_examples()
            examples.extend(manual_examples)
            logger.info(f"Added {len(manual_examples)} manual examples")

        # 4. Balance the dataset
        balanced_examples = self._balance_dataset(examples)
        logger.info(f"Balanced to {len(balanced_examples)} examples")

        # 5. Split into train/eval
        train_examples, eval_examples = self._split_dataset(balanced_examples)
        logger.info(f"Split: {len(train_examples)} train, {len(eval_examples)} eval")

        # 6. Build final dataset
        tenant_ids = list(set(
            ex.tenant_id for ex in examples if ex.tenant_id
        ))

        return TrainingDataset(
            train_examples=train_examples,
            eval_examples=eval_examples,
            tenant_ids=tenant_ids,
        )

    def _process_historical_queries(
        self,
        queries: List[Dict[str, Any]],
    ) -> List[TrainingExample]:
        """
        Process historical queries into training examples.

        Maps detected intents to our Intent enum.
        """
        examples = []

        # Intent mapping from historical data
        intent_mapping = {
            "search": Intent.SEARCH,
            "buscar": Intent.SEARCH,
            "analysis": Intent.ANALYZE,
            "analizar": Intent.ANALYZE,
            "conversation": Intent.CHAT,
            "chat": Intent.CHAT,
            "count": Intent.COUNT,
            "contar": Intent.COUNT,
            "list": Intent.LIST,
            "listar": Intent.LIST,
            "compare": Intent.COMPARE,
            "comparar": Intent.COMPARE,
            "summarize": Intent.SUMMARIZE,
            "resumir": Intent.SUMMARIZE,
            "extract": Intent.EXTRACT,
            "extraer": Intent.EXTRACT,
        }

        for query_data in queries:
            query_text = query_data.get("query_text", "").strip()
            detected_intent = query_data.get("intent", "").lower()

            if not query_text or not detected_intent:
                continue

            # Map to our Intent enum
            intent = intent_mapping.get(detected_intent)
            if not intent:
                # Default to SEARCH for unknown intents
                intent = Intent.SEARCH

            examples.append(TrainingExample(
                text=query_text,
                intent=intent,
                source="historical",
                tenant_id=query_data.get("tenant_id"),
                created_at=query_data.get("created_at"),
            ))

        return examples

    def _generate_synthetic_queries(
        self,
        documents: List[Dict[str, Any]],
        entities: List[Dict[str, Any]],
        doc_type_dist: Dict[str, int],
    ) -> List[TrainingExample]:
        """
        Generate synthetic queries from document metadata.

        Uses templates and document types to create varied training data.
        """
        examples = []

        # Extract unique document types
        doc_types = list(doc_type_dist.keys()) if doc_type_dist else []
        if not doc_types:
            # Fallback to common types
            doc_types = ["contrato", "factura", "informe", "acta", "documento"]

        # Extract entity values
        entity_values = [e.get("entity_value", "") for e in entities if e.get("entity_value")]
        if not entity_values:
            # Fallback entities
            entity_values = ["ACME", "empresa", "cliente", "proveedor"]

        # Date values for templates
        date_values = [
            "enero", "febrero", "marzo", "abril", "mayo", "junio",
            "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre",
            "2024", "2023", "este mes", "este año", "el mes pasado",
        ]

        # Generate examples for each intent
        for intent, templates in SYNTHETIC_TEMPLATES.items():
            num_examples = self.config.synthetic_multiplier * self.config.min_examples_per_intent

            for _ in range(num_examples):
                template = random.choice(templates)

                # Fill in template variables
                doc_type = random.choice(doc_types)
                # Use synonyms if available
                if doc_type.lower() in DOCUMENT_TYPE_SYNONYMS:
                    doc_type = random.choice(DOCUMENT_TYPE_SYNONYMS[doc_type.lower()])

                entity = random.choice(entity_values) if entity_values else ""
                date = random.choice(date_values)

                query = template.format(
                    type=doc_type,
                    entity=entity,
                    date=date,
                )

                examples.append(TrainingExample(
                    text=query,
                    intent=intent,
                    source="synthetic",
                    document_types=[doc_type],
                    entities=[entity] if entity else [],
                ))

        return examples

    def _get_manual_examples(self) -> List[TrainingExample]:
        """
        Get manually curated baseline examples.

        These ensure coverage for tricky cases and edge cases.
        """
        manual_data = [
            # SEARCH intent
            ("busca contratos", Intent.SEARCH),
            ("encuentra documentos de ACME", Intent.SEARCH),
            ("necesito las facturas", Intent.SEARCH),
            ("muéstrame los informes", Intent.SEARCH),
            ("dame los documentos del proyecto", Intent.SEARCH),
            ("quiero ver los archivos", Intent.SEARCH),
            ("documentos relacionados con el cliente", Intent.SEARCH),

            # COUNT intent
            ("cuántos contratos tengo", Intent.COUNT),
            ("cuántos documentos hay", Intent.COUNT),
            ("número de facturas", Intent.COUNT),
            ("total de archivos", Intent.COUNT),
            ("cantidad de informes este mes", Intent.COUNT),
            ("cuántos contratos tiene ACME", Intent.COUNT),
            ("cuántos documentos he subido", Intent.COUNT),

            # LIST intent
            ("lista de contratos", Intent.LIST),
            ("listar documentos", Intent.LIST),
            ("qué contratos tengo", Intent.LIST),
            ("cuáles son los documentos", Intent.LIST),
            ("muestra todos los archivos", Intent.LIST),
            ("enumera las facturas", Intent.LIST),
            ("listado de informes", Intent.LIST),

            # ANALYZE intent
            ("analiza el contrato", Intent.ANALYZE),
            ("revisa el documento", Intent.ANALYZE),
            ("examina el informe", Intent.ANALYZE),
            ("qué contiene el contrato", Intent.ANALYZE),
            ("evalúa el documento", Intent.ANALYZE),
            ("analiza las cláusulas", Intent.ANALYZE),
            ("revisa los riesgos del contrato", Intent.ANALYZE),
            ("qué dice el documento", Intent.ANALYZE),

            # COMPARE intent
            ("compara los contratos", Intent.COMPARE),
            ("diferencias entre versiones", Intent.COMPARE),
            ("qué cambió en el documento", Intent.COMPARE),
            ("comparar facturas", Intent.COMPARE),
            ("versiones del contrato", Intent.COMPARE),

            # SUMMARIZE intent
            ("resume el documento", Intent.SUMMARIZE),
            ("resumen del contrato", Intent.SUMMARIZE),
            ("puntos clave del informe", Intent.SUMMARIZE),
            ("sintetiza el documento", Intent.SUMMARIZE),
            ("resumen ejecutivo", Intent.SUMMARIZE),

            # EXTRACT intent
            ("extrae datos del contrato", Intent.EXTRACT),
            ("saca las fechas del documento", Intent.EXTRACT),
            ("extrae las cláusulas", Intent.EXTRACT),
            ("obtén los montos", Intent.EXTRACT),
            ("información del cliente", Intent.EXTRACT),

            # CHAT intent
            ("hola", Intent.CHAT),
            ("hola Emma", Intent.CHAT),
            ("buenos días", Intent.CHAT),
            ("gracias", Intent.CHAT),
            ("muchas gracias", Intent.CHAT),
            ("quién eres", Intent.CHAT),
            ("qué puedes hacer", Intent.CHAT),
            ("ayuda", Intent.CHAT),
            ("cómo funciona", Intent.CHAT),
            ("ok", Intent.CHAT),
            ("vale", Intent.CHAT),
            ("perfecto", Intent.CHAT),
            ("entendido", Intent.CHAT),
            ("adiós", Intent.CHAT),
            ("hasta luego", Intent.CHAT),
        ]

        return [
            TrainingExample(text=text, intent=intent, source="manual")
            for text, intent in manual_data
        ]

    def _balance_dataset(
        self,
        examples: List[TrainingExample],
    ) -> List[TrainingExample]:
        """
        Balance the dataset to prevent class imbalance.

        Ensures each intent has at least min_examples_per_intent.
        Optionally oversamples minority classes.
        """
        # Group by intent
        by_intent: Dict[Intent, List[TrainingExample]] = {
            intent: [] for intent in Intent
        }

        for ex in examples:
            by_intent[ex.intent].append(ex)

        # Find the target count (max of min_examples or median)
        counts = [len(exs) for exs in by_intent.values() if exs]
        if not counts:
            logger.warning("No examples to balance")
            return examples

        median_count = sorted(counts)[len(counts) // 2]
        target_count = max(self.config.min_examples_per_intent, median_count)

        balanced = []

        for intent, exs in by_intent.items():
            if not exs:
                logger.warning(f"No examples for intent {intent.value}")
                continue

            # If too few, oversample
            if len(exs) < target_count:
                # Duplicate existing examples
                while len(exs) < target_count:
                    exs.append(random.choice(exs))

            # If too many, undersample
            elif len(exs) > target_count * 2:
                exs = random.sample(exs, target_count * 2)

            balanced.extend(exs)

        # Shuffle
        random.shuffle(balanced)

        return balanced

    def _split_dataset(
        self,
        examples: List[TrainingExample],
    ) -> Tuple[List[TrainingExample], List[TrainingExample]]:
        """
        Split dataset into train and eval sets.

        Uses stratified splitting to maintain class distribution.
        """
        eval_size = int(len(examples) * self.config.eval_split)

        # Group by intent for stratified split
        by_intent: Dict[Intent, List[TrainingExample]] = {}
        for ex in examples:
            if ex.intent not in by_intent:
                by_intent[ex.intent] = []
            by_intent[ex.intent].append(ex)

        train_examples = []
        eval_examples = []

        for intent, exs in by_intent.items():
            random.shuffle(exs)
            split_idx = max(1, int(len(exs) * self.config.eval_split))
            eval_examples.extend(exs[:split_idx])
            train_examples.extend(exs[split_idx:])

        return train_examples, eval_examples


# Singleton instance
dataset_builder = DatasetBuilder()
