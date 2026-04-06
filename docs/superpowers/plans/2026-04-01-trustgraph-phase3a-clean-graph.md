# TrustGraph Phase 3a: Clean Graph — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Transform the TrustGraph from an open-world graph with noise into a clean, deduplicated, ontology-validated knowledge base.

**Architecture:** Four components — entity blacklist filtering at extraction time, canonical name resolution to prevent URI duplicates, semantic predicate resolution via Weaviate OntologyTerms collection (replacing SequenceMatcher fuzzy matching), and new FalkorDB indexes for confidence/method queries. All changes are in `knowledge-tree-service` (KTS) except OntologyTerms collection creation in `weaviate-service`.

**Tech Stack:** FalkorDB, Weaviate (BGE-M3 embeddings via intelligence-docs-service), Python 3.9+, httpx, pytest, asyncio

**Spec:** `docs/superpowers/specs/2026-04-01-trustgraph-phase3-knowledge-expert-design.md` — Phase 3a sections

---

## File Structure

### New Files
| File | Responsibility |
|------|---------------|
| `knowledge-tree-service/config/entity_blacklist.yaml` | Static blacklist of generic terms to exclude from entity extraction |
| `knowledge-tree-service/app/services/entity_blacklist.py` | Load and check terms against blacklist (singleton, cached) |
| `knowledge-tree-service/app/services/ontology_search.py` | Vector search against Weaviate OntologyTerms for predicate resolution |
| `knowledge-tree-service/scripts/cleanup_blacklisted_entities.py` | Retroactive cleanup of blacklisted nodes from existing graph |
| `knowledge-tree-service/scripts/dedup_entities.py` | Offline entity deduplication (analyze + merge) |
| `knowledge-tree-service/scripts/promote_predicates.py` | Analyze `extracted/` predicates for promotion to ontology |
| `knowledge-tree-service/scripts/seed_ontology_terms.py` | Seed OntologyTerms Weaviate collection with embeddings |
| `knowledge-tree-service/tests/test_entity_blacklist.py` | Tests for blacklist loading and filtering |
| `knowledge-tree-service/tests/test_canonical_names.py` | Tests for honorific/suffix stripping in URIBuilder |
| `knowledge-tree-service/tests/test_ontology_search.py` | Tests for vector-based predicate resolution |

### Modified Files
| File | Lines | Change |
|------|-------|--------|
| `knowledge-tree-service/app/services/uri_builder.py` | 88-136 | Add honorific prefix and corporate suffix stripping to `normalize_name()` |
| `knowledge-tree-service/app/services/extractors/coordinator.py` | 126-148 | Add blacklist check before dedup loop |
| `knowledge-tree-service/app/services/extractors/relationships.py` | 105-125 | Replace 3-tier string matching with vector search + binary validation |
| `knowledge-tree-service/app/services/ontology_registry.py` | 84-108 | Add `semantic_match()` method using OntologyTerms |
| `knowledge-tree-service/scripts/seed_ontology.py` | 51-89 | Expand PREDICATES from 32 to ~85 (add trust/, medical/, documental/) |
| `knowledge-tree-service/config/graphs/trustgraph_schema.cypher` | append | Add 4 new indexes (confidence, extraction_method, merged, has_contradiction) |
| `knowledge-tree-service/requirements.txt` | append | Add `pyyaml>=6.0` for YAML blacklist loading |
| `weaviate-service/app/services/weaviate_service.py` | ~3185 | Add `ensure_ontology_terms_collection()` method |

---

## Task 1: FalkorDB Schema Updates

**Files:**
- Modify: `knowledge-tree-service/config/graphs/trustgraph_schema.cypher`
- Modify: `knowledge-tree-service/app/services/falkordb_client.py` (bootstrap_schema reads this file)

- [ ] **Step 1: Add 4 new indexes to the schema file**

Append to `backend/microservices/knowledge-tree-service/config/graphs/trustgraph_schema.cypher`:

```cypher
CREATE INDEX FOR ()-[r:Rel]-() ON (r.confidence);
CREATE INDEX FOR ()-[r:Rel]-() ON (r.extraction_method);
CREATE INDEX FOR (n:Node) ON (n.merged);
CREATE INDEX FOR ()-[r:Rel]-() ON (r.has_contradiction);
```

- [ ] **Step 2: Verify bootstrap_schema loads these indexes**

Run in the KTS container or local test:

```bash
cd backend/microservices/knowledge-tree-service
python -c "
import asyncio
from app.services.falkordb_client import FalkorDBClient
async def check():
    c = FalkorDBClient()
    await c.initialize()
    await c.bootstrap_schema()
    rows = await c.execute_cypher('CALL db.indexes()')
    for r in rows:
        print(r)
    await c.close()
asyncio.run(check())
"
```

Expected: 13 indexes listed (9 existing + 4 new).

- [ ] **Step 3: Commit**

```bash
git add backend/microservices/knowledge-tree-service/config/graphs/trustgraph_schema.cypher
git commit -m "feat(kts): add confidence, extraction_method, merged, has_contradiction indexes"
```

---

## Task 2: Entity Blacklist — Config + Service

**Files:**
- Create: `knowledge-tree-service/config/entity_blacklist.yaml`
- Create: `knowledge-tree-service/app/services/entity_blacklist.py`
- Create: `knowledge-tree-service/tests/test_entity_blacklist.py`
- Modify: `knowledge-tree-service/requirements.txt`

- [ ] **Step 1: Add PyYAML dependency**

Append to `backend/microservices/knowledge-tree-service/requirements.txt`:

```
pyyaml>=6.0
```

- [ ] **Step 2: Write the failing tests**

Create `backend/microservices/knowledge-tree-service/tests/test_entity_blacklist.py`:

```python
"""Tests for entity blacklist loading and matching."""

import pytest
from app.services.entity_blacklist import EntityBlacklist


class TestEntityBlacklistLoad:
    def test_loads_from_yaml(self):
        bl = EntityBlacklist()
        assert len(bl.terms) > 0

    def test_contains_known_generic_terms(self):
        bl = EntityBlacklist()
        assert bl.is_blacklisted("mayor de edad")
        assert bl.is_blacklisted("conyuge")
        assert bl.is_blacklisted("herederos forzosos")

    def test_case_insensitive(self):
        bl = EntityBlacklist()
        assert bl.is_blacklisted("Mayor de Edad")
        assert bl.is_blacklisted("CONYUGE")

    def test_accent_insensitive(self):
        bl = EntityBlacklist()
        assert bl.is_blacklisted("cónyuge")

    def test_does_not_match_real_entities(self):
        bl = EntityBlacklist()
        assert not bl.is_blacklisted("Juan García López")
        assert not bl.is_blacklisted("ACME S.L.")
        assert not bl.is_blacklisted("Ley 31/1995")

    def test_does_not_match_empty_string(self):
        bl = EntityBlacklist()
        assert not bl.is_blacklisted("")
        assert not bl.is_blacklisted("   ")


class TestEntityBlacklistSingleton:
    def test_same_instance(self):
        bl1 = EntityBlacklist()
        bl2 = EntityBlacklist()
        # Both should use the same loaded terms set
        assert bl1.terms is bl2.terms
```

- [ ] **Step 3: Run tests to verify they fail**

```bash
cd backend/microservices/knowledge-tree-service
python -m pytest tests/test_entity_blacklist.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'app.services.entity_blacklist'`

- [ ] **Step 4: Create the blacklist YAML config**

Create `backend/microservices/knowledge-tree-service/config/entity_blacklist.yaml`:

```yaml
# Entity blacklist — generic concepts that should NOT be extracted as :Node entities.
# Terms are matched case-insensitively and accent-insensitively.
# Add new terms as needed; changes take effect after service restart.

legal_concepts:
  - "mayor de edad"
  - "menor de edad"
  - "conyuge"
  - "herederos forzosos"
  - "parte contratante"
  - "representante legal"
  - "persona fisica"
  - "persona juridica"
  - "tercero"
  - "causante"
  - "deudor"
  - "acreedor"
  - "demandante"
  - "demandado"
  - "arrendador"
  - "arrendatario"
  - "fiador"

generic:
  - "empresa"
  - "persona"
  - "documento"
  - "articulo"
  - "parte"
  - "seccion"
  - "capitulo"
  - "titulo"
  - "disposicion"
  - "clausula"
  - "anexo"
```

- [ ] **Step 5: Implement EntityBlacklist service**

Create `backend/microservices/knowledge-tree-service/app/services/entity_blacklist.py`:

