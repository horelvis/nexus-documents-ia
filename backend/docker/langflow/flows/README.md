# Langflow Agents para Nexus

## Agentes Disponibles

Todos los archivos son compatibles con Langflow y usan componentes nativos:

### 1. **financial_analysis_agent.json**
- Análisis de documentos financieros
- Seguimiento de facturas y vencimientos
- Análisis de gastos y flujo de caja

### 2. **rag_assistant_agent.json**
- Búsqueda semántica en documentos
- Q&A con contexto
- Integración con Qdrant vectorstore

### 3. **document_analyzer_agent.json**
- Análisis multi-formato de documentos
- Extracción de entidades
- Generación de metadatos y tags

### 4. **legal_compliance_agent.json**
- Análisis de contratos
- Verificación de compliance
- Identificación de riesgos legales

### 5. **digital_signature_agent.json**
- Gestión de flujos de firma
- Seguimiento de firmantes
- Workflows secuenciales/paralelos

## Cómo Importar:

1. **Abrir Langflow**:
   ```bash
   http://localhost:7860
   ```

2. **Importar Flow**:
   - Click en "Import" (arriba derecha)
   - Seleccionar archivo `*_langflow_native.json`
   - El flow aparecerá en el canvas

3. **Configurar Conexiones** (si es necesario):
   - **Ollama URL**: `http://ollama-service:11434` (ya configurado)
   - **Qdrant Host**: `qdrant` (ya configurado)
   - **Collection Name**: Ajustar según tu tenant

4. **Probar el Flow**:
   - Click en "Run" o icono de play
   - Usar el chat para probar

## Ajustes Comunes:

### Para Ollama:
- Asegurarse que el modelo existe: `llama3.2`
- Para embeddings: `nomic-embed-text`

### Para Qdrant:
- La colección debe existir o se creará automáticamente
- Puerto por defecto: 6333

### Personalización:
- Modificar los prompts en PromptTemplate
- Ajustar temperatura y max_tokens
- Cambiar el número de documentos a recuperar (k)

## Solución de Problemas:

1. **"Component not found"**: Actualiza Langflow a la última versión
2. **"Connection refused"**: Verifica que los servicios estén corriendo
3. **"Model not found"**: Descarga el modelo con `ollama pull llama3.2`

## Exportar Después de Modificar:

1. Hacer cambios en Langflow
2. Click en "Export" → "Download Flow"
3. Guardar en `langflow/flows/`
4. El agente se cargará automáticamente