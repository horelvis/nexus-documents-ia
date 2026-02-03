#!/usr/bin/env python3
"""
Seed Legal Knowledge Graph

Populates the legal knowledge graph with Spanish legislation from BOE presets.
This script should be run once during initial setup or when adding new laws.

Usage:
    python scripts/seed_legal_graph.py

    # Seed specific domain only
    python scripts/seed_legal_graph.py --domain labor

    # Force re-seed (update existing)
    python scripts/seed_legal_graph.py --force
"""

import asyncio
import argparse
import logging
import sys
from pathlib import Path

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.services.sil.legal_graph_service import (
    legal_graph,
    LegalLaw,
    LegalDomain,
    LawStatus,
)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


# =============================================================================
# Spanish Legislation Database
# =============================================================================

SPANISH_LAWS = [
    # LABORAL
    LegalLaw(
        boe_id="BOE-A-2015-11430",
        title="Real Decreto Legislativo 2/2015, de 23 de octubre, por el que se aprueba el texto refundido de la Ley del Estatuto de los Trabajadores",
        short_name="ET",
        domain=LegalDomain.LABOR,
        publication_date="2015-10-24",
        keywords=["trabajo", "contrato laboral", "despido", "jornada", "vacaciones", "salario"],
    ),
    LegalLaw(
        boe_id="BOE-A-2020-11043",
        title="Real Decreto-ley 28/2020, de 22 de septiembre, de trabajo a distancia",
        short_name="Ley Teletrabajo",
        domain=LegalDomain.LABOR,
        publication_date="2020-09-23",
        keywords=["teletrabajo", "trabajo remoto", "trabajo a distancia"],
    ),
    LegalLaw(
        boe_id="BOE-A-1995-24292",
        title="Ley 31/1995, de 8 de noviembre, de prevención de Riesgos Laborales",
        short_name="LPRL",
        domain=LegalDomain.LABOR,
        publication_date="1995-11-10",
        keywords=["prevención", "riesgos laborales", "seguridad", "salud laboral"],
    ),
    LegalLaw(
        boe_id="BOE-A-2015-11724",
        title="Real Decreto Legislativo 5/2000, de 4 de agosto, por el que se aprueba el texto refundido de la Ley sobre Infracciones y Sanciones en el Orden Social",
        short_name="LISOS",
        domain=LegalDomain.LABOR,
        publication_date="2000-08-08",
        keywords=["infracciones", "sanciones", "laboral", "inspección trabajo"],
    ),
    LegalLaw(
        boe_id="BOE-A-2007-6115",
        title="Ley Orgánica 3/2007, de 22 de marzo, para la igualdad efectiva de mujeres y hombres",
        short_name="Ley de Igualdad",
        domain=LegalDomain.LABOR,
        publication_date="2007-03-23",
        keywords=["igualdad", "género", "discriminación", "conciliación"],
    ),
    LegalLaw(
        boe_id="BOE-A-2007-13409",
        title="Ley 20/2007, de 11 de julio, del Estatuto del trabajo autónomo",
        short_name="LETA",
        domain=LegalDomain.LABOR,
        publication_date="2007-07-12",
        keywords=["autónomo", "freelance", "trabajador independiente"],
    ),
    LegalLaw(
        boe_id="BOE-A-2015-11723",
        title="Real Decreto Legislativo 8/2015, de 30 de octubre, por el que se aprueba el texto refundido de la Ley General de la Seguridad Social",
        short_name="LGSS",
        domain=LegalDomain.LABOR,
        publication_date="2015-10-31",
        keywords=["seguridad social", "cotización", "pensiones", "prestaciones"],
    ),

    # FISCAL
    LegalLaw(
        boe_id="BOE-A-2003-23186",
        title="Ley 58/2003, de 17 de diciembre, General Tributaria",
        short_name="LGT",
        domain=LegalDomain.FISCAL,
        publication_date="2003-12-18",
        keywords=["tributario", "impuestos", "hacienda", "obligaciones fiscales"],
    ),
    LegalLaw(
        boe_id="BOE-A-2006-20764",
        title="Ley 35/2006, de 28 de noviembre, del Impuesto sobre la Renta de las Personas Físicas",
        short_name="LIRPF",
        domain=LegalDomain.FISCAL,
        publication_date="2006-11-29",
        keywords=["irpf", "renta", "personas físicas", "declaración"],
    ),
    LegalLaw(
        boe_id="BOE-A-2014-12328",
        title="Ley 27/2014, de 27 de noviembre, del Impuesto sobre Sociedades",
        short_name="LIS",
        domain=LegalDomain.FISCAL,
        publication_date="2014-11-28",
        keywords=["impuesto sociedades", "empresas", "beneficios"],
    ),
    LegalLaw(
        boe_id="BOE-A-1992-28740",
        title="Ley 37/1992, de 28 de diciembre, del Impuesto sobre el Valor Añadido",
        short_name="LIVA",
        domain=LegalDomain.FISCAL,
        publication_date="1992-12-29",
        keywords=["iva", "valor añadido", "factura", "impuesto indirecto"],
    ),
    LegalLaw(
        boe_id="BOE-A-2012-14696",
        title="Real Decreto 1619/2012, de 30 de noviembre, por el que se aprueba el Reglamento por el que se regulan las obligaciones de facturación",
        short_name="Reglamento Facturación",
        domain=LegalDomain.FISCAL,
        publication_date="2012-12-01",
        keywords=["factura", "facturación", "requisitos factura"],
    ),

    # PROTECCIÓN DE DATOS
    LegalLaw(
        boe_id="BOE-A-2018-16673",
        title="Ley Orgánica 3/2018, de 5 de diciembre, de Protección de Datos Personales y garantía de los derechos digitales",
        short_name="LOPDGDD",
        domain=LegalDomain.PRIVACY,
        publication_date="2018-12-06",
        keywords=["protección datos", "privacidad", "rgpd", "derechos digitales"],
    ),

    # MERCANTIL
    LegalLaw(
        boe_id="BOE-A-2010-10544",
        title="Real Decreto Legislativo 1/2010, de 2 de julio, por el que se aprueba el texto refundido de la Ley de Sociedades de Capital",
        short_name="LSC",
        domain=LegalDomain.MERCANTILE,
        publication_date="2010-07-03",
        keywords=["sociedades", "capital", "SA", "SL", "acciones", "participaciones"],
    ),
    LegalLaw(
        boe_id="BOE-A-1885-6627",
        title="Real Decreto de 22 de agosto de 1885 por el que se publica el Código de Comercio",
        short_name="CCom",
        domain=LegalDomain.MERCANTILE,
        publication_date="1885-10-16",
        keywords=["comercio", "mercantil", "comerciantes", "contratos mercantiles"],
    ),
    LegalLaw(
        boe_id="BOE-A-2007-5909",
        title="Ley 2/2007, de 15 de marzo, de sociedades profesionales",
        short_name="LSP",
        domain=LegalDomain.MERCANTILE,
        publication_date="2007-03-16",
        keywords=["sociedades profesionales", "profesionales liberales"],
    ),

    # CIVIL
    LegalLaw(
        boe_id="BOE-A-1889-4763",
        title="Real Decreto de 24 de julio de 1889 por el que se publica el Código Civil",
        short_name="CC",
        domain=LegalDomain.CIVIL,
        publication_date="1889-07-25",
        keywords=["civil", "contratos", "obligaciones", "familia", "sucesiones"],
    ),
    LegalLaw(
        boe_id="BOE-A-2000-323",
        title="Ley 1/2000, de 7 de enero, de Enjuiciamiento Civil",
        short_name="LEC",
        domain=LegalDomain.CIVIL,
        publication_date="2000-01-08",
        keywords=["procesal civil", "demanda", "juicio", "ejecución"],
    ),

    # ADMINISTRATIVO
    LegalLaw(
        boe_id="BOE-A-2015-10565",
        title="Ley 39/2015, de 1 de octubre, del Procedimiento Administrativo Común de las Administraciones Públicas",
        short_name="LPACAP",
        domain=LegalDomain.ADMINISTRATIVE,
        publication_date="2015-10-02",
        keywords=["procedimiento administrativo", "administración", "recursos"],
    ),
    LegalLaw(
        boe_id="BOE-A-2015-10566",
        title="Ley 40/2015, de 1 de octubre, de Régimen Jurídico del Sector Público",
        short_name="LRJSP",
        domain=LegalDomain.ADMINISTRATIVE,
        publication_date="2015-10-02",
        keywords=["sector público", "administración", "responsabilidad patrimonial"],
    ),
    LegalLaw(
        boe_id="BOE-A-2017-12902",
        title="Ley 9/2017, de 8 de noviembre, de Contratos del Sector Público",
        short_name="LCSP",
        domain=LegalDomain.ADMINISTRATIVE,
        publication_date="2017-11-09",
        keywords=["contratos públicos", "licitación", "sector público"],
    ),

    # COMPLIANCE
    LegalLaw(
        boe_id="BOE-A-2010-6737",
        title="Ley 10/2010, de 28 de abril, de prevención del blanqueo de capitales y de la financiación del terrorismo",
        short_name="LPBC",
        domain=LegalDomain.COMPLIANCE,
        publication_date="2010-04-29",
        keywords=["blanqueo capitales", "AML", "compliance", "KYC"],
    ),
    LegalLaw(
        boe_id="BOE-A-1995-25444",
        title="Ley Orgánica 10/1995, de 23 de noviembre, del Código Penal",
        short_name="CP",
        domain=LegalDomain.COMPLIANCE,
        publication_date="1995-11-24",
        keywords=["penal", "delito", "responsabilidad penal personas jurídicas"],
    ),
    LegalLaw(
        boe_id="BOE-A-2020-11218",
        title="Real Decreto Legislativo 1/2020, de 5 de mayo, por el que se aprueba el texto refundido de la Ley Concursal",
        short_name="LC",
        domain=LegalDomain.COMPLIANCE,
        publication_date="2020-05-07",
        keywords=["concursal", "insolvencia", "quiebra", "reestructuración"],
    ),
    LegalLaw(
        boe_id="BOE-A-2019-2364",
        title="Ley 1/2019, de 20 de febrero, de Secretos Empresariales",
        short_name="LSE",
        domain=LegalDomain.COMPLIANCE,
        publication_date="2019-02-21",
        keywords=["secretos empresariales", "información confidencial", "know-how"],
    ),
    LegalLaw(
        boe_id="BOE-A-2015-8147",
        title="Ley 22/2015, de 20 de julio, de Auditoría de Cuentas",
        short_name="LAC",
        domain=LegalDomain.COMPLIANCE,
        publication_date="2015-07-21",
        keywords=["auditoría", "cuentas anuales", "informe auditor"],
    ),

    # PROPIEDAD INTELECTUAL
    LegalLaw(
        boe_id="BOE-A-1996-8930",
        title="Real Decreto Legislativo 1/1996, de 12 de abril, por el que se aprueba el texto refundido de la Ley de Propiedad Intelectual",
        short_name="LPI",
        domain=LegalDomain.IP,
        publication_date="1996-04-22",
        keywords=["propiedad intelectual", "derechos autor", "copyright"],
    ),
    LegalLaw(
        boe_id="BOE-A-2001-23093",
        title="Ley 17/2001, de 7 de diciembre, de Marcas",
        short_name="LM",
        domain=LegalDomain.IP,
        publication_date="2001-12-08",
        keywords=["marcas", "registro marca", "signos distintivos"],
    ),
    LegalLaw(
        boe_id="BOE-A-2015-11929",
        title="Ley 24/2015, de 24 de julio, de Patentes",
        short_name="LP",
        domain=LegalDomain.IP,
        publication_date="2015-07-25",
        keywords=["patentes", "invenciones", "propiedad industrial"],
    ),

    # EDUCACIÓN
    LegalLaw(
        boe_id="BOE-A-2006-7899",
        title="Ley Orgánica 2/2006, de 3 de mayo, de Educación",
        short_name="LOE",
        domain=LegalDomain.EDUCATION,
        publication_date="2006-05-04",
        keywords=["educación", "enseñanza", "escolar", "centros educativos", "profesorado", "alumnado"],
    ),
    LegalLaw(
        boe_id="BOE-A-2020-17264",
        title="Ley Orgánica 3/2020, de 29 de diciembre, por la que se modifica la Ley Orgánica 2/2006, de 3 de mayo, de Educación",
        short_name="LOMLOE",
        domain=LegalDomain.EDUCATION,
        publication_date="2020-12-30",
        keywords=["educación", "LOMLOE", "reforma educativa", "currículo", "evaluación"],
    ),
    LegalLaw(
        boe_id="BOE-A-2023-7500",
        title="Ley Orgánica 2/2023, de 22 de marzo, del Sistema Universitario",
        short_name="LOSU",
        domain=LegalDomain.EDUCATION,
        publication_date="2023-03-23",
        keywords=["universidad", "universitario", "grado", "máster", "doctorado", "investigación"],
    ),
    LegalLaw(
        boe_id="BOE-A-2022-5139",
        title="Real Decreto 243/2022, de 5 de abril, por el que se establecen la ordenación y las enseñanzas mínimas del Bachillerato",
        short_name="RD Bachillerato",
        domain=LegalDomain.EDUCATION,
        publication_date="2022-04-06",
        keywords=["bachillerato", "enseñanza secundaria", "currículo", "materias"],
    ),
    LegalLaw(
        boe_id="BOE-A-2022-4975",
        title="Real Decreto 217/2022, de 29 de marzo, por el que se establece la ordenación y las enseñanzas mínimas de la Educación Secundaria Obligatoria",
        short_name="RD ESO",
        domain=LegalDomain.EDUCATION,
        publication_date="2022-03-30",
        keywords=["ESO", "secundaria obligatoria", "currículo", "competencias", "evaluación"],
    ),
    LegalLaw(
        boe_id="BOE-A-1985-12978",
        title="Ley Orgánica 8/1985, de 3 de julio, reguladora del Derecho a la Educación",
        short_name="LODE",
        domain=LegalDomain.EDUCATION,
        publication_date="1985-07-04",
        keywords=["derecho educación", "libertad enseñanza", "centros concertados", "participación"],
    ),
    LegalLaw(
        boe_id="BOE-A-2022-2296",
        title="Real Decreto 95/2022, de 1 de febrero, por el que se establece la ordenación y las enseñanzas mínimas de la Educación Infantil",
        short_name="RD Infantil",
        domain=LegalDomain.EDUCATION,
        publication_date="2022-02-02",
        keywords=["educación infantil", "preescolar", "primer ciclo", "segundo ciclo"],
    ),

    # COMERCIO Y CONSUMIDORES
    LegalLaw(
        boe_id="BOE-A-2007-20555",
        title="Real Decreto Legislativo 1/2007, de 16 de noviembre, por el que se aprueba el texto refundido de la Ley General para la Defensa de los Consumidores y Usuarios",
        short_name="LGDCU",
        domain=LegalDomain.COMMERCE,
        publication_date="2007-11-30",
        keywords=["consumidores", "usuarios", "derechos consumidor", "garantías"],
    ),
    LegalLaw(
        boe_id="BOE-A-1991-628",
        title="Ley 3/1991, de 10 de enero, de Competencia Desleal",
        short_name="LCD",
        domain=LegalDomain.COMMERCE,
        publication_date="1991-01-11",
        keywords=["competencia desleal", "publicidad engañosa", "prácticas desleales"],
    ),
    LegalLaw(
        boe_id="BOE-A-2002-13758",
        title="Ley 34/2002, de 11 de julio, de servicios de la sociedad de la información y de comercio electrónico",
        short_name="LSSI",
        domain=LegalDomain.COMMERCE,
        publication_date="2002-07-12",
        keywords=["comercio electrónico", "internet", "cookies", "LSSI"],
    ),

    # INMOBILIARIO
    LegalLaw(
        boe_id="BOE-A-1994-26003",
        title="Ley 29/1994, de 24 de noviembre, de Arrendamientos Urbanos",
        short_name="LAU",
        domain=LegalDomain.REAL_ESTATE,
        publication_date="1994-11-25",
        keywords=["arrendamiento", "alquiler", "vivienda", "local comercial"],
    ),
    LegalLaw(
        boe_id="BOE-A-1960-10906",
        title="Ley 49/1960, de 21 de julio, sobre propiedad horizontal",
        short_name="LPH",
        domain=LegalDomain.REAL_ESTATE,
        publication_date="1960-07-23",
        keywords=["propiedad horizontal", "comunidad propietarios", "elementos comunes"],
    ),
    LegalLaw(
        boe_id="BOE-A-1946-2453",
        title="Decreto de 8 de febrero de 1946 por el que se aprueba la nueva redacción oficial de la Ley Hipotecaria",
        short_name="LH",
        domain=LegalDomain.REAL_ESTATE,
        publication_date="1946-02-27",
        keywords=["hipoteca", "registro propiedad", "inscripción"],
    ),
]

