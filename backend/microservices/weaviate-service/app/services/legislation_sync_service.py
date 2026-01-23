"""
Legislation Sync Service - Detección de cambios en legislación española

Este servicio:
1. Sincroniza periódicamente con el BOE para detectar cambios
2. Almacena versiones históricas de cada ley
3. Detecta qué artículos específicos fueron modificados
4. Genera alertas cuando hay cambios relevantes

Arquitectura:
    ┌─────────────────────────────────────────────────────────────────────┐
    │                    Legislation Sync Service                         │
    ├─────────────────────────────────────────────────────────────────────┤
    │  BOE API ──► Sync Job ──► Change Detection ──► Version Storage     │
    │                              │                                      │
    │                              ▼                                      │
    │                    Article-level Diff ──► Alerts/Notifications     │
    └─────────────────────────────────────────────────────────────────────┘

Uso:
    from app.services.legislation_sync_service import legislation_sync

    # Sincronizar una ley específica
    changes = await legislation_sync.sync_legislation("BOE-A-2015-11430")

    # Ver qué artículos cambiaron
    for change in changes.article_changes:
        print(f"Art. {change.article_number}: {change.change_type}")
        print(f"  Antes: {change.old_text[:100]}...")
        print(f"  Después: {change.new_text[:100]}...")

    # Sincronizar todas las leyes indexadas
    results = await legislation_sync.sync_all()
"""

import asyncio
import difflib
import hashlib
import json
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)


# =============================================================================
# Data Classes
# =============================================================================

class ChangeType(str, Enum):
    """Type of change detected in legislation."""
    ADDED = "added"           # Nuevo artículo/sección
    REMOVED = "removed"       # Artículo eliminado
    MODIFIED = "modified"     # Contenido modificado
    RENUMBERED = "renumbered" # Renumeración
    DEROGATED = "derogated"   # Derogación total/parcial


class ChangeSeverity(str, Enum):
    """Severity/importance of the change."""
    CRITICAL = "critical"   # Cambio fundamental (derogación, nuevo régimen)
    HIGH = "high"          # Cambio importante (obligaciones, plazos, sanciones)
    MEDIUM = "medium"      # Cambio moderado (procedimientos, requisitos)
    LOW = "low"            # Cambio menor (redacción, clarificaciones)


@dataclass
class ArticleChange:
    """Represents a change in a specific article."""
    article_number: str           # "34", "31bis", "Disposición Adicional 1ª"
    article_title: Optional[str]  # Título del artículo si existe
    change_type: ChangeType
    severity: ChangeSeverity
    old_text: Optional[str]       # Texto anterior (None si es nuevo)
    new_text: Optional[str]       # Texto nuevo (None si fue eliminado)
    diff_html: Optional[str]      # Diff en formato HTML para visualización
    summary: Optional[str]        # Resumen del cambio (generado por LLM)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "article_number": self.article_number,
            "article_title": self.article_title,
            "change_type": self.change_type.value,
            "severity": self.severity.value,
            "old_text": self.old_text,
            "new_text": self.new_text,
            "diff_html": self.diff_html,
            "summary": self.summary,
        }


@dataclass
class LegislationVersion:
    """Represents a specific version of legislation."""
    boe_id: str
    version_number: int
    version_date: datetime
    full_text: str
    text_hash: str                # SHA256 del texto para comparación rápida
    articles: Dict[str, str]      # {article_number: article_text}
    metadata: Dict[str, Any]
    modification_references: List[str]  # BOE IDs de las modificaciones

    @classmethod
    def from_text(cls, boe_id: str, version_number: int, text: str,
                  metadata: Optional[Dict] = None) -> "LegislationVersion":
        """Create a version from raw text."""
        text_hash = hashlib.sha256(text.encode()).hexdigest()
        articles = cls._extract_articles(text)

        return cls(
            boe_id=boe_id,
            version_number=version_number,
            version_date=datetime.utcnow(),
            full_text=text,
            text_hash=text_hash,
            articles=articles,
            metadata=metadata or {},
            modification_references=[],
        )

    @staticmethod
    def _extract_articles(text: str) -> Dict[str, str]:
        """Extract individual articles from legislation text."""
        articles = {}

        # Patrones para detectar artículos en legislación española
        patterns = [
            # Artículo X. / Artículo X bis. / Artículo X ter.
            r'(Artículo\s+(\d+(?:\s*(?:bis|ter|quater|quinquies|sexies|septies|octies|nonies|decies))?)\s*\.?\s*[^\n]*)\n(.*?)(?=Artículo\s+\d|Disposición|TÍTULO|CAPÍTULO|$)',
            # Disposición adicional/transitoria/final/derogatoria
            r'(Disposición\s+(adicional|transitoria|final|derogatoria)\s+(\w+)\s*\.?\s*[^\n]*)\n(.*?)(?=Disposición|Artículo|TÍTULO|$)',
        ]

        for pattern in patterns:
            matches = re.findall(pattern, text, re.IGNORECASE | re.DOTALL)
            for match in matches:
                if len(match) >= 3:
                    # Artículos normales
                    article_num = match[1].strip()
                    article_text = match[2].strip() if len(match) > 2 else ""
                    articles[article_num] = article_text[:10000]  # Limitar tamaño

        return articles

    def to_dict(self) -> Dict[str, Any]:
        return {
            "boe_id": self.boe_id,
            "version_number": self.version_number,
            "version_date": self.version_date.isoformat(),
            "text_hash": self.text_hash,
            "article_count": len(self.articles),
            "metadata": self.metadata,
            "modification_references": self.modification_references,
        }


