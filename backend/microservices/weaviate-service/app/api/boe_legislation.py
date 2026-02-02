"""
API endpoints for BOE Legislation Download and Management
Allows downloading Spanish legislation from BOE and indexing into public knowledge base.

Endpoints:
- GET /boe/presets - List available legislation presets
- GET /boe/legislation/{boe_id} - Get legislation info by BOE ID
- POST /boe/download - Download and index legislation by BOE ID
- POST /boe/download/preset - Download all legislation in a preset
- GET /boe/search - Search BOE for legislation
- POST /boe/sync/{boe_id} - Sync legislation and detect changes
- POST /boe/sync/preset/{preset_name} - Sync all legislation in a preset
- POST /boe/sync/all - Sync all tracked legislation
- GET /boe/updates - Get legislation with pending updates
- GET /boe/legislation/{boe_id}/versions - Get version history
- POST /boe/legislation/{boe_id}/compare - Compare two versions
"""
from fastapi import APIRouter, HTTPException, Depends, Query, BackgroundTasks
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from enum import Enum
import logging
import uuid

from app.core.security import verify_api_key

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/boe", tags=["boe-legislation"])


# =============================================================================
# Schemas
# =============================================================================

class BOEPresetCategory(str, Enum):
    """Available BOE legislation preset categories."""
    LABORAL = "laboral"
    PROTECCION_DATOS = "proteccion_datos"
    EDUCACION = "educacion"
    CIVIL = "civil"
    MERCANTIL = "mercantil"
    FISCAL = "fiscal"
    ADMINISTRATIVO = "administrativo"
    COMPLIANCE = "compliance"
    PROPIEDAD_INTELECTUAL = "propiedad_intelectual"
    COMERCIO_CONSUMIDORES = "comercio_consumidores"
    EMPRENDIMIENTO = "emprendimiento"
    INMOBILIARIO = "inmobiliario"
    CONTABILIDAD = "contabilidad"


class BOEDownloadRequest(BaseModel):
    """Request to download BOE legislation."""
    boe_id: str = Field(..., description="BOE identifier (e.g., BOE-A-2015-11430)")
    index_to_weaviate: bool = Field(True, description="Whether to index in Weaviate")


class BOEPresetDownloadRequest(BaseModel):
    """Request to download a preset of BOE legislation."""
    preset: BOEPresetCategory = Field(..., description="Preset category to download")
    index_to_weaviate: bool = Field(True, description="Whether to index in Weaviate")


class BOELegislationInfo(BaseModel):
    """Information about a BOE legislation document."""
    boe_id: str
    title: str
    rango: str = ""
    departamento: str = ""
    fecha_publicacion: Optional[str] = None
    fecha_vigencia: Optional[str] = None
    estatus_derogacion: str = "N"
    url_eli: str = ""
    url_html: str = ""
    materias: List[str] = []
    content_length: int = 0


class BOEDownloadResult(BaseModel):
    """Result of BOE legislation download."""
    success: bool
    boe_id: str
    title: Optional[str] = None
    indexed: bool = False
    error: Optional[str] = None


class BOEPresetInfo(BaseModel):
    """Information about a BOE preset."""
    name: str
    description: str
    legislation_count: int
    legislation_ids: List[str]


class BOESearchResult(BaseModel):
    """Result from BOE search."""
    boe_id: str
    titulo: str
    rango: str
    fecha_publicacion: str


class ChangeTypeEnum(str, Enum):
    """Type of change in legislation."""
    ADDED = "added"
    REMOVED = "removed"
    MODIFIED = "modified"
    RENUMBERED = "renumbered"
    DEROGATED = "derogated"


class ChangeSeverityEnum(str, Enum):
    """Severity of the change."""
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class ArticleChangeResponse(BaseModel):
    """Response model for article-level changes."""
    article_number: str
    article_title: Optional[str] = None
    change_type: ChangeTypeEnum
    severity: ChangeSeverityEnum
    old_text: Optional[str] = None
    new_text: Optional[str] = None
    diff_html: Optional[str] = None
    summary: Optional[str] = None


class SyncResultResponse(BaseModel):
    """Response model for sync operation."""
    boe_id: str
    title: str
    has_changes: bool
    old_version: Optional[int] = None
    new_version: Optional[int] = None
    article_changes: List[ArticleChangeResponse] = []
    sync_time: str
    change_summary: Optional[Dict[str, Any]] = None
    error: Optional[str] = None


class VersionHistoryResponse(BaseModel):
    """Response model for version history."""
    boe_id: str
    version_number: int
    version_date: str
    text_hash: str
    article_count: int
    metadata: Dict[str, Any] = {}
    modification_references: List[str] = []


class PendingUpdateResponse(BaseModel):
    """Response model for pending updates."""
    boe_id: str
    title: str
    stored_version: int
    has_new_references: bool