# Key articles for each law (structural info only, not content!)
KEY_ARTICLES = {
    "BOE-A-2015-11430": [  # ET
        ("34", "Jornada", "Límites de jornada laboral: máximo 40h/semana"),
        ("35", "Horas extraordinarias", "Máximo 80h/año, compensación obligatoria"),
        ("38", "Vacaciones", "Mínimo 30 días naturales al año"),
        ("14", "Período de prueba", "Duración máxima según categoría"),
        ("52", "Extinción por causas objetivas", "Causas de despido objetivo"),
        ("54", "Despido disciplinario", "Causas de despido disciplinario"),
        ("56", "Despido improcedente", "Indemnización por despido improcedente"),
    ],
    "BOE-A-2018-16673": [  # LOPDGDD
        ("5", "Deber de confidencialidad", "Obligación de secreto de datos personales"),
        ("6", "Tratamiento basado en consentimiento", "Requisitos del consentimiento"),
        ("13", "Derechos de los afectados", "Información, acceso, rectificación, supresión"),
        ("28", "Obligaciones generales del responsable", "Accountability, DPO"),
        ("89", "Derecho a la desconexión digital", "Límites al uso de dispositivos"),
    ],
    "BOE-A-1992-28740": [  # IVA
        ("4", "Hecho imponible", "Operaciones sujetas a IVA"),
        ("20", "Exenciones interiores", "Operaciones exentas de IVA"),
        ("90", "Tipo impositivo general", "21% tipo general"),
        ("91", "Tipos reducidos", "10% y 4% tipos reducidos"),
    ],
}


