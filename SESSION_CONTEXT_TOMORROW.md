# 📋 Contexto Continuidad – Enfoque Asesorías Laborales

## 🗓️ Fecha
15 noviembre 2025 – 18:30 CET

## 🎯 Objetivo general
Convertir NexusDocs360 en la plataforma IA de referencia para **asesorías laborales**, con una hoja de ruta clara de funcionalidades CORE que podamos reutilizar después en gestorías fiscales/contables.

---

## ✅ Estado actual (resumen)
- **Landing** orientada a asesorías → mensajes, badges y testimonios adaptados.
- **Catálogo de workflows AI** expuesto vía `/temporalio/ai-workflows`, con formularios dinámicos en frontend.
- **Temporalio** estable: search attributes corregidos, catálogo curado lista legal/documental funcionando.
- **Infra**: microservicios operativos (Temporalio, Weaviate, firma, storage). Faltan pipelines específicos para ingestión laboral.

---

## 🔧 Backlog prioritario (asesorías laborales)

| Módulo | Función | Estado | Notas/Dependencias |
| --- | --- | --- | --- |
| Ingesta documental | Drag & drop multiarchivo con metadatos (cliente, periodo, tipo) | ⚙️ existente pero genérico | Adaptar UI/validaciones para documentos laborales |
| Ingesta por email | Conector IMAP/365 + reglas por cliente | ⏳ por implementar | Necesita microservicio de watcher + colas |
| OCR + normalización | OCR ya disponible (Gotenberg/PDF). Falta pipeline laboral | 🔄 parcial | Crear plantillas específicas (nómina, contrato, certificado) |
| Clasificación IA | Detectar modelo 111/190/303, nómina, contrato, certificado, comunicaciones ITSS | ✅ base (clasif genérica) | Entrenar prompts/etiquetas laborales + motor de reglas |
| Búsqueda semántica | Implementada con Weaviate | ✅ | Añadir filtros “cliente”, “tipo modelo”, “fecha vencimiento” |
| Alertas/vencimientos | Jobs para contratos y obligaciones | ⏳ | Requiere scheduler + metadatos en DB |
| ACL / espacios clientes | ACL básica multi-tenant | ✅ base | Añadir roles “asesor”, “cliente empresa” y carpetas compartidas |
| Firma electrónica | Microservicio listo | ✅ | Crear plantillas de firma (contrato, anexo, certificado) y flujos preconfigurados |
| Portal cliente | UI ligera para empresas finales | ⏳ | Reutilizar componentes de sharing + auth delegada |
| Panel analítico | Charts de obligaciones, carga por asesor, incidencias | ⏳ | Base de datos ya tiene eventos → crear endpoints + dashboards |
| Chat IA laboral | Emma/LLM ya disponible | ⚙️ | Afinar prompt + retrieval sobre documentos laborales y convenios |

---

## 📌 Recomendación de corto plazo (orden sugerido)
1. **Ingesta omnicanal** (drag & drop + email) con pipeline de OCR y clasificación laboral.
2. **Metadatos críticos**: cliente, periodo fiscal, tipo de modelo, status firma.
3. **Alertas y calendario**: modelos 111/190/303, vencimientos de contratos/ITSS.
4. **Portal cliente**: acceso seguro, subida de docs y seguimiento de firmas.
5. **Analytics**: tablero interno (carga asesores, obligaciones pendientes).

---

## 🧱 Bloqueos / Riesgos
- **Datos de entrenamiento**: necesitamos ejemplos reales (anonimizados) de nóminas/modelos para mejorar clasificación.
- **Firmas avanzadas**: validar requisitos legales según clientes (EU vs LATAM).
- **Coste de almacenamiento**: incremento por ingestión masiva → revisar cuotas y archivado.

---

## 🔁 Próximas sesiones
- **Backend**: diseñar pipeline de ingesta + clasificación específica.
- **Frontend**: UI de carga por cliente + calendario de obligaciones.
- **Go-to-market**: preparar pitch deck y pricing para pilotos (3-5 asesorías).

> Guardar este archivo antes de pausar y retomarlo la próxima sesión. Familiarizarnos con `backend/app/data/ai_workflow_catalog.py` y los microservicios de ingestión será clave para acelerar los siguientes pasos. 