```python
"""
EntityBlacklist — filters generic concepts from entity extraction.

Loads terms from config/entity_blacklist.yaml on first access.
Matching is case-insensitive and accent-insensitive (NFD + strip combining).
"""

import logging
import re
import unicodedata
from pathlib import Path
from typing import FrozenSet

import yaml

logger = logging.getLogger(__name__)

_CONFIG_PATH = Path(__file__).resolve().parent.parent / "config" / "entity_blacklist.yaml"

# Module-level singleton: loaded once, shared across all instances
_loaded_terms: FrozenSet[str] | None = None


def _normalize(text: str) -> str:
    """Lowercase + strip accents for comparison."""
    nfd = unicodedata.normalize("NFD", text.strip())
    stripped = "".join(ch for ch in nfd if unicodedata.category(ch) != "Mn")
    return stripped.lower()


def _load_terms() -> FrozenSet[str]:
    """Load and normalize all blacklist terms from YAML config."""
    global _loaded_terms
    if _loaded_terms is not None:
        return _loaded_terms

    try:
        with open(_CONFIG_PATH, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
    except FileNotFoundError:
        logger.warning("Blacklist config not found at %s — using empty blacklist", _CONFIG_PATH)
        _loaded_terms = frozenset()
        return _loaded_terms

    terms = set()
    for category, items in data.items():
        if isinstance(items, list):
            for item in items:
                if isinstance(item, str) and item.strip():
                    terms.add(_normalize(item))

    _loaded_terms = frozenset(terms)
    logger.info("EntityBlacklist loaded %d terms from %s", len(_loaded_terms), _CONFIG_PATH)
    return _loaded_terms


class EntityBlacklist:
    """Check entity names against a static blacklist.

    Thread-safe singleton — terms are loaded once at module level.
    """

    @property
    def terms(self) -> FrozenSet[str]:
        return _load_terms()

    def is_blacklisted(self, name: str) -> bool:
        """Return True if the name matches a blacklisted term."""
        if not name or not name.strip():
            return False
        return _normalize(name) in self.terms
```

- [ ] **Step 6: Run tests to verify they pass**

```bash
cd backend/microservices/knowledge-tree-service
python -m pytest tests/test_entity_blacklist.py -v
```

Expected: All 8 tests PASS.

- [ ] **Step 7: Commit**

```bash
git add backend/microservices/knowledge-tree-service/config/entity_blacklist.yaml \
       backend/microservices/knowledge-tree-service/app/services/entity_blacklist.py \
       backend/microservices/knowledge-tree-service/tests/test_entity_blacklist.py \
       backend/microservices/knowledge-tree-service/requirements.txt
git commit -m "feat(kts): entity blacklist service with YAML config and tests"
```

---

## Task 3: Integrate Blacklist Into Extraction Coordinator

**Files:**
- Modify: `knowledge-tree-service/app/services/extractors/coordinator.py:126-148`
- Modify: `knowledge-tree-service/tests/test_coordinator.py`

- [ ] **Step 1: Write the failing test**

Add to `backend/microservices/knowledge-tree-service/tests/test_coordinator.py`:

```python
class TestBlacklistFiltering:
    """Blacklisted entities should be dropped before storage."""

    @pytest.mark.asyncio
    async def test_blacklisted_subject_dropped(self, falkordb_client):
        """Triples with blacklisted subjects should not be stored."""
        coord = _make_coordinator(falkordb_client)
        # "mayor de edad" is in the blacklist
        blacklisted_triples = [
            _label_triple("mayor de edad"),
            _type_triple("mayor de edad", "concept"),
        ]
        real_triples = [
            _label_triple("Juan García"),
            _rel_triple("Juan García", "ACME S.L."),
        ]

        with patch.object(coord._definitions, "extract", new_callable=AsyncMock) as mock_def, \
             patch.object(coord._relationships, "extract", new_callable=AsyncMock) as mock_rel, \
             patch.object(coord._objects, "extract", new_callable=AsyncMock) as mock_obj, \
             patch.object(coord._topics, "extract", new_callable=AsyncMock) as mock_top:
            mock_def.return_value = [blacklisted_triples[0], real_triples[0]]
            mock_rel.return_value = [real_triples[1]]
            mock_obj.return_value = [blacklisted_triples[1]]
            mock_top.return_value = []

            result = await coord.extract_chunk(
                chunk_text=SAMPLE_CHUNK,
                document_uri=DOC_URI,
                user="test-user",
                collection="default",
            )

        # Only the 2 real triples should be stored (label + rel)
        assert result["triples_created"] == 2

    @pytest.mark.asyncio
    async def test_blacklisted_object_dropped(self, falkordb_client):
        """Triples with blacklisted objects (Node type) should be dropped."""
        coord = _make_coordinator(falkordb_client)
        triples = [
            {
                "subject": "Juan García",
                "predicate_ontology": "legal",
                "predicate_name": "empleado-de",
                "object": "empresa",  # blacklisted generic term
                "object_is_node": True,
                "extraction_method": "llm_relationships",
                "source_chunk": SAMPLE_CHUNK[:200],
            },
        ]

        with patch.object(coord._definitions, "extract", new_callable=AsyncMock) as mock_def, \
             patch.object(coord._relationships, "extract", new_callable=AsyncMock) as mock_rel, \
             patch.object(coord._objects, "extract", new_callable=AsyncMock) as mock_obj, \
             patch.object(coord._topics, "extract", new_callable=AsyncMock) as mock_top:
            mock_def.return_value = []
            mock_rel.return_value = triples
            mock_obj.return_value = []
            mock_top.return_value = []

            result = await coord.extract_chunk(
                chunk_text=SAMPLE_CHUNK,
                document_uri=DOC_URI,
                user="test-user",
                collection="default",
            )

        assert result["triples_created"] == 0
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd backend/microservices/knowledge-tree-service
python -m pytest tests/test_coordinator.py::TestBlacklistFiltering -v
```

Expected: FAIL — blacklisted triples are still stored (2+1 instead of 2+0).

- [ ] **Step 3: Add blacklist filtering to coordinator**

Modify `backend/microservices/knowledge-tree-service/app/services/extractors/coordinator.py`.

Add import at top (after line 24):

```python
from app.services.entity_blacklist import EntityBlacklist
```

Add blacklist filtering inside `extract_chunk()`, between the dedup loop (line 148) and entity linking (line 152). After `deduped_triples` is built, insert:

```python
        # ── Blacklist filtering: drop triples with blacklisted subjects/objects ──
        _blacklist = EntityBlacklist()
        pre_blacklist = len(deduped_triples)
        filtered_triples: List[Dict[str, Any]] = []
        for triple in deduped_triples:
            subject = triple.get("subject", "")
            obj = triple.get("object", "")
            obj_is_node = triple.get("object_is_node", False)

            if _blacklist.is_blacklisted(subject):
                continue
            if obj_is_node and _blacklist.is_blacklisted(obj):
                continue
            filtered_triples.append(triple)

        blacklisted_count = pre_blacklist - len(filtered_triples)
        if blacklisted_count:
            logger.info("Blacklist filtered %d triples", blacklisted_count)
        deduped_triples = filtered_triples
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd backend/microservices/knowledge-tree-service
python -m pytest tests/test_coordinator.py::TestBlacklistFiltering -v
```

Expected: Both tests PASS.

- [ ] **Step 5: Run all existing coordinator tests to check for regressions**

```bash
cd backend/microservices/knowledge-tree-service
python -m pytest tests/test_coordinator.py -v
```

Expected: All tests PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/microservices/knowledge-tree-service/app/services/extractors/coordinator.py \
       backend/microservices/knowledge-tree-service/tests/test_coordinator.py
git commit -m "feat(kts): integrate entity blacklist filtering into extraction coordinator"
```

---

## Task 4: Canonical Name Resolution — Honorific & Suffix Stripping

**Files:**
- Modify: `knowledge-tree-service/app/services/uri_builder.py:88-136`
- Create: `knowledge-tree-service/tests/test_canonical_names.py`

- [ ] **Step 1: Write the failing tests**

Create `backend/microservices/knowledge-tree-service/tests/test_canonical_names.py`:

```python
"""Tests for canonical name resolution — honorific prefix and corporate suffix stripping."""

import pytest
from app.services.uri_builder import URIBuilder


class TestHonorificStripping:
    """Honorific prefixes should be stripped so D. Carlos = Carlos."""

    def test_d_dot_prefix(self):
        assert URIBuilder.normalize_name("D. Carlos Ruiz") == "carlos-ruiz"

    def test_dna_dot_prefix(self):
        assert URIBuilder.normalize_name("Dña. María López") == "maria-lopez"

    def test_don_prefix(self):
        assert URIBuilder.normalize_name("Don Pedro García") == "pedro-garcia"

    def test_dona_prefix(self):
        assert URIBuilder.normalize_name("Doña Ana Martínez") == "ana-martinez"

    def test_sr_prefix(self):
        assert URIBuilder.normalize_name("Sr. José Fernández") == "jose-fernandez"

    def test_sra_prefix(self):
        assert URIBuilder.normalize_name("Sra. Carmen Rodríguez") == "carmen-rodriguez"

    def test_dr_prefix(self):
        assert URIBuilder.normalize_name("Dr. Miguel Sánchez") == "miguel-sanchez"

    def test_dra_prefix(self):
        assert URIBuilder.normalize_name("Dra. Laura Gómez") == "laura-gomez"

    def test_no_false_positive_on_daniel(self):
        """Names starting with 'D' that are not honorifics should be kept."""
        assert URIBuilder.normalize_name("Daniel Ruiz") == "daniel-ruiz"

    def test_no_false_positive_on_dragones(self):
        assert URIBuilder.normalize_name("Dragones S.L.") == "dragones"

    def test_multiple_prefixes_stripped(self):
        """Edge case: only one prefix should be stripped."""
        assert URIBuilder.normalize_name("D. Don Carlos") == "don-carlos"

    def test_entity_uri_dedup(self):
        """D. Carlos and Carlos should produce the same entity URI."""
        uri1 = URIBuilder.entity("default", "D. Carlos Ruiz Fernández")
        uri2 = URIBuilder.entity("default", "Carlos Ruiz Fernández")
        assert uri1 == uri2