class VersionCompareRequest(BaseModel):
    """Request to compare two versions."""
    version1: int = Field(..., description="First version number")
    version2: int = Field(..., description="Second version number")


# =============================================================================
# Presets Definition (same as boe_legislation_downloader.py)
# =============================================================================

BOE_PRESETS = {
    BOEPresetCategory.LABORAL: {
        "description": "Legislación laboral: ET, PRL, LISOS, Igualdad, LETA, Seguridad Social",
        "ids": [
            "BOE-A-2015-11430",  # Estatuto de los Trabajadores
            "BOE-A-2020-11043",  # Ley de Trabajo a Distancia
            "BOE-A-1995-24292",  # Ley de Prevención de Riesgos Laborales
            "BOE-A-2015-11724",  # LISOS (Infracciones y Sanciones)
            "BOE-A-2007-6115",   # Ley de Igualdad (LO 3/2007)
            "BOE-A-2007-13409",  # Estatuto del Trabajo Autónomo (LETA)
            "BOE-A-2015-11723",  # Ley General de la Seguridad Social
        ],
    },
    BOEPresetCategory.PROTECCION_DATOS: {
        "description": "Protección de datos: LOPDGDD",
        "ids": [
            "BOE-A-2018-16673",  # LOPDGDD
        ],
    },
    BOEPresetCategory.FISCAL: {
        "description": "Legislación fiscal: LGT, IRPF, IS, IVA, Reglamento de Facturación",
        "ids": [
            "BOE-A-2003-23186",  # Ley General Tributaria (LGT)
            "BOE-A-2006-20764",  # Ley del IRPF
            "BOE-A-2014-12328",  # Ley del Impuesto sobre Sociedades
            "BOE-A-1992-28740",  # Ley del IVA
            "BOE-A-2012-14696",  # Reglamento de Facturación
        ],
    },
    BOEPresetCategory.MERCANTIL: {
        "description": "Derecho mercantil: Sociedades de Capital, Código de Comercio",
        "ids": [
            "BOE-A-2010-10544",  # Ley de Sociedades de Capital
            "BOE-A-1885-6627",   # Código de Comercio
            "BOE-A-2007-5909",   # Ley de Sociedades Profesionales
        ],
    },
    BOEPresetCategory.CIVIL: {
        "description": "Derecho civil: Código Civil, LEC",
        "ids": [
            "BOE-A-1889-4763",   # Código Civil
            "BOE-A-2000-323",    # LEC (Ley de Enjuiciamiento Civil)
        ],
    },
    BOEPresetCategory.ADMINISTRATIVO: {
        "description": "Derecho administrativo: LPACAP, LRJSP, Contratos del Sector Público",
        "ids": [
            "BOE-A-2015-10565",  # LPACAP
            "BOE-A-2015-10566",  # LRJSP
            "BOE-A-2017-12902",  # Ley de Contratos del Sector Público
        ],
    },
    BOEPresetCategory.COMPLIANCE: {
        "description": "Compliance empresarial: Blanqueo de capitales, Código Penal, Concursal, Secretos empresariales",
        "ids": [
            "BOE-A-2010-6737",   # Ley de Prevención del Blanqueo de Capitales (LPBC)
            "BOE-A-1995-25444",  # Código Penal (responsabilidad personas jurídicas)
            "BOE-A-2020-11218",  # Ley Concursal (insolvencia)
            "BOE-A-2019-2364",   # Ley de Secretos Empresariales
            "BOE-A-2015-8147",   # Ley de Auditoría de Cuentas
        ],
    },
    BOEPresetCategory.PROPIEDAD_INTELECTUAL: {
        "description": "Propiedad intelectual e industrial: LPI, Marcas, Patentes",
        "ids": [
            "BOE-A-1996-8930",   # Ley de Propiedad Intelectual (LPI)
            "BOE-A-2001-23093",  # Ley de Marcas
            "BOE-A-2015-11929",  # Ley de Patentes
        ],
    },
    BOEPresetCategory.COMERCIO_CONSUMIDORES: {
        "description": "Comercio y consumidores: LGDCU, Competencia Desleal, LSSI",
        "ids": [
            "BOE-A-2007-20555",  # LGDCU (Consumidores y Usuarios)
            "BOE-A-1991-628",    # Ley de Competencia Desleal (LCD)
            "BOE-A-1996-1072",   # Ley de Ordenación del Comercio Minorista (LOCM)
            "BOE-A-2013-12888",  # Ley de Garantía de la Unidad de Mercado (LGUM)
            "BOE-A-2002-13758",  # Ley de Servicios de la Sociedad de la Información (LSSI)
        ],
    },
    BOEPresetCategory.EMPRENDIMIENTO: {
        "description": "Emprendimiento y startups: Ley de Emprendedores, Crea y Crece, Startups",
        "ids": [
            "BOE-A-2013-10074",  # Ley de Emprendedores
            "BOE-A-2022-15818",  # Ley Crea y Crece (factura electrónica B2B)
            "BOE-A-2022-23042",  # Ley de Startups
        ],
    },
    BOEPresetCategory.INMOBILIARIO: {
        "description": "Derecho inmobiliario: LAU, Propiedad Horizontal, Ley Hipotecaria",
        "ids": [
            "BOE-A-1994-26003",  # Ley de Arrendamientos Urbanos (LAU)
            "BOE-A-2019-6635",   # Reforma LAU 2019 (vivienda)
            "BOE-A-1960-10906",  # Ley de Propiedad Horizontal
            "BOE-A-1946-2453",   # Ley Hipotecaria
            "BOE-A-2019-3814",   # Ley de Crédito Inmobiliario
        ],
    },
    BOEPresetCategory.CONTABILIDAD: {
        "description": "Contabilidad: Plan General de Contabilidad, PGC Pymes",
        "ids": [
            "BOE-A-2007-19884",  # Plan General de Contabilidad
            "BOE-A-2007-19966",  # PGC Pymes
        ],
    },
    BOEPresetCategory.EDUCACION: {
        "description": "Legislación educativa: LOMLOE, LOU",
        "ids": [
            "BOE-A-2020-17264",  # LOMLOE (Ley de Educación)
            "BOE-A-2006-7899",   # LOE
            "BOE-A-2001-24515",  # LOU (Universidades)
        ],
    },
}