@dataclass
class SyncResult:
    """Result of syncing legislation with BOE."""
    boe_id: str
    title: str
    has_changes: bool
    old_version: Optional[int]
    new_version: Optional[int]
    article_changes: List[ArticleChange]
    sync_time: datetime
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "boe_id": self.boe_id,
            "title": self.title,
            "has_changes": self.has_changes,
            "old_version": self.old_version,
            "new_version": self.new_version,
            "article_changes": [c.to_dict() for c in self.article_changes],
            "sync_time": self.sync_time.isoformat(),
            "change_summary": {
                "total_changes": len(self.article_changes),
                "by_type": self._count_by_type(),
                "by_severity": self._count_by_severity(),
            },
            "error": self.error,
        }

    def _count_by_type(self) -> Dict[str, int]:
        counts = {}
        for change in self.article_changes:
            counts[change.change_type.value] = counts.get(change.change_type.value, 0) + 1
        return counts

    def _count_by_severity(self) -> Dict[str, int]:
        counts = {}
        for change in self.article_changes:
            counts[change.severity.value] = counts.get(change.severity.value, 0) + 1
        return counts


# =============================================================================
# Legislation Sync Service
# =============================================================================

class LegislationSyncService:
    """
    Service for syncing and tracking changes in Spanish legislation.

    Features:
    - Periodic sync with BOE API
    - Version history storage
    - Article-level change detection
    - Diff generation for visualization
    - Change severity classification
    """

    BOE_API_URL = "https://www.boe.es/datosabiertos/api"

    def __init__(self):
        self._versions_cache: Dict[str, List[LegislationVersion]] = {}
        self._redis = None
        self._llm_client = None
        self._initialized = False

    async def initialize(self) -> None:
        """Initialize the service."""
        if self._initialized:
            return

        try:
            import redis.asyncio as redis
            self._redis = redis.Redis(
                host=settings.redis_host,
                port=settings.redis_port,
                decode_responses=True,
            )
            logger.info("✅ Legislation Sync Service initialized")
        except Exception as e:
            logger.warning(f"Redis not available, using in-memory cache: {e}")

        self._initialized = True

    async def _get_llm_client(self):
        """Lazy load LLM client for change summaries."""
        if self._llm_client is None:
            try:
                from app.agents.llm_client import get_llm_client
                self._llm_client = await get_llm_client()
            except Exception as e:
                logger.warning(f"LLM client not available: {e}")
        return self._llm_client

    # =========================================================================
    # Core Sync Methods
    # =========================================================================

    async def sync_legislation(self, boe_id: str, force: bool = False) -> SyncResult:
        """
        Sync a specific legislation with BOE and detect changes.

        Args:
            boe_id: BOE identifier (e.g., BOE-A-2015-11430)
            force: Force sync even if no apparent changes

        Returns:
            SyncResult with detected changes
        """
        await self.initialize()

        logger.info(f"🔄 Syncing legislation: {boe_id}")

        try:
            # 1. Fetch current version from BOE
            current_data = await self._fetch_from_boe(boe_id)
            if not current_data:
                return SyncResult(
                    boe_id=boe_id,
                    title="",
                    has_changes=False,
                    old_version=None,
                    new_version=None,
                    article_changes=[],
                    sync_time=datetime.utcnow(),
                    error="Failed to fetch from BOE",
                )

            # 2. Create version from current BOE data
            current_version = LegislationVersion.from_text(
                boe_id=boe_id,
                version_number=0,  # Will be set properly
                text=current_data["content"],
                metadata={
                    "title": current_data["title"],
                    "rango": current_data.get("rango", ""),
                    "fecha_publicacion": current_data.get("fecha_publicacion"),
                    "referencias_posteriores": current_data.get("referencias_posteriores", []),
                }
            )

            # 3. Get previous version from storage
            previous_version = await self._get_latest_version(boe_id)

            # 4. Compare versions
            if previous_version and previous_version.text_hash == current_version.text_hash and not force:
                # No changes
                logger.info(f"✅ No changes detected for {boe_id}")
                return SyncResult(
                    boe_id=boe_id,
                    title=current_data["title"],
                    has_changes=False,
                    old_version=previous_version.version_number,
                    new_version=previous_version.version_number,
                    article_changes=[],
                    sync_time=datetime.utcnow(),
                )

            # 5. Detect article-level changes
            article_changes = []
            if previous_version:
                article_changes = await self._detect_article_changes(
                    previous_version,
                    current_version
                )
                current_version.version_number = previous_version.version_number + 1
            else:
                current_version.version_number = 1

            # 6. Store new version
            await self._store_version(current_version)

            # 7. Generate change summaries with LLM (if available)
            if article_changes:
                await self._generate_change_summaries(article_changes)

            logger.info(
                f"✅ Sync complete for {boe_id}: "
                f"{len(article_changes)} article changes detected"
            )

            return SyncResult(
                boe_id=boe_id,
                title=current_data["title"],
                has_changes=len(article_changes) > 0 or previous_version is None,
                old_version=previous_version.version_number if previous_version else None,
                new_version=current_version.version_number,
                article_changes=article_changes,
                sync_time=datetime.utcnow(),
            )

        except Exception as e:
            logger.error(f"Error syncing {boe_id}: {e}")
            return SyncResult(
                boe_id=boe_id,
                title="",
                has_changes=False,
                old_version=None,
                new_version=None,
                article_changes=[],
                sync_time=datetime.utcnow(),
                error=str(e),
            )

    async def sync_all_tracked(self) -> List[SyncResult]:
        """Sync all tracked legislation."""
        await self.initialize()

        tracked_ids = await self._get_tracked_legislation_ids()
        results = []

        for boe_id in tracked_ids:
            result = await self.sync_legislation(boe_id)
            results.append(result)
            await asyncio.sleep(1)  # Rate limiting

        return results

    async def sync_preset(self, preset_name: str) -> List[SyncResult]:
        """Sync all legislation in a preset."""
        from app.api.boe_legislation import BOE_PRESETS, BOEPresetCategory

        try:
            preset = BOEPresetCategory(preset_name)
            preset_info = BOE_PRESETS.get(preset)
            if not preset_info:
                return []

            results = []
            for boe_id in preset_info["ids"]:
                result = await self.sync_legislation(boe_id)
                results.append(result)
                await asyncio.sleep(1)

            return results

        except ValueError:
            logger.error(f"Invalid preset: {preset_name}")
            return []

    # =========================================================================
    # Change Detection
    # =========================================================================

    async def _detect_article_changes(
        self,
        old_version: LegislationVersion,
        new_version: LegislationVersion
    ) -> List[ArticleChange]:
        """Detect changes at article level between two versions."""
        changes = []

        old_articles = old_version.articles
        new_articles = new_version.articles

        all_article_nums = set(old_articles.keys()) | set(new_articles.keys())

        for article_num in sorted(all_article_nums, key=self._article_sort_key):
            old_text = old_articles.get(article_num)
            new_text = new_articles.get(article_num)

            if old_text is None and new_text is not None:
                # New article added
                changes.append(ArticleChange(
                    article_number=article_num,
                    article_title=self._extract_article_title(new_text),
                    change_type=ChangeType.ADDED,
                    severity=self._classify_severity(None, new_text),
                    old_text=None,
                    new_text=new_text,
                    diff_html=self._generate_diff_html(None, new_text),
                    summary=None,
                ))

            elif old_text is not None and new_text is None:
                # Article removed/derogated
                changes.append(ArticleChange(
                    article_number=article_num,
                    article_title=self._extract_article_title(old_text),
                    change_type=ChangeType.REMOVED,
                    severity=ChangeSeverity.HIGH,
                    old_text=old_text,
                    new_text=None,
                    diff_html=self._generate_diff_html(old_text, None),
                    summary=None,
                ))

            elif old_text != new_text:
                # Article modified
                changes.append(ArticleChange(
                    article_number=article_num,
                    article_title=self._extract_article_title(new_text),
                    change_type=ChangeType.MODIFIED,
                    severity=self._classify_severity(old_text, new_text),
                    old_text=old_text,
                    new_text=new_text,
                    diff_html=self._generate_diff_html(old_text, new_text),
                    summary=None,
                ))

        return changes

    def _classify_severity(self, old_text: Optional[str], new_text: Optional[str]) -> ChangeSeverity:
        """Classify the severity of a change based on content analysis."""
        text_to_analyze = new_text or old_text or ""
        text_lower = text_to_analyze.lower()

        # Keywords that indicate critical changes
        critical_keywords = [
            "deroga", "queda sin efecto", "se suprime", "nulidad",
            "prohib", "sancion", "infracción muy grave", "inhabilitación"
        ]

        # Keywords that indicate high-importance changes
        high_keywords = [
            "obligación", "plazo", "multa", "sanción", "infracción grave",
            "responsabilidad", "deber", "requisito", "condición"
        ]

        # Keywords that indicate medium-importance changes
        medium_keywords = [
            "procedimiento", "trámite", "solicitud", "documentación",
            "comunicación", "notificación"
        ]

        for keyword in critical_keywords:
            if keyword in text_lower:
                return ChangeSeverity.CRITICAL

        for keyword in high_keywords:
            if keyword in text_lower:
                return ChangeSeverity.HIGH

        for keyword in medium_keywords:
            if keyword in text_lower:
                return ChangeSeverity.MEDIUM

        return ChangeSeverity.LOW

    def _generate_diff_html(self, old_text: Optional[str], new_text: Optional[str]) -> str:
        """Generate HTML diff for visualization."""
        if old_text is None:
            return f'<ins class="diff-added">{new_text}</ins>'
        if new_text is None:
            return f'<del class="diff-removed">{old_text}</del>'

        # Use difflib for word-level diff
        old_words = old_text.split()
        new_words = new_text.split()

        diff = difflib.unified_diff(old_words, new_words, lineterm='')

        html_parts = []
        for line in diff:
            if line.startswith('+') and not line.startswith('+++'):
                html_parts.append(f'<ins class="diff-added">{line[1:]}</ins>')
            elif line.startswith('-') and not line.startswith('---'):
                html_parts.append(f'<del class="diff-removed">{line[1:]}</del>')
            elif not line.startswith('@@') and not line.startswith('---') and not line.startswith('+++'):
                html_parts.append(line)

        return ' '.join(html_parts) if html_parts else new_text

    def _extract_article_title(self, text: str) -> Optional[str]:
        """Extract the title/header from an article text."""
        if not text:
            return None

        # First line is usually the title
        lines = text.strip().split('\n')
        if lines:
            title = lines[0].strip()
            # Clean up and limit length
            title = re.sub(r'\s+', ' ', title)
            return title[:200] if len(title) > 200 else title
        return None

    def _article_sort_key(self, article_num: str) -> Tuple[int, str]:
        """Sort key for article numbers (handles "31bis", "31ter", etc.)."""
        match = re.match(r'(\d+)\s*(.*)', article_num)
        if match:
            return (int(match.group(1)), match.group(2))
        return (9999, article_num)

    # =========================================================================
    # LLM-based Change Summaries
    # =========================================================================

    async def _generate_change_summaries(self, changes: List[ArticleChange]) -> None:
        """Generate human-readable summaries for changes using LLM."""
        llm = await self._get_llm_client()
        if not llm:
            return

        for change in changes[:10]:  # Limit to 10 to avoid too many LLM calls
            if change.summary:
                continue

            try:
                prompt = self._build_summary_prompt(change)
                response = await llm.chat(
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.3,
                    max_tokens=200,
                )
                if response and response.content:
                    change.summary = response.content.strip()
            except Exception as e:
                logger.warning(f"Failed to generate summary for {change.article_number}: {e}")

    def _build_summary_prompt(self, change: ArticleChange) -> str:
        """Build prompt for change summary generation."""
        if change.change_type == ChangeType.ADDED:
            return f"""Resume en 1-2 frases qué establece este nuevo artículo de legislación española:

Artículo {change.article_number}:
{change.new_text[:1000]}

Responde SOLO con el resumen, sin explicaciones adicionales."""

        elif change.change_type == ChangeType.REMOVED:
            return f"""Resume en 1 frase qué contenía este artículo que ha sido eliminado:

Artículo {change.article_number}:
{change.old_text[:1000]}

Responde SOLO con el resumen, sin explicaciones adicionales."""

        else:  # MODIFIED
            return f"""Compara estos dos textos y resume en 1-2 frases qué cambió:

ANTES (Artículo {change.article_number}):
{(change.old_text or '')[:500]}

DESPUÉS:
{(change.new_text or '')[:500]}

Responde SOLO con el resumen del cambio, sin explicaciones adicionales."""

    # =========================================================================
    # BOE API Interaction
    # =========================================================================

    async def _fetch_from_boe(self, boe_id: str) -> Optional[Dict[str, Any]]:
        """Fetch legislation from BOE API."""
        import xml.etree.ElementTree as ET

        async with httpx.AsyncClient(timeout=120.0, follow_redirects=True) as client:
            try:
                # Metadata
                meta_url = f"{self.BOE_API_URL}/legislacion-consolidada/id/{boe_id}"
                meta_response = await client.get(meta_url, headers={'Accept': 'application/xml'})

                if meta_response.status_code != 200:
                    return None

                root = ET.fromstring(meta_response.text)
                metadatos = root.find('.//metadatos')

                if metadatos is None:
                    return None

                def get_text(tag: str, default: str = "") -> str:
                    el = metadatos.find(f'.//{tag}')
                    return el.text if el is not None and el.text else default

                # Full text
                text_url = f"{self.BOE_API_URL}/legislacion-consolidada/id/{boe_id}/texto"
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

                # Analysis (for modification references)
                analysis_url = f"{self.BOE_API_URL}/legislacion-consolidada/id/{boe_id}/analisis"
                analysis_response = await client.get(analysis_url, headers={'Accept': 'application/xml'})

                referencias_posteriores = []
                if analysis_response.status_code == 200:
                    analysis_root = ET.fromstring(analysis_response.text)
                    refs = analysis_root.findall('.//referencias/posteriores/posterior')
                    referencias_posteriores = [r.text for r in refs if r.text]

                return {
                    "boe_id": boe_id,
                    "title": get_text("titulo"),
                    "rango": get_text("rango"),
                    "content": content,
                    "fecha_publicacion": get_text("fecha_publicacion"),
                    "estatus_derogacion": get_text("estatus_derogacion"),
                    "referencias_posteriores": referencias_posteriores,
                }

            except Exception as e:
                logger.error(f"Error fetching {boe_id} from BOE: {e}")
                return None

    # =========================================================================
    # Version Storage
    # =========================================================================

    async def _get_latest_version(self, boe_id: str) -> Optional[LegislationVersion]:
        """Get the latest stored version of legislation."""
        # Try Redis first
        if self._redis:
            try:
                key = f"legislation:version:{boe_id}:latest"
                data = await self._redis.get(key)
                if data:
                    return self._deserialize_version(json.loads(data))
            except Exception as e:
                logger.warning(f"Redis get failed: {e}")

        # Fallback to in-memory cache
        versions = self._versions_cache.get(boe_id, [])
        return versions[-1] if versions else None

    async def _store_version(self, version: LegislationVersion) -> None:
        """Store a new version of legislation."""
        # Store in Redis
        if self._redis:
            try:
                # Store latest
                key = f"legislation:version:{version.boe_id}:latest"
                await self._redis.set(key, json.dumps(self._serialize_version(version)))

                # Store in history
                history_key = f"legislation:version:{version.boe_id}:history"
                await self._redis.lpush(history_key, json.dumps(self._serialize_version(version)))
                await self._redis.ltrim(history_key, 0, 99)  # Keep last 100 versions

            except Exception as e:
                logger.warning(f"Redis store failed: {e}")

        # Also store in memory
        if version.boe_id not in self._versions_cache:
            self._versions_cache[version.boe_id] = []
        self._versions_cache[version.boe_id].append(version)

    async def _get_tracked_legislation_ids(self) -> List[str]:
        """Get list of legislation IDs being tracked."""
        if self._redis:
            try:
                keys = await self._redis.keys("legislation:version:BOE-*:latest")
                return [k.split(":")[2] for k in keys]
            except Exception as e:
                logger.warning(f"Redis keys failed: {e}")

        return list(self._versions_cache.keys())

    def _serialize_version(self, version: LegislationVersion) -> Dict[str, Any]:
        """Serialize version for storage."""
        return {
            "boe_id": version.boe_id,
            "version_number": version.version_number,
            "version_date": version.version_date.isoformat(),
            "full_text": version.full_text[:500000],  # Limit size
            "text_hash": version.text_hash,
            "articles": version.articles,
            "metadata": version.metadata,
            "modification_references": version.modification_references,
        }

    def _deserialize_version(self, data: Dict[str, Any]) -> LegislationVersion:
        """Deserialize version from storage."""
        return LegislationVersion(
            boe_id=data["boe_id"],
            version_number=data["version_number"],
            version_date=datetime.fromisoformat(data["version_date"]),
            full_text=data["full_text"],
            text_hash=data["text_hash"],
            articles=data["articles"],
            metadata=data["metadata"],
            modification_references=data["modification_references"],
        )

    # =========================================================================
    # Public API Methods
    # =========================================================================

    async def get_version_history(self, boe_id: str, limit: int = 10) -> List[Dict[str, Any]]:
        """Get version history for legislation."""
        if self._redis:
            try:
                history_key = f"legislation:version:{boe_id}:history"
                items = await self._redis.lrange(history_key, 0, limit - 1)
                return [
                    self._deserialize_version(json.loads(item)).to_dict()
                    for item in items
                ]
            except Exception as e:
                logger.warning(f"Redis history failed: {e}")

        versions = self._versions_cache.get(boe_id, [])
        return [v.to_dict() for v in versions[-limit:]]

    async def get_pending_updates(self) -> List[Dict[str, Any]]:
        """Get list of legislation with pending updates from BOE."""
        await self.initialize()

        tracked_ids = await self._get_tracked_legislation_ids()
        pending = []

        for boe_id in tracked_ids:
            try:
                current = await self._fetch_from_boe(boe_id)
                if not current:
                    continue

                stored = await self._get_latest_version(boe_id)
                if not stored:
                    continue

                current_hash = hashlib.sha256(current["content"].encode()).hexdigest()

                if current_hash != stored.text_hash:
                    pending.append({
                        "boe_id": boe_id,
                        "title": current["title"],
                        "stored_version": stored.version_number,
                        "has_new_references": len(current.get("referencias_posteriores", [])) > len(stored.modification_references),
                    })

            except Exception as e:
                logger.warning(f"Error checking {boe_id}: {e}")

        return pending

    async def compare_versions(
        self,
        boe_id: str,
        version1: int,
        version2: int
    ) -> Optional[List[ArticleChange]]:
        """Compare two specific versions of legislation."""
        if self._redis:
            try:
                history_key = f"legislation:version:{boe_id}:history"
                items = await self._redis.lrange(history_key, 0, 99)

                v1_data = None
                v2_data = None

                for item in items:
                    data = json.loads(item)
                    if data["version_number"] == version1:
                        v1_data = data
                    if data["version_number"] == version2:
                        v2_data = data

                if v1_data and v2_data:
                    v1 = self._deserialize_version(v1_data)
                    v2 = self._deserialize_version(v2_data)
                    return await self._detect_article_changes(v1, v2)

            except Exception as e:
                logger.warning(f"Version comparison failed: {e}")

        return None


# =============================================================================
# Global Instance
# =============================================================================

legislation_sync = LegislationSyncService()


# =============================================================================
# Convenience Functions
# =============================================================================

async def sync_legislation(boe_id: str, force: bool = False) -> SyncResult:
    """Sync a specific legislation with BOE."""
    return await legislation_sync.sync_legislation(boe_id, force)


async def get_pending_updates() -> List[Dict[str, Any]]:
    """Get legislation with pending updates."""
    return await legislation_sync.get_pending_updates()


async def get_version_history(boe_id: str, limit: int = 10) -> List[Dict[str, Any]]:
    """Get version history for legislation."""
    return await legislation_sync.get_version_history(boe_id, limit)
