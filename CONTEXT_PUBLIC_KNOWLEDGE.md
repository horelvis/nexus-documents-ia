# Contexto: Base de Conocimiento Público Legal

**Fecha**: 2025-12-02
**Estado**: Implementación completada, pendiente verificación frontend

## Resumen del Trabajo Realizado

### 1. Base de Conocimiento Público en Weaviate

Se implementó una base de datos vectorial pública para documentos legales compartidos entre todos los tenants.

**Archivos creados en weaviate-service:**
- `/backend/microservices/weaviate-service/app/schemas/public_knowledge.py` - Schemas Pydantic
- `/backend/microservices/weaviate-service/app/services/public_knowledge_service.py` - Servicio principal
- `/backend/microservices/weaviate-service/app/api/public_knowledge.py` - Endpoints REST

**Colección Weaviate:** `PublicKnowledge`

**Categorías disponibles:**
- legislation, regulation, jurisprudence, template, guideline, reference, form, treaty

**Jurisdicciones:**
- es (España), eu (Unión Europea), int (Internacional), regional

### 2. Documentos Ingestados (25 total)

**Fiscales España (5):**
- Ley General Tributaria
- Ley IRPF
- Ley Impuesto Sociedades
- Ley IVA
- Reglamento Facturación

**Laborales España (8):**
- Estatuto de los Trabajadores
- Ley Prevención Riesgos Laborales
- Ley de Igualdad
- LISOS
- Ley Reguladora Jurisdicción Social
- Ley Libertad Sindical
- Real Decreto Salario Mínimo
- Real Decreto Relaciones Laborales Especiales

**Directivas UE (8):**
- RGPD
- Directiva IVA
- Directiva Tiempo de Trabajo
- Directiva Despidos Colectivos
- Directiva ETT
- Directiva Insolvencia
- Directiva Condiciones Transparentes
- Directiva Conciliación

**Otros (4):**
- LOPDGDD
- Estatuto Trabajadores (versión resumida)
- 2 documentos adicionales

### 3. Scripts de Ingesta

**CLI de gestión:** `/backend/scripts/public_knowledge_cli.py`
```bash
# Ejemplos de uso:
python3 scripts/public_knowledge_cli.py --api-url http://localhost:8005 stats
python3 scripts/public_knowledge_cli.py --api-url http://localhost:8005 search "RGPD"
python3 scripts/public_knowledge_cli.py --api-url http://localhost:8005 categories
```

**Script de ingesta masiva:** `/backend/scripts/ingest_public_knowledge.py`
- Soporta BOE, EUR-Lex y archivos locales

### 4. Proxy en Backend Principal

Se añadieron endpoints proxy en `/backend/app/api/v1/weaviate.py`:

```
GET  /api/v1/weaviate/public-knowledge/health
GET  /api/v1/weaviate/public-knowledge/stats
GET  /api/v1/weaviate/public-knowledge/categories
GET  /api/v1/weaviate/public-knowledge/jurisdictions
POST /api/v1/weaviate/public-knowledge/search
GET  /api/v1/weaviate/public-knowledge/documents/{doc_id}
```

**Prueba verificada:**
```bash
curl http://localhost:8000/api/v1/weaviate/public-knowledge/stats
# → {"total_documents":25,"documents_by_category":{"legislation":14,"regulation":11},...}
```

### 5. Frontend - Página de Administración

**Página creada:** `/frontend/src/app/(main)/[tenantId]/admin/public-knowledge/page.tsx`

**Características:**
- Estadísticas de la base de conocimiento
- Selector de categorías habilitadas (switches)
- Búsqueda híbrida (semántica + keywords)
- Tabla de resultados con: título, categoría, jurisdicción, referencia legal, verificación, score
- Tarjetas informativas por categoría

**Sidebar actualizado:** `/frontend/src/components/layout/app-sidebar.tsx`
- Añadido enlace "Base de Conocimiento Legal" en Admin Actions
- Icono: IconScale, Color: blue
- URL: `/admin/public-knowledge`

**Traducciones añadidas:**
- `/frontend/src/lib/i18n/locales/es.json` - Español completo
- `/frontend/src/lib/i18n/locales/en.json` - Inglés completo
- `/frontend/src/lib/i18n/locales/fr.json` - Francés completo

### 6. Integración con Elysia

Se añadió herramienta `search_public_knowledge` en Elysia para que Emma pueda buscar en la base pública:

**Archivos modificados:**
- `/backend/microservices/weaviate-service/app/services/elysia_service.py`
- `/backend/microservices/weaviate-service/app/services/elysia_tools.py`

## Pendiente para Verificar

1. **Frontend**: Recargar la página `/admin/public-knowledge` y verificar que:
   - Carga las estadísticas correctamente
   - La búsqueda funciona
   - Los switches de categorías funcionan
   - Las traducciones se muestran correctamente

2. **Elysia**: Probar que Emma puede usar la herramienta `search_public_knowledge` desde el chat

## Comandos Útiles

```bash
# Ver stats desde container
docker exec docker-weaviate-service-1 curl -s http://localhost:8000/public-knowledge/stats

# Buscar desde container
docker exec docker-weaviate-service-1 curl -s -X POST http://localhost:8000/public-knowledge/search \
  -H "Content-Type: application/json" \
  -d '{"query": "RGPD", "limit": 5}'

# Via backend principal
curl http://localhost:8000/api/v1/weaviate/public-knowledge/stats
```

## Errores Conocidos Corregidos

1. **Autenticación**: Cambiado de `X-API-Key` a `Authorization: Bearer {token}` (HTTPBearer)
2. **URL Frontend**: Cambiado de `http://localhost:8005` directo a usar `useApiClient()` con `/weaviate/public-knowledge/*`

## Próximos Pasos Sugeridos

1. Añadir más documentos legales (jurisprudencia, tratados internacionales)
2. Implementar scraping automático de BOE/EUR-Lex para actualizaciones
3. Añadir filtros por fecha de publicación/vigencia
4. Implementar caché de búsquedas frecuentes
