# Public Knowledge & BOE Legislation System

## Overview

The Public Knowledge system provides **shared Spanish legislation** across all tenants in NouxCube. It consists of three integrated components:

1. **Weaviate PublicKnowledge Collection**: Chunked legislation with BGE-M3 embeddings for semantic RAG retrieval
2. **Apache AGE Legal Graph**: Law nodes with relationship edges (MODIFIES, REFERENCES, DEROGATES)
3. **BOE Download API**: Automated download and indexing from Spain's Official Gazette

## Architecture

```
┌─────────────────┐     ┌──────────────────────┐     ┌─────────────────────┐
│   BOE API       │     │  IndexingPipeline    │     │    Weaviate         │
│  (boe.es)       │────▶│  (legal_sections)    │────▶│  PublicKnowledge    │
└─────────────────┘     └──────────┬───────────┘     └─────────────────────┘
                                   │
                                   ▼
                        ┌──────────────────────┐
                        │  LegalGraphService   │
                        │  (Apache AGE)        │
                        └──────────────────────┘
                                   │
                                   ▼
                        ┌──────────────────────┐
                        │ knowledge_graph_public│
                        │ - LegalLaw nodes     │
                        │ - MODIFIES edges     │
                        │ - REFERENCES edges   │
                        │ - DEROGATES edges    │
                        └──────────────────────┘
```

## Components

### 1. PublicKnowledge Collection (Weaviate)

Stores chunked legislation with metadata for hybrid search.

**Schema fields**:
- `title`: Full law title with short name
- `content`: Chunk text (~1500 chars with 200 overlap)
- `boe_id`: BOE identifier (e.g., `BOE-A-2015-11430`)
- `legal_reference`: Same as boe_id
- `category`: LEGISLATION, REGULATION, JURISPRUDENCE
- `jurisdiction`: SPAIN, EU
- `legal_status`: vigente, derogada
- `keywords`: Law short name + materias from BOE
- `eli_uri`: European Legislation Identifier

**Chunk Strategy**: `legal_sections` with 1500 char target, 200 overlap.

### 2. Legal Knowledge Graph (Apache AGE)

Graph database storing law relationships for context expansion.

**Node: LegalLaw**
```
{
  boe_id: "BOE-A-2015-11430",
  title: "Real Decreto Legislativo 2/2015...",
  short_name: "ET",
  domain: "labor",
  status: "vigente",
  publication_date: "2015-10-24",
  eli_uri: "...",
  weaviate_uuid: "..."
}
```

**Edge Types**:
- `MODIFIES`: Law A modifies Law B
- `REFERENCES`: Law A cites Law B
- `DEROGATES`: Law A repeals Law B

**Graph Statistics** (as of Feb 2026):
- 49 law nodes
- 103 edges (43 MODIFIES, 24 REFERENCES, 9 DEROGATES)
- Hub laws: CCom (11 conn), CC (9), LE (9), LSC (7)

### 3. BOE Download API

REST endpoints on `weaviate-service:8007/boe/`.

## API Reference

### List Presets
```http
GET /boe/presets
```

Returns 13 preset categories with law counts.

### Download Preset
```http
POST /boe/download/preset
Content-Type: application/json
X-API-Key: {API_KEY}

{
  "preset": "laboral",
  "index_to_weaviate": true
}
```

Downloads all laws in the preset and indexes them.

### Download Single Law
```http
POST /boe/download
Content-Type: application/json
X-API-Key: {API_KEY}

{
  "boe_id": "BOE-A-2015-11430",
  "index_to_weaviate": true
}
```

### Get All Law IDs
```http
GET /boe/all-legislation-ids
```

Returns all 47 unique BOE IDs across presets.

### Sync Law (Detect Changes)
```http
POST /boe/sync/{boe_id}?force=false
X-API-Key: {API_KEY}
```

Compares stored version with BOE and detects article-level changes.

## Available Presets

| Preset | Laws | Description |
|--------|------|-------------|
| `laboral` | 7 | ET, LTD, LPRL, LISOS, LOI, LETA, LGSS |
| `fiscal` | 5 | LGT, LIRPF, LIS, LIVA, Reglamento Facturación |
| `mercantil` | 3 | LSC, CCom, LSP |
| `civil` | 2 | CC, LEC |
| `administrativo` | 3 | LPACAP, LRJSP, LCSP |
| `compliance` | 5 | LPBC, CP, LC, LSE, Auditoría |
| `propiedad_intelectual` | 3 | LPI, LM, LP |
| `comercio_consumidores` | 5 | LGDCU, LCD, LOCM, LGUM, LSSI |
| `emprendimiento` | 3 | LE, LCC, LS |
| `inmobiliario` | 5 | LAU, LPH, LH, Crédito Inmobiliario |
| `contabilidad` | 2 | PGC, PGC Pymes |
| `educacion` | 3 | LOMLOE, LOE, LOU |
| `proteccion_datos` | 1 | LOPDGDD |

