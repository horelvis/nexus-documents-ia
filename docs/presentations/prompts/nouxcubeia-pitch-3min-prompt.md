# Prompt: Presentación NouxCubeIA (3 minutos)

## Contexto para el LLM

Eres un experto en comunicación corporativa y presentaciones de producto tecnológico. Tu tarea es crear una presentación de 3 minutos sobre NouxCubeIA, un sistema de gestión documental con IA.

## Información del Proyecto

### Empresa
- **Nombre**: Venzia IT
- **Producto**: NouxCubeIA
- **Asistente IA**: Emma

### Stack Tecnológico (simplificar para audiencia no técnica)
- Modelo LLM: Qwen3 (open source, ejecutado localmente)
- Base de datos vectorial: Weaviate
- Framework de agentes: Microsoft Agent Framework
- Infraestructura: Docker, GPU local (RTX 4090)

### Problema que Resuelve
1. Las empresas usan ChatGPT/Gemini/Claude pero:
   - Costes elevados por token
   - Datos confidenciales enviados a servidores externos
   - Sin integración con documentos internos

2. Los sistemas RAG actuales tienen problemas ocultos:
   - Fragmentación de información (chunking)
   - Contextos limitados (8K-32K tokens)
   - "Olvido" de información relevante
   - Alucinaciones

### Solución NouxCubeIA
- IA como pilar arquitectónico (no como añadido)
- Modelo open source ejecutado on-premise
- Pipeline RAG de 7 capas optimizado
- Agentes especializados por dominio (legal, fiscal, laboral)
- Privacidad total: datos nunca salen de la empresa

### Emma - Asistente IA
- Coordinadora central con múltiples agentes especializados
- Contexto conversacional persistente
- Especializada en gestión documental (ISO 15489)
- Responde en el idioma del usuario

### Roadmap 2026
- **Q1 2026 - RLM**: Recursive Language Models para procesar documentos de 100+ páginas completos (100x más contexto)
- **Q2 2026 - LoRA**: Aprendizaje continuo para especializar Emma por dominio y cliente

## Requisitos de la Presentación

### Formato
- Documento Markdown con sintaxis de diapositivas (`---` como separador)
- 8-10 diapositivas máximo
- ~20-30 segundos por diapositiva
- Lenguaje claro para audiencia NO técnica (ejecutivos, managers)

### Estructura Sugerida (puedes reordenar)

1. **Apertura impactante**: El problema actual con IA en empresas
2. **El coste oculto**: Privacidad y dependencia de proveedores
3. **La oportunidad**: Modelos open source
4. **El gap del mercado**: Falta de soluciones documentales
5. **Nuestra solución**: NouxCubeIA
6. **Emma**: La IA que entiende tus documentos
7. **Diferenciadores**: Por qué somos diferentes
8. **Visión de futuro**: Roadmap 2026
9. **Cierre/CTA**: Siguiente paso

### Estilo de Comunicación
- Evitar jerga técnica (no mencionar "tokens", "embeddings", "RAG")
- Usar analogías comprensibles
- Datos concretos cuando sea posible
- Tono profesional pero accesible
- Enfatizar beneficios de negocio, no características técnicas

### Elementos Visuales (sugerencias para cada slide)
- Incluir sugerencias de iconos o imágenes
- Indicar puntos clave en bullets (máximo 3-4 por slide)
- Proponer una frase memorable o "headline" por slide

## Output Esperado

Genera un documento Markdown con:
1. Título de cada diapositiva
2. Headline/frase impactante
3. 3-4 bullets con los puntos clave
4. Sugerencia visual (icono/imagen)
5. Notas del presentador (qué decir en ~25 segundos)

---

## Ejemplo de Formato de Salida

```markdown
# NouxCubeIA - Presentación 3 min

---

## Slide 1: [Título]

> **"Headline impactante"**

- Punto clave 1
- Punto clave 2
- Punto clave 3

📊 *Visual sugerido: [descripción]*

**Notas del presentador:**
[Texto de ~25 segundos para leer/memorizar]

---

## Slide 2: [Título]
...
```

---

## Genera la presentación completa ahora.
