# Remove `domain` Field Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Eliminate the `domain` field across the stack, consolidating on `document_type` as the single taxonomy. Remove 3 parallel detection systems. Refactor `analyze_document()` to not depend on domain. Delete `applicable_laws` precomputation in favor of JIT TrustGraph queries.

**Architecture:** Purely additive removal + one refactor. The classifier (source of truth in `intelligence-docs-service`) stops emitting `domain`. Downstream consumers (weaviate-service, emma-agent-service, knowledge-tree-service, backend/app, frontend) are cleaned layer by layer. One functional rewrite: `ContextualRetrievalService.analyze_document()` is simplified to use `document_type` + entities instead of a `DomainDetectionResult`.

**Tech Stack:** Python 3.9+ / FastAPI / Pydantic / LangGraph / Weaviate / FalkorDB / TypeScript / Next.js. No new dependencies.

**Spec reference:** `docs/superpowers/specs/2026-04-22-remove-domain-field-design.md`

**Preconditions verified:**
- `Nouxcube_documents` collection is empty (0 objects) — no data migration needed
- `nouxcube` DB has 0 `indexed_documents` — no row migration
- Langfuse `emma_react_system` prompt requires manual promotion post-deploy (out of this plan's scope)

---

## Global rules for execution

- **Branch:** directly on `development` (confirmed in spec §11)
- **Verification between phases:** lightweight — `grep` + container import check. No full test suite until Phase 9
- **Commits:** one per phase by default. At Phase 9 user confirms whether to squash into a single consolidated commit
- **Read before Edit:** every file must be `Read` in the same session before `Edit` (tool requirement)
- **Safety:** if a step fails verification, STOP — do not proceed to next phase; report and ask

---

## Phase 1 — Classifier (source of truth)

### Task 1: Remove `domain` from `intelligence-docs-service` classifier

**Files:**
- Modify: `backend/microservices/intelligence-docs-service/app/providers/base.py`
- Modify: `backend/microservices/intelligence-docs-service/app/pipeline/classifier.py`
- Modify: `backend/microservices/intelligence-docs-service/tests/test_classifier.py`

- [ ] **Step 1: Read the 3 files to confirm current shape**

```bash
grep -n "domain" backend/microservices/intelligence-docs-service/app/providers/base.py
grep -n "domain" backend/microservices/intelligence-docs-service/app/pipeline/classifier.py
grep -n "domain" backend/microservices/intelligence-docs-service/tests/test_classifier.py
```

Expected: matches in all 3. The tuples in `classifier.py` are `(regex, doc_type, domain)`.

- [ ] **Step 2: Remove `domain` from `ClassificationResult` dataclass**

File: `backend/microservices/intelligence-docs-service/app/providers/base.py`

Before:
```python
@dataclass
class ClassificationResult:
    document_type: str
    confidence: float
    domain: str = ""
    provider: str = ""
```

After:
```python
@dataclass
class ClassificationResult:
    document_type: str
    confidence: float
    provider: str = ""
```

- [ ] **Step 3: Refactor `FILENAME_PATTERNS` to 2-tuple**

File: `backend/microservices/intelligence-docs-service/app/pipeline/classifier.py`

Before:
```python
FILENAME_PATTERNS: list[tuple[str, str, str]] = [
    (r"factura|invoice", "factura", "fiscal"),
    (r"contrato|contract", "contrato", "legal"),
    ...
]
```

After:
```python
FILENAME_PATTERNS: list[tuple[str, str]] = [
    (r"factura|invoice", "factura"),
    (r"contrato|contract", "contrato"),
    (r"nomina|payroll|payslip", "nomina"),
    (r"modelo.?(111|190|303|347|390)", "modelo_fiscal"),
    (r"sentencia|resoluci[oó]n", "sentencia"),
    (r"convenio", "convenio"),
    (r"estatuto", "estatuto"),
    (r"informe|report", "informe"),
    (r"acta", "acta"),
    (r"escritura", "escritura"),
    (r"p[oó]liza", "poliza"),
    (r"balance|cuenta.*resultado", "contable"),
    (r"certificado", "certificado"),
    (r"demanda", "demanda"),
]
```

And the loops:

Before:
```python
for pattern, doc_type, domain in FILENAME_PATTERNS:
    if re.search(pattern, fname_lower, re.IGNORECASE):
        return ClassificationResult(
            document_type=doc_type,
            confidence=0.75,
            domain=domain,
            provider="heuristic",
        )
```

After:
```python
for pattern, doc_type in FILENAME_PATTERNS:
    if re.search(pattern, fname_lower, re.IGNORECASE):
        return ClassificationResult(
            document_type=doc_type,
            confidence=0.75,
            provider="heuristic",
        )
```

(Same change applies to the content-heuristic loop below it.)

And the default fallback:

Before:
```python
return ClassificationResult(
    document_type="general",
    confidence=0.30,
    domain="general",
    provider="heuristic",
)
```

After:
```python
return ClassificationResult(
    document_type="general",
    confidence=0.30,
    provider="heuristic",
)
```

- [ ] **Step 4: Update `test_classifier.py`**

File: `backend/microservices/intelligence-docs-service/tests/test_classifier.py`

Grep for `domain` assertions and remove them:

```bash
grep -n "domain" backend/microservices/intelligence-docs-service/tests/test_classifier.py
```

For each match, remove the `domain=...` keyword argument or `result.domain == ...` assertion. The tests should still pass — they're asserting `document_type` which is unchanged.

- [ ] **Step 5: Verify imports and tests**

```bash
docker exec docker-intelligence-docs-service-1 python -c "from app.pipeline.classifier import classify_document, FILENAME_PATTERNS; assert all(len(t) == 2 for t in FILENAME_PATTERNS); print('classifier ok, tuples are 2-wide')"
docker exec docker-intelligence-docs-service-1 python -c "from app.providers.base import ClassificationResult; r = ClassificationResult(document_type='x', confidence=0.5); assert not hasattr(r, 'domain'); print('ClassificationResult has no domain field')"
```

Expected: both print "ok"-style messages. If `assert` fires, stop and investigate.

- [ ] **Step 6: Run classifier tests if available**

```bash
docker exec docker-intelligence-docs-service-1 python -m pytest tests/test_classifier.py -x 2>&1 | tail -20
```

Expected: all tests pass. If they depend on `domain` output we didn't update in Step 4, fix before proceeding.

- [ ] **Step 7: Commit Phase 1**

```bash
git add backend/microservices/intelligence-docs-service/app/providers/base.py \
        backend/microservices/intelligence-docs-service/app/pipeline/classifier.py \
        backend/microservices/intelligence-docs-service/tests/test_classifier.py

git commit -m "$(cat <<'EOF'
refactor(intelligence-docs): drop `domain` from ClassificationResult

Phase 1/9 of domain-field removal. The classifier is the source of truth
for document classification — it previously returned `(document_type,
domain)` but domain was always derivable from document_type via the same
FILENAME_PATTERNS regex match. Removing the redundancy.

- ClassificationResult: drop `domain: str = ""` field
- FILENAME_PATTERNS: 3-tuple (regex, doc_type, domain) → 2-tuple (regex, doc_type)
- classify_document() loops + default fallback: no more domain
- tests updated

Spec: docs/superpowers/specs/2026-04-22-remove-domain-field-design.md
Plan: docs/superpowers/plans/2026-04-22-remove-domain-field.md
EOF
)"
```

---

## Phase 2 — Contextual retrieval (biggest change)

### Task 2: Rewrite `ContextualRetrievalService` without domain

**Files:**
- Modify: `backend/microservices/weaviate-service/app/services/rag/contextual_retrieval.py` (~200 lines removed, ~50 changed)
- Modify: `backend/microservices/weaviate-service/app/services/rag/context_enricher.py`
- Modify: `backend/microservices/weaviate-service/app/services/rag/indexing_pipeline.py`

- [ ] **Step 1: Read full `contextual_retrieval.py`**

Read the entire file to understand the structure (you'll need to know what references `LegalDomain`, `SPANISH_LEGISLATION`, `LawReference` etc.):

```bash
wc -l backend/microservices/weaviate-service/app/services/rag/contextual_retrieval.py
```

Scan for the symbols we're removing:

```bash
grep -n "LegalDomain\|SPANISH_LEGISLATION\|LawReference\|DomainDetectionResult\|applicable_laws\|detect_domain\|_get_applicable_laws\|domain_confidence\|secondary_domains" backend/microservices/weaviate-service/app/services/rag/contextual_retrieval.py
```

- [ ] **Step 2: Delete the top-level domain infrastructure**

Delete these from `contextual_retrieval.py` (in order — the imports/enums first):

1. `class LegalDomain(str, Enum)` — the full enum
2. `SPANISH_LEGISLATION: Dict[LegalDomain, Dict[str, Any]]` — the entire dictionary
3. `@dataclass class LawReference` (lines 555-569 approximately) — the dataclass + its `to_citation()` method
4. `@dataclass class DomainDetectionResult` (lines 572-579) — the dataclass
5. `def detect_domain(self, text, metadata)` (lines 645-722) — the entire method
6. `def _get_applicable_laws(self, domain, detected_keywords)` (lines 724-…) — the entire method

Use Read + Edit surgically for each. After each deletion, run:

```bash
docker exec docker-weaviate-service-1 python -c "from app.services.rag import contextual_retrieval as cr; print([s for s in dir(cr) if 'domain' in s.lower() or 'law' in s.lower()])"
```

Expected (eventually, after all 6 deletions): empty list or only unrelated symbols.

- [ ] **Step 3: Refactor `ContextGenerationResult` dataclass**

Before:
```python
@dataclass
class ContextGenerationResult:
    document_id: str
    domain: LegalDomain
    context_prefix: str
    applicable_laws: List[LawReference]
    document_summary: str
    key_entities: List[str]
    metadata: Dict[str, Any] = field(default_factory=dict)
```

After:
```python
@dataclass
class ContextGenerationResult:
    document_id: str
    document_type: str
    context_prefix: str
    document_summary: str
    key_entities: List[str]
    metadata: Dict[str, Any] = field(default_factory=dict)
```

- [ ] **Step 4: Refactor `ContextualizedChunk` dataclass**

Before:
```python
@dataclass
class ContextualizedChunk:
    original_text: str
    contextualized_text: str
    context_prefix: str
    chunk_index: int
    domain: LegalDomain
    applicable_laws: List[str]
    metadata: Dict[str, Any] = field(default_factory=dict)
```

After:
```python
@dataclass
class ContextualizedChunk:
    original_text: str
    contextualized_text: str
    context_prefix: str
    chunk_index: int
    document_type: str
    metadata: Dict[str, Any] = field(default_factory=dict)
```

- [ ] **Step 5: Rewrite `generate_context_prefix()`**

Before (illustrative — find via `grep -n "def generate_context_prefix"`):
```python
def generate_context_prefix(self, domain_result: DomainDetectionResult, document_type: str = "") -> str:
    parts = [
        f"[CONTEXTO] Documento del dominio {domain_result.primary_domain.value}",
        f", tipo {document_type}" if document_type else "",
        ". Legislación aplicable: " + ", ".join(l.to_citation() for l in domain_result.applicable_laws[:3]),
        " [CONTENIDO]",
    ]
    return "".join(parts)
```

After:
```python
def generate_context_prefix(self, document_type: str = "", key_entities: Optional[List[str]] = None) -> str:
    """Generate a context prefix string from document_type and key entities.

    The prefix is prepended to each chunk before embedding, improving
    retrieval relevance per Anthropic's Contextual Retrieval pattern.
    """
    parts = ["[CONTEXTO]"]
    if document_type and document_type != "general":
        parts.append(f" Documento tipo `{document_type}`.")
    if key_entities:
        ent_summary = ", ".join(key_entities[:5])
        parts.append(f" Entidades: {ent_summary}.")
    parts.append(" [CONTENIDO]")
    return "".join(parts)
```

- [ ] **Step 6: Rewrite `analyze_document()`**

Full before/after. Replace the entire method body.

Before (approximately L 819-876 in current file):
```python
async def analyze_document(
    self, document_id: str, text: str, metadata: Optional[Dict[str, Any]] = None,
    use_llm: bool = True,
) -> ContextGenerationResult:
    metadata = metadata or {}
    domain_result = self.detect_domain(text, metadata)
    document_type = metadata.get("document_type", "")
    context_prefix = self.generate_context_prefix(domain_result, document_type=document_type)
    key_entities = self._extract_key_entities(text, domain_result.primary_domain)
    doc_summary = self._generate_simple_summary(text)
    if use_llm and self._enabled:
        try:
            llm_client = await self._get_llm_client()
            if llm_client:
                enhanced_context = await self._enhance_with_llm(text, domain_result, llm_client)
                if enhanced_context:
                    context_prefix = enhanced_context
        except Exception as e:
            logger.warning(f"LLM enhancement failed, using rule-based context: {e}")
    return ContextGenerationResult(
        document_id=document_id,
        domain=domain_result.primary_domain,
        context_prefix=context_prefix,
        applicable_laws=domain_result.applicable_laws,
        document_summary=doc_summary,
        key_entities=key_entities,
        metadata={
            "domain_confidence": domain_result.confidence,
            "secondary_domains": [d.value for d in domain_result.secondary_domains],
            "detected_keywords": domain_result.detected_keywords[:10],
        }
    )
```

After:
```python
async def analyze_document(
    self, document_id: str, text: str, metadata: Optional[Dict[str, Any]] = None,
    use_llm: bool = True,
) -> ContextGenerationResult:
    """Analyze a document and generate contextual information.

    The context prefix is built from `document_type` (provided by the
    upstream classifier) and key entities extracted from the text. When
    LLM enhancement is enabled, a richer prefix is generated.
    """
    metadata = metadata or {}
    document_type = metadata.get("document_type", "general")
    key_entities = self._extract_key_entities(text)
    doc_summary = self._generate_simple_summary(text)
    context_prefix = self.generate_context_prefix(document_type, key_entities=key_entities)

    if use_llm and self._enabled:
        try:
            llm_client = await self._get_llm_client()
            if llm_client:
                enhanced_context = await self._enhance_with_llm(
                    text, document_type, key_entities, llm_client
                )
                if enhanced_context:
                    context_prefix = enhanced_context
        except Exception as e:
            logger.warning(f"LLM enhancement failed, using rule-based context: {e}")

    return ContextGenerationResult(
        document_id=document_id,
        document_type=document_type,
        context_prefix=context_prefix,
        document_summary=doc_summary,
        key_entities=key_entities,
        metadata={},
    )
```

- [ ] **Step 7: Rewrite `_enhance_with_llm()`**

Before (signature uses `DomainDetectionResult`):
```python
async def _enhance_with_llm(self, text: str, domain_result: DomainDetectionResult, llm_client) -> Optional[str]:
    ...
    prompt = f"""Genera un contexto BREVE (máximo 100 palabras) para este fragmento de documento.

DOMINIO DETECTADO: {domain_result.primary_domain.value}
LEGISLACIÓN APLICABLE: {', '.join(l.to_citation() for l in domain_result.applicable_laws[:3])}

DOCUMENTO (primeros 1000 caracteres):
{text[:1000]}
...
```

After:
```python
async def _enhance_with_llm(
    self, text: str, document_type: str, key_entities: List[str], llm_client
) -> Optional[str]:
    """Use LLM to generate enhanced contextual prefix from document_type + entities."""
    if len(text) < 200:
        return None

    entities_text = ", ".join(key_entities[:5]) if key_entities else "(ninguna extraída)"
    prompt = f"""Genera un contexto BREVE (máximo 100 palabras) para este fragmento de documento.

TIPO DE DOCUMENTO: {document_type}
ENTIDADES CLAVE: {entities_text}

DOCUMENTO (primeros 1000 caracteres):
{text[:1000]}

FORMATO REQUERIDO:
[CONTEXTO] [Tipo de documento]. [Descripción breve]. Entidades: [entidades relevantes]. [CONTENIDO]

Responde SOLO con el contexto, sin explicaciones adicionales. /no_think"""

    try:
        response = await llm_client.chat(
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
            max_tokens=200,
        )
        if response and response.content:
            context = re.sub(r"<think>.*?</think>\s*", "", response.content, flags=re.DOTALL).strip()
            if not context.startswith("[CONTEXTO]"):
                context = f"[CONTEXTO] {context}"
            if not context.endswith("[CONTENIDO]"):
                context = f"{context} [CONTENIDO]"
            return context
    except Exception as e:
        logger.warning(f"LLM context enhancement failed: {e}")
    return None
```

- [ ] **Step 8: Simplify `_extract_key_entities()`**

Before:
```python
def _extract_key_entities(self, text: str, domain: LegalDomain) -> List[str]:
    entities = []
    # Common patterns
    # Dates
    date_pattern = r'\d{1,2}[/-]\d{1,2}[/-]\d{2,4}'
    dates = re.findall(date_pattern, text)
    entities.extend([f"fecha:{d}" for d in dates[:3]])
    # Money amounts (EUR)
    money_pattern = r'(\d{1,3}(?:\.\d{3})*(?:,\d{2})?)\s*(?:€|euros?|EUR)'
    amounts = re.findall(money_pattern, text, re.IGNORECASE)
    entities.extend([f"importe:{a}€" for a in amounts[:3]])
    # NIFs/CIFs
    nif_pattern = r'[A-Z]?\d{7,8}[A-Z]'
    nifs = re.findall(nif_pattern, text)
    entities.extend([f"nif:{n}" for n in nifs[:2]])
    return entities[:10]
```

After (identical body, `domain` param removed — the extraction is domain-agnostic regex):
```python
def _extract_key_entities(self, text: str) -> List[str]:
    """Extract common entities (dates, money, NIFs) from document text."""
    entities = []
    date_pattern = r'\d{1,2}[/-]\d{1,2}[/-]\d{2,4}'
    dates = re.findall(date_pattern, text)
    entities.extend([f"fecha:{d}" for d in dates[:3]])
    money_pattern = r'(\d{1,3}(?:\.\d{3})*(?:,\d{2})?)\s*(?:€|euros?|EUR)'
    amounts = re.findall(money_pattern, text, re.IGNORECASE)
    entities.extend([f"importe:{a}€" for a in amounts[:3]])
    nif_pattern = r'[A-Z]?\d{7,8}[A-Z]'
    nifs = re.findall(nif_pattern, text)
    entities.extend([f"nif:{n}" for n in nifs[:2]])
    return entities[:10]
```

- [ ] **Step 9: Update `indexing_pipeline.py`**

Search for usages of the old API:

```bash
grep -n "context_result\|contextual_domain\|contextual_laws\|domain_result\|applicable_laws" backend/microservices/weaviate-service/app/services/rag/indexing_pipeline.py
```

For each usage:
- `chunk.metadata["contextual_domain"] = contextual_domain` → delete the line
- `chunk.metadata["contextual_laws"] = applicable_laws` → delete the line
- Any `domain_result.xxx` access → replace with `context_result.document_type`
- Any consumer of `ContextGenerationResult.domain` → replace with `.document_type`
- Any consumer of `ContextGenerationResult.applicable_laws` → delete

- [ ] **Step 10: Update `context_enricher.py`**

```bash
grep -n "domain" backend/microservices/weaviate-service/app/services/rag/context_enricher.py
```

Expected finds: test/example metadata `{"domain": "labor"}` on line ~25, and a docstring mention on line ~129.

Delete `"domain": "labor"` from the example metadata dict. Update docstring to remove the "(title, domain, etc.)" phrasing.

- [ ] **Step 11: Verify imports and no orphan symbols**

```bash
docker exec docker-weaviate-service-1 python -c "
from app.services.rag.contextual_retrieval import ContextualRetrievalService, ContextGenerationResult, ContextualizedChunk
svc = ContextualRetrievalService()
assert not hasattr(svc, 'detect_domain'), 'detect_domain still exists'
assert not hasattr(svc, '_get_applicable_laws'), '_get_applicable_laws still exists'
result = ContextGenerationResult(document_id='x', document_type='contrato', context_prefix='', document_summary='', key_entities=[])
assert not hasattr(result, 'domain'), 'ContextGenerationResult.domain still exists'
assert not hasattr(result, 'applicable_laws'), 'ContextGenerationResult.applicable_laws still exists'
print('ContextualRetrievalService + dataclasses clean')
"
```

Expected: prints "ContextualRetrievalService + dataclasses clean". If any assertion fires, stop.

- [ ] **Step 12: Verify weaviate-service main still imports**

```bash
docker exec docker-weaviate-service-1 python -c "from app.main import app; print('weaviate-service main ok, routes:', len(app.routes))"
```

Expected: prints count (was 45 before; might be 44-45 now since we didn't add/remove routes).

- [ ] **Step 13: Commit Phase 2**

```bash
git add backend/microservices/weaviate-service/app/services/rag/contextual_retrieval.py \
        backend/microservices/weaviate-service/app/services/rag/context_enricher.py \
        backend/microservices/weaviate-service/app/services/rag/indexing_pipeline.py

git commit -m "$(cat <<'EOF'
refactor(weaviate-service): simplify ContextualRetrievalService without domain

Phase 2/9 of domain-field removal. The contextual retrieval module had
its own parallel domain detector (keyword scoring over SPANISH_LEGISLATION
dict) producing LegalDomain enum values, independent from and potentially
contradicting the classifier's domain. Eliminated.

- LegalDomain enum, SPANISH_LEGISLATION dict, LawReference, DomainDetectionResult: removed
- detect_domain(), _get_applicable_laws(): removed
- ContextGenerationResult: `domain` + `applicable_laws` fields removed, `document_type` added
- ContextualizedChunk: same shape change
- analyze_document(): rewritten to use document_type + entities; no domain detection step
- generate_context_prefix(): new signature (document_type, key_entities)
- _enhance_with_llm(): prompt uses TIPO DE DOCUMENTO + ENTIDADES CLAVE instead of domain+laws
- _extract_key_entities(): drop unused `domain` param
- indexing_pipeline.py: drop `contextual_domain` / `contextual_laws` metadata writes
- context_enricher.py: drop `"domain": "labor"` example metadata

applicable_laws is no longer precomputed per document. The agent queries
TrustGraph via graph_rag when it needs legal context, which is cheaper
and more precise (laws match the question, not the document).

Spec: docs/superpowers/specs/2026-04-22-remove-domain-field-design.md
EOF
)"
```

---

## Phase 3 — Entity extraction + TrustGraph entity schema

### Task 3: Remove domain detection from extraction_service + triples

**Files:**
- Modify: `backend/microservices/weaviate-service/app/services/knowledge/extraction_service.py`
- Modify: `backend/microservices/knowledge-tree-service/app/schemas/triples.py`
- Modify: `backend/microservices/knowledge-tree-service/app/services/extractors/coordinator.py`
- Modify: `backend/microservices/knowledge-tree-service/app/services/triple_store.py`
- Modify: `backend/microservices/knowledge-tree-service/tests/test_coordinator.py`
- Modify: `backend/microservices/knowledge-tree-service/tests/test_triple_store.py`
- Modify: `backend/microservices/knowledge-tree-service/tests/test_triple_query.py`
- Modify: `backend/microservices/knowledge-tree-service/tests/test_integration_pipeline.py`
- Modify: `backend/microservices/knowledge-tree-service/tests/conftest.py`
- Modify: `backend/microservices/knowledge-tree-service/tests/run_tests.sh`
- Modify: `backend/microservices/background-worker/worker_app/tasks/trustgraph_tasks.py`

- [ ] **Step 1: Survey domain usage in extraction_service.py**

```bash
grep -n "domain\|DomainType" backend/microservices/weaviate-service/app/services/knowledge/extraction_service.py
```

Identify: `DomainType` enum definition, `_domain_keywords` dict, `_detect_domain()` method, per-entity `domain` field writes, `result.domain = domain` line.

- [ ] **Step 2: Remove `DomainType` enum and `_domain_keywords`**

Edit `extraction_service.py`:
- Delete the `class DomainType(str, Enum)` block (find with `grep -n "class DomainType"`)
- Delete the `self._domain_keywords = {...}` assignment in `__init__` (around L 101)
- Delete the `async def _detect_domain(self, content, document_type)` method

- [ ] **Step 3: Remove domain propagation in `extract()` / main flow**

In the same file:
- Remove `domain = await self._detect_domain(content, document_type)` call
- Remove `if entity.domain == DomainType.GENERAL: entity.domain = domain` branch
- Remove `result.domain = domain` line
- Remove `domain=entity.domain` in any downstream construction
- Remove `domain: Optional[str] = None` and `domain=domain` in function signatures that receive/pass it

- [ ] **Step 4: Remove `domain` from knowledge-tree-service Pydantic schemas**

```bash
grep -n "domain" backend/microservices/knowledge-tree-service/app/schemas/triples.py
```

For each Pydantic model containing `domain: Optional[str]` or similar, delete the field. Typical offenders:
- `EntityCreate`
- `TripleCreate`
- `EntityResponse`

Example before:
```python
class EntityCreate(BaseModel):
    name: str
    entity_type: str
    domain: Optional[str] = None  # ← remove
    properties: Dict[str, Any] = Field(default_factory=dict)
```

After:
```python
class EntityCreate(BaseModel):
    name: str
    entity_type: str
    properties: Dict[str, Any] = Field(default_factory=dict)
```

- [ ] **Step 5: Clean coordinator and triple_store**

```bash
grep -n "domain" backend/microservices/knowledge-tree-service/app/services/extractors/coordinator.py
grep -n "domain" backend/microservices/knowledge-tree-service/app/services/triple_store.py
```

For each occurrence, evaluate:
- If `domain` is passed to FalkorDB via Cypher MERGE/CREATE → delete the property
- If `domain` is a function parameter with no use → delete the param
- If it's a dict key being read (`metadata.get("domain")`) → delete the line

- [ ] **Step 6: Update knowledge-tree tests**

For each test file, remove assertions on `domain` and fixture data that sets `domain`:

```bash
for f in backend/microservices/knowledge-tree-service/tests/test_coordinator.py \
         backend/microservices/knowledge-tree-service/tests/test_triple_store.py \
         backend/microservices/knowledge-tree-service/tests/test_triple_query.py \
         backend/microservices/knowledge-tree-service/tests/test_integration_pipeline.py \
         backend/microservices/knowledge-tree-service/tests/conftest.py; do
    echo "=== $f ==="
    grep -n "domain" "$f"
done
```

Read each file, remove `domain=...` kwargs and `result.domain == "..."` assertions. Update fixtures accordingly.

For `run_tests.sh`, grep for any `--domain` CLI flag or env var, remove.

- [ ] **Step 7: Clean background-worker**

```bash
grep -n "domain" backend/microservices/background-worker/worker_app/tasks/trustgraph_tasks.py
```

For each match, remove `domain` from task payloads and Redis stream messages.

- [ ] **Step 8: Verify imports**

```bash
docker exec docker-weaviate-service-1 python -c "from app.services.knowledge.extraction_service import *; print('extraction_service ok')"
docker exec docker-knowledge-tree-service-1 python -c "from app.main import app; print('knowledge-tree main ok, routes:', len(app.routes))"
docker exec docker-background-worker-1 python -c "from worker_app.tasks.trustgraph_tasks import *; print('trustgraph_tasks ok')"
```

Expected: all print "ok" messages.

- [ ] **Step 9: Commit Phase 3**

```bash
git add backend/microservices/weaviate-service/app/services/knowledge/extraction_service.py \
        backend/microservices/knowledge-tree-service/app/schemas/triples.py \
        backend/microservices/knowledge-tree-service/app/services/extractors/coordinator.py \
        backend/microservices/knowledge-tree-service/app/services/triple_store.py \
        backend/microservices/knowledge-tree-service/tests/ \
        backend/microservices/background-worker/worker_app/tasks/trustgraph_tasks.py

git commit -m "$(cat <<'EOF'
refactor(knowledge+worker): drop `domain` from entity extraction

Phase 3/9. Third and final parallel domain detector (in
extraction_service.py with its own DomainType enum and _domain_keywords
dict) removed. Entities and triples in TrustGraph no longer carry a
`domain` property — entity_type is granular enough for graph queries.

- weaviate-service/extraction_service.py: DomainType enum, _domain_keywords,
  _detect_domain() removed; entity/result domain propagation removed
- knowledge-tree-service/schemas/triples.py: Pydantic `domain` fields removed
- coordinator.py, triple_store.py: Cypher property writes and param passes cleaned
- tests: fixtures and assertions updated
- background-worker/trustgraph_tasks.py: task payloads cleaned

Spec: docs/superpowers/specs/2026-04-22-remove-domain-field-design.md
EOF
)"
```

---

## Phase 4 — Weaviate schema + indexing + search

### Task 4: Remove `domain` property and `domain_filter` from Weaviate

**Files:**
- Modify: `backend/microservices/weaviate-service/app/schemas/weaviate.py`
- Modify: `backend/microservices/weaviate-service/app/services/weaviate_service.py`
- Modify: `backend/microservices/weaviate-service/app/api/weaviate.py`

- [ ] **Step 1: Delete `domain` from Pydantic request/response models**

File: `backend/microservices/weaviate-service/app/schemas/weaviate.py`

Find (exact lines):
```python
# Line 27
domain: Optional[str] = Field(default="", description="Business domain (e.g., legal, fiscal, medical)")

# Line 90
domain: Optional[str] = None

# Line 115
domain_filter: Optional[str] = Field(default=None, description="Filter by business domain (e.g., legal, fiscal)")
```

Delete all 3 lines. Do not touch `semantic_type`, `semantic_type_filter`, `quality_score` — those stay.

- [ ] **Step 2: Delete `domain` property from Weaviate collection schema**

In the same file, find the `Nouxcube_documents` collection schema definition (has `"name": "Nouxcube_documents"`). Look for the properties list:

```bash
grep -n '"name": "Nouxcube_documents"\|"name": "domain"\|"name": "semantic_type"' backend/microservices/weaviate-service/app/schemas/weaviate.py
```

Find the property block:
```python
{
    "name": "domain",
    "dataType": ["text"],
    "description": "Business domain",
    ...
},
```

Delete this entire property block. Keep `semantic_type` and others.

- [ ] **Step 3: Update indexing to stop writing `domain`**

File: `backend/microservices/weaviate-service/app/services/weaviate_service.py`

Find L ~976:
```python
"domain": chunk_metadata.get("domain", "") or base_properties.get("domain", ""),
```

Delete this line.

- [ ] **Step 4: Update search to remove `domain_filter` branch**

Same file, L ~1264-1268:
```python
domain_filter = getattr(search_request, 'domain_filter', None)
if domain_filter and "domain" in _schema_props:
    f = Filter.by_property("domain").equal(domain_filter)
    ...
    logger.debug(f"🏷️ Filtering by domain: {domain_filter}")
```

Delete this entire block (the `domain_filter` variable + the if branch).

Also L ~1403:
```python
getattr(search_request, 'domain_filter', None),
```

Delete this argument from whatever function call it's in (may need to also remove the corresponding parameter in the callee's signature).

- [ ] **Step 5: Update module docstring (L ~3-7)**

Before:
```python
Single-org refactor: collections are fixed (Nouxcube_documents,
Nouxcube_knowledge, Nouxcube_visual, TrustGraphEntities, OntologyTerms).
ACL is enforced by the ``roles`` TEXT_ARRAY property + the ``EVERYONE``
sentinel. Legal/BOE knowledge is unified into TrustGraph (FalkorDB).
```

No change needed (already clean from PublicKnowledge cleanup). Verify nothing mentions `domain`.

- [ ] **Step 6: Clean api/weaviate.py**

```bash
grep -n "domain" backend/microservices/weaviate-service/app/api/weaviate.py
```

Expected finds:
- L 1265: `domain_filter: Optional[str] = None` in a request model — delete
- L 1292: `domain_filter=request.domain_filter` in a call — delete the kwarg

Remove both.

- [ ] **Step 7: Verify imports + schema**

```bash
docker exec docker-weaviate-service-1 python -c "
from app.schemas.weaviate import SearchRequest, IndexingRequest
req = SearchRequest(query='test')
assert not hasattr(req, 'domain_filter'), 'domain_filter still present'
print('SearchRequest has no domain_filter')
"

docker exec docker-weaviate-service-1 python -c "from app.main import app; print('weaviate-service main ok')"
```

- [ ] **Step 8: Commit Phase 4**

```bash
git add backend/microservices/weaviate-service/app/schemas/weaviate.py \
        backend/microservices/weaviate-service/app/services/weaviate_service.py \
        backend/microservices/weaviate-service/app/api/weaviate.py

git commit -m "$(cat <<'EOF'
refactor(weaviate-service): drop `domain` property and `domain_filter`

Phase 4/9. Weaviate Nouxcube_documents no longer stores `domain` as a
first-class property. Hybrid search no longer accepts `domain_filter`.
Consumers that want to filter by business area use `semantic_type_filter`
with a list of types.

- schemas/weaviate.py: Pydantic fields + Weaviate class schema property removed
- weaviate_service.py: indexing write (L ~976) + search filter branch (L ~1264) removed
- api/weaviate.py: request model field + endpoint kwarg removed

Weaviate was empty (0 Nouxcube_documents objects) so no data migration.

Spec: docs/superpowers/specs/2026-04-22-remove-domain-field-design.md
EOF
)"
```

---

## Phase 5 — Emma agent + tool

### Task 5: Remove `domain_filter` from smart_search tool + emma service refs

**Files:**
- Modify: `backend/microservices/emma-agent-service/app/agents/langgraph/tools/smart_search.py`
- Modify: `backend/microservices/emma-agent-service/app/agents/langgraph/sectors/config.py`
- Modify: `backend/microservices/emma-agent-service/app/clients/weaviate_client.py`
- Modify: `backend/microservices/emma-agent-service/app/clients/knowledge_tree_client.py`
- Modify: `backend/microservices/emma-agent-service/app/core/config.py`
- Modify: `backend/microservices/emma-agent-service/app/core/langfuse_config.py`
- Modify: `backend/microservices/emma-agent-service/app/services/memorag/service.py`
- Modify: `backend/microservices/emma-agent-service/app/services/memory/memory_generator.py`
- Modify: `backend/microservices/emma-agent-service/app/services/predictive_analysis/service.py`
- Modify: `backend/microservices/emma-agent-service/app/services/predictive_analysis/prediction_synthesizer.py`
- Modify: `backend/microservices/emma-agent-service/app/services/rule_engine.py`
- Modify: `backend/microservices/emma-agent-service/app/services/few_shot_retriever.py`
- Modify: `backend/microservices/emma-agent-service/app/services/guardrail_registry.py`
- Modify: `backend/microservices/emma-agent-service/app/schemas/predictive_analysis.py`
- Modify: `backend/microservices/emma-agent-service/app/schemas/prompts.py`
- Modify: `backend/microservices/emma-agent-service/app/api/emma.py`
- Modify: `backend/microservices/emma-agent-service/app/api/explainability.py`
- Modify: `backend/microservices/emma-agent-service/app/workers/event_listener.py`
- Modify: `backend/microservices/emma-agent-service/app/agents/langgraph/tools/specialists.py`
- Modify: `backend/microservices/emma-agent-service/app/agents/langgraph/sectors/predictive_config.py`
- Modify: `backend/microservices/emma-agent-service/app/agents/langgraph/sectors/registry.py`
- Modify: `backend/microservices/emma-agent-service/scripts/migrate_retrieval_intelligence_prompts.py`

- [ ] **Step 1: Update smart_search.py — remove tool param + logic**

File: `backend/microservices/emma-agent-service/app/agents/langgraph/tools/smart_search.py`

Find and delete:
- L ~190-192: the `domain_filter: Optional[str] = Field(default=None, ...)` tool param
- L ~239: `domain_filter = arguments.get("domain_filter")` line
- L ~264: `enriched_domain = domain_filter` line
- L ~311: `domain_filter=enriched_domain,` kwarg (inside a call — remove only this line within the call)
- L ~368-369: `enriched_domain=enriched_domain,` inside `_fan_out_search` or similar caller
- L ~381: `domain_filter=enriched_domain,` (second call site)
- L ~625-627: `enriched_domain: Optional[str],` function parameter signature line
- L ~652-653: `domain_filter=enriched_domain,` (third call site)
- L ~704: `"domain": r.metadata.get("domain", ""),` line in result serialization

For each call site that passed `domain_filter=enriched_domain`, also remove that kwarg from the callee's signature if it was there.

- [ ] **Step 2: Clean sectors/config.py**

File: `backend/microservices/emma-agent-service/app/agents/langgraph/sectors/config.py`

Find L ~96:
```python
"name", "title", "short_name", "boe_id", "domain",
```

Change to:
```python
"name", "title", "short_name", "boe_id",
```

Also check L 137 for `men_domain` — this is **NOT** related to business domain, it's medical mental-domain. Verify context; keep unless you confirm otherwise.

Update docstring at top of file (L 2-10) if it explicitly says "all domains" in the sector-config sense:

Before:
```python
"""Single configuration for all domains. The knowledge graph provides
dynamic context per query.

Entity patterns from all domains (legal, medical, documental) are merged
into this single config.
"""
```

After:
```python
"""Unified entity-pattern configuration.

Entity patterns from all prior sector configs (legal, medical,
documental) are merged into this single config. Per-query context is
provided dynamically by the knowledge graph.
"""
```

- [ ] **Step 3: Audit and clean remaining emma service files**

For each file in the Task 5 file list, run:

```bash
for f in \
  backend/microservices/emma-agent-service/app/clients/weaviate_client.py \
  backend/microservices/emma-agent-service/app/clients/knowledge_tree_client.py \
  backend/microservices/emma-agent-service/app/core/config.py \
  backend/microservices/emma-agent-service/app/core/langfuse_config.py \
  backend/microservices/emma-agent-service/app/services/memorag/service.py \
  backend/microservices/emma-agent-service/app/services/memory/memory_generator.py \
  backend/microservices/emma-agent-service/app/services/predictive_analysis/service.py \
  backend/microservices/emma-agent-service/app/services/predictive_analysis/prediction_synthesizer.py \
  backend/microservices/emma-agent-service/app/services/rule_engine.py \
  backend/microservices/emma-agent-service/app/services/few_shot_retriever.py \
  backend/microservices/emma-agent-service/app/services/guardrail_registry.py \
  backend/microservices/emma-agent-service/app/schemas/predictive_analysis.py \
  backend/microservices/emma-agent-service/app/schemas/prompts.py \
  backend/microservices/emma-agent-service/app/api/emma.py \
  backend/microservices/emma-agent-service/app/api/explainability.py \
  backend/microservices/emma-agent-service/app/workers/event_listener.py \
  backend/microservices/emma-agent-service/app/agents/langgraph/tools/specialists.py \
  backend/microservices/emma-agent-service/app/agents/langgraph/sectors/predictive_config.py \
  backend/microservices/emma-agent-service/app/agents/langgraph/sectors/registry.py; do
    echo "=== $f ==="
    grep -n "domain" "$f"
done
```

For each match, **classify before editing**:
- If `domain` is business-domain (legal/fiscal/medical) → remove
- If it's email `domain`, URL `domain`, `DomainError`, `damain` (typo), `DomainName` (hostname class), `Domain` as a word in docstring referring to problem domain → **KEEP**

Use your judgment. When unsure, show the line context with `-C 3` and decide. Record any ambiguous cases; don't silently delete.

Typical patterns to delete:
- `domain: Optional[str] = Field(...)` in Pydantic models for requests/responses
- `metadata.get("domain")` / `meta["domain"]`
- `domain=...` kwargs being passed down
- `DomainType`, `LegalDomain` imports (already deleted in earlier phases; remove orphan imports)

Typical patterns to keep:
- `DomainError` (exception class name)
- `"domain"` inside `urlparse().netloc` or similar URL parsing
- `men_domain` (medical mental domain, in-code identifier with different semantics)

- [ ] **Step 4: Clean migrate_retrieval_intelligence_prompts.py script**

```bash
grep -n "domain" backend/microservices/emma-agent-service/scripts/migrate_retrieval_intelligence_prompts.py
```

This is a one-off migration script. If it embeds `domain_filter` references in prompt text being pushed to Langfuse, update the embedded prompt text. If it's purely historical, evaluate deleting it (check last-modified and uses).

- [ ] **Step 5: Verify emma-agent-service imports**

```bash
docker exec docker-emma-agent-service-1 python -c "from app.main import app; print('emma main ok, routes:', len(app.routes))"
docker exec docker-emma-agent-service-1 python -c "
from app.agents.langgraph.tools.smart_search import SmartSearchTool
tool = SmartSearchTool()
schema = tool.args_schema.model_json_schema() if tool.args_schema else tool.to_openai_function()
import json
fields = schema.get('properties', {}) if isinstance(schema, dict) else {}
assert 'domain_filter' not in fields, f'domain_filter still in tool schema: {list(fields.keys())}'
print('smart_search tool schema clean:', list(fields.keys()))
"
```

Expected: prints field list without `domain_filter`.

- [ ] **Step 6: Commit Phase 5**

```bash
git add backend/microservices/emma-agent-service/

git commit -m "$(cat <<'EOF'
refactor(emma-agent-service): drop `domain_filter` tool param + domain refs

Phase 5/9. The smart_search tool no longer exposes `domain_filter` to
the ReAct agent. Consumers that want to filter by business area use
`semantic_type_filter` with a list of types (more precise). Emma service
files audited for domain references; all business-domain refs removed,
URL/email/error-class usages preserved.

- smart_search.py: domain_filter param, enriched_domain logic, metadata
  serialization cleaned
- sectors/config.py: "domain" removed from graph search properties;
  docstring clarified
- Client wrappers, config, API, workers, schemas, services: ~20 files
  audited, business-domain references removed

Langfuse prompt `emma_react_system` must be promoted separately via the
Langfuse UI to remove any references to `domain_filter` in the tool
description. Until then, the LLM may emit tool calls with that argument,
which the tool will reject as unknown kwarg — acceptable transient
behavior.

Spec: docs/superpowers/specs/2026-04-22-remove-domain-field-design.md
EOF
)"
```

---

## Phase 6 — Backend API + connectors

### Task 6: Clean backend/app and core/connectors

**Files:**
- Modify: `backend/app/api/v1/weaviate.py`
- Modify: `backend/app/services/weaviate_client.py`
- Modify: `backend/app/services/unified_indexing_service.py`
- Modify: `backend/app/services/data_learning/content_model_discovery.py`
- Modify: `backend/app/services/data_learning/indexing_strategy_optimizer.py`
- Modify: `backend/app/schemas/connector.py`
- Modify: `backend/app/schemas/data_learning.py`
- Modify: `backend/app/db/models.py`
- Modify: `backend/core/connectors/metadata_schema.py`
- Modify: `backend/core/connectors/adapters/base.py`
- Modify: `backend/core/connectors/adapters/google_drive.py`
- Modify: `backend/core/connectors/adapters/alfresco.py`

- [ ] **Step 1: Survey backend/app**

```bash
for f in \
  backend/app/api/v1/weaviate.py \
  backend/app/services/weaviate_client.py \
  backend/app/services/unified_indexing_service.py \
  backend/app/services/data_learning/content_model_discovery.py \
  backend/app/services/data_learning/indexing_strategy_optimizer.py \
  backend/app/schemas/connector.py \
  backend/app/schemas/data_learning.py \
  backend/app/db/models.py; do
    echo "=== $f ==="
    grep -n "domain" "$f"
done
```

- [ ] **Step 2: Classify each match (business-domain vs unrelated)**

For each match, **classify before editing**:

**REMOVE** when it means business-domain (legal/fiscal/medical):
- `domain: Optional[str]` in Pydantic `DocumentIndex`, `DocumentMetadata`, connector payloads
- `metadata.get("domain")` / `meta["domain"]` reads when the lookup is about document business area
- `domain=...` kwargs propagating business-area labels
- Data-learning heuristic scoring columns/dicts named `domain`
- `LegalDomain` / `DomainType` imports (orphans from earlier phases)

**KEEP** when `domain` refers to something unrelated:
- `DomainError` or any exception class name
- `"domain"` inside URL parsing (`urlparse().netloc`, `request.url.domain`)
- Email `domain` references (`user@domain.com` splits)
- `Domain` as an English word in docstrings ("problem domain", "input domain")
- `DomainName` class for hostnames

When unsure, read ±3 lines of context. Do NOT silently delete.

**SPECIAL CASE — `db/models.py`**: if a SQLAlchemy column `domain = Column(String)` exists on a model, dropping it needs an Alembic migration (even though `indexed_documents` is empty per spec preconditions). Process:
1. Check with: `grep -n "domain.*Column\|^\s*domain\s*=\s*Column" backend/app/db/models.py`
2. If found, flag to user BEFORE editing — we need to coordinate: generate migration, inspect it, commit together.
3. If not found, proceed with code-only removal.

- [ ] **Step 3: Clean connector adapters**

```bash
grep -n "domain" backend/core/connectors/metadata_schema.py \
                 backend/core/connectors/adapters/base.py \
                 backend/core/connectors/adapters/google_drive.py \
                 backend/core/connectors/adapters/alfresco.py
```

Adapters currently emit `domain` as part of the connector metadata dict. Remove it from:
- `base.py`: the `ConnectorMetadata` schema / base class attribute
- `google_drive.py` + `alfresco.py`: the adapter-specific emission (often an inferred value from filename)
- `metadata_schema.py`: field definitions

- [ ] **Step 4: SPECIAL CASE — backend/app/db/models.py**

If `domain` is a column on an SQLAlchemy model, writing an Alembic migration is needed:

```bash
grep -n "domain.*Column\|^ *domain " backend/app/db/models.py
```

If a column exists:
- Create migration: `cd backend && python scripts/create_migration.py -m "drop_domain_column" --autogenerate`
- The migration auto-generates a `drop_column` operation
- Verify the migration doesn't touch unrelated tables
- Add migration file to this phase's commit

If no column: skip migration, just remove field refs in code.

- [ ] **Step 5: Verify backend api imports**

```bash
docker exec docker-api-1 python -c "from app.main import app; print('backend api main ok, routes:', len(app.routes))"
```

- [ ] **Step 6: Commit Phase 6**

```bash
git add backend/app/ backend/core/connectors/

# If an alembic migration was generated, also add it:
# git add backend/alembic/versions/xxxxx_drop_domain_column.py

git commit -m "$(cat <<'EOF'
refactor(backend+connectors): drop `domain` from models, schemas, adapters

Phase 6/9. Backend FastAPI, unified indexing service, data learning, and
connector adapters stop emitting/consuming the `domain` field in their
payloads and metadata.

- app/api/v1/weaviate.py, services/weaviate_client.py: request/response
  field passes cleaned
- app/services/unified_indexing_service.py: metadata normalization no
  longer propagates domain
- app/services/data_learning/*: heuristic scoring column removed
- app/schemas/connector.py, data_learning.py: Pydantic fields removed
- app/db/models.py: (if applicable) SQLAlchemy `domain` column removed
  + alembic migration attached
- core/connectors/metadata_schema.py, adapters/{base,google_drive,alfresco}.py:
  domain field removed from connector metadata contract

Spec: docs/superpowers/specs/2026-04-22-remove-domain-field-design.md
EOF
)"
```

---

## Phase 7 — Frontend + scripts + env cleanup

### Task 7: Frontend types + delete orphan script + env cleanup

**Files:**
- Modify: `frontend/src/lib/services/data-learning.service.ts`
- Delete: `backend/scripts/contextualize_chunks.py`
- Modify: `backend/docker/.env`
- Modify: `backend/docker/docker-compose.yml.saas`
- Modify: `backend/docker/docker-compose.onpremise.yml`

- [ ] **Step 1: Clean frontend data-learning types**

```bash
grep -n "domain" frontend/src/lib/services/data-learning.service.ts
```

For each match classify business-domain vs URL-domain (this file deals with data learning, so likely business-domain). Remove field from TS types, remove from request/response shapes, remove any UI references (there shouldn't be any in this service file).

- [ ] **Step 2: Delete contextualize_chunks.py**

Verify no import references first:

```bash
grep -rn "contextualize_chunks" backend/ frontend/ docs/ 2>/dev/null | grep -v "docs/superpowers"
```

Expected: 0 live references. If any exist (e.g., in a compose command or another script), stop and resolve.

Delete:
```bash
rm backend/scripts/contextualize_chunks.py
```

- [ ] **Step 3: Remove `ACTIVE_SECTOR` from env**

File: `backend/docker/.env`

```bash
grep -n "ACTIVE_SECTOR\|ACTIVE_DOMAIN\|DOMAIN_" backend/docker/.env
```

Expected: `ACTIVE_SECTOR=documental` at L ~267. Delete the line (and surrounding comment/section header if appropriate).

- [ ] **Step 4: Scan compose files**

```bash
grep -n "ACTIVE_SECTOR\|ACTIVE_DOMAIN\|DOMAIN_" backend/docker/docker-compose.yml.saas backend/docker/docker-compose.onpremise.yml
```

Remove any `ACTIVE_SECTOR: ${ACTIVE_SECTOR:-...}` entries from environment blocks. Do **NOT** touch entries related to URL `DOMAIN=...` (e.g., for reverse proxy).

- [ ] **Step 5: Verify containers still boot after env change**

```bash
docker compose -f backend/docker/docker-compose.yml -f backend/docker/docker-compose.onpremise.yml config --quiet && echo "compose config valid"
```

Expected: prints "compose config valid". If error, fix YAML and retry.

Optionally restart one service to confirm env works:
```bash
docker compose -f backend/docker/docker-compose.yml -f backend/docker/docker-compose.onpremise.yml restart emma-agent-service
sleep 5
docker compose -f backend/docker/docker-compose.yml -f backend/docker/docker-compose.onpremise.yml ps emma-agent-service
```

Expected: `healthy`.

- [ ] **Step 6: Commit Phase 7**

```bash
git add frontend/src/lib/services/data-learning.service.ts \
        backend/docker/.env \
        backend/docker/docker-compose.yml.saas \
        backend/docker/docker-compose.onpremise.yml

# contextualize_chunks.py is deleted — git add -u covers it, or explicitly:
git add -u backend/scripts/contextualize_chunks.py 2>/dev/null || true

git commit -m "$(cat <<'EOF'
chore: delete domain-dependent script, remove ACTIVE_SECTOR env, clean frontend types

Phase 7/9.

- frontend/src/lib/services/data-learning.service.ts: TS types cleaned
  (domain field removed from data learning contract)
- backend/scripts/contextualize_chunks.py: deleted (depended on
  applicable_laws + detect_domain, both removed in Phase 2; confirmed no
  cron/scheduler references the script)
- backend/docker/.env: ACTIVE_SECTOR=documental removed (ignored since
  2026-03-31 sector unification)
- docker-compose.*.yml: any ACTIVE_SECTOR references cleaned

URL `DOMAIN=nouxcube.com` variables preserved — those are hostname
config, not business-domain.

Spec: docs/superpowers/specs/2026-04-22-remove-domain-field-design.md
EOF
)"
```

---

## Phase 8 — Docs

### Task 8: Update CLAUDE.md + architecture docs

**Files:**
- Modify: `CLAUDE.md`
- Modify: `docs/architecture/EMMA_AI.md`
- Modify: `docs/architecture/SIL.md`
- Modify: `docs/architecture/SLM_ROUTER.md`

- [ ] **Step 1: Update CLAUDE.md Enrichment Properties section**

```bash
grep -n "domain\|Enrichment Properties" CLAUDE.md
```

Find the "Enrichment Properties" section. Current text (approximately):

Before:
```
**Enrichment Properties** (first-class Weaviate properties, not JSONB):
- `domain` — Business domain (legal, fiscal, medical)
- `semantic_type` — Document type (factura, contrato, nomina)
- `quality_score` — Quality 0.0-1.0 from DocumentIntelligence
- `associated_person` — Person from folder hierarchy or entity extraction
```

After:
```
**Enrichment Properties** (first-class Weaviate properties, not JSONB):
- `semantic_type` — Document type (factura, contrato, nomina, sentencia, etc.) — sole taxonomy
- `quality_score` — Quality 0.0-1.0 from DocumentIntelligence
- `associated_person` — Person from folder hierarchy or entity extraction
```

- [ ] **Step 2: Update CLAUDE.md SmartSearch section**

Find the SmartSearch bullet points. Remove any mention of `domain_filter`:

Before (hypothetical — grep and confirm):
```
- domain_filter: filter by business area
- semantic_type_filter: filter by document type
- person_filter: filter by person
- folder_filter: filter by folder
```

After:
```
- semantic_type_filter: filter by document type (supports list of types)
- person_filter: filter by person
- folder_filter: filter by folder
```

- [ ] **Step 3: Update CLAUDE.md 5-Signal Re-Ranking if it mentions domain**

Grep for `domain` remaining in CLAUDE.md and fix each in context.

- [ ] **Step 4: Update architecture docs**

For each:

```bash
grep -n "domain" docs/architecture/EMMA_AI.md \
                docs/architecture/SIL.md \
                docs/architecture/SLM_ROUTER.md
```

Read each match in context. Replace business-domain references with `document_type` or remove. Update diagrams/flow descriptions to not mention domain detection as a step.

- [ ] **Step 5: Verify no orphan references**

```bash
grep -rln "domain_filter\|LegalDomain\|DomainType\|DomainDetectionResult\|detect_domain\|applicable_laws" \
  backend/ frontend/src/ docs/architecture/ CLAUDE.md README*.md 2>/dev/null \
  | grep -v "superpowers" \
  | grep -v "alembic/versions/_archived"
```

Expected: 0 matches.

- [ ] **Step 6: Commit Phase 8**

```bash
git add CLAUDE.md docs/architecture/

git commit -m "$(cat <<'EOF'
docs: reflect `domain` removal — document_type is sole taxonomy

Phase 8/9. CLAUDE.md and architecture docs updated to reflect the
post-refactor state.

- CLAUDE.md: Enrichment Properties no longer lists `domain` as a
  first-class property; SmartSearch filter list updated to
  (semantic_type_filter, person_filter, folder_filter)
- docs/architecture/EMMA_AI.md: SmartSearch + ingestion flow no longer
  shows domain detection step
- docs/architecture/SIL.md, SLM_ROUTER.md: domain references removed
  or replaced with document_type

Spec: docs/superpowers/specs/2026-04-22-remove-domain-field-design.md
EOF
)"
```

---

## Phase 9 — Final verification + Langfuse prompt handoff

### Task 9: Final sweep and coordination note

**Files:** none (verification + coordination)

- [ ] **Step 1: Global sweep for business-domain references**

```bash
grep -rln "domain" backend/ frontend/src/ docs/architecture/ CLAUDE.md README*.md 2>/dev/null \
  | grep -v "superpowers" \
  | grep -v "alembic/versions/_archived" \
  | grep -v "node_modules"
```

For EVERY file in the output, open and verify each `domain` occurrence is legitimate:
- URL domain
- Email domain
- `DomainError` exception
- Docstring using "domain" as a general English word ("problem domain", "input domain")
- `DOMAIN=nouxcube.com` env var

If any occurrence is a business-domain leftover, create a small fixup commit.

- [ ] **Step 2: All-services import check**

```bash
for c in docker-api-1 docker-weaviate-service-1 docker-emma-agent-service-1 \
         docker-intelligence-docs-service-1 docker-knowledge-tree-service-1 \
         docker-background-worker-1; do
    echo "=== $c ==="
    docker exec "$c" python -c "from app.main import app; print('routes:', len(app.routes))" 2>&1 | tail -3
done
```

Expected: every container prints a route count without import errors.

For `background-worker` which may not have `app.main`, use:
```bash
docker exec docker-background-worker-1 python -c "from worker_app.tasks.trustgraph_tasks import *; print('trustgraph tasks ok')"
```

- [ ] **Step 3: Smart_search tool JSON schema check**

```bash
docker exec docker-emma-agent-service-1 python -c "
from app.agents.langgraph.tools.smart_search import SmartSearchTool
tool = SmartSearchTool()
try:
    schema = tool.args_schema.model_json_schema()
except AttributeError:
    schema = tool.get_input_schema().schema()
fields = schema.get('properties', {})
forbidden = {'domain_filter', 'enriched_domain'}
intersect = forbidden & set(fields.keys())
assert not intersect, f'forbidden fields present: {intersect}'
print('smart_search schema clean:', sorted(fields.keys()))
"
```

Expected: prints `smart_search schema clean: [...]` with no `domain_filter`.

- [ ] **Step 4: E2E query check (optional, requires indexed data)**

Weaviate is empty per preconditions — E2E will find 0 results but should NOT error:

```bash
curl -s -X POST http://localhost:8019/emma/query \
  -H "Content-Type: application/json" \
  -d '{"query": "list contracts", "user_id": "a060f046-9992-4d1a-87c4-fa5c6f8c066c", "user_roles": ["EVERYONE"]}' \
  > /tmp/emma_e2e.json
python3 -c "
import json
d = json.load(open('/tmp/emma_e2e.json'))
print('has response:', 'response' in d or 'answer' in d)
print('no domain_filter error in trace:', 'domain_filter' not in json.dumps(d).lower() or 'error' not in json.dumps(d).lower())
"
```

Expected: response payload present, no `domain_filter`-related error. If the LLM's tool call tries to pass `domain_filter` because Langfuse prompt isn't updated yet, the tool should reject with "unknown argument" and the agent should retry — this is the known transient behavior called out in Phase 5 commit.

- [ ] **Step 5: Write Langfuse prompt handoff note**

Create a file noting the Langfuse action required:

```bash
cat > /tmp/LANGFUSE_HANDOFF.md <<'EOF'
# Langfuse prompt update required — post-domain-removal

After the `refactor: remove domain field` changes are deployed, the
Langfuse prompt `emma_react_system` must be promoted to a new version
with any mention of `domain_filter` removed from the tool descriptions.

Steps:
1. Open Langfuse UI (http://localhost:3002)
2. Navigate to Prompts → `emma_react_system`
3. Edit the prompt: remove `domain_filter` from the `smart_search` tool
   description. The tool now accepts `semantic_type_filter`, `person_filter`,
   `folder_filter` only.
4. Save as new version and promote to `production` label.

Until this is done, the LLM may attempt `smart_search(domain_filter=...)`
calls which the tool will reject. The agent will recover on the next
iteration by retrying without that argument.
EOF
echo "Handoff note written to /tmp/LANGFUSE_HANDOFF.md"
```

Include this note in the PR description or paste it in chat for user reference. Do NOT commit it (it's operational, not code).

- [ ] **Step 6: Decide final commit strategy**

Ask the user: "Phases 1-8 each have their own commit. Do you want to (a) keep them separate for review, or (b) squash into a single `refactor: remove domain field` commit before pushing?"

If (b), run:
```bash
# Interactive-free squash of last 8 commits (Phases 1-8):
git reset --soft HEAD~8
git commit -m "$(cat <<'EOF'
refactor: remove `domain` field across entire stack

Consolidates Phases 1-8 of the domain-removal refactor.

[Include full summary of all 8 phases here, or reference the spec.]

Spec: docs/superpowers/specs/2026-04-22-remove-domain-field-design.md
Plan: docs/superpowers/plans/2026-04-22-remove-domain-field.md
EOF
)"
```

If (a), leave as-is.

- [ ] **Step 7: Push**

```bash
git push origin development
```

Expected: fast-forward push, no conflicts (since we've been on `development` throughout and pulled at plan start).

- [ ] **Step 8: Post-push reminder**

Deliver to user:
- Confirmation that push succeeded
- The `/tmp/LANGFUSE_HANDOFF.md` content (copy-paste into chat)
- Suggestion to watch Emma service logs for `unknown argument 'domain_filter'` errors in the ReAct loop until Langfuse prompt is updated

---

## Acceptance criteria (final checklist)

- [ ] Phase 1-8 commits merged to `development` (either separate or squashed per user choice)
- [ ] Zero business-domain references outside archived migrations and historical specs/plans
- [ ] All 6 service containers import cleanly (`app.main` or equivalent)
- [ ] `smart_search` tool schema has no `domain_filter`
- [ ] `ContextualRetrievalService` has no `detect_domain`, `_get_applicable_laws`
- [ ] Langfuse handoff note delivered to user
- [ ] `backend/scripts/contextualize_chunks.py` deleted
- [ ] `ACTIVE_SECTOR` removed from `backend/docker/.env`
- [ ] CLAUDE.md `Enrichment Properties` section does not list `domain`
