#!/usr/bin/env python3
"""
Seed few-shot examples for Emma.

Populates emma_few_shot_examples table with initial Q&A pairs for
improved response consistency. Examples are auto-embedded using
weaviate-service's BGE-M3 embeddings.

Usage:
    # Seed all examples
    python scripts/seed_few_shot_examples.py

    # Seed specific domain
    python scripts/seed_few_shot_examples.py --domain legal

    # Dry run
    python scripts/seed_few_shot_examples.py --dry-run
"""

import argparse
import asyncio
import os
import sys
from pathlib import Path
from typing import List, Dict, Any

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))


# Seed data organized by domain
SEED_EXAMPLES: List[Dict[str, Any]] = [
    # ══════════════════════════════════════════════════════════════════════════
    # LEGAL - Labor Law
    # ══════════════════════════════════════════════════════════════════════════
    {
        "question": "¿Cuántos días de preaviso debe dar un trabajador para dimitir?",
        "answer": "Según el artículo 49.1.d) del Estatuto de los Trabajadores, el trabajador debe preavisar con la antelación que establezca el convenio colectivo aplicable. En ausencia de convenio, la jurisprudencia ha establecido 15 días como plazo razonable. No obstante, algunos convenios pueden establecer plazos diferentes según la categoría profesional.",
        "category": "dimision_laboral",
        "domain": "legal",
        "tags": ["preaviso", "dimision", "estatuto_trabajadores"],
        "quality_score": 0.95,
    },
    {
        "question": "¿Qué indemnización corresponde por despido improcedente?",
        "answer": "La indemnización por despido improcedente está regulada en el artículo 56 del Estatuto de los Trabajadores: 33 días de salario por año trabajado, con un máximo de 24 mensualidades, para contratos posteriores al 12 de febrero de 2012. Para antigüedad anterior a esa fecha, se aplica 45 días por año con máximo de 42 mensualidades (disposición transitoria 11ª ET).",
        "category": "despido",
        "domain": "legal",
        "tags": ["despido_improcedente", "indemnizacion", "estatuto_trabajadores"],
        "quality_score": 0.95,
    },
    {
        "question": "¿Cuál es el período de prueba máximo?",
        "answer": "El artículo 14 del Estatuto de los Trabajadores establece: máximo 6 meses para técnicos titulados, 2 meses para el resto de trabajadores (o 3 meses en empresas de menos de 25 trabajadores). El convenio colectivo puede reducir estos plazos pero nunca ampliarlos. Durante el período de prueba, cualquiera de las partes puede desistir sin preaviso ni indemnización.",
        "category": "contratacion",
        "domain": "legal",
        "tags": ["periodo_prueba", "contratacion", "estatuto_trabajadores"],
        "quality_score": 0.95,
    },
    {
        "question": "¿Cuántos días de vacaciones corresponden por año trabajado?",
        "answer": "El artículo 38 del Estatuto de los Trabajadores establece un mínimo de 30 días naturales de vacaciones anuales retribuidas, que no pueden compensarse económicamente. Este es un mínimo legal; los convenios colectivos pueden mejorar este derecho. Las vacaciones son proporcionales al tiempo trabajado en caso de contratos inferiores a un año.",
        "category": "vacaciones",
        "domain": "legal",
        "tags": ["vacaciones", "derechos_laborales", "estatuto_trabajadores"],
        "quality_score": 0.90,
    },

    # ══════════════════════════════════════════════════════════════════════════
    # LEGAL - Fiscal
    # ══════════════════════════════════════════════════════════════════════════
    {
        "question": "¿Cuáles son los plazos para presentar el Modelo 303 de IVA?",
        "answer": "El Modelo 303 (autoliquidación trimestral del IVA) debe presentarse: 1T: del 1 al 20 de abril, 2T: del 1 al 20 de julio, 3T: del 1 al 20 de octubre, 4T: del 1 al 30 de enero del año siguiente. Para grandes empresas (>6M€ facturación), la declaración es mensual (modelo 303 hasta el día 20 del mes siguiente).",
        "category": "iva",
        "domain": "legal",
        "tags": ["iva", "modelo_303", "plazos_fiscales"],
        "quality_score": 0.95,
    },
    {
        "question": "¿Qué gastos son deducibles en el IRPF para autónomos?",
        "answer": "Los gastos deducibles para autónomos incluyen: consumos de explotación, gastos de personal, arrendamientos, servicios profesionales, tributos, amortizaciones, y otros gastos necesarios para la actividad. Los gastos de manutención tienen límites: 26,67€/día en España (48,08€ con pernocta) y 48,08€/día en extranjero (91,35€ con pernocta). Deben estar justificados, contabilizados y correlacionados con la actividad.",
        "category": "irpf",
        "domain": "legal",
        "tags": ["irpf", "autonomos", "gastos_deducibles"],
        "quality_score": 0.90,
    },

    # ══════════════════════════════════════════════════════════════════════════
    # LEGAL - Contract
    # ══════════════════════════════════════════════════════════════════════════
    {
        "question": "¿Qué cláusulas debe contener un contrato de arrendamiento de vivienda?",
        "answer": "Un contrato de arrendamiento de vivienda debe incluir: identificación de las partes, descripción del inmueble, duración (mínimo 5 años según LAU, o 7 si arrendador es persona jurídica), renta y forma de actualización, fianza (1 mensualidad mínimo), inventario de bienes, distribución de gastos, y causas de resolución. Es recomendable inscribirlo en el Registro de la Propiedad.",
        "category": "arrendamiento",
        "domain": "legal",
        "tags": ["arrendamiento", "contrato", "lau"],
        "quality_score": 0.90,
    },
    {
        "question": "¿Qué diferencia hay entre contrato indefinido y temporal?",
        "answer": "El contrato indefinido no tiene fecha de finalización y es la forma ordinaria de contratación. El contrato temporal tiene duración determinada y solo puede usarse para: obra o servicio determinado, circunstancias de la producción, o sustitución de trabajadores. La reforma laboral de 2022 restringió significativamente los contratos temporales, siendo el indefinido la regla general.",
        "category": "contratacion",
        "domain": "legal",
        "tags": ["contrato_indefinido", "contrato_temporal", "reforma_laboral"],
        "quality_score": 0.90,
    },

    # ══════════════════════════════════════════════════════════════════════════
    # LEGAL - Privacy/GDPR
    # ══════════════════════════════════════════════════════════════════════════
    {
        "question": "¿Cuáles son los derechos ARCO bajo el RGPD?",
        "answer": "Los derechos ARCO (Acceso, Rectificación, Cancelación, Oposición) se ampliaron con el RGPD a derechos ARSULIPO: Acceso, Rectificación, Supresión, Limitación, Portabilidad y Oposición. El responsable debe responder en 1 mes (prorrogable 2 meses más). El incumplimiento puede suponer sanciones de hasta 20M€ o 4% del volumen de negocio global.",
        "category": "proteccion_datos",
        "domain": "legal",
        "tags": ["rgpd", "lopdgdd", "derechos_arco"],
        "quality_score": 0.95,
    },

    # ══════════════════════════════════════════════════════════════════════════
    # MEDICAL
    # ══════════════════════════════════════════════════════════════════════════
    {
        "question": "¿Cuánto tiempo debe conservarse la historia clínica?",
        "answer": "Según la Ley 41/2002 de autonomía del paciente, la historia clínica debe conservarse un mínimo de 5 años desde la última asistencia. Sin embargo, la LOPDGDD y normativa autonómica pueden establecer plazos mayores. En la práctica, muchos centros conservan historiales 15-20 años o indefinidamente para casos especiales.",
        "category": "historia_clinica",
        "domain": "medical",
        "tags": ["historia_clinica", "conservacion", "ley_autonomia_paciente"],
        "quality_score": 0.85,
    },
    {
        "question": "¿Quién puede acceder a la historia clínica de un paciente?",
        "answer": "Pueden acceder: el paciente, profesionales sanitarios que lo atiendan (con acceso proporcional), personal de administración/gestión (solo datos indispensables), y terceros con autorización del paciente. Los menores a partir de 16 años tienen derecho a decidir sobre su propia salud. Existen excepciones para investigación epidemiológica o autoridad judicial.",
        "category": "historia_clinica",
        "domain": "medical",
        "tags": ["acceso_historia_clinica", "confidencialidad", "derechos_paciente"],
        "quality_score": 0.85,
    },

    # ══════════════════════════════════════════════════════════════════════════
    # DOCUMENTAL
    # ══════════════════════════════════════════════════════════════════════════
    {
        "question": "¿Cuánto tiempo debo conservar las facturas de mi empresa?",
        "answer": "Las facturas deben conservarse durante 6 años según el Código de Comercio (art. 30). Sin embargo, para efectos fiscales, el plazo de prescripción es de 4 años desde la presentación de la declaración. Es recomendable conservar 6 años completos. El archivo puede ser físico o digital siempre que garantice la autenticidad e integridad.",
        "category": "archivo",
        "domain": "documental",
        "tags": ["facturas", "conservacion", "codigo_comercio"],
        "quality_score": 0.90,
    },
    {
        "question": "¿Qué documentos requieren firma electrónica cualificada?",
        "answer": "Requieren firma electrónica cualificada: contratos con la Administración Pública, documentos notariales, actos inscritos en registros públicos, y declaraciones tributarias. Para documentos entre particulares, la firma electrónica avanzada es generalmente suficiente. La firma cualificada tiene el mismo valor que la manuscrita según el Reglamento eIDAS.",
        "category": "firma_electronica",
        "domain": "documental",
        "tags": ["firma_electronica", "eidas", "documentos_legales"],
        "quality_score": 0.85,
    },

    # ══════════════════════════════════════════════════════════════════════════
    # GENERAL
    # ══════════════════════════════════════════════════════════════════════════
    {
        "question": "¿Cómo busco documentos en el sistema?",
        "answer": "Puedes buscar documentos de varias formas: 1) Escribe tu pregunta en lenguaje natural y encontraré los documentos relevantes, 2) Usa filtros por tipo de documento, fecha o etiquetas, 3) Pregunta específicamente por un documento si conoces su nombre. También puedo analizar documentos que ya tengas abiertos.",
        "category": "uso_sistema",
        "domain": "general",
        "tags": ["busqueda", "ayuda", "tutorial"],
        "quality_score": 0.80,
    },
    {
        "question": "¿Puedes generar un documento nuevo?",
        "answer": "Sí, puedo ayudarte a generar varios tipos de documentos: contratos, informes, actas, cartas formales, y más. Dime qué tipo de documento necesitas y te guiaré en el proceso, solicitando la información necesaria. También puedo usar documentos existentes como plantilla o referencia.",
        "category": "uso_sistema",
        "domain": "general",
        "tags": ["generacion", "documentos", "ayuda"],
        "quality_score": 0.80,
    },
]