# =============================================================================
# BOE Downloader Service (embedded for simplicity)
# =============================================================================

class BOEDownloaderService:
    """Service for downloading legislation from BOE API."""

    BASE_URL = "https://www.boe.es/datosabiertos/api"

    async def get_legislation_info(self, boe_id: str) -> Optional[BOELegislationInfo]:
        """Get legislation info without downloading full content."""
        import httpx
        import xml.etree.ElementTree as ET

        url = f"{self.BASE_URL}/legislacion-consolidada/id/{boe_id}"

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(url, headers={'Accept': 'application/xml'})
                if response.status_code != 200:
                    return None

                root = ET.fromstring(response.text)
                metadatos = root.find('.//metadatos')
                if metadatos is None:
                    return None

                def get_text(tag: str, default: str = "") -> str:
                    el = metadatos.find(f'.//{tag}')
                    return el.text if el is not None and el.text else default

                return BOELegislationInfo(
                    boe_id=boe_id,
                    title=get_text('titulo'),
                    rango=get_text('rango'),
                    departamento=get_text('departamento'),
                    fecha_publicacion=get_text('fecha_publicacion'),
                    fecha_vigencia=get_text('fecha_vigencia'),
                    estatus_derogacion=get_text('estatus_derogacion', 'N'),
                    url_eli=get_text('url_eli'),
                    url_html=get_text('url_html_consolidada'),
                )

        except Exception as e:
            logger.error(f"Error fetching BOE info for {boe_id}: {e}")
            return None

    async def download_and_index(self, boe_id: str, index: bool = True) -> BOEDownloadResult:
        """Download legislation and optionally index to Weaviate."""
        import httpx
        import xml.etree.ElementTree as ET
        from datetime import datetime

        try:
            async with httpx.AsyncClient(timeout=120.0, follow_redirects=True) as client:
                # 1. Get metadata
                url = f"{self.BASE_URL}/legislacion-consolidada/id/{boe_id}"
                response = await client.get(url, headers={'Accept': 'application/xml'})
                if response.status_code != 200:
                    return BOEDownloadResult(success=False, boe_id=boe_id, error=f"BOE API error: {response.status_code}")

                root = ET.fromstring(response.text)
                metadatos = root.find('.//metadatos')
                if metadatos is None:
                    return BOEDownloadResult(success=False, boe_id=boe_id, error="No metadata found")

                def get_text(elem, tag: str, default: str = "") -> str:
                    el = elem.find(f'.//{tag}')
                    return el.text if el is not None and el.text else default

                title = get_text(metadatos, 'titulo')
                rango = get_text(metadatos, 'rango')

                # 2. Get full text
                text_url = f"{self.BASE_URL}/legislacion-consolidada/id/{boe_id}/texto"
                text_response = await client.get(text_url, headers={'Accept': 'application/xml'})

                content = ""
                if text_response.status_code == 200:
                    text_root = ET.fromstring(text_response.text)
                    bloques = text_root.findall('.//bloque')
                    all_text = []
                    for bloque in bloques:
                        version = bloque.find('.//version')
                        if version is not None:
                            paragraphs = version.findall('.//p')
                            bloque_text = "\n".join([p.text for p in paragraphs if p.text])
                            if bloque_text.strip():
                                all_text.append(bloque_text)
                    content = "\n\n".join(all_text)

                # 3. Get analysis (materias)
                analysis_url = f"{self.BASE_URL}/legislacion-consolidada/id/{boe_id}/analisis"
                analysis_response = await client.get(analysis_url, headers={'Accept': 'application/xml'})
                materias = []
                if analysis_response.status_code == 200:
                    analysis_root = ET.fromstring(analysis_response.text)
                    materias_elems = analysis_root.findall('.//materias/materia')
                    materias = [m.text for m in materias_elems if m.text]

                if not content:
                    return BOEDownloadResult(success=False, boe_id=boe_id, title=title, error="No content found")

                # 4. Index to Weaviate via IndexingPipeline (unified pipeline)
                indexed = False
                if index:
                    try:
                        from app.services.rag.indexing_pipeline import indexing_pipeline
                        from app.services.public_knowledge_service import public_knowledge_service
                        from app.schemas.public_knowledge import (
                            PublicDocumentCreate,
                            PublicDocumentCategory,
                            Jurisdiction,
                        )

                        await public_knowledge_service.initialize()

                        # Determine category and legal status
                        category = PublicDocumentCategory.LEGISLATION
                        if 'decreto' in rango.lower() and 'legislativo' not in rango.lower():
                            category = PublicDocumentCategory.REGULATION
                        legal_status = "derogada" if get_text(metadatos, 'estatus_derogacion') == "S" else "vigente"

                        # --- Stage A: Run unified IndexingPipeline (skip text extraction) ---
                        pipeline_result = await indexing_pipeline.process_text(
                            document_id=boe_id,
                            text=content,  # Full text, no truncation — chunker handles it
                            metadata={
                                "title": title,
                                "source": "boe",
                                "boe_id": boe_id,
                                "document_type": "legislation",
                                "rango": rango,
                                "category": category.value,
                                "jurisdiction": Jurisdiction.SPAIN.value,
                                "legal_status": legal_status,
                                "materias": materias,
                                "source_url": get_text(metadatos, 'url_html_consolidada') or get_text(metadatos, 'url_eli'),
                                "eli_uri": get_text(metadatos, 'url_eli'),
                            },
                            tenant_id="public_knowledge",
                            collection_name="PublicKnowledge",
                            indexing_strategy={
                                "chunking_type": "legal_sections",
                                "chunking_config": {
                                    "target_chunk_size": 1500,
                                    "overlap": 200,
                                },
                            },
                        )

                        if not pipeline_result.success:
                            logger.warning(f"Pipeline failed for {boe_id}: {pipeline_result.errors}")

                        # --- Stage B: Store chunks in PublicKnowledge collection ---
                        # Dedup existing objects for this boe_id
                        await public_knowledge_service._dedup_same_version(boe_id, 1)

                        doc_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"boe:{boe_id}"))  # Deterministic UUID from boe_id
                        now = datetime.now()

                        document = PublicDocumentCreate(
                            id=doc_id,
                            title=title,
                            content=content[:100000],  # Parent doc summary
                            summary=title[:500],
                            category=category,
                            jurisdiction=Jurisdiction.SPAIN,
                            legal_reference=boe_id,
                            source_url=get_text(metadatos, 'url_html_consolidada') or get_text(metadatos, 'url_eli'),
                            source_name="BOE",
                            keywords=materias[:10] + title.split()[:5],
                            topics=materias[:5],
                            verified=True,
                            version="1.0",
                            version_number=1,
                            is_current_version=True,
                            modification_type="original",
                            legal_status=legal_status,
                            boe_id=boe_id,
                            eli_uri=get_text(metadatos, 'url_eli'),
                        )

                        result = await public_knowledge_service.add_document(document)
                        indexed = True
                        weaviate_uuid = result.id if result else None
                        logger.info(
                            f"✅ Indexed {boe_id}: {title[:60]}... "
                            f"({len(pipeline_result.chunks)} pipeline chunks, "
                            f"domain={pipeline_result.contextual_domain})"
                        )

                        # --- Stage C: Legal reference extraction + graph ---
                        try:
                            from app.services.sil.legal_graph_service import (
                                legal_graph,
                                LegalLaw,
                                LawStatus,
                            )
                            from app.services.knowledge.legal_reference_extractor import (
                                legal_reference_extractor,
                            )

                            # Detect domain from materias
                            domain = detect_legal_domain(materias, title)
                            short_name = extract_law_short_name(title, boe_id)
                            status = LawStatus.DEROGADA if get_text(metadatos, 'estatus_derogacion') == "S" else LawStatus.VIGENTE

                            # Create LegalLaw node in public graph
                            law = LegalLaw(
                                boe_id=boe_id,
                                title=title,
                                short_name=short_name,
                                domain=domain,
                                status=status,
                                publication_date=get_text(metadatos, 'fecha_publicacion'),
                                effective_date=get_text(metadatos, 'fecha_vigencia'),
                                eli_uri=get_text(metadatos, 'url_eli'),
                                summary=title[:500],
                                keywords=materias[:10],
                                weaviate_uuid=weaviate_uuid,
                            )
                            await legal_graph.add_law(law)
                            logger.info(f"✅ Added legal_law node: {short_name} ({boe_id})")

                            # Extract legal references from full text
                            legal_refs = await legal_reference_extractor.extract(
                                text=content, boe_id=boe_id
                            )

                            # Store references as graph edges
                            if legal_refs.total_references > 0:
                                ref_counts = await legal_graph.store_references(boe_id, legal_refs)
                                logger.info(f"✅ Stored legal refs for {boe_id}: {ref_counts}")

                            # Enrich with BOE /analisis API (posterior references)
                            try:
                                boe_analysis = await legal_reference_extractor.enrich_from_boe_api(boe_id)
                                for ref in boe_analysis.posterior_references:
                                    ref_boe_id = ref.get("identificador", "")
                                    if ref_boe_id:
                                        await legal_graph.add_reference(
                                            ref_boe_id, boe_id, "MODIFIES",
                                            context_snippet=ref.get("titulo", "")[:200],
                                        )
                            except Exception as api_err:
                                logger.debug(f"BOE /analisis enrichment skipped: {api_err}")

                        except Exception as graph_error:
                            logger.warning(f"⚠️ Failed to process legal graph for {boe_id}: {graph_error}")

                    except Exception as e:
                        logger.error(f"Failed to index {boe_id}: {e}")

                return BOEDownloadResult(
                    success=True,
                    boe_id=boe_id,
                    title=title,
                    indexed=indexed,
                )

        except Exception as e:
            logger.error(f"Error downloading {boe_id}: {e}")
            return BOEDownloadResult(success=False, boe_id=boe_id, error=str(e))

    async def search_boe(self, query: str, limit: int = 10) -> List[BOESearchResult]:
        """Search BOE for legislation."""
        import httpx
        import xml.etree.ElementTree as ET

        url = f"{self.BASE_URL}/legislacion-consolidada"
        params = {"q": query, "limit": limit}

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(url, params=params, headers={'Accept': 'application/xml'})
                if response.status_code != 200:
                    return []

                root = ET.fromstring(response.text)
                items = root.findall('.//item')

                results = []
                for item in items:
                    def get_text(tag: str) -> str:
                        el = item.find(f'.//{tag}')
                        return el.text if el is not None and el.text else ""

                    results.append(BOESearchResult(
                        boe_id=get_text('identificador'),
                        titulo=get_text('titulo'),
                        rango=get_text('rango'),
                        fecha_publicacion=get_text('fecha_publicacion'),
                    ))

                return results

        except Exception as e:
            logger.error(f"BOE search error: {e}")
            return []


