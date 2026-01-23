#!/usr/bin/env python3
"""
BOE Legislation Downloader - Script completo para descargar legislación consolidada del BOE

Funcionalidades:
- Descarga legislación por ID (BOE-A-XXXX-XXXXX)
- Extrae texto consolidado completo con todos los artículos
- Guarda metadatos completos (materias, análisis, versiones, ELI)
- Indexa automáticamente en el conocimiento público de Weaviate
- Soporta descarga masiva de legislación importante

Uso:
    # Descargar una ley específica
    python boe_legislation_downloader.py --id BOE-A-2015-11430

    # Descargar varias leyes importantes
    python boe_legislation_downloader.py --preset laboral
    python boe_legislation_downloader.py --preset educacion
    python boe_legislation_downloader.py --preset proteccion_datos

    # Listar legislación disponible
    python boe_legislation_downloader.py --list --limit 50

    # Solo descargar sin indexar
    python boe_legislation_downloader.py --id BOE-A-2015-11430 --no-index

API del BOE:
    https://www.boe.es/datosabiertos/api/legislacion-consolidada
    Documentación: https://www.boe.es/datosabiertos/documentos/APIconsolidada.pdf
"""

import argparse
import asyncio
import httpx
import json
import logging
import sys
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Añadir path para imports del proyecto
sys.path.insert(0, str(Path(__file__).parent.parent))


@dataclass
class LegislationDocument:
    """Representa un documento de legislación consolidada del BOE"""
    id: str
    title: str
    content: str
    summary: str = ""

    # Metadatos básicos
    rango: str = ""  # Ley, Real Decreto, etc.
    ambito: str = ""  # Estatal, Autonómico
    departamento: str = ""
    fecha_disposicion: Optional[datetime] = None
    fecha_publicacion: Optional[datetime] = None
    fecha_vigencia: Optional[datetime] = None
    numero_oficial: str = ""

    # Estado
    estatus_derogacion: str = "N"
    estatus_consolidacion: str = ""
    vigencia_agotada: str = "N"

    # URLs
    url_eli: str = ""
    url_html: str = ""
    url_pdf: str = ""

    # Análisis
    materias: List[str] = field(default_factory=list)
    notas: List[str] = field(default_factory=list)
    referencias_anteriores: List[str] = field(default_factory=list)
    referencias_posteriores: List[str] = field(default_factory=list)

    # Texto estructurado
    bloques: List[Dict[str, str]] = field(default_factory=list)


