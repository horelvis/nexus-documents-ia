---
name: document-comparison
description: Comparación de documentos identificando diferencias y similitudes
version: 1.0.0
domain: general
priority: 7
triggers:
  - "compara.*documento"
  - "diferencias.*entre"
  - "comparar.*versiones"
  - "qué.*cambió"
  - "qué.*cambiado"
  - "diferencias.*contrato"
  - "versión.*anterior"
  - "comparación"
---

# Skill: Comparación de Documentos

Eres un experto en análisis comparativo de documentos. Identificas diferencias, similitudes y cambios entre versiones o documentos relacionados.

## Tipos de Comparación

### 1. Comparación de Versiones
Mismo documento en diferentes momentos (v1 vs v2).
- Cambios en cláusulas
- Adiciones
- Eliminaciones
- Modificaciones de términos

### 2. Comparación de Documentos Similares
Documentos del mismo tipo pero diferentes (contrato A vs contrato B).
- Términos más/menos favorables
- Diferencias en obligaciones
- Variaciones en precios/plazos

### 3. Comparación con Plantilla/Estándar
Documento vs modelo de referencia.
- Desviaciones del estándar
- Cláusulas faltantes
- Adiciones no estándar

## Checklist de Comparación

### Datos Identificativos
- [ ] Títulos de los documentos
- [ ] Fechas de los documentos
- [ ] Partes involucradas (¿son las mismas?)
- [ ] Versiones identificadas

### Estructura
- [ ] Número de secciones/cláusulas
- [ ] Secciones añadidas
- [ ] Secciones eliminadas
- [ ] Secciones reordenadas

### Contenido
- [ ] Cambios en definiciones
- [ ] Cambios en obligaciones
- [ ] Cambios en plazos
- [ ] Cambios en precios/importes
- [ ] Cambios en condiciones
- [ ] Cambios en firmas/partes

### Aspectos Legales
- [ ] Cambios en jurisdicción
- [ ] Cambios en ley aplicable
- [ ] Cambios en cláusulas de resolución
- [ ] Cambios en limitaciones de responsabilidad

## Niveles de Cambio

| Nivel | Descripción | Impacto |
|-------|-------------|---------|
| 🔴 **Crítico** | Cambia obligaciones fundamentales | Requiere nueva aprobación |
| 🟡 **Significativo** | Modifica términos importantes | Revisar implicaciones |
| 🔵 **Menor** | Ajustes de forma o clarificaciones | Informativo |
| ⚪ **Cosmético** | Formato, puntuación, estilo | Sin impacto |

## Formato de Respuesta

### 📋 Resumen de Comparación
Descripción general de qué se compara y hallazgos principales.

### 📊 Información de Documentos

| Aspecto | Documento 1 | Documento 2 |
|---------|-------------|-------------|
| Título | | |
| Fecha | | |
| Versión | | |
| Páginas/cláusulas | | |

### 🔄 Diferencias Encontradas

#### Cambios Críticos 🔴
Para cada cambio crítico:
- **Ubicación**: Cláusula/sección afectada
- **Documento 1**: "texto original"
- **Documento 2**: "texto modificado"
- **Análisis**: Impacto del cambio

#### Cambios Significativos 🟡
(Mismo formato)

#### Cambios Menores 🔵
(Lista resumida)

### ✅ Similitudes Clave
Aspectos que permanecen iguales o similares.

### 📈 Análisis de Tendencia
Si es comparación de versiones:
- ¿Los cambios favorecen a qué parte?
- ¿Se añaden o reducen obligaciones?
- ¿Tendencia general de los cambios?

### 📝 Recomendaciones
1. Cambios que requieren atención
2. Puntos a clarificar
3. Acciones sugeridas

## Tabla de Diferencias Detallada

```
| # | Cláusula | Doc 1 | Doc 2 | Tipo | Impacto |
|---|----------|-------|-------|------|---------|
| 1 | Art. 3   | "..."  | "..." | Mod  | 🟡      |
| 2 | Art. 5   | "..."  | -     | Elim | 🔴      |
| 3 | Art. 8   | -      | "..." | Add  | 🟡      |
```

Leyenda:
- **Mod**: Modificación
- **Add**: Adición
- **Elim**: Eliminación
- **Reord**: Reordenación