# Global instance
boe_service = BOEDownloaderService()


# =============================================================================
# Helper Functions for Legal Graph Integration
# =============================================================================

# Known law short names (common abbreviations)
LAW_SHORT_NAMES = {
    "BOE-A-2015-11430": "ET",        # Estatuto de los Trabajadores
    "BOE-A-2020-11043": "LTD",       # Ley de Trabajo a Distancia
    "BOE-A-1995-24292": "LPRL",      # Ley de Prevención de Riesgos Laborales
    "BOE-A-2015-11724": "LISOS",     # Ley de Infracciones y Sanciones
    "BOE-A-2007-6115": "LOI",        # Ley de Igualdad
    "BOE-A-2007-13409": "LETA",      # Ley del Trabajo Autónomo
    "BOE-A-2015-11723": "LGSS",      # Ley General de la Seguridad Social
    "BOE-A-2018-16673": "LOPDGDD",   # Ley de Protección de Datos
    "BOE-A-2003-23186": "LGT",       # Ley General Tributaria
    "BOE-A-2006-20764": "LIRPF",     # Ley del IRPF
    "BOE-A-2014-12328": "LIS",       # Ley del Impuesto sobre Sociedades
    "BOE-A-1992-28740": "LIVA",      # Ley del IVA
    "BOE-A-2010-10544": "LSC",       # Ley de Sociedades de Capital
    "BOE-A-1885-6627": "CCom",       # Código de Comercio
    "BOE-A-1889-4763": "CC",         # Código Civil
    "BOE-A-2000-323": "LEC",         # Ley de Enjuiciamiento Civil
    "BOE-A-2015-10565": "LPACAP",    # Procedimiento Administrativo Común
    "BOE-A-2015-10566": "LRJSP",     # Régimen Jurídico del Sector Público
    "BOE-A-2017-12902": "LCSP",      # Ley de Contratos del Sector Público
    "BOE-A-2010-6737": "LPBC",       # Ley de Blanqueo de Capitales
    "BOE-A-1995-25444": "CP",        # Código Penal
    "BOE-A-2020-11218": "LC",        # Ley Concursal
    "BOE-A-2019-2364": "LSE",        # Ley de Secretos Empresariales
    "BOE-A-1996-8930": "LPI",        # Ley de Propiedad Intelectual
    "BOE-A-2001-23093": "LM",        # Ley de Marcas
    "BOE-A-2015-11929": "LP",        # Ley de Patentes
    "BOE-A-2007-20555": "LGDCU",     # Ley de Consumidores y Usuarios
    "BOE-A-1991-628": "LCD",         # Ley de Competencia Desleal
    "BOE-A-2002-13758": "LSSI",      # Ley de Servicios de la Sociedad de la Información
    "BOE-A-2013-10074": "LE",        # Ley de Emprendedores
    "BOE-A-2022-15818": "LCC",       # Ley Crea y Crece
    "BOE-A-2022-23042": "LS",        # Ley de Startups
    "BOE-A-1994-26003": "LAU",       # Ley de Arrendamientos Urbanos
    "BOE-A-1960-10906": "LPH",       # Ley de Propiedad Horizontal
    "BOE-A-1946-2453": "LH",         # Ley Hipotecaria
    "BOE-A-2007-19884": "PGC",       # Plan General de Contabilidad
    "BOE-A-2020-17264": "LOMLOE",    # Ley de Educación
    "BOE-A-2001-24515": "LOU",       # Ley Orgánica de Universidades
}