class BOELegislationDownloader:
    """Descargador de legislación consolidada del BOE"""

    BASE_URL = "https://www.boe.es/datosabiertos/api"

    # Presets de legislación importante por categoría
    PRESETS = {
        "laboral": [
            "BOE-A-2015-11430",  # Estatuto de los Trabajadores
            "BOE-A-2020-11043",  # Ley de Trabajo a Distancia
            "BOE-A-1995-24292",  # Ley de Prevención de Riesgos Laborales
            "BOE-A-2015-11724",  # LISOS (Infracciones y Sanciones)
            "BOE-A-2007-6115",   # Ley de Igualdad (LO 3/2007)
            "BOE-A-2007-13409",  # Estatuto del Trabajo Autónomo (LETA)
            "BOE-A-2015-11723",  # Ley General de la Seguridad Social
        ],
        "proteccion_datos": [
            "BOE-A-2018-16673",  # LOPDGDD
            "BOE-A-1999-23750",  # LOPD (derogada pero referencia histórica)
        ],
        "educacion": [
            "BOE-A-2020-17264",  # LOMLOE (Ley de Educación)
            "BOE-A-2013-12886",  # LOMCE
            "BOE-A-2006-7899",   # LOE
            "BOE-A-2001-24515",  # LOU (Universidades)
            "BOE-A-2022-5139",   # Ley de Convivencia Universitaria
        ],
        "civil": [
            "BOE-A-1889-4763",   # Código Civil
            "BOE-A-2000-323",    # LEC (Ley de Enjuiciamiento Civil)
        ],
        "mercantil": [
            "BOE-A-2010-10544",  # Ley de Sociedades de Capital
            "BOE-A-1885-6627",   # Código de Comercio
            "BOE-A-2007-5909",   # Ley de Sociedades Profesionales
        ],
        "fiscal": [
            "BOE-A-2003-23186",  # Ley General Tributaria (LGT)
            "BOE-A-2006-20764",  # Ley del IRPF
            "BOE-A-2014-12328",  # Ley del Impuesto sobre Sociedades
            "BOE-A-1992-28740",  # Ley del IVA
            "BOE-A-2012-14696",  # Reglamento de Facturación
        ],
        "administrativo": [
            "BOE-A-2015-10565",  # LPACAP
            "BOE-A-2015-10566",  # LRJSP
            "BOE-A-2017-12902",  # Ley de Contratos del Sector Público
        ],
        # === NUEVOS PRESETS PARA EMPRESAS ===
        "compliance": [
            "BOE-A-2010-6737",   # Ley de Prevención del Blanqueo de Capitales (LPBC)
            "BOE-A-1995-25444",  # Código Penal (responsabilidad personas jurídicas)
            "BOE-A-2020-11218",  # Ley Concursal (insolvencia)
            "BOE-A-2019-2364",   # Ley de Secretos Empresariales
            "BOE-A-2015-8147",   # Ley de Auditoría de Cuentas
        ],
        "propiedad_intelectual": [
            "BOE-A-1996-8930",   # Ley de Propiedad Intelectual (LPI)
            "BOE-A-2001-23093",  # Ley de Marcas
            "BOE-A-2015-11929",  # Ley de Patentes
        ],
        "comercio_consumidores": [
            "BOE-A-2007-20555",  # LGDCU (Consumidores y Usuarios)
            "BOE-A-1991-628",    # Ley de Competencia Desleal (LCD)
            "BOE-A-1996-1072",   # Ley de Ordenación del Comercio Minorista (LOCM)
            "BOE-A-2013-12888",  # Ley de Garantía de la Unidad de Mercado (LGUM)
            "BOE-A-2002-13758",  # Ley de Servicios de la Sociedad de la Información (LSSI)
        ],
        "emprendimiento": [
            "BOE-A-2013-10074",  # Ley de Emprendedores
            "BOE-A-2022-15818",  # Ley Crea y Crece (factura electrónica B2B)
            "BOE-A-2022-23042",  # Ley de Startups
        ],
        "inmobiliario": [
            "BOE-A-1994-26003",  # Ley de Arrendamientos Urbanos (LAU)
            "BOE-A-2019-6635",   # Reforma LAU 2019 (vivienda)
            "BOE-A-1960-10906",  # Ley de Propiedad Horizontal
            "BOE-A-1946-2453",   # Ley Hipotecaria
            "BOE-A-2019-3814",   # Ley de Crédito Inmobiliario
        ],
        "contabilidad": [
            "BOE-A-2007-19884",  # Plan General de Contabilidad
            "BOE-A-2007-19966",  # PGC Pymes
        ],
    }

    def __init__(self, weaviate_url: str = None, api_key: str = None):
        self.weaviate_url = weaviate_url or "http://localhost:8007"
        self.api_key = api_key or "dev_microservice_key_12345"
        self.headers_xml = {
            'Accept': 'application/xml',
            'User-Agent': 'NouxCubeIA-BOE-Downloader/1.0'
        }
        self.headers_json = {
            'Accept': 'application/json',
            'User-Agent': 'NouxCubeIA-BOE-Downloader/1.0'
        }

    async def download_legislation(self, boe_id: str) -> Optional[LegislationDocument]:
        """Descarga una ley completa por su ID del BOE"""
        logger.info(f"Descargando legislación: {boe_id}")

        async with httpx.AsyncClient(timeout=120.0, follow_redirects=True) as client:
            # 1. Obtener metadatos principales
            doc = await self._fetch_metadata(client, boe_id)
            if not doc:
                return None

            # 2. Obtener análisis (materias, notas, referencias)
            await self._fetch_analysis(client, boe_id, doc)

            # 3. Obtener texto consolidado completo
            await self._fetch_full_text(client, boe_id, doc)

            logger.info(f"✅ Descargado: {doc.title[:60]}... ({len(doc.content)} chars)")
            return doc

    async def _fetch_metadata(self, client: httpx.AsyncClient, boe_id: str) -> Optional[LegislationDocument]:
        """Obtiene los metadatos principales de la legislación"""
        url = f"{self.BASE_URL}/legislacion-consolidada/id/{boe_id}"

        try:
            response = await client.get(url, headers=self.headers_xml)
            if response.status_code != 200:
                logger.error(f"Error obteniendo metadatos de {boe_id}: {response.status_code}")
                return None

            root = ET.fromstring(response.text)
            data = root.find('.//data')
            if data is None:
                return None

            metadatos = data.find('.//metadatos')
            if metadatos is None:
                return None

            def get_text(elem, tag: str, default: str = "") -> str:
                el = elem.find(f'.//{tag}')
                return el.text if el is not None and el.text else default

            def parse_date(date_str: str) -> Optional[datetime]:
                if not date_str or len(date_str) < 8:
                    return None
                try:
                    return datetime.strptime(date_str[:8], "%Y%m%d")
                except:
                    return None

            doc = LegislationDocument(
                id=boe_id,
                title=get_text(metadatos, 'titulo'),
                content="",  # Se llenará después
                rango=get_text(metadatos, 'rango'),
                ambito=get_text(metadatos, 'ambito'),
                departamento=get_text(metadatos, 'departamento'),
                fecha_disposicion=parse_date(get_text(metadatos, 'fecha_disposicion')),
                fecha_publicacion=parse_date(get_text(metadatos, 'fecha_publicacion')),
                fecha_vigencia=parse_date(get_text(metadatos, 'fecha_vigencia')),
                numero_oficial=get_text(metadatos, 'numero_oficial'),
                estatus_derogacion=get_text(metadatos, 'estatus_derogacion', 'N'),
                estatus_consolidacion=get_text(metadatos, 'estado_consolidacion'),
                vigencia_agotada=get_text(metadatos, 'vigencia_agotada', 'N'),
                url_eli=get_text(metadatos, 'url_eli'),
                url_html=get_text(metadatos, 'url_html_consolidada'),
            )

            return doc

        except Exception as e:
            logger.error(f"Error parseando metadatos de {boe_id}: {e}")
            return None

    async def _fetch_analysis(self, client: httpx.AsyncClient, boe_id: str, doc: LegislationDocument):
        """Obtiene el análisis jurídico (materias, notas, referencias)"""
        url = f"{self.BASE_URL}/legislacion-consolidada/id/{boe_id}/analisis"

        try:
            response = await client.get(url, headers=self.headers_xml)
            if response.status_code != 200:
                return

            root = ET.fromstring(response.text)

            # Materias
            materias = root.findall('.//materias/materia')
            doc.materias = [m.text for m in materias if m.text]

            # Notas
            notas = root.findall('.//notas/nota')
            doc.notas = [n.text for n in notas if n.text]

            # Referencias anteriores
            refs_ant = root.findall('.//referencias/anteriores/anterior')
            doc.referencias_anteriores = [r.text for r in refs_ant if r.text]

            # Referencias posteriores
            refs_post = root.findall('.//referencias/posteriores/posterior')
            doc.referencias_posteriores = [r.text for r in refs_post if r.text]

        except Exception as e:
            logger.warning(f"Error obteniendo análisis de {boe_id}: {e}")

    async def _fetch_full_text(self, client: httpx.AsyncClient, boe_id: str, doc: LegislationDocument):
        """Obtiene el texto consolidado completo"""
        url = f"{self.BASE_URL}/legislacion-consolidada/id/{boe_id}/texto"

        try:
            response = await client.get(url, headers=self.headers_xml)
            if response.status_code != 200:
                logger.warning(f"No se pudo obtener texto de {boe_id}: {response.status_code}")
                return

            root = ET.fromstring(response.text)
            bloques = root.findall('.//bloque')

            all_text = []
            for bloque in bloques:
                version = bloque.find('.//version')
                if version is not None:
                    # Extraer todos los párrafos
                    paragraphs = version.findall('.//p')
                    bloque_text = "\n".join([p.text for p in paragraphs if p.text])
                    if bloque_text.strip():
                        all_text.append(bloque_text)
                        doc.bloques.append({
                            'text': bloque_text,
                        })

            doc.content = "\n\n".join(all_text)

            # Generar resumen (primeros párrafos)
            if doc.content:
                summary_parts = doc.content[:2000].split('\n')[:5]
                doc.summary = " ".join(summary_parts)

        except Exception as e:
            logger.error(f"Error obteniendo texto de {boe_id}: {e}")

    async def list_legislation(self, limit: int = 50, offset: int = 0) -> List[Dict[str, Any]]:
        """Lista la legislación consolidada disponible"""
        url = f"{self.BASE_URL}/legislacion-consolidada?limit={limit}&offset={offset}"

        async with httpx.AsyncClient(timeout=60.0) as client:
            try:
                response = await client.get(url, headers=self.headers_xml)
                if response.status_code != 200:
                    logger.error(f"Error listando legislación: {response.status_code}")
                    return []

                root = ET.fromstring(response.text)
                items = root.findall('.//item')

                results = []
                for item in items:
                    def get_text(tag: str) -> str:
                        el = item.find(f'.//{tag}')
                        return el.text if el is not None and el.text else ""

                    results.append({
                        'id': get_text('identificador'),
                        'titulo': get_text('titulo'),
                        'rango': get_text('rango'),
                        'ambito': get_text('ambito'),
                        'fecha_publicacion': get_text('fecha_publicacion'),
                    })

                return results

            except Exception as e:
                logger.error(f"Error listando legislación: {e}")
                return []

    async def index_to_weaviate(self, doc: LegislationDocument) -> bool:
        """Indexa un documento en el conocimiento público de Weaviate"""
        try:
            # Importar servicio interno si está disponible
            try:
                from app.services.public_knowledge_service import public_knowledge_service
                from app.schemas.public_knowledge import (
                    PublicDocumentCreate,
                    PublicDocumentCategory,
                    Jurisdiction
                )
                use_internal = True
            except ImportError:
                use_internal = False

            # Determinar categoría basada en materias
            category = self._determine_category(doc)

            # Preparar keywords basados en materias y título
            keywords = list(doc.materias[:10])
            keywords.extend(doc.title.split()[:5])

            if use_internal:
                # Usar servicio interno directamente
                await public_knowledge_service.initialize()

                # Mapear categoría a enum
                category_enum = PublicDocumentCategory.LEGISLATION
                if category == "regulation":
                    category_enum = PublicDocumentCategory.REGULATION
                elif category == "jurisprudence":
                    category_enum = PublicDocumentCategory.JURISPRUDENCE
                elif category == "treaty":
                    category_enum = PublicDocumentCategory.TREATY

                document = PublicDocumentCreate(
                    title=doc.title,
                    content=doc.content[:100000],  # Limitar tamaño
                    summary=doc.summary[:1000] if doc.summary else doc.title[:500],
                    category=category_enum,
                    jurisdiction=Jurisdiction.SPAIN,
                    legal_reference=doc.id,
                    source_url=doc.url_html or doc.url_eli,
                    source_name="BOE",
                    keywords=keywords,
                    topics=doc.materias[:5],
                    verified=True,
                    version="1.0",
                    version_number=1,
                    is_current_version=True,
                    modification_type="original",
                    legal_status="derogada" if doc.estatus_derogacion == "S" else "vigente",
                    boe_id=doc.id,
                    eli_uri=doc.url_eli,
                    publication_date=doc.fecha_publicacion,
                    effective_date=doc.fecha_vigencia,
                )

                await public_knowledge_service.add_document(document)
                logger.info(f"✅ Indexado en Weaviate (interno): {doc.id}")
                return True

            else:
                # Fallback: usar API HTTP
                document_data = {
                    "title": doc.title,
                    "content": doc.content[:100000],
                    "summary": doc.summary[:1000],
                    "category": category,
                    "jurisdiction": "es",
                    "legal_reference": doc.id,
                    "source_url": doc.url_html or doc.url_eli,
                    "source_name": "BOE",
                    "keywords": keywords,
                    "topics": doc.materias[:5],
                    "verified": True,
                    "version": "1.0",
                    "version_number": 1,
                    "is_current_version": True,
                    "modification_type": "original",
                    "legal_status": "derogada" if doc.estatus_derogacion == "S" else "vigente",
                    "boe_id": doc.id,
                    "eli_uri": doc.url_eli,
                }

                if doc.fecha_publicacion:
                    document_data["publication_date"] = doc.fecha_publicacion.isoformat() + "Z"
                if doc.fecha_vigencia:
                    document_data["effective_date"] = doc.fecha_vigencia.isoformat() + "Z"

                async with httpx.AsyncClient(timeout=60.0) as client:
                    response = await client.post(
                        f"{self.weaviate_url}/public-knowledge/documents",
                        headers={
                            "Content-Type": "application/json",
                            "Authorization": f"Bearer {self.api_key}"
                        },
                        json=document_data
                    )

                    if response.status_code in (200, 201):
                        logger.info(f"✅ Indexado en Weaviate (API): {doc.id}")
                        return True
                    else:
                        logger.error(f"❌ Error indexando {doc.id}: {response.status_code} - {response.text[:200]}")
                        return False

        except Exception as e:
            logger.error(f"❌ Error indexando {doc.id}: {e}")
            return False

    def _determine_category(self, doc: LegislationDocument) -> str:
        """Determina la categoría del documento basado en su rango"""
        rango = doc.rango.lower()

        if 'ley' in rango:
            return "legislation"
        elif 'decreto' in rango:
            return "legislation" if 'legislativo' in rango else "regulation"
        elif 'orden' in rango or 'resolución' in rango:
            return "regulation"
        elif 'sentencia' in rango or 'auto' in rango:
            return "jurisprudence"
        elif 'tratado' in rango or 'convenio' in rango:
            return "treaty"
        else:
            return "legislation"

    async def download_preset(self, preset_name: str, index: bool = True) -> List[LegislationDocument]:
        """Descarga un conjunto predefinido de legislación"""
        if preset_name not in self.PRESETS:
            logger.error(f"Preset '{preset_name}' no encontrado. Disponibles: {list(self.PRESETS.keys())}")
            return []

        ids = self.PRESETS[preset_name]
        logger.info(f"Descargando preset '{preset_name}': {len(ids)} documentos")

        documents = []
        for boe_id in ids:
            doc = await self.download_legislation(boe_id)
            if doc:
                documents.append(doc)
                if index:
                    await self.index_to_weaviate(doc)
                # Pequeña pausa para no saturar el servidor
                await asyncio.sleep(1)

        logger.info(f"✅ Descargados {len(documents)}/{len(ids)} documentos del preset '{preset_name}'")
        return documents

    async def download_all_presets(self, index: bool = True) -> Dict[str, List[LegislationDocument]]:
        """Descarga todos los presets disponibles"""
        results = {}
        for preset_name in self.PRESETS:
            results[preset_name] = await self.download_preset(preset_name, index)
            await asyncio.sleep(2)  # Pausa entre presets
        return results