class TestCorporateSuffixStripping:
    """Corporate suffixes should be stripped so 'ACME S.L.' = 'ACME'."""

    def test_sl_suffix(self):
        assert URIBuilder.normalize_name("ACME S.L.") == "acme"

    def test_sa_suffix(self):
        assert URIBuilder.normalize_name("TechCorp S.A.") == "techcorp"

    def test_slu_suffix(self):
        assert URIBuilder.normalize_name("Gestiones SLU") == "gestiones"

    def test_sc_suffix(self):
        assert URIBuilder.normalize_name("Cooperativa S.C.") == "cooperativa"

    def test_no_false_positive_on_short_names(self):
        """Names that happen to end with 'sl' should not be truncated."""
        assert URIBuilder.normalize_name("Basel") == "basel"

    def test_entity_uri_dedup(self):
        """ACME S.L. and ACME should produce the same entity URI."""
        uri1 = URIBuilder.entity("default", "ACME S.L.")
        uri2 = URIBuilder.entity("default", "ACME")
        assert uri1 == uri2


class TestExistingNormalizationPreserved:
    """Ensure existing normalization behavior is not broken."""

    def test_comma_reorder(self):
        assert URIBuilder.normalize_name("García, Juan") == "juan-garcia"

    def test_accents_stripped(self):
        assert URIBuilder.normalize_name("José María Azañón") == "jose-maria-azanon"

    def test_spanish_articles_kept(self):
        assert URIBuilder.normalize_name("María de los Ángeles") == "maria-de-los-angeles"

    def test_numbers_preserved(self):
        assert URIBuilder.normalize_name("Ley 39/2015") == "ley-39-2015"
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd backend/microservices/knowledge-tree-service
python -m pytest tests/test_canonical_names.py -v
```

Expected: FAIL — honorific and suffix tests fail because `normalize_name()` doesn't strip them.

- [ ] **Step 3: Implement honorific and suffix stripping**

Modify `backend/microservices/knowledge-tree-service/app/services/uri_builder.py`.

Add two regex patterns as class attributes after `_COMMA_NAME_RE` (after line 85):

```python
    # Honorific prefixes to strip (matched at start of name, case-insensitive)
    _HONORIFIC_RE = re.compile(
        r"^(?:d(?:ña|ra|on|oña|r)?|sra?)\.\s*",
        re.IGNORECASE,
    )

    # Corporate suffixes to strip (matched at end of name, case-insensitive)
    # Requires word boundary or period before suffix to avoid false positives
    _CORPORATE_SUFFIX_RE = re.compile(
        r"\s*\b(?:s\.?l\.?u?\.?|s\.?a\.?|s\.?c\.?)\.?\s*$",
        re.IGNORECASE,
    )
```

Then in `normalize_name()`, add two stripping steps right after the comma reorder block (after line 124, before `# 1. NFD + strip combining marks`):

```python
        # 0b. Strip honorific prefixes
        stripped = cls._HONORIFIC_RE.sub("", stripped).strip()

        # 0c. Strip corporate suffixes
        stripped = cls._CORPORATE_SUFFIX_RE.sub("", stripped).strip()
```

- [ ] **Step 4: Run new tests to verify they pass**

```bash
cd backend/microservices/knowledge-tree-service
python -m pytest tests/test_canonical_names.py -v
```

Expected: All tests PASS.

- [ ] **Step 5: Run existing URI builder tests for regressions**

```bash
cd backend/microservices/knowledge-tree-service
python -m pytest tests/test_uri_builder.py -v
```

Expected: All pass. Note: `test_strips_punctuation` may need updating if "García, Juan (DNI: 12345678A)" now reorders to "Juan García" differently. Check output — if it fails, the old assertion was `garcia-juan-dni-12345678a` and the new one with comma-reorder will be `juan-garcia-dni-12345678a`. Update the test assertion.

- [ ] **Step 6: Commit**

```bash
git add backend/microservices/knowledge-tree-service/app/services/uri_builder.py \
       backend/microservices/knowledge-tree-service/tests/test_canonical_names.py
git commit -m "feat(kts): canonical name resolution — strip honorifics and corporate suffixes"
```

---

## Task 5: Expand Ontology Predicates (32 → ~85)

**Files:**
- Modify: `knowledge-tree-service/scripts/seed_ontology.py:51-89`

- [ ] **Step 1: Expand PREDICATES list**

Modify `backend/microservices/knowledge-tree-service/scripts/seed_ontology.py`. Replace the PREDICATES list (lines 51-89) with the expanded version:

```python
PREDICATES: List[Tuple[str, str, str, str, str]] = [
    # ── Core (~15) ─────────────────────────────────────────────────────────────
    ("core", "label",         "Human-readable name of an entity",                              "any",          "literal"),
    ("core", "definition",    "Formal definition or description of an entity",                 "any",          "literal"),
    ("core", "type",          "Semantic type classification of an entity",                     "any",          "literal"),
    ("core", "has-topic",     "Associates an entity with a topic or subject area",             "document",     "topic"),
    ("core", "mentioned-in",  "Entity appears in the referenced document or chunk",            "entity",       "document"),
    ("core", "contained-in",  "Document or folder is contained within a parent folder",        "document",     "folder"),
    ("core", "part-of",       "Entity or section is a structural part of a larger entity",     "any",          "any"),
    ("core", "instance-of",   "Entity is an instance of a class or category",                  "entity",       "class"),
    ("core", "supports",      "Claim or argument provides evidence supporting another claim",  "claim",        "claim"),
    ("core", "contradicts",   "Claim or argument is in conflict with another claim",           "claim",        "claim"),
    ("core", "semantic-type", "Fine-grained document type (factura, contrato, nomina, etc.)",  "document",     "literal"),
    ("core", "domain",        "Business domain classification (legal, fiscal, medical, etc.)", "document",     "literal"),
    ("core", "same-as",       "Two entities are the same real-world entity (dedup audit)",     "entity",       "entity"),
    ("core", "supersedes",    "This entity or version replaces an older one",                  "any",          "any"),
    ("core", "related-to",    "General semantic relationship between two entities",            "any",          "any"),

    # ── Legal (~25) ────────────────────────────────────────────────────────────
    ("legal", "empleado-de",       "Relacion laboral entre persona y empresa",                          "person",       "organization"),
    ("legal", "firmante-de",       "Persona que firma un contrato o documento",                         "person",       "document"),
    ("legal", "representante-de",  "Persona que actua como representante legal de una organizacion",    "person",       "organization"),
    ("legal", "regulado-por",      "Entidad o actividad que esta regulada por una norma juridica",      "any",          "legislation"),
    ("legal", "salario-bruto",     "Importe del salario bruto anual o mensual pactado",                "contract",     "literal"),
    ("legal", "tipo-contrato",     "Modalidad o tipo de contrato laboral",                             "contract",     "literal"),
    ("legal", "vigente-desde",     "Fecha de inicio de vigencia de un contrato o norma",               "contract",     "literal"),
    ("legal", "vigente-hasta",     "Fecha de finalizacion de vigencia de un contrato o norma",         "contract",     "literal"),
    ("legal", "clausula",          "Clausula o disposicion especifica de un contrato",                 "contract",     "literal"),
    ("legal", "obligacion",        "Obligacion impuesta por un contrato o norma",                      "any",          "literal"),
    ("legal", "derecho",           "Derecho reconocido a una parte por un contrato o norma",           "any",          "literal"),
    ("legal", "modifica",          "Norma que modifica o enmienda otra norma juridica",                "legislation",  "legislation"),
    ("legal", "derogado-por",      "Norma que ha sido derogada por otra posterior",                    "legislation",  "legislation"),
    ("legal", "references-law",    "Document or clause that references a specific law or article",     "document",     "legislation"),
    ("legal", "parte-de-contrato", "Persona u organizacion que es parte en un contrato",               "any",          "contract"),
    ("legal", "beneficiario-de",   "Persona o entidad que recibe un beneficio de un contrato o norma", "any",          "any"),
    ("legal", "garante-de",        "Persona o entidad que garantiza una obligacion",                   "any",          "any"),
    ("legal", "obligacion-de",     "Obligacion especifica que recae sobre una parte",                  "any",          "literal"),
    ("legal", "duracion",          "Periodo de duracion de un contrato o relacion",                    "contract",     "literal"),
    ("legal", "importe",           "Cantidad economica asociada a un contrato o transaccion",          "any",          "literal"),
    ("legal", "cargo-de",          "Persona que ocupa un cargo en una organizacion",                   "person",       "organization"),
    ("legal", "filial-de",         "Organizacion que es filial o subsidiaria de otra",                 "organization", "organization"),
    ("legal", "administrador-de",  "Persona que es administrador de una sociedad",                     "person",       "organization"),
    ("legal", "sujeto-a",          "Entidad sujeta a una norma o regulacion",                          "any",          "legislation"),
    ("legal", "sancion",           "Sancion o penalizacion prevista por incumplimiento",               "any",          "literal"),

    # ── Trust (~4) ─────────────────────────────────────────────────────────────
    ("trust", "authority-weight",    "Peso de autoridad 0.0-1.0 por tipo de documento fuente",       "document-type", "literal"),
    ("trust", "source-reliability",  "Fiabilidad de la fuente de extraccion (manual/llm/imported)",  "extraction",    "literal"),
    ("trust", "temporal-validity",   "Indica si el triple sigue vigente temporalmente",              "triple",        "literal"),
    ("trust", "consensus-score",     "Numero de fuentes independientes que confirman el triple",     "triple",        "literal"),

    # ── Medical (~12) ──────────────────────────────────────────────────────────
    ("medical", "diagnosticado-con",   "Paciente diagnosticado con una enfermedad o condicion",       "person",    "condition"),
    ("medical", "prescrito-por",       "Medicamento o tratamiento prescrito por un profesional",      "treatment", "person"),
    ("medical", "tratado-en",          "Paciente tratado en un centro o servicio medico",             "person",    "facility"),
    ("medical", "alergia-a",           "Paciente con alergia documentada a una sustancia",           "person",    "substance"),
    ("medical", "medicacion",          "Medicamento activo en el tratamiento del paciente",          "person",    "literal"),
    ("medical", "antecedente",         "Antecedente medico relevante del paciente",                  "person",    "literal"),
    ("medical", "resultado-de",        "Resultado de una prueba diagnostica o analisis",             "test",      "literal"),
    ("medical", "derivado-a",          "Paciente derivado a un especialista o servicio",             "person",    "person"),
    ("medical", "fecha-ingreso",       "Fecha de ingreso hospitalario",                              "person",    "literal"),
    ("medical", "fecha-alta",          "Fecha de alta hospitalaria",                                 "person",    "literal"),
    ("medical", "grupo-sanguineo",     "Grupo sanguineo del paciente",                               "person",    "literal"),
    ("medical", "profesional-responsable", "Profesional medico responsable del paciente",            "person",    "person"),

    # ── Documental (~10) ───────────────────────────────────────────────────────
    ("documental", "autor-de",        "Persona autora de un documento o informe",                    "person",    "document"),
    ("documental", "revisado-por",    "Persona que reviso o valido un documento",                    "document",  "person"),
    ("documental", "aprobado-por",    "Persona que aprobo formalmente un documento",                 "document",  "person"),
    ("documental", "version-de",      "Documento que es una version de otro anterior",               "document",  "document"),
    ("documental", "fecha-creacion",  "Fecha de creacion del documento",                             "document",  "literal"),
    ("documental", "fecha-revision",  "Fecha de ultima revision del documento",                      "document",  "literal"),
    ("documental", "destinatario-de", "Persona o entidad destinataria de un documento",              "document",  "any"),
    ("documental", "clasificado-como", "Clasificacion documental (confidencial, publico, etc.)",     "document",  "literal"),
    ("documental", "referencia",      "Codigo o numero de referencia del documento",                 "document",  "literal"),
    ("documental", "adjunto-a",       "Documento adjunto a otro documento principal",                "document",  "document"),

    # ── Prov (~6) ──────────────────────────────────────────────────────────────
    ("prov", "derived-from",   "Triple or entity derived from a source document or chunk",      "triple",       "document"),
    ("prov", "method",         "Extraction method used to produce this triple or entity",        "triple",       "literal"),
    ("prov", "model",          "LLM or model name used during extraction",                       "triple",       "literal"),
    ("prov", "timestamp",      "ISO 8601 timestamp when the triple was extracted",               "triple",       "literal"),
    ("prov", "chunk-text",     "Raw text of the source chunk that yielded this triple",          "triple",       "literal"),
    ("prov", "chunk-offset",   "Character offset of the source chunk within the document",       "triple",       "literal"),
]
```

- [ ] **Step 2: Verify the count**

```bash
cd backend/microservices/knowledge-tree-service
python -c "from scripts.seed_ontology import PREDICATES; print(f'{len(PREDICATES)} predicates')"
```

Expected: ~82 predicates.

- [ ] **Step 3: Run seed in dry-run mode**

```bash
cd backend/microservices/knowledge-tree-service
python scripts/seed_ontology.py --list
```

Expected: All predicates listed, grouped by namespace.

- [ ] **Step 4: Commit**

```bash
git add backend/microservices/knowledge-tree-service/scripts/seed_ontology.py
git commit -m "feat(kts): expand ontology from 32 to ~82 predicates (trust, medical, documental)"
```

---

## Task 6: OntologyTerms Weaviate Collection

**Files:**
- Modify: `weaviate-service/app/services/weaviate_service.py`
- Create: `knowledge-tree-service/scripts/seed_ontology_terms.py`

- [ ] **Step 1: Add `ensure_ontology_terms_collection()` to weaviate-service**

In `backend/microservices/weaviate-service/app/services/weaviate_service.py`, add after `ensure_trustgraph_entities_collection()` (after line ~3249):

```python
    ONTOLOGY_TERMS_COLLECTION = "OntologyTerms"

    async def ensure_ontology_terms_collection(self) -> bool:
        """Create OntologyTerms collection if it does not already exist.

        Stores vectorized predicate definitions for semantic predicate matching.
        Returns True if the collection is available.
        """
        collection_name = self.ONTOLOGY_TERMS_COLLECTION
        try:
            existing = self.client.collections.list_all()
            if collection_name in existing:
                logger.info(f"Collection {collection_name} already exists")
                return True

            dims = getattr(settings, "embedding_dimensions", 1024)

            self.client.collections.create(
                name=collection_name,
                description="Vectorized predicate definitions for Ontology RAG (Phase 3a)",
                vectorizer_config=weaviate.classes.config.Configure.Vectorizer.none(),
                vector_index_config=weaviate.classes.config.Configure.VectorIndex.hnsw(
                    distance_metric=weaviate.classes.config.VectorDistances.COSINE,
                ),
                properties=[
                    weaviate.classes.config.Property(
                        name="predicate_name",
                        data_type=weaviate.classes.config.DataType.TEXT,
                        description="Predicate name (e.g. empleado-de)",
                    ),
                    weaviate.classes.config.Property(
                        name="namespace",
                        data_type=weaviate.classes.config.DataType.TEXT,
                        description="Ontology namespace (core, legal, trust, medical, documental)",
                    ),
                    weaviate.classes.config.Property(
                        name="description",
                        data_type=weaviate.classes.config.DataType.TEXT,
                        description="Human-readable description of the predicate",
                    ),
                    weaviate.classes.config.Property(
                        name="domain_type",
                        data_type=weaviate.classes.config.DataType.TEXT,
                        description="Expected subject type",
                    ),
                    weaviate.classes.config.Property(
                        name="range_type",
                        data_type=weaviate.classes.config.DataType.TEXT,
                        description="Expected object type",
                    ),
                    weaviate.classes.config.Property(
                        name="embed_text",
                        data_type=weaviate.classes.config.DataType.TEXT,
                        description="Text that was embedded (name + description)",
                    ),
                ],
            )
            logger.info(f"Created collection {collection_name} ({dims} dims, cosine HNSW)")
            return True

        except Exception as e:
            logger.error(f"Failed to ensure {collection_name} collection: {e}")
            return False

    async def search_ontology_terms(
        self,
        query_embedding: list[float],
        limit: int = 3,
        namespace: str | None = None,
    ) -> list[dict]:
        """Vector similarity search over OntologyTerms.

        Args:
            query_embedding: Pre-computed query vector.
            limit: Max results.
            namespace: Optional filter by ontology namespace.

        Returns:
            List of dicts with predicate_name, namespace, description, score.
        """
        try:
            await self.ensure_ontology_terms_collection()
            col = self.client.collections.get(self.ONTOLOGY_TERMS_COLLECTION)

            filters = None
            if namespace:
                filters = weaviate.classes.query.Filter.by_property("namespace").equal(namespace)

            response = col.query.near_vector(
                near_vector=query_embedding,
                limit=limit,
                filters=filters,
                return_metadata=weaviate.classes.query.MetadataQuery(distance=True),
            )

            results = []
            for obj in response.objects:
                score = 1.0 - (obj.metadata.distance or 0.0)
                results.append({
                    "predicate_name": obj.properties.get("predicate_name", ""),
                    "namespace": obj.properties.get("namespace", ""),
                    "description": obj.properties.get("description", ""),
                    "score": round(score, 4),
                })
            return results

        except Exception as e:
            logger.error(f"OntologyTerms search failed: {e}")
            return []
```