def extract_law_short_name(title: str, boe_id: str) -> str:
    """
    Extract short name from law title.

    First checks known abbreviations, then tries to extract from title.

    Args:
        title: Full law title
        boe_id: BOE identifier

    Returns:
        Short name (e.g., "ET", "LOPDGDD")
    """
    import re

    # Check known short names first
    if boe_id in LAW_SHORT_NAMES:
        return LAW_SHORT_NAMES[boe_id]

    # Try to extract from parentheses (e.g., "... (LOPDGDD)")
    paren_match = re.search(r'\(([A-Z]{2,10})\)', title)
    if paren_match:
        return paren_match.group(1)

    # Try to create acronym from "Ley de/del ..."
    if "Ley" in title:
        # Extract meaningful words after "Ley"
        words = re.findall(r'\b[A-Z][a-záéíóú]+\b', title)
        if words and len(words) >= 2:
            # Skip common words
            skip_words = {'Ley', 'Real', 'Decreto', 'Orgánica', 'General', 'De', 'Del', 'La', 'El', 'Los', 'Las'}
            acronym = ''.join([w[0] for w in words if w not in skip_words][:4])
            if len(acronym) >= 2:
                return acronym

    # Fallback: use BOE ID
    return boe_id.split('-')[-1][:6]


def detect_legal_domain(materias: List[str], title: str) -> "LegalDomain":
    """
    Detect the legal domain from materias (subjects) and title.

    Args:
        materias: List of subject/topic strings from BOE
        title: Law title

    Returns:
        LegalDomain enum value
    """
    from app.services.sil.legal_graph_service import LegalDomain

    # Combine materias and title for analysis
    text = " ".join(materias + [title]).lower()

    # Domain detection rules (order matters - more specific first)
    domain_rules = [
        (LegalDomain.LABOR, ["laboral", "trabajador", "trabajo", "empleo", "despido", "salario", "contrato de trabajo", "seguridad social", "prevención de riesgos"]),
        (LegalDomain.PRIVACY, ["protección de datos", "datos personales", "privacidad", "rgpd", "lopdgdd"]),
        (LegalDomain.FISCAL, ["tribut", "fiscal", "impuesto", "irpf", "iva", "hacienda", "tributaria"]),
        (LegalDomain.MERCANTILE, ["mercantil", "sociedad", "comercio", "empresa", "competencia", "consumidor"]),
        (LegalDomain.CIVIL, ["civil", "código civil", "enjuiciamiento", "propiedad", "arrendamiento", "hipoteca"]),
        (LegalDomain.ADMINISTRATIVE, ["administrativ", "procedimiento", "sector público", "contratación pública"]),
        (LegalDomain.COMPLIANCE, ["blanqueo", "penal", "concursal", "insolvencia", "auditoría", "secretos"]),
        (LegalDomain.IP, ["propiedad intelectual", "marca", "patente", "autor"]),
        (LegalDomain.COMMERCE, ["consumidor", "comercio minorista", "publicidad"]),
        (LegalDomain.REAL_ESTATE, ["inmobiliario", "arrendamiento urbano", "propiedad horizontal", "hipotecaria", "vivienda"]),
        (LegalDomain.EDUCATION, ["educación", "universidad", "enseñanza", "educativ"]),
    ]

    for domain, keywords in domain_rules:
        for keyword in keywords:
            if keyword in text:
                return domain

    return LegalDomain.GENERAL