async def main():
    parser = argparse.ArgumentParser(
        description="Descarga legislación consolidada del BOE",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Ejemplos:
  # Descargar una ley específica
  python boe_legislation_downloader.py --id BOE-A-2015-11430

  # Descargar preset de legislación laboral
  python boe_legislation_downloader.py --preset laboral

  # Descargar todos los presets
  python boe_legislation_downloader.py --preset all

  # Listar legislación disponible
  python boe_legislation_downloader.py --list --limit 20

  # Solo descargar sin indexar en Weaviate
  python boe_legislation_downloader.py --id BOE-A-2015-11430 --no-index

Presets disponibles:
  - laboral: Estatuto de los Trabajadores, PRL, Ley de Igualdad, LETA, etc.
  - proteccion_datos: LOPDGDD
  - educacion: LOMLOE, LOE, LOU
  - civil: Código Civil, LEC
  - mercantil: Ley de Sociedades de Capital, Código de Comercio, Sociedades Profesionales
  - fiscal: LGT, IRPF, IS, IVA, Reglamento de Facturación
  - administrativo: LPACAP, LRJSP, Contratos del Sector Público
  - compliance: Blanqueo de Capitales, Código Penal, Ley Concursal, Secretos Empresariales
  - propiedad_intelectual: LPI, Marcas, Patentes
  - comercio_consumidores: LGDCU, Competencia Desleal, LOCM, LSSI
  - emprendimiento: Ley de Emprendedores, Crea y Crece, Ley de Startups
  - inmobiliario: LAU, Propiedad Horizontal, Ley Hipotecaria, Crédito Inmobiliario
  - contabilidad: Plan General Contabilidad, PGC Pymes
        """
    )

    parser.add_argument('--id', help='ID del BOE a descargar (ej: BOE-A-2015-11430)')
    parser.add_argument('--preset', help='Preset de legislación a descargar (laboral, educacion, etc.)')
    parser.add_argument('--list', action='store_true', help='Listar legislación disponible')
    parser.add_argument('--limit', type=int, default=50, help='Límite de resultados (default: 50)')
    parser.add_argument('--no-index', action='store_true', help='No indexar en Weaviate')
    parser.add_argument('--weaviate-url', default='http://localhost:8007', help='URL del servicio Weaviate')
    parser.add_argument('--output', help='Archivo JSON para guardar resultados')

    args = parser.parse_args()

    downloader = BOELegislationDownloader(weaviate_url=args.weaviate_url)

    if args.list:
        # Listar legislación disponible
        print(f"Listando legislación del BOE (limit={args.limit})...")
        results = await downloader.list_legislation(limit=args.limit)

        print(f"\n{'='*80}")
        print(f"{'ID':<25} {'Rango':<25} {'Título':<30}")
        print(f"{'='*80}")

        for r in results:
            titulo_short = r['titulo'][:28] + '...' if len(r['titulo']) > 30 else r['titulo']
            print(f"{r['id']:<25} {r['rango'][:23]:<25} {titulo_short}")

        print(f"\nTotal: {len(results)} documentos")

    elif args.preset:
        # Descargar preset
        if args.preset == 'all':
            results = await downloader.download_all_presets(index=not args.no_index)
            for preset_name, docs in results.items():
                print(f"\n{preset_name}: {len(docs)} documentos descargados")
        else:
            documents = await downloader.download_preset(args.preset, index=not args.no_index)
            print(f"\nDescargados {len(documents)} documentos del preset '{args.preset}'")

            if args.output:
                with open(args.output, 'w', encoding='utf-8') as f:
                    json.dump([{
                        'id': d.id,
                        'title': d.title,
                        'content': d.content[:5000] + '...' if len(d.content) > 5000 else d.content,
                        'materias': d.materias,
                        'rango': d.rango,
                    } for d in documents], f, ensure_ascii=False, indent=2)
                print(f"Resultados guardados en {args.output}")

    elif args.id:
        # Descargar una ley específica
        doc = await downloader.download_legislation(args.id)

        if doc:
            print(f"\n{'='*80}")
            print(f"ID: {doc.id}")
            print(f"Título: {doc.title}")
            print(f"Rango: {doc.rango}")
            print(f"Departamento: {doc.departamento}")
            print(f"Fecha publicación: {doc.fecha_publicacion}")
            print(f"Materias: {', '.join(doc.materias[:5])}")
            print(f"Contenido: {len(doc.content)} caracteres")
            print(f"Bloques: {len(doc.bloques)}")
            print(f"{'='*80}")

            if not args.no_index:
                success = await downloader.index_to_weaviate(doc)
                if success:
                    print("✅ Documento indexado en Weaviate")

            if args.output:
                with open(args.output, 'w', encoding='utf-8') as f:
                    json.dump({
                        'id': doc.id,
                        'title': doc.title,
                        'content': doc.content,
                        'summary': doc.summary,
                        'materias': doc.materias,
                        'rango': doc.rango,
                        'departamento': doc.departamento,
                        'url_eli': doc.url_eli,
                        'fecha_publicacion': doc.fecha_publicacion.isoformat() if doc.fecha_publicacion else None,
                    }, f, ensure_ascii=False, indent=2)
                print(f"Documento guardado en {args.output}")
        else:
            print(f"❌ No se pudo descargar {args.id}")

    else:
        parser.print_help()


if __name__ == "__main__":
    asyncio.run(main())