- [ ] **Step 2: Create the seed script for OntologyTerms**

Create `backend/microservices/knowledge-tree-service/scripts/seed_ontology_terms.py`:

```python
#!/usr/bin/env python3
"""
Seed OntologyTerms Weaviate collection with vectorized predicate definitions.

For each predicate in seed_ontology.PREDICATES (excluding prov/*),
generates an embedding via intelligence-docs-service and inserts into
the OntologyTerms collection.

Usage:
    docker compose exec knowledge-tree-service python scripts/seed_ontology_terms.py
    docker compose exec knowledge-tree-service python scripts/seed_ontology_terms.py --force
    docker compose exec knowledge-tree-service python scripts/seed_ontology_terms.py --dry-run
"""

import argparse
import asyncio
import logging
import sys
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.seed_ontology import PREDICATES

logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger(__name__)

GREEN = "\033[92m"
YELLOW = "\033[93m"
RED = "\033[91m"
BOLD = "\033[1m"
RESET = "\033[0m"

# Namespaces to skip (system-only, not for extraction)
SKIP_NAMESPACES = {"prov"}

WEAVIATE_SERVICE_URL = "http://weaviate-service:8007"
INTELLIGENCE_DOCS_URL = "http://intelligence-docs-service:8012"


async def _embed_text(text: str) -> list[float] | None:
    """Generate embedding via intelligence-docs-service."""
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(
            f"{INTELLIGENCE_DOCS_URL}/embed",
            json={"text": text, "task": "retrieval.passage"},
        )
        if resp.status_code == 200:
            data = resp.json()
            return data.get("embedding") or data.get("embeddings", [None])[0]
    return None


async def _ensure_collection() -> bool:
    """Ensure OntologyTerms collection exists via weaviate-service."""
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(f"{WEAVIATE_SERVICE_URL}/trustgraph/ensure-ontology-terms")
        return resp.status_code == 200


async def _upsert_term(
    predicate_name: str,
    namespace: str,
    description: str,
    domain_type: str,
    range_type: str,
    embedding: list[float],
) -> bool:
    """Insert a single OntologyTerm into Weaviate."""
    embed_text = f"{predicate_name}: {description}"
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(
            f"{WEAVIATE_SERVICE_URL}/trustgraph/ontology-terms",
            json={
                "predicate_name": predicate_name,
                "namespace": namespace,
                "description": description,
                "domain_type": domain_type,
                "range_type": range_type,
                "embed_text": embed_text,
                "embedding": embedding,
            },
        )
        return resp.status_code in (200, 201)


async def seed_ontology_terms(dry_run: bool = False, force: bool = False) -> tuple:
    """Seed OntologyTerms Weaviate collection.

    Returns (created, skipped, errors) counts.
    """
    # Filter out prov/* predicates
    extractable = [p for p in PREDICATES if p[0] not in SKIP_NAMESPACES]
    print(f"  {len(extractable)} extractable predicates (excluded: {SKIP_NAMESPACES})")

    if not dry_run:
        ok = await _ensure_collection()
        if not ok:
            print(f"  {RED}Failed to ensure OntologyTerms collection{RESET}")
            return 0, 0, 1

    created = 0
    skipped = 0
    errors = 0

    for sector, name, description, domain_type, range_type in extractable:
        label = f"{sector}/{name}"
        embed_text = f"{name}: {description}"

        if dry_run:
            print(f"  WOULD SEED  {label}  embed_text={embed_text!r:.80}")
            created += 1
            continue

        try:
            embedding = await _embed_text(embed_text)
            if not embedding:
                print(f"  {RED}EMBED FAIL{RESET}  {label}")
                errors += 1
                continue

            ok = await _upsert_term(name, sector, description, domain_type, range_type, embedding)
            if ok:
                print(f"  {GREEN}OK{RESET}  {label}  ({len(embedding)} dims)")
                created += 1
            else:
                print(f"  {RED}UPSERT FAIL{RESET}  {label}")
                errors += 1
        except Exception as exc:
            print(f"  {RED}ERROR{RESET}  {label}: {exc}")
            errors += 1

    return created, skipped, errors


def main():
    parser = argparse.ArgumentParser(description="Seed OntologyTerms Weaviate collection")
    parser.add_argument("--force", action="store_true", help="Clear and reseed all terms")
    parser.add_argument("--dry-run", action="store_true", help="Preview without changes")
    args = parser.parse_args()

    print("=" * 60)
    print("OntologyTerms Weaviate seed")
    print("=" * 60)

    created, skipped, errors = asyncio.run(
        seed_ontology_terms(dry_run=args.dry_run, force=args.force)
    )

    print(f"\nResults: {created} created, {skipped} skipped, {errors} errors")
    if errors > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
```

- [ ] **Step 3: Add weaviate-service API endpoints for OntologyTerms**

Add to the weaviate-service API (the exact file depends on routing; add to the trustgraph endpoints file). Two endpoints needed:

1. `POST /trustgraph/ensure-ontology-terms` — calls `ensure_ontology_terms_collection()`
2. `POST /trustgraph/ontology-terms` — inserts a term with pre-computed embedding
3. `POST /trustgraph/ontology-terms/search` — vector search (used by KTS)

These follow the existing pattern used for TrustGraphEntities endpoints.

- [ ] **Step 4: Commit**

```bash
git add backend/microservices/weaviate-service/app/services/weaviate_service.py \
       backend/microservices/knowledge-tree-service/scripts/seed_ontology_terms.py
git commit -m "feat(weaviate+kts): OntologyTerms collection + seed script for Ontology RAG"
```

---

## Task 7: Ontology Search Service (KTS Side)

**Files:**
- Create: `knowledge-tree-service/app/services/ontology_search.py`
- Create: `knowledge-tree-service/tests/test_ontology_search.py`

- [ ] **Step 1: Write the failing tests**

Create `backend/microservices/knowledge-tree-service/tests/test_ontology_search.py`:

```python
"""Tests for ontology search — vector-based predicate resolution."""

import pytest
from unittest.mock import AsyncMock, patch

from app.services.ontology_search import OntologySearch


class TestOntologySearch:
    @pytest.mark.asyncio
    async def test_exact_match_returns_predicate(self):
        """Known predicates should resolve via exact match (no vector search needed)."""
        search = OntologySearch()
        result = await search.resolve_predicate("empleado-de")
        assert result is not None
        assert result["predicate_name"] == "empleado-de"
        assert result["namespace"] == "legal"
        assert result["method"] == "exact"

    @pytest.mark.asyncio
    async def test_unknown_predicate_calls_vector_search(self):
        """Unknown predicates should trigger vector search."""
        search = OntologySearch()
        mock_results = [
            {"predicate_name": "empleado-de", "namespace": "legal", "description": "...", "score": 0.91},
        ]
        with patch.object(search, "_vector_search", new_callable=AsyncMock, return_value=mock_results):
            result = await search.resolve_predicate("trabaja en")
        assert result is not None
        assert result["predicate_name"] == "empleado-de"
        assert result["method"] == "semantic_match"

    @pytest.mark.asyncio
    async def test_low_score_returns_none(self):
        """Predicates with no close semantic match should return None."""
        search = OntologySearch()
        mock_results = [
            {"predicate_name": "label", "namespace": "core", "description": "...", "score": 0.50},
        ]
        with patch.object(search, "_vector_search", new_callable=AsyncMock, return_value=mock_results):
            result = await search.resolve_predicate("zzz-unknown-thing")
        assert result is None

    @pytest.mark.asyncio
    async def test_vector_search_failure_returns_none(self):
        """If vector search fails, gracefully return None."""
        search = OntologySearch()
        with patch.object(search, "_vector_search", new_callable=AsyncMock, side_effect=Exception("timeout")):
            result = await search.resolve_predicate("trabaja en")
        assert result is None
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd backend/microservices/knowledge-tree-service
python -m pytest tests/test_ontology_search.py -v
```

Expected: FAIL — `ModuleNotFoundError`.

- [ ] **Step 3: Implement OntologySearch**

Create `backend/microservices/knowledge-tree-service/app/services/ontology_search.py`:

```python
"""
OntologySearch — vector-based predicate resolution via Weaviate OntologyTerms.

Resolution order:
1. Exact match in OntologyRegistry (fast, no network)
2. Vector search in OntologyTerms (semantic matching)
3. None — predicate is unknown
"""

import logging
from typing import Any, Dict, Optional

import httpx

from app.core.config import settings
from app.services.ontology_registry import get_namespace

logger = logging.getLogger(__name__)

# Minimum cosine similarity to accept a semantic match
_SEMANTIC_THRESHOLD = 0.80

# Weaviate service URL for OntologyTerms search
_WEAVIATE_URL = getattr(settings, "weaviate_service_url", "http://weaviate-service:8007")
_INTELLIGENCE_URL = getattr(settings, "intelligence_docs_url", "http://intelligence-docs-service:8012")


class OntologySearch:
    """Resolve predicates using exact match + vector semantic search."""

    async def resolve_predicate(self, predicate: str) -> Optional[Dict[str, Any]]:
        """Resolve a predicate name to its canonical ontology entry.

        Returns dict with keys: predicate_name, namespace, method, score
        or None if no match found.
        """
        # Step 1: exact match (free, no network)
        namespace = get_namespace(predicate)
        if namespace:
            return {
                "predicate_name": predicate,
                "namespace": namespace,
                "method": "exact",
                "score": 1.0,
            }

        # Step 2: vector search
        try:
            results = await self._vector_search(predicate)
        except Exception as exc:
            logger.warning("OntologySearch vector search failed: %s", exc)
            return None

        if not results:
            return None

        best = results[0]
        if best["score"] >= _SEMANTIC_THRESHOLD:
            return {
                "predicate_name": best["predicate_name"],
                "namespace": best["namespace"],
                "method": "semantic_match",
                "score": best["score"],
            }

        return None

    async def _vector_search(self, predicate: str, limit: int = 3) -> list:
        """Embed the predicate text and search OntologyTerms."""
        # Generate embedding for the predicate text
        async with httpx.AsyncClient(timeout=10.0) as client:
            embed_resp = await client.post(
                f"{_INTELLIGENCE_URL}/embed",
                json={"text": predicate, "task": "retrieval.query"},
            )
            if embed_resp.status_code != 200:
                logger.warning("Embedding failed for predicate %r: %s", predicate, embed_resp.status_code)
                return []
            embed_data = embed_resp.json()
            embedding = embed_data.get("embedding") or embed_data.get("embeddings", [None])[0]
            if not embedding:
                return []

        # Search OntologyTerms
        async with httpx.AsyncClient(timeout=10.0) as client:
            search_resp = await client.post(
                f"{_WEAVIATE_URL}/trustgraph/ontology-terms/search",
                json={"embedding": embedding, "limit": limit},
            )
            if search_resp.status_code != 200:
                return []
            return search_resp.json().get("results", [])
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd backend/microservices/knowledge-tree-service
python -m pytest tests/test_ontology_search.py -v
```

Expected: All 4 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/microservices/knowledge-tree-service/app/services/ontology_search.py \
       backend/microservices/knowledge-tree-service/tests/test_ontology_search.py
git commit -m "feat(kts): OntologySearch service — vector-based predicate resolution"
```

---

## Task 8: Rewrite RelationshipsExtractor Predicate Resolution

**Files:**
- Modify: `knowledge-tree-service/app/services/extractors/relationships.py:105-125`
- Modify: `knowledge-tree-service/tests/test_extractors.py`

- [ ] **Step 1: Write the failing test**

Add to `backend/microservices/knowledge-tree-service/tests/test_extractors.py`:

```python
class TestSemanticPredicateResolution:
    """RelationshipsExtractor should use OntologySearch for predicate resolution."""

    @pytest.mark.asyncio
    async def test_semantic_match_uses_ontology_predicate(self):
        """When vector search finds a match, use the ontology predicate."""
        from app.services.extractors.relationships import RelationshipsExtractor

        ext = RelationshipsExtractor()
        # Mock LLM to return a triple with a non-ontology predicate
        llm_output = '{"subject": "Juan", "predicate": "trabaja en", "object": "ACME", "object-entity": true}'

        mock_resolve = AsyncMock(return_value={
            "predicate_name": "empleado-de",
            "namespace": "legal",
            "method": "semantic_match",
            "score": 0.91,
        })

        with patch("app.services.extractors.relationships.ontology_search.resolve_predicate", mock_resolve):
            triples = ext._parse_output(llm_output, "dummy chunk")

        assert len(triples) == 1
        assert triples[0]["predicate_name"] == "empleado-de"
        assert triples[0]["predicate_ontology"] == "legal"
        assert triples[0]["extraction_method"] == "llm_relationships_semantic"

    @pytest.mark.asyncio
    async def test_no_match_goes_to_binary_validation(self):
        """When no semantic match, binary validation decides keep/drop."""
        from app.services.extractors.relationships import RelationshipsExtractor

        ext = RelationshipsExtractor()
        llm_output = '{"subject": "Juan", "predicate": "pertenece a", "object": "Club", "object-entity": true}'

        mock_resolve = AsyncMock(return_value=None)

        with patch("app.services.extractors.relationships.ontology_search.resolve_predicate", mock_resolve):
            triples = ext._parse_output(llm_output, "dummy chunk")

        # Without binary validation mock, it falls through to extracted/ namespace
        assert len(triples) == 1
        assert triples[0]["predicate_ontology"] == "extracted"
        assert triples[0]["extraction_method"] == "llm_relationships_freeform"
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd backend/microservices/knowledge-tree-service
python -m pytest tests/test_extractors.py::TestSemanticPredicateResolution -v
```

Expected: FAIL — `ontology_search` not imported/used in relationships.py.

- [ ] **Step 3: Rewrite predicate resolution in RelationshipsExtractor**

Modify `backend/microservices/knowledge-tree-service/app/services/extractors/relationships.py`.

Add import at top (after line 20):

```python
from app.services.ontology_search import OntologySearch

# Module-level singleton
ontology_search = OntologySearch()
```

Replace the `_parse_output` method's 3-tier resolution block (lines 105-125) with:

```python
            # 4-tier predicate resolution: exact → semantic → freeform
            extraction_method = "llm_relationships"
            ontology = get_namespace(predicate)

            if ontology:
                # Tier 1: exact match in registry
                predicate_name = predicate
            else:
                # Tier 2: semantic vector search in OntologyTerms
                # Note: _parse_output is sync, so we cache the async result.
                # In practice this is called from async extract() which wraps it.
                # For now, use the sync fallback (fuzzy_match) and upgrade
                # to async in the extract() wrapper.
                fuzzy = fuzzy_match(predicate, threshold=0.8)
                if fuzzy:
                    predicate_name = fuzzy[0]
                    ontology = fuzzy[1]
                    extraction_method = "llm_relationships_fuzzy"
                else:
                    # Tier 3: free-form → generate URI
                    predicate_name = _normalize_predicate_name(predicate)
                    if not predicate_name:
                        continue
                    ontology = "extracted"
                    extraction_method = "llm_relationships_freeform"
```

**Important note:** Since `_parse_output()` is synchronous but `OntologySearch.resolve_predicate()` is async, the semantic search integration needs to happen in the `extract()` method (which is async) as a post-processing step. Add a new method `_resolve_predicates_async()` that runs after `_parse_output()`:

Override `extract()` in `RelationshipsExtractor`:

```python
    async def extract(self, chunk_text: str) -> list:
        """Extract triples and resolve predicates with async OntologySearch."""
        triples = await super().extract(chunk_text)

        # Post-process: try semantic resolution for freeform predicates
        resolved = []
        for triple in triples:
            if triple.get("extraction_method") == "llm_relationships_freeform":
                original_name = triple.get("predicate_name", "")
                match = await ontology_search.resolve_predicate(original_name)
                if match:
                    triple["predicate_name"] = match["predicate_name"]
                    triple["predicate_ontology"] = match["namespace"]
                    triple["extraction_method"] = "llm_relationships_semantic"
            resolved.append(triple)

        return resolved
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd backend/microservices/knowledge-tree-service
python -m pytest tests/test_extractors.py::TestSemanticPredicateResolution -v
```

Expected: All tests PASS.

- [ ] **Step 5: Run all extractor tests for regressions**

```bash
cd backend/microservices/knowledge-tree-service
python -m pytest tests/test_extractors.py -v
```

Expected: All PASS.

- [ ] **Step 6: Update confidence base scores**

Add to `_CONFIDENCE_BASE` in `coordinator.py`:

```python
    "llm_relationships_semantic": 0.85,
```

- [ ] **Step 7: Commit**

```bash
git add backend/microservices/knowledge-tree-service/app/services/extractors/relationships.py \
       backend/microservices/knowledge-tree-service/app/services/extractors/coordinator.py \
       backend/microservices/knowledge-tree-service/tests/test_extractors.py
git commit -m "feat(kts): semantic predicate resolution via OntologyTerms in RelationshipsExtractor"
```

---

## Task 9: Retroactive Cleanup Script

**Files:**
- Create: `knowledge-tree-service/scripts/cleanup_blacklisted_entities.py`

- [ ] **Step 1: Create the cleanup script**

Create `backend/microservices/knowledge-tree-service/scripts/cleanup_blacklisted_entities.py`:

```python
#!/usr/bin/env python3
"""
Cleanup blacklisted entities from the TrustGraph.

Scans all :Node entities, checks against entity_blacklist.yaml,
and removes blacklisted nodes along with their relationships.

DRY RUN by default — use --apply to execute changes.

Usage:
    docker compose exec knowledge-tree-service python scripts/cleanup_blacklisted_entities.py
    docker compose exec knowledge-tree-service python scripts/cleanup_blacklisted_entities.py --apply
    docker compose exec knowledge-tree-service python scripts/cleanup_blacklisted_entities.py --tenant-id UUID
"""