async def seed_laws(domain: str = None, force: bool = False) -> None:
    """Seed the legal knowledge graph with Spanish laws."""

    logger.info("🚀 Starting legal knowledge graph seeding...")

    await legal_graph.initialize()

    # Filter by domain if specified
    laws_to_seed = SPANISH_LAWS
    if domain:
        try:
            target_domain = LegalDomain(domain)
            laws_to_seed = [l for l in SPANISH_LAWS if l.domain == target_domain]
            logger.info(f"📂 Filtering to domain: {domain} ({len(laws_to_seed)} laws)")
        except ValueError:
            logger.warning(f"Unknown domain: {domain}, seeding all laws")

    # Seed laws (always upsert via MERGE — safe to re-run)
    success_count = 0
    for law in laws_to_seed:
        success = await legal_graph.add_law(law)
        if success:
            success_count += 1

    logger.info(f"✅ Seeded {success_count}/{len(laws_to_seed)} laws")

    # Print stats
    stats = await legal_graph.get_graph_stats()
    logger.info(f"📊 Graph stats: {stats}")


async def main():
    parser = argparse.ArgumentParser(description="Seed legal knowledge graph")
    parser.add_argument("--domain", type=str, help="Only seed specific domain")
    parser.add_argument("--force", action="store_true", help="Force update existing")

    args = parser.parse_args()

    await seed_laws(domain=args.domain, force=args.force)


if __name__ == "__main__":
    asyncio.run(main())
