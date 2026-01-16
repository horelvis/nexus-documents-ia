# Caso de Uso: Prueba del Sistema de Aprendizaje de Emma

## Objetivo
Validar que el sistema de aprendizaje funciona end-to-end desde la UI, incluyendo:
1. **Knowledge Extraction**: Extracción automática de entidades al subir documentos
2. **Preference Learning**: Aprendizaje de preferencias del usuario basado en interacciones

---

## Pre-requisitos

1. Servicios corriendo:
   ```bash
   cd backend/docker && ./start-dev.sh
   cd frontend && npm run dev
   ```

2. Usuario autenticado en la aplicación

3. Documento de prueba (usar el siguiente contenido de ejemplo)

---

## Documento de Prueba

Crear un archivo `contrato_prueba.txt` con el siguiente contenido:

```
CONTRATO DE PRESTACIÓN DE SERVICIOS PROFESIONALES

Entre las partes:

PRIMERA PARTE (EL CONTRATANTE):
Juan García López, con RFC GALJ850315ABC, domiciliado en Av. Reforma 123,
Ciudad de México, actuando en representación de Tecnología Avanzada S.A. de C.V.

SEGUNDA PARTE (EL CONTRATISTA):
María Rodríguez Hernández, con RFC ROHM900520XYZ, domiciliada en
Calle Insurgentes 456, Guadalajara, Jalisco.

CLÁUSULAS:

PRIMERA - OBJETO DEL CONTRATO:
El Contratista se compromete a prestar servicios de consultoría en
transformación digital para el Contratante, incluyendo análisis de procesos,
implementación de sistemas y capacitación del personal.

SEGUNDA - MONTO Y FORMA DE PAGO:
El monto total del contrato es de $150,000.00 MXN (Ciento cincuenta mil pesos 00/100 M.N.),
que se pagará en tres parcialidades:
- 40% al inicio: $60,000.00 MXN
- 30% a mitad del proyecto: $45,000.00 MXN
- 30% al finalizar: $45,000.00 MXN

TERCERA - PLAZO:
El presente contrato tendrá una vigencia de seis (6) meses, iniciando el
15 de enero de 2024 y finalizando el 15 de julio de 2024.

CUARTA - CONFIDENCIALIDAD:
Las partes se comprometen a mantener estricta confidencialidad sobre toda
la información técnica, comercial y financiera intercambiada durante la
vigencia de este contrato.

QUINTA - PENALIZACIONES:
En caso de incumplimiento por parte del Contratista, se aplicará una
penalización del 10% sobre el monto total del contrato por cada mes de retraso.

SEXTA - JURISDICCIÓN:
Para la interpretación y cumplimiento de este contrato, las partes se
someten a la jurisdicción de los tribunales de la Ciudad de México.

Firmado en Ciudad de México, a 10 de enero de 2024.


_______________________          _______________________
Juan García López                María Rodríguez Hernández
El Contratante                   El Contratista
```

---

## Pasos del Caso de Uso

### Paso 1: Subir Documento

1. Acceder a la sección de **Documentos** en la aplicación
2. Hacer clic en **"Subir documento"**
3. Seleccionar el archivo `contrato_prueba.txt`
4. Agregar metadatos opcionales:
   - Categoría: `Contratos`
   - Tags: `servicios`, `consultoría`
5. Hacer clic en **"Subir"**

**Resultado Esperado:**
- El documento se procesa exitosamente
- En el log del backend, debería aparecer:
  ```
  [doc-xxx] Extracting knowledge entities...
  [doc-xxx] ✅ Knowledge extraction completed: X entities, Y relationships
  ```

### Paso 2: Verificar Knowledge Extraction (API)

Ejecutar en terminal:

```bash
# Obtener estadísticas de conocimiento
curl -s "http://localhost:8000/api/v1/weaviate/knowledge/stats" \
  -H "Authorization: Bearer YOUR_TOKEN" | jq

# Listar entidades extraídas
curl -s "http://localhost:8000/api/v1/weaviate/knowledge/entities?limit=20" \
  -H "Authorization: Bearer YOUR_TOKEN" | jq
```

**Resultado Esperado:**
```json
{
  "total_entities": 8,
  "entities_by_type": {
    "person": 2,
    "organization": 1,
    "amount": 4,
    "date": 2,
    "clause": 6
  },
  "entities_by_domain": {
    "legal": 8
  }
}
```

Entidades que deben extraerse:
| Tipo | Valor |
|------|-------|
| person | Juan García López |
| person | María Rodríguez Hernández |
| organization | Tecnología Avanzada S.A. de C.V. |
| amount | $150,000.00 MXN |
| amount | $60,000.00 MXN |
| amount | $45,000.00 MXN |
| date | 15 de enero de 2024 |
| date | 15 de julio de 2024 |
| clause | Confidencialidad |
| clause | Penalizaciones |

---

### Paso 3: Ver Documento (Tracking de Vistas)

1. En la lista de documentos, hacer clic en el documento subido
2. Navegar por el contenido (scroll)
3. Permanecer en la vista por al menos 30 segundos

**Resultado Esperado:**
- La vista se registra en el sistema de learning
- Verificar con:
  ```bash
  curl -s "http://localhost:8000/api/v1/weaviate/learning/stats" \
    -H "Authorization: Bearer YOUR_TOKEN" | jq
  ```
  Debería mostrar `total_document_views: 1`