# =============================================================================
# API Endpoints
# =============================================================================

@router.get("/presets", response_model=List[BOEPresetInfo])
async def list_presets():
    """List all available BOE legislation presets."""
    return [
        BOEPresetInfo(
            name=preset.value,
            description=info["description"],
            legislation_count=len(info["ids"]),
            legislation_ids=info["ids"],
        )
        for preset, info in BOE_PRESETS.items()
    ]


@router.get("/presets/{preset_name}", response_model=BOEPresetInfo)
async def get_preset(preset_name: BOEPresetCategory):
    """Get details of a specific preset."""
    info = BOE_PRESETS.get(preset_name)
    if not info:
        raise HTTPException(status_code=404, detail=f"Preset '{preset_name}' not found")

    return BOEPresetInfo(
        name=preset_name.value,
        description=info["description"],
        legislation_count=len(info["ids"]),
        legislation_ids=info["ids"],
    )


@router.get("/legislation/{boe_id}", response_model=BOELegislationInfo)
async def get_legislation_info(boe_id: str):
    """Get information about a BOE legislation document (without downloading full content)."""
    info = await boe_service.get_legislation_info(boe_id)
    if not info:
        raise HTTPException(status_code=404, detail=f"Legislation '{boe_id}' not found in BOE")
    return info