## Client Onboarding

### Full Legislation Download

```bash
# Set API key
API_KEY=$(grep MICROSERVICES_API_KEY backend/docker/.env | cut -d= -f2)

# Download all presets (takes ~10-15 minutes)
PRESETS=(laboral fiscal mercantil civil administrativo compliance
         propiedad_intelectual comercio_consumidores emprendimiento
         inmobiliario contabilidad educacion proteccion_datos)

for preset in "${PRESETS[@]}"; do
  echo "Downloading: $preset"
  curl -s -X POST "http://localhost:8007/boe/download/preset" \
    -H "Content-Type: application/json" \
    -H "X-API-Key: $API_KEY" \
    -d "{\"preset\": \"$preset\", \"index_to_weaviate\": true}" | jq '.[] | .boe_id + ": " + (.success | tostring)'
done
```

### Verify Installation

```bash
# Check PublicKnowledge count
curl -s -X POST "http://localhost:8080/v1/graphql" \
  -H "Content-Type: application/json" \
  -d '{"query": "{ Get { PublicKnowledge(limit: 500) { boe_id } } }"}' \
  | jq -r '.data.Get.PublicKnowledge[].boe_id' | sort -u | wc -l

# Check Legal Graph stats
curl -s "http://localhost:8007/legal/stats" -H "X-API-Key: $API_KEY" | jq .
```

### Connect Orphan Laws

After download, some laws may lack connections in the graph. Run:

```bash
docker compose -f backend/docker/docker-compose.onpremise.yml exec weaviate-service \
  bash -c 'cd /app && PYTHONPATH=/app python scripts/connect_orphan_laws.py'
```

## RAG Integration

The LangGraph pipeline uses Public Knowledge in the `retrieve` node:

1. **graph_expand** node extracts `expanded_boe_ids` from QA matches and Apache AGE
2. **retrieve** node uses these IDs to filter PublicKnowledge searches
3. Results are merged with tenant documents for context

```python
# In retrieve_node
expanded_boe_ids = state.get("expanded_boe_ids", [])

# Search PublicKnowledge with BOE ID filter
public_results = await weaviate_client.search_public_knowledge(
    query=query,
    limit=5,
    domain=domain,
    boe_ids=expanded_boe_ids if expanded_boe_ids else None,
)
```

## Known Limitations

### Laws Not in Consolidada API

5 laws return 404 from BOE's `/legislacion-consolidada` endpoint:

| BOE ID | Short Name | Reason |
|--------|------------|--------|
| BOE-A-2007-5909 | LSP | Not consolidated |
| BOE-A-2020-11218 | LC | Recently updated |
| BOE-A-2015-11929 | LP | Not in consolidada |
| BOE-A-2022-23042 | LS | Too recent |
| BOE-A-2019-6635 | LAU Reform | Partial modification |

These can be:
- Manually seeded via `seed_legal_graph.py`
- Downloaded from `/diario-boe` endpoint (original BOE, not consolidated)

## File Reference

| File | Purpose |
|------|---------|
| `weaviate-service/app/api/boe_legislation.py` | BOE download API endpoints |
| `weaviate-service/app/api/legal_graph.py` | Legal graph CRUD endpoints |
| `weaviate-service/app/services/sil/legal_graph_service.py` | Apache AGE graph operations |
| `weaviate-service/app/services/public_knowledge_service.py` | Weaviate PublicKnowledge CRUD |
| `weaviate-service/app/services/legislation_sync_service.py` | Change detection and sync |
| `weaviate-service/scripts/seed_legal_graph.py` | Initial graph population |
| `weaviate-service/scripts/connect_orphan_laws.py` | Connect orphan laws to hubs |
| `weaviate-service/scripts/populate_legal_edges.py` | Create edges from BOE analysis |
| `emma-agent-service/app/agents/langgraph/nodes/graph_expand.py` | Graph expansion for RAG |
| `emma-agent-service/app/agents/langgraph/nodes/retrieve.py` | Retrieval with PublicKnowledge |

## Maintenance

### Sync All Tracked Laws

```bash
curl -X POST "http://localhost:8007/boe/sync/all" \
  -H "X-API-Key: $API_KEY" | jq '.[] | select(.has_changes) | .boe_id'
```

### Check for Pending Updates

```bash
curl "http://localhost:8007/boe/updates" \
  -H "X-API-Key: $API_KEY" | jq .
```

### Rebuild Graph Edges

```bash
docker compose exec weaviate-service bash -c \
  'cd /app && PYTHONPATH=/app python scripts/populate_legal_edges.py'
```