---

### Paso 4: Chatear con Emma

1. Navegar a la sección **Chat** o hacer clic en **"Ask Emma"** desde el documento
2. Realizar las siguientes preguntas en orden:

#### Pregunta 1: General
```
¿Cuáles son las partes involucradas en el contrato?
```

**Resultado Esperado:**
- Emma identifica: Juan García López y María Rodríguez Hernández
- Menciona Tecnología Avanzada S.A. de C.V.
- Los botones de 👍/👎 aparecen en la respuesta

#### Pregunta 2: Sobre montos
```
¿Cuál es el monto total y cómo se divide el pago?
```

**Resultado Esperado:**
- Emma responde con los $150,000.00 MXN
- Detalla las tres parcialidades (40%, 30%, 30%)

#### Pregunta 3: Sobre cláusulas
```
¿Qué dice la cláusula de penalizaciones?
```

**Resultado Esperado:**
- Emma explica la penalización del 10% por mes de retraso
- Referencias al documento fuente

---

### Paso 5: Dar Feedback (👍/👎)

1. En una de las respuestas de Emma, hacer clic en el botón **👍** (thumbs up)
2. Debería aparecer un toast: "Thanks for your feedback!" o "¡Gracias por tu feedback!"

3. En otra respuesta, hacer clic en **👎** (thumbs down)
4. Debería aparecer: "We'll work to improve." o "Trabajaremos para mejorar."

**Verificar en API:**
```bash
curl -s "http://localhost:8000/api/v1/weaviate/learning/profile" \
  -H "Authorization: Bearer YOUR_TOKEN" | jq
```

**Resultado Esperado:**
- El perfil muestra interacciones registradas
- Los `ranking_weights` pueden haber cambiado ligeramente basándose en el feedback

---

### Paso 6: Verificar Perfil de Aprendizaje

```bash
curl -s "http://localhost:8000/api/v1/weaviate/learning/context" \
  -H "Authorization: Bearer YOUR_TOKEN" | jq
```

**Resultado Esperado:**
```json
{
  "language": "es",
  "preferences": {
    "response_style": "balanced",
    "expertise_level": "general"
  },
  "learning_enabled": true,
  "learning_applied": true,
  "ranking_weights": {
    "recency": 0.3,
    "frequency": 0.3,
    "relevance": 0.4
  }
}
```

---

### Paso 7: Buscar en Knowledge Graph

1. En el chat de Emma, preguntar:
   ```
   ¿Qué contratos tenemos con cláusulas de confidencialidad?
   ```

**Resultado Esperado:**
- Emma utiliza el Knowledge Graph para encontrar el contrato
- La respuesta incluye información estructurada de las entidades

---

## Verificación de Logs

Durante todo el proceso, los logs del backend deberían mostrar:

```log
# Al subir documento
INFO - [doc-xxx] Processing document: contrato_prueba.txt
INFO - [doc-xxx] Stage 1: Text extraction completed
INFO - [doc-xxx] Stage 2: Document intelligence completed
INFO - [doc-xxx] Stage 3: Semantic chunking completed
INFO - [doc-xxx] Stage 4: Knowledge extraction - 8 entities, 3 relationships
INFO - [doc-xxx] ✅ Indexing completed successfully

# Al dar feedback
INFO - 📝 Recording feedback: session=conv_xxx, rating=5
INFO - ✅ Feedback recorded for learning

# Al consultar Emma con learning
INFO - 🧠 Loading user learning context
INFO - 📊 Applying personalized ranking weights
```

---

## Criterios de Éxito

| Componente | Criterio | Verificación |
|------------|----------|--------------|
| Knowledge Extraction | Entidades extraídas correctamente | API `/knowledge/stats` muestra > 0 entidades |
| Knowledge Storage | Entidades en Weaviate | API `/knowledge/entities` devuelve lista |
| Document View Tracking | Vista registrada | API `/learning/stats` muestra views > 0 |
| Feedback UI | Botones 👍/👎 funcionan | Toast aparece al hacer clic |
| Feedback Backend | Feedback registrado | Logs muestran "Feedback recorded" |
| Learning Profile | Perfil actualizado | API `/learning/profile` devuelve datos |
| Learning Applied | Emma usa contexto | `learning_applied: true` en respuesta |

---

## Troubleshooting

### Entidades no se extraen
1. Verificar que LangExtract está configurado:
   ```bash
   docker compose logs langextract-service
   ```
2. Revisar si el documento tiene texto extraíble

### Feedback no se registra
1. Verificar conexión a Redis:
   ```bash
   docker compose exec redis redis-cli ping
   ```
2. Revisar logs de weaviate-service:
   ```bash
   docker compose logs weaviate-service | grep -i feedback
   ```

### Knowledge Graph vacío
1. Verificar que la colección existe:
   ```bash
   curl http://localhost:8080/v1/schema | jq '.classes[] | select(.class | startswith("Nexus"))'
   ```
2. Reindexar documento si es necesario

---

## Notas Adicionales

- El sistema de aprendizaje es **gradual**: necesita múltiples interacciones para mostrar cambios significativos
- Los ranking weights tienen límites: relevance máximo 0.6, mínimos 0.1
- El feedback positivo aumenta peso de "relevance", negativo aumenta "recency" y "frequency"
- Las preferencias persisten en Redis con TTL de 7 días, sincronizándose a PostgreSQL periódicamente