@router.post("/download", response_model=BOEDownloadResult)
async def download_legislation(
    request: BOEDownloadRequest,
    api_key: str = Depends(verify_api_key)
):
    """
    Download a specific BOE legislation document and optionally index it.
    Requires API key authentication.
    """
    return await boe_service.download_and_index(
        boe_id=request.boe_id,
        index=request.index_to_weaviate,
    )


@router.post("/download/preset", response_model=List[BOEDownloadResult])
async def download_preset(
    request: BOEPresetDownloadRequest,
    background_tasks: BackgroundTasks,
    api_key: str = Depends(verify_api_key)
):
    """
    Download all legislation in a preset category.
    This can take a while for large presets.
    Requires API key authentication.
    """
    preset_info = BOE_PRESETS.get(request.preset)
    if not preset_info:
        raise HTTPException(status_code=404, detail=f"Preset '{request.preset}' not found")

    results = []
    for boe_id in preset_info["ids"]:
        result = await boe_service.download_and_index(
            boe_id=boe_id,
            index=request.index_to_weaviate,
        )
        results.append(result)

    return results


@router.get("/search", response_model=List[BOESearchResult])
async def search_boe(
    query: str = Query(..., description="Search query"),
    limit: int = Query(10, ge=1, le=50, description="Max results"),
):
    """Search BOE for legislation (does not download or index)."""
    return await boe_service.search_boe(query=query, limit=limit)


@router.get("/all-legislation-ids")
async def get_all_legislation_ids():
    """Get all BOE IDs across all presets (for bulk operations)."""
    all_ids = set()
    for info in BOE_PRESETS.values():
        all_ids.update(info["ids"])

    return {
        "total_unique": len(all_ids),
        "ids": sorted(list(all_ids)),
    }


# =============================================================================
# Sync Endpoints - Change Detection
# =============================================================================

@router.post("/sync/{boe_id}", response_model=SyncResultResponse)
async def sync_legislation(
    boe_id: str,
    force: bool = Query(False, description="Force sync even if no apparent changes"),
    api_key: str = Depends(verify_api_key)
):
    """
    Sync a specific legislation with BOE and detect article-level changes.

    This endpoint:
    1. Fetches the current version from BOE
    2. Compares with the stored version
    3. Detects changes at the article level
    4. Generates HTML diffs for visualization
    5. Classifies change severity (CRITICAL, HIGH, MEDIUM, LOW)
    6. Generates LLM-based change summaries (if available)

    Requires API key authentication.
    """
    from app.services.legislation_sync_service import legislation_sync

    result = await legislation_sync.sync_legislation(boe_id, force=force)

    return SyncResultResponse(
        boe_id=result.boe_id,
        title=result.title,
        has_changes=result.has_changes,
        old_version=result.old_version,
        new_version=result.new_version,
        article_changes=[
            ArticleChangeResponse(
                article_number=c.article_number,
                article_title=c.article_title,
                change_type=ChangeTypeEnum(c.change_type.value),
                severity=ChangeSeverityEnum(c.severity.value),
                old_text=c.old_text,
                new_text=c.new_text,
                diff_html=c.diff_html,
                summary=c.summary,
            )
            for c in result.article_changes
        ],
        sync_time=result.sync_time.isoformat(),
        change_summary=result.to_dict().get("change_summary"),
        error=result.error,
    )


