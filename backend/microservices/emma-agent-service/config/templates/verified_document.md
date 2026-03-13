## Documento Verificado
{% if source_filenames %}
**Documento fuente:** {{ source_filenames | join(", ") }}
{% endif %}
{% if source_summary %}
**Resumen:** {{ source_summary }}
{% endif %}

*{{ claims | length }} afirmaciones verificadas · Consulta: {{ query }}*

{% for claim in claims %}
{{ loop.index }}. {{ claim.text }}{% if claim.verification_type == "corroborated" %} [CORROBORADO]{% elif claim.verification_type == "fidelity_only" %} [FIDELIDAD]{% elif claim.verification_type == "independent" %} [VERIFICADO]{% endif %}{% if claim.confidence > 0 %} (confianza: {{ "%.0f"|format(claim.confidence * 100) }}%){% endif %}{% if claim.status == "corrected" and claim.original_text %} *(corregido de: {{ claim.original_text[:50] }}...)*{% endif %}

{% if claim.verification_reason %}   > *{{ claim.verification_reason }}*
{% endif %}
{% if claim.evidence_sources %}   **Fuentes:** {% for src in claim.evidence_sources %}*{{ src.title or src.id }}*{% if src.source == "web" and src.url %} ([enlace]({{ src.url }})){% endif %}{% if src.source == "jurisprudence" and src.roj %} ({{ src.roj }}){% endif %}{% if not loop.last %} · {% endif %}{% endfor %}
{% endif %}
{% endfor %}

{% if sources %}
---

### Fuentes Consultadas ({{ sources | length }})

| Tipo | Título | URL |
|------|--------|-----|
{% for src in sources %}| {% if src.source == "web" or src.source == "public_knowledge" %}Web{% elif src.source == "uploaded" %}Cargado{% elif src.source == "jurisprudence" %}Jurisprudencia{% elif src.source == "doi" %}DOI Validado{% elif src.source == "crossref" %}CrossRef{% elif src.source == "doi_invalid" %}DOI Inválido{% elif src.source == "doi_mismatch" %}DOI No Corresponde{% elif src.source == "citation_unverified" %}Cita No Verificada{% else %}Interno{% endif %} | {{ src.title or src.id }} | {{ src.url or "—" }} |
{% endfor %}
{% endif %}

{% if doi_validations %}
---

### Validación Bibliográfica ({{ doi_validations | selectattr("valid") | list | length }}/{{ doi_validations | length }} DOIs válidos)

| Estado | DOI | Publicación |
|--------|-----|-------------|
{% for dv in doi_validations %}| {% if dv.valid %}✅ Válido{% else %}❌ Inválido{% endif %} | `{{ dv.doi }}` | {% if dv.metadata and dv.metadata.title %}{{ dv.metadata.title }}{% if dv.metadata.authors %} — {{ dv.metadata.authors[:3] | join(", ") }}{% endif %}{% if dv.metadata.year %} ({{ dv.metadata.year }}){% endif %}{% else %}*No se pudo resolver*{% endif %} |
{% endfor %}
{% endif %}

---

### Metodología de Verificación

Cada afirmación se evalúa en dos niveles independientes:

| Tipo | Significado | Confianza máx. |
|------|-------------|:--------------:|
| **[FIDELIDAD]** | La afirmación representa fielmente el documento fuente (NLI entailment), pero no se encontró evidencia independiente. | 80% |
| **[CORROBORADO]** | Fiel al documento fuente **y** respaldada por evidencia independiente (otros documentos, legislación, web). | 100% |
| **[VERIFICADO]** | Sin documento fuente. Respaldada exclusivamente por evidencia independiente externa. | 100% |

**Tier 1 — Fidelidad:** Evaluación NLI que verifica si la afirmación está contenida (*entailed*) en el texto fuente, basada en FACTS Grounding (Google DeepMind, 2024). Confianza limitada al 80% porque la fuente de generación y verificación coinciden.

**Tier 2 — Corroboración externa:** Búsqueda en fuentes independientes (excluyendo documentos fuente), siguiendo SAFE (Google DeepMind, 2024) y CoVe (Meta, 2024).