async def get_embedding(text: str, weaviate_url: str, api_key: str) -> List[float]:
    """Get embedding from weaviate-service."""
    import httpx

    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(
            f"{weaviate_url}/embed",
            json={"text": text},
            headers={"X-API-Key": api_key},
        )
        if response.status_code == 200:
            return response.json().get("embedding")
        else:
            print(f"⚠️ Failed to get embedding: {response.status_code}")
            return None


async def seed_examples(
    examples: List[Dict[str, Any]],
    database_url: str,
    weaviate_url: str,
    api_key: str,
    dry_run: bool = False,
    domain_filter: str = None,
) -> Dict[str, int]:
    """Seed examples into the database."""
    from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy import text

    results = {"created": 0, "skipped": 0, "errors": 0}

    # Filter by domain if specified
    if domain_filter:
        examples = [e for e in examples if e.get("domain") == domain_filter]

    if dry_run:
        print("\n🔍 DRY RUN - No changes will be made\n")
        print("=" * 60)
        for ex in examples:
            print(f"📝 {ex['category']}: {ex['question'][:50]}...")
            print(f"   Domain: {ex['domain']}, Tags: {ex.get('tags', [])}")
        print("=" * 60)
        print(f"\nTotal: {len(examples)} examples would be created")
        return results

    # Connect to database
    engine = create_async_engine(database_url)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    print(f"\n🚀 Seeding {len(examples)} few-shot examples...\n")

    async with async_session() as session:
        for ex in examples:
            try:
                # Get embedding
                embedding = await get_embedding(ex["question"], weaviate_url, api_key)
                embedding_str = None
                if embedding:
                    embedding_str = "[" + ",".join(str(x) for x in embedding) + "]"

                # Check if example already exists (by question similarity)
                check_query = text("""
                    SELECT id FROM emma_few_shot_examples
                    WHERE question = :question
                    LIMIT 1
                """)
                check_result = await session.execute(check_query, {"question": ex["question"]})
                if check_result.fetchone():
                    results["skipped"] += 1
                    print(f"⏭️  Skipped (exists): {ex['category']}")
                    continue

                # Insert example
                if embedding_str:
                    insert_query = text("""
                        INSERT INTO emma_few_shot_examples
                            (question, answer, category, domain, tags, quality_score, embedding_vector)
                        VALUES
                            (:question, :answer, :category, :domain, :tags, :quality_score, :embedding::vector)
                    """)
                else:
                    insert_query = text("""
                        INSERT INTO emma_few_shot_examples
                            (question, answer, category, domain, tags, quality_score)
                        VALUES
                            (:question, :answer, :category, :domain, :tags, :quality_score)
                    """)

                params = {
                    "question": ex["question"],
                    "answer": ex["answer"],
                    "category": ex.get("category"),
                    "domain": ex.get("domain"),
                    "tags": ex.get("tags"),
                    "quality_score": ex.get("quality_score", 1.0),
                }
                if embedding_str:
                    params["embedding"] = embedding_str

                await session.execute(insert_query, params)
                results["created"] += 1
                print(f"✅ Created: {ex['category']} - {ex['question'][:40]}...")

            except Exception as e:
                results["errors"] += 1
                print(f"❌ Error: {e}")

        await session.commit()

    print("\n" + "=" * 60)
    print("Seeding Summary:")
    print(f"  Created: {results['created']}")
    print(f"  Skipped: {results['skipped']}")
    print(f"  Errors:  {results['errors']}")
    print("=" * 60)

    return results


def main():
    parser = argparse.ArgumentParser(description="Seed few-shot examples for Emma")
    parser.add_argument("--dry-run", action="store_true", help="Preview without making changes")
    parser.add_argument("--domain", type=str, help="Filter by domain (legal, medical, documental, general)")
    parser.add_argument("--database-url", type=str, help="Database URL")
    parser.add_argument("--weaviate-url", type=str, help="Weaviate service URL")

    args = parser.parse_args()

    database_url = args.database_url or os.getenv(
        "DATABASE_URL",
        "postgresql+asyncpg://postgres:postgres@localhost:5432/nexus_db"
    )
    weaviate_url = args.weaviate_url or os.getenv(
        "WEAVIATE_SERVICE_URL",
        "http://localhost:8007"
    )
    api_key = os.getenv("MICROSERVICES_API_KEY", "development-key")

    asyncio.run(seed_examples(
        SEED_EXAMPLES,
        database_url,
        weaviate_url,
        api_key,
        dry_run=args.dry_run,
        domain_filter=args.domain,
    ))


if __name__ == "__main__":
    main()