@router.post("/sync/preset/{preset_name}", response_model=List[SyncResultResponse])
async def sync_preset(
    preset_name: str,
    api_key: str = Depends(verify_api_key)
):
    """
    Sync all legislation in a preset and detect changes.

    This is useful for periodically checking if any laws in a category
    have been modified.

    Requires API key authentication.
    """
    from app.services.legislation_sync_service import legislation_sync

    results = await legislation_sync.sync_preset(preset_name)

    return [
        SyncResultResponse(
            boe_id=r.boe_id,
            title=r.title,
            has_changes=r.has_changes,
            old_version=r.old_version,
            new_version=r.new_version,
            article_changes=[
                ArticleChangeResponse(
                    article_number=c.article_number,
                    article_title=c.article_title,
                    change_type=ChangeTypeEnum(c.change_type.value),
                    severity=ChangeSeverityEnum(c.severity.value),
                    old_text=c.old_text,
                    new_text=c.new_text,
                    diff_html=c.diff_html,
                    summary=c.summary,
                )
                for c in r.article_changes
            ],
            sync_time=r.sync_time.isoformat(),
            change_summary=r.to_dict().get("change_summary"),
            error=r.error,
        )
        for r in results
    ]


@router.post("/sync/all", response_model=List[SyncResultResponse])
async def sync_all_tracked(
    api_key: str = Depends(verify_api_key)
):
    """
    Sync all tracked legislation and detect changes.

    This syncs all legislation that has been previously indexed.
    Can take a while if many laws are tracked.

    Requires API key authentication.
    """
    from app.services.legislation_sync_service import legislation_sync

    results = await legislation_sync.sync_all_tracked()

    return [
        SyncResultResponse(
            boe_id=r.boe_id,
            title=r.title,
            has_changes=r.has_changes,
            old_version=r.old_version,
            new_version=r.new_version,
            article_changes=[
                ArticleChangeResponse(
                    article_number=c.article_number,
                    article_title=c.article_title,
                    change_type=ChangeTypeEnum(c.change_type.value),
                    severity=ChangeSeverityEnum(c.severity.value),
                    old_text=c.old_text,
                    new_text=c.new_text,
                    diff_html=c.diff_html,
                    summary=c.summary,
                )
                for c in r.article_changes
            ],
            sync_time=r.sync_time.isoformat(),
            change_summary=r.to_dict().get("change_summary"),
            error=r.error,
        )
        for r in results
    ]


@router.get("/updates", response_model=List[PendingUpdateResponse])
async def get_pending_updates(
    api_key: str = Depends(verify_api_key)
):
    """
    Get list of legislation with pending updates from BOE.

    This checks all tracked legislation against BOE to see if there
    are newer versions available. Does not download or apply changes.

    Requires API key authentication.
    """
    from app.services.legislation_sync_service import legislation_sync

    updates = await legislation_sync.get_pending_updates()

    return [
        PendingUpdateResponse(
            boe_id=u["boe_id"],
            title=u["title"],
            stored_version=u["stored_version"],
            has_new_references=u["has_new_references"],
        )
        for u in updates
    ]


@router.get("/legislation/{boe_id}/versions", response_model=List[VersionHistoryResponse])
async def get_version_history(
    boe_id: str,
    limit: int = Query(10, ge=1, le=100, description="Maximum versions to return"),
):
    """
    Get version history for a specific legislation.

    Returns the stored versions with their metadata and hashes.
    Useful for auditing when laws were synced and what changed.
    """
    from app.services.legislation_sync_service import legislation_sync

    versions = await legislation_sync.get_version_history(boe_id, limit=limit)

    return [
        VersionHistoryResponse(
            boe_id=v["boe_id"],
            version_number=v["version_number"],
            version_date=v["version_date"],
            text_hash=v["text_hash"],
            article_count=v["article_count"],
            metadata=v["metadata"],
            modification_references=v["modification_references"],
        )
        for v in versions
    ]


@router.post("/legislation/{boe_id}/compare", response_model=List[ArticleChangeResponse])
async def compare_versions(
    boe_id: str,
    request: VersionCompareRequest,
    api_key: str = Depends(verify_api_key)
):
    """
    Compare two specific versions of legislation.

    Returns the article-level differences between version1 and version2.
    Useful for understanding what changed between two points in time.

    Requires API key authentication.
    """
    from app.services.legislation_sync_service import legislation_sync

    changes = await legislation_sync.compare_versions(
        boe_id,
        request.version1,
        request.version2
    )

    if changes is None:
        raise HTTPException(
            status_code=404,
            detail=f"Could not find versions {request.version1} and/or {request.version2} for {boe_id}"
        )

    return [
        ArticleChangeResponse(
            article_number=c.article_number,
            article_title=c.article_title,
            change_type=ChangeTypeEnum(c.change_type.value),
            severity=ChangeSeverityEnum(c.severity.value),
            old_text=c.old_text,
            new_text=c.new_text,
            diff_html=c.diff_html,
            summary=c.summary,
        )
        for c in changes
    ]