import argparse
import asyncio
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.services.entity_blacklist import EntityBlacklist
from app.services.falkordb_client import FalkorDBClient

logging.basicConfig(level=logging.WARNING)

GREEN = "\033[92m"
YELLOW = "\033[93m"
RED = "\033[91m"
BOLD = "\033[1m"
RESET = "\033[0m"


async def cleanup(tenant_id: str | None, apply: bool) -> dict:
    client = FalkorDBClient()
    await client.initialize()
    blacklist = EntityBlacklist()

    stats = {"scanned": 0, "blacklisted": 0, "rels_removed": 0, "nodes_removed": 0}

    try:
        # Fetch all entity nodes (not documents, not folders)
        user_filter = f"AND n.user = '{tenant_id}'" if tenant_id else ""
        query = (
            f"MATCH (n:Node) WHERE n.uri STARTS WITH 'nouxcube://entity/' {user_filter} "
            "RETURN n.uri AS uri"
        )
        rows = await client.execute_cypher(query)
        stats["scanned"] = len(rows)

        blacklisted_uris = []
        for row in rows:
            uri = row.get("uri", "")
            # Extract entity name from URI: nouxcube://entity/{collection}/{name}
            parts = uri.split("/")
            if len(parts) >= 5:
                name = parts[-1].replace("-", " ")
                if blacklist.is_blacklisted(name):
                    blacklisted_uris.append(uri)

        stats["blacklisted"] = len(blacklisted_uris)
        print(f"\n  Scanned {stats['scanned']} entity nodes")
        print(f"  Found {stats['blacklisted']} blacklisted entities\n")

        for uri in blacklisted_uris:
            # Count relationships
            count_q = "MATCH (n:Node {uri: $uri})-[r:Rel]-() RETURN count(r) AS cnt"
            cnt_rows = await client.execute_cypher(count_q, params={"uri": uri})
            rel_count = cnt_rows[0]["cnt"] if cnt_rows else 0
            stats["rels_removed"] += rel_count

            if apply:
                # DETACH DELETE removes node + all its relationships
                del_q = "MATCH (n:Node {uri: $uri}) DETACH DELETE n"
                await client.execute_cypher(del_q, params={"uri": uri})
                stats["nodes_removed"] += 1
                print(f"  {RED}DELETED{RESET}  {uri}  ({rel_count} rels)")
            else:
                print(f"  {YELLOW}WOULD DELETE{RESET}  {uri}  ({rel_count} rels)")

    finally:
        await client.close()

    return stats


def main():
    parser = argparse.ArgumentParser(description="Cleanup blacklisted entities from TrustGraph")
    parser.add_argument("--apply", action="store_true", help="Actually delete (default is dry-run)")
    parser.add_argument("--tenant-id", type=str, default=None, help="Filter by tenant ID")
    args = parser.parse_args()

    mode = "APPLY" if args.apply else "DRY RUN"
    print(f"{'=' * 60}")
    print(f"Blacklisted Entity Cleanup — {mode}")
    print(f"{'=' * 60}")

    stats = asyncio.run(cleanup(args.tenant_id, args.apply))

    print(f"\n{'=' * 60}")
    print(f"Scanned: {stats['scanned']}, Blacklisted: {stats['blacklisted']}")
    print(f"Relationships affected: {stats['rels_removed']}")
    if args.apply:
        print(f"Nodes deleted: {stats['nodes_removed']}")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Commit**

```bash
git add backend/microservices/knowledge-tree-service/scripts/cleanup_blacklisted_entities.py
git commit -m "feat(kts): retroactive cleanup script for blacklisted entities"
```

---

## Task 10: Entity Deduplication Script

**Files:**
- Create: `knowledge-tree-service/scripts/dedup_entities.py`

- [ ] **Step 1: Create the dedup script**

Create `backend/microservices/knowledge-tree-service/scripts/dedup_entities.py`:

```python
#!/usr/bin/env python3
"""
Entity deduplication for TrustGraph.

Finds duplicate entities by applying canonical name resolution
(honorific/suffix stripping) and groups them. Optionally merges
duplicates by re-pointing relationships and creating same-as edges.

DRY RUN by default — use --apply to execute merges.

Usage:
    docker compose exec knowledge-tree-service python scripts/dedup_entities.py
    docker compose exec knowledge-tree-service python scripts/dedup_entities.py --apply
    docker compose exec knowledge-tree-service python scripts/dedup_entities.py --tenant-id UUID
"""

import argparse
import asyncio
import json
import logging
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.services.falkordb_client import FalkorDBClient
from app.services.uri_builder import URIBuilder

logging.basicConfig(level=logging.WARNING)

GREEN = "\033[92m"
YELLOW = "\033[93m"
RED = "\033[91m"
BOLD = "\033[1m"
RESET = "\033[0m"


async def find_duplicates(client: FalkorDBClient, tenant_id: str | None) -> list:
    """Find entity nodes that resolve to the same canonical name."""
    user_filter = f"AND n.user = '{tenant_id}'" if tenant_id else ""
    query = (
        f"MATCH (n:Node) WHERE n.uri STARTS WITH 'nouxcube://entity/' {user_filter} "
        "RETURN n.uri AS uri, n.created_at AS created_at"
    )
    rows = await client.execute_cypher(query)

    # Group by canonical name
    groups: dict[str, list] = defaultdict(list)
    for row in rows:
        uri = row.get("uri", "")
        parts = uri.split("/")
        if len(parts) < 5:
            continue
        raw_name = parts[-1].replace("-", " ")
        canonical = URIBuilder.normalize_name(raw_name)
        if canonical:
            groups[canonical].append({
                "uri": uri,
                "created_at": row.get("created_at"),
            })

    # Filter to groups with >1 member (actual duplicates)
    return [
        {"canonical": name, "entities": entities}
        for name, entities in groups.items()
        if len(entities) > 1
    ]


async def merge_duplicates(
    client: FalkorDBClient,
    group: dict,
    user: str,
    collection: str,
    apply: bool,
) -> dict:
    """Merge a duplicate group: keep canonical, re-point relationships."""
    entities = group["entities"]
    # Choose canonical: prefer oldest (first created_at), or first alphabetically
    canonical = sorted(entities, key=lambda e: e.get("created_at") or "")[0]
    canonical_uri = canonical["uri"]
    duplicates = [e for e in entities if e["uri"] != canonical_uri]

    stats = {"rels_repointed": 0, "same_as_created": 0}

    for dup in duplicates:
        dup_uri = dup["uri"]

        if apply:
            # Re-point outgoing relationships
            await client.execute_cypher(
                "MATCH (old:Node {uri: $old_uri})-[r:Rel]->(o) "
                "MATCH (new:Node {uri: $new_uri}) "
                "CREATE (new)-[r2:Rel]->(o) "
                "SET r2 = properties(r) "
                "DELETE r",
                params={"old_uri": dup_uri, "new_uri": canonical_uri},
            )
            # Re-point incoming relationships
            await client.execute_cypher(
                "MATCH (s)-[r:Rel]->(old:Node {uri: $old_uri}) "
                "MATCH (new:Node {uri: $new_uri}) "
                "CREATE (s)-[r2:Rel]->(new) "
                "SET r2 = properties(r) "
                "DELETE r",
                params={"old_uri": dup_uri, "new_uri": canonical_uri},
            )
            # Create same-as audit edge
            await client.execute_cypher(
                "MATCH (canon:Node {uri: $canon}), (dup:Node {uri: $dup}) "
                "MERGE (canon)-[:Rel {uri: 'nouxcube://predicate/core/same-as', "
                "user: $user, collection: $collection, extraction_method: 'dedup_script'}]->(dup) "
                "SET dup.merged = true",
                params={"canon": canonical_uri, "dup": dup_uri, "user": user, "collection": collection},
            )
            stats["same_as_created"] += 1

    return stats


async def run(tenant_id: str | None, apply: bool, output_json: str | None) -> dict:
    client = FalkorDBClient()
    await client.initialize()

    try:
        groups = await find_duplicates(client, tenant_id)
        print(f"\n  Found {len(groups)} duplicate groups\n")

        total_stats = {"groups": len(groups), "merged": 0, "rels_repointed": 0}

        for group in groups:
            canonical = group["canonical"]
            entities = group["entities"]
            uris = [e["uri"] for e in entities]

            if apply:
                stats = await merge_duplicates(
                    client, group,
                    user=tenant_id or "_system",
                    collection="default",
                    apply=True,
                )
                total_stats["merged"] += 1
                print(f"  {GREEN}MERGED{RESET}  {canonical}  ({len(entities)} → 1)")
            else:
                print(f"  {YELLOW}WOULD MERGE{RESET}  {canonical}  ({len(entities)} entities)")
                for uri in uris:
                    print(f"    - {uri}")

        if output_json:
            with open(output_json, "w") as f:
                json.dump(groups, f, indent=2, default=str)
            print(f"\n  Wrote {len(groups)} groups to {output_json}")

        return total_stats

    finally:
        await client.close()


def main():
    parser = argparse.ArgumentParser(description="Entity deduplication for TrustGraph")
    parser.add_argument("--apply", action="store_true", help="Execute merges (default is dry-run)")
    parser.add_argument("--tenant-id", type=str, default=None, help="Filter by tenant ID")
    parser.add_argument("--output", type=str, default=None, help="Write duplicate groups to JSON file")
    args = parser.parse_args()

    mode = "APPLY" if args.apply else "DRY RUN"
    print(f"{'=' * 60}")
    print(f"Entity Deduplication — {mode}")
    print(f"{'=' * 60}")

    stats = asyncio.run(run(args.tenant_id, args.apply, args.output))

    print(f"\n{'=' * 60}")
    print(f"Groups: {stats['groups']}, Merged: {stats['merged']}")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Commit**

```bash
git add backend/microservices/knowledge-tree-service/scripts/dedup_entities.py
git commit -m "feat(kts): entity deduplication script with canonical name matching"
```

---

## Task 11: Predicate Promotion Script

**Files:**
- Create: `knowledge-tree-service/scripts/promote_predicates.py`

- [ ] **Step 1: Create the promotion script**

Create `backend/microservices/knowledge-tree-service/scripts/promote_predicates.py`:

```python
#!/usr/bin/env python3
"""
Predicate promotion pipeline for TrustGraph.

Analyzes predicates in the 'extracted/' namespace, groups by frequency
and confidence, and identifies candidates for promotion to the official
ontology or merging with existing predicates.

DRY RUN by default — outputs analysis only.

Usage:
    docker compose exec knowledge-tree-service python scripts/promote_predicates.py
    docker compose exec knowledge-tree-service python scripts/promote_predicates.py --min-freq 5 --min-confidence 0.65
"""

