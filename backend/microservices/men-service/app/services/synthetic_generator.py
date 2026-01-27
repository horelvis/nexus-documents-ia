"""
Synthetic Data Generator for Expert Training.

Generates domain-specific training examples when custom
training data is not available.

Uses templates and patterns to create diverse examples
for each supported domain.
"""

import logging
import random
from typing import Dict, List

logger = logging.getLogger(__name__)


class SyntheticDataGenerator:
    """
    Generate synthetic training data for expert fine-tuning.

    Creates domain-specific question-answer pairs that help
    the expert learn domain terminology and response patterns.
    """

    # Domain-specific templates
    DOMAIN_TEMPLATES: Dict[str, Dict] = {
        "legal": {
            "queries": [
                "¿Cuál es el plazo de prescripción para {topic}?",
                "¿Qué dice la normativa sobre {topic}?",
                "¿Cuáles son los requisitos legales para {topic}?",
                "Explica la jurisprudencia reciente sobre {topic}",
                "¿Qué obligaciones tiene una empresa respecto a {topic}?",
                "¿Cómo se aplica la ley de {topic}?",
                "¿Qué sanciones existen por incumplir {topic}?",
            ],
            "topics": [
                "protección de datos personales",
                "contratos laborales",
                "responsabilidad civil",
                "propiedad intelectual",
                "derecho mercantil",
                "competencia desleal",
                "prevención de riesgos laborales",
            ],
            "response_prefix": "Según la normativa vigente, ",
        },
        "contract": {
            "queries": [
                "¿Qué cláusulas debe incluir un contrato de {topic}?",
                "¿Cómo se calcula la penalización por incumplimiento en {topic}?",
                "¿Cuándo vence el contrato de {topic}?",
                "¿Qué condiciones tiene el contrato de {topic}?",
                "¿Cómo renovar el contrato de {topic}?",
                "¿Qué partes intervienen en el contrato de {topic}?",
                "Lista los contratos activos de {topic}",
            ],
            "topics": [
                "arrendamiento comercial",
                "suministro de servicios",
                "licencia de software",
                "distribución",
                "franquicia",
                "consultoría",
                "mantenimiento",
            ],
            "response_prefix": "El contrato establece que ",
        },
        "compliance": {
            "queries": [
                "¿Cumplimos con la normativa de {topic}?",
                "¿Qué auditorías se requieren para {topic}?",
                "¿Cuál es el estado de cumplimiento de {topic}?",
                "¿Qué certificaciones tenemos para {topic}?",
                "¿Hay hallazgos pendientes de {topic}?",
                "¿Cuándo es la próxima revisión de {topic}?",
                "Genera un informe de cumplimiento de {topic}",
            ],
            "topics": [
                "ISO 27001",
                "RGPD",
                "prevención de blanqueo",
                "control interno",
                "SOC 2",
                "gestión de riesgos",
                "protección al consumidor",
            ],
            "response_prefix": "En relación al cumplimiento, ",
        },
        "finance": {
            "queries": [
                "¿Cuál es el presupuesto asignado a {topic}?",
                "Muestra las facturas pendientes de {topic}",
                "¿Cuál es el estado financiero de {topic}?",
                "¿Hay pagos vencidos de {topic}?",
                "Genera el balance de {topic}",
                "¿Cuáles son los gastos de {topic}?",
                "¿Qué ingresos se registraron por {topic}?",
            ],
            "topics": [
                "el departamento de ventas",
                "proyectos de desarrollo",
                "servicios externos",
                "marketing digital",
                "operaciones",
                "recursos humanos",
                "infraestructura TI",
            ],
            "response_prefix": "Los datos financieros indican que ",
        },
        "hr": {
            "queries": [
                "¿Cuántos empleados tiene {topic}?",
                "¿Cuál es la política de vacaciones para {topic}?",
                "Lista las contrataciones recientes en {topic}",
                "¿Hay evaluaciones pendientes en {topic}?",
                "¿Cuál es el organigrama de {topic}?",
                "¿Qué beneficios tiene {topic}?",
                "Muestra las nóminas de {topic}",
            ],
            "topics": [
                "el departamento de tecnología",
                "el equipo comercial",
                "atención al cliente",
                "administración",
                "producción",
                "calidad",
                "dirección general",
            ],
            "response_prefix": "Según los registros de RRHH, ",
        },
        "technical": {
            "queries": [
                "¿Cómo funciona el sistema de {topic}?",
                "¿Cuál es la arquitectura de {topic}?",
                "Documenta el proceso de {topic}",
                "¿Qué APIs están disponibles para {topic}?",
                "¿Cómo se configura {topic}?",
                "¿Hay manuales técnicos de {topic}?",
                "Lista las integraciones de {topic}",
            ],
            "topics": [
                "gestión documental",
                "autenticación de usuarios",
                "búsqueda semántica",
                "procesamiento de facturas",
                "firma electrónica",
                "notificaciones",
                "reporting",
            ],
            "response_prefix": "Técnicamente, ",
        },
    }

    def __init__(self, domain: str):
        """
        Initialize generator for a specific domain.

        Args:
            domain: Target domain (legal, contract, etc.)
        """
        self.domain = domain
        self.templates = self.DOMAIN_TEMPLATES.get(domain, self.DOMAIN_TEMPLATES["legal"])

    def generate(self, num_samples: int = 100) -> List[Dict[str, str]]:
        """
        Generate synthetic training examples.

        Args:
            num_samples: Number of examples to generate

        Returns:
            List of {input, output} dictionaries
        """
        examples = []

        queries = self.templates["queries"]
        topics = self.templates["topics"]
        prefix = self.templates["response_prefix"]

        for _ in range(num_samples):
            # Select random query and topic
            query_template = random.choice(queries)
            topic = random.choice(topics)

            # Generate query
            query = query_template.format(topic=topic)

            # Generate response
            response = self._generate_response(query, topic, prefix)

            examples.append({
                "input": query,
                "output": response
            })

        logger.info(f"Generated {len(examples)} synthetic examples for domain '{self.domain}'")

        return examples

    def _generate_response(self, query: str, topic: str, prefix: str) -> str:
        """Generate a plausible response for training."""
        # Response templates by query type
        if "cuántos" in query.lower() or "lista" in query.lower():
            response = f"{prefix}se han identificado varios registros relacionados con {topic}. "
            response += "Para obtener información detallada, consulte los documentos correspondientes."

        elif "plazo" in query.lower() or "vence" in query.lower():
            response = f"{prefix}los plazos establecidos para {topic} varían según las condiciones específicas. "
            response += "Revise la documentación relevante para fechas exactas."

        elif "requisitos" in query.lower() or "obligaciones" in query.lower():
            response = f"{prefix}los requisitos principales para {topic} incluyen:\n"
            response += "1. Documentación completa y actualizada\n"
            response += "2. Cumplimiento de normativas aplicables\n"
            response += "3. Revisión periódica según calendario establecido"

        elif "cómo" in query.lower() or "proceso" in query.lower():
            response = f"{prefix}el proceso de {topic} sigue estos pasos:\n"
            response += "1. Revisión inicial de requisitos\n"
            response += "2. Validación de documentación\n"
            response += "3. Aprobación según flujo establecido\n"
            response += "4. Registro y seguimiento"

        elif "estado" in query.lower() or "cumplimos" in query.lower():
            response = f"{prefix}el estado actual de {topic} es conforme. "
            response += "La última revisión se completó satisfactoriamente."

        else:
            response = f"{prefix}en relación a {topic}, la información disponible indica "
            response += "que se están cumpliendo los estándares establecidos. "
            response += "Consulte los documentos específicos para más detalles."

        return response

    @classmethod
    def get_supported_domains(cls) -> List[str]:
        """Get list of domains with template support."""
        return list(cls.DOMAIN_TEMPLATES.keys())


def generate_synthetic_data(
    domain: str,
    num_samples: int = 100,
    tenant_context: dict = None
) -> List[Dict[str, str]]:
    """
    Convenience function to generate synthetic data.

    Args:
        domain: Target domain
        num_samples: Number of examples
        tenant_context: Optional tenant-specific context to customize examples

    Returns:
        List of training examples
    """
    generator = SyntheticDataGenerator(domain)
    examples = generator.generate(num_samples)

    # If tenant context provided, customize some examples
    if tenant_context:
        # Add tenant-specific topics if available
        if "document_types" in tenant_context:
            for i, doc_type in enumerate(tenant_context["document_types"][:10]):
                if i < len(examples):
                    examples[i]["input"] = examples[i]["input"].replace(
                        list(generator.templates["topics"])[0],
                        doc_type
                    )

        if "known_clients" in tenant_context:
            for i, client in enumerate(tenant_context["known_clients"][:10]):
                idx = len(examples) // 2 + i
                if idx < len(examples):
                    examples[idx]["input"] += f" para {client}"

    return examples