import argparse
import asyncio
import json
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.services.falkordb_client import FalkorDBClient

logging.basicConfig(level=logging.WARNING)

GREEN = "\033[92m"
YELLOW = "\033[93m"
RED = "\033[91m"
BOLD = "\033[1m"
RESET = "\033[0m"


async def analyze_extracted_predicates(
    client: FalkorDBClient,
    min_freq: int,
    min_confidence: float,
) -> list:
    """Find extracted/ predicates with their frequency and avg confidence."""
    query = (
        "MATCH ()-[r:Rel]->() "
        "WHERE r.uri STARTS WITH 'nouxcube://predicate/extracted/' "
        "RETURN r.uri AS predicate_uri, "
        "count(r) AS frequency, "
        "avg(r.confidence) AS avg_confidence "
        "ORDER BY frequency DESC"
    )
    rows = await client.execute_cypher(query)

    candidates = []
    for row in rows:
        uri = row.get("predicate_uri", "")
        freq = row.get("frequency", 0)
        avg_conf = row.get("avg_confidence", 0.0)

        # Extract name from URI
        parts = uri.split("/")
        name = parts[-1] if parts else uri

        candidates.append({
            "uri": uri,
            "name": name,
            "frequency": freq,
            "avg_confidence": round(avg_conf, 3) if avg_conf else 0.0,
            "qualifies": freq >= min_freq and (avg_conf or 0) >= min_confidence,
        })

    return candidates


async def run(min_freq: int, min_confidence: float, output_json: str | None) -> None:
    client = FalkorDBClient()
    await client.initialize()

    try:
        candidates = await analyze_extracted_predicates(client, min_freq, min_confidence)

        qualified = [c for c in candidates if c["qualifies"]]
        unqualified = [c for c in candidates if not c["qualifies"]]

        print(f"\n  Total extracted/ predicates: {len(candidates)}")
        print(f"  Qualify for promotion (freq>={min_freq}, conf>={min_confidence}): {len(qualified)}")
        print(f"  Below threshold: {len(unqualified)}\n")

        if qualified:
            print(f"  {BOLD}=== PROMOTION CANDIDATES ==={RESET}\n")
            for c in qualified:
                print(f"  {GREEN}PROMOTE{RESET}  {c['name']:<30}  freq={c['frequency']:<4}  conf={c['avg_confidence']}")

        if unqualified:
            print(f"\n  {BOLD}=== BELOW THRESHOLD ==={RESET}\n")
            for c in unqualified[:20]:  # Show top 20
                print(f"  {YELLOW}KEEP{RESET}    {c['name']:<30}  freq={c['frequency']:<4}  conf={c['avg_confidence']}")
            if len(unqualified) > 20:
                print(f"  ... and {len(unqualified) - 20} more")

        if output_json:
            with open(output_json, "w") as f:
                json.dump({"qualified": qualified, "unqualified": unqualified}, f, indent=2)
            print(f"\n  Wrote analysis to {output_json}")

    finally:
        await client.close()


def main():
    parser = argparse.ArgumentParser(description="Analyze extracted predicates for promotion")
    parser.add_argument("--min-freq", type=int, default=3, help="Minimum frequency (default: 3)")
    parser.add_argument("--min-confidence", type=float, default=0.65, help="Minimum avg confidence (default: 0.65)")
    parser.add_argument("--output", type=str, default=None, help="Write results to JSON")
    args = parser.parse_args()

    print(f"{'=' * 60}")
    print(f"Predicate Promotion Analysis")
    print(f"  min_freq={args.min_freq}  min_confidence={args.min_confidence}")
    print(f"{'=' * 60}")

    asyncio.run(run(args.min_freq, args.min_confidence, args.output))


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Commit**

```bash
git add backend/microservices/knowledge-tree-service/scripts/promote_predicates.py
git commit -m "feat(kts): predicate promotion analysis script for extracted/ namespace"
```

---

## Task 12: Update TRUSTGRAPH.md & Final Integration Test

**Files:**
- Modify: `docs/architecture/TRUSTGRAPH.md`

- [ ] **Step 1: Update phase status in TRUSTGRAPH.md**

Update the Implementation Phases section (lines 267-286):

```markdown
### Phase 1: Automated Ingest (COMPLETE)

Schema migration, 4 LLM extractors, PROV-O provenance, contradiction detection, mini-ontology, API endpoints, cross-service integration, reindexation script. KTS fully rewritten: 18 commits, 59 files changed, +6,107 / -7,658 lines (net -1,551). 92 tests.

### Phase 2: Semantic Similarity Retrieval (COMPLETE)

Entity embeddings in Weaviate (`TrustGraphEntities`), 7-stage graph_rag pipeline (entity retrieval, BFS subgraph, label resolution, semantic pre-filter, LLM edge scoring, context formatting, source provenance), frontend SourceEvidence panel with confidence badges.

### Phase 3a: Clean Graph (COMPLETE)

Entity blacklist (YAML config + coordinator filtering), canonical name resolution (honorific/suffix stripping in URIBuilder), entity dedup script, Ontology RAG (OntologyTerms Weaviate collection, semantic predicate resolution), expanded ontology (32→~82 predicates with trust/medical/documental namespaces), predicate promotion pipeline, 4 new FalkorDB indexes.

### Phase 3b: Smart Traversal (PLANNED)

Authority weight triples, multi-hop Cypher templates, LLM-guided traversal expansion, consensus scoring.

### Phase 3c: Knowledge Expert (PLANNED)

Graph data assembly, report templates, KPI engine, document generation tool.
```

- [ ] **Step 2: Run all KTS tests**

```bash
cd backend/microservices/knowledge-tree-service
python -m pytest tests/ -v --tb=short
```

Expected: All tests PASS.

- [ ] **Step 3: Commit**

```bash
git add docs/architecture/TRUSTGRAPH.md
git commit -m "docs: update TRUSTGRAPH.md — Phase 2 complete, Phase 3a complete"
```

---

## Summary

| Task | Component | New Files | Modified Files | Tests |
|------|-----------|-----------|----------------|-------|
| 1 | FalkorDB Schema | 0 | 1 | manual verify |
| 2 | Entity Blacklist service | 3 | 1 | 8 tests |
| 3 | Blacklist → Coordinator | 0 | 2 | 2 tests |
| 4 | Canonical Names | 1 | 1 | 16 tests |
| 5 | Expanded Ontology | 0 | 1 | manual verify |
| 6 | OntologyTerms Weaviate | 1 | 1 | — |
| 7 | OntologySearch service | 2 | 0 | 4 tests |
| 8 | Predicate resolution rewrite | 0 | 2 | 2 tests |
| 9 | Cleanup script | 1 | 0 | — |
| 10 | Dedup script | 1 | 0 | — |
| 11 | Promotion script | 1 | 0 | — |
| 12 | Docs + integration | 0 | 1 | full suite |
| **Total** | | **10 new** | **10 modified** | **32+ tests** |
