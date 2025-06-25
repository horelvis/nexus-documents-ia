# Casos de Prueba - Nexus Document Management System

## 1. Autenticación y Gestión de Usuarios

### TC-AUTH-001: Registro de nuevo usuario
**Objetivo**: Verificar que un nuevo usuario puede registrarse exitosamente
**Precondiciones**: Usuario no registrado
**Pasos**:
1. Navegar a la página de registro
2. Ingresar email válido
3. Ingresar contraseña segura
4. Confirmar contraseña
5. Click en "Registrarse"

**Resultado esperado**: 
- Usuario creado exitosamente
- Redirección al onboarding
- Email de verificación enviado

### TC-AUTH-002: Login con credenciales válidas
**Objetivo**: Verificar que un usuario puede iniciar sesión
**Precondiciones**: Usuario registrado y verificado
**Pasos**:
1. Navegar a la página de login
2. Ingresar email registrado
3. Ingresar contraseña correcta
4. Click en "Iniciar sesión"

**Resultado esperado**:
- Login exitoso
- Redirección al dashboard
- Token de sesión generado

### TC-AUTH-003: Login con credenciales inválidas
**Objetivo**: Verificar manejo de errores en login
**Precondiciones**: Usuario registrado
**Pasos**:
1. Navegar a la página de login
2. Ingresar email válido
3. Ingresar contraseña incorrecta
4. Click en "Iniciar sesión"

**Resultado esperado**:
- Mensaje de error "Credenciales inválidas"
- No se permite acceso
- Contador de intentos incrementado

### TC-AUTH-004: Logout de usuario
**Objetivo**: Verificar cierre de sesión correcto
**Precondiciones**: Usuario logueado
**Pasos**:
1. Click en avatar de usuario
2. Seleccionar "Cerrar sesión"
3. Confirmar logout

**Resultado esperado**:
- Sesión cerrada
- Redirección a página de login
- Token invalidado

### TC-AUTH-005: Recuperación de contraseña
**Objetivo**: Verificar proceso de recuperación de contraseña
**Precondiciones**: Usuario registrado
**Pasos**:
1. En página de login, click "¿Olvidaste tu contraseña?"
2. Ingresar email registrado
3. Click en "Enviar email de recuperación"
4. Abrir email y click en link
5. Ingresar nueva contraseña
6. Confirmar nueva contraseña

**Resultado esperado**:
- Email enviado exitosamente
- Link de recuperación válido por 24h
- Contraseña actualizada
- Puede hacer login con nueva contraseña

## 2. Gestión de Documentos

### TC-DOC-001: Subir documento individual
**Objetivo**: Verificar carga de un documento
**Precondiciones**: Usuario autenticado
**Pasos**:
1. Click en "Subir documento"
2. Seleccionar archivo PDF/DOCX/TXT
3. Agregar etiquetas opcionales
4. Click en "Subir"

**Resultado esperado**:
- Archivo subido exitosamente
- Procesamiento iniciado
- Documento visible en lista
- Notificación de éxito

### TC-DOC-002: Subir múltiples documentos
**Objetivo**: Verificar carga masiva
**Precondiciones**: Usuario autenticado
**Pasos**:
1. Click en "Subir documento"
2. Seleccionar múltiples archivos (máx 10)
3. Verificar preview de archivos
4. Click en "Subir todos"

**Resultado esperado**:
- Todos los archivos subidos
- Barra de progreso individual
- Procesamiento en paralelo
- Notificaciones por cada archivo

### TC-DOC-003: Ver detalles de documento
**Objetivo**: Verificar visualización de documento
**Precondiciones**: Documento subido y procesado
**Pasos**:
1. Click en documento de la lista
2. Verificar panel de detalles
3. Click en "Ver documento"

**Resultado esperado**:
- Metadatos visibles (tamaño, fecha, tipo)
- Preview del documento
- Etiquetas y análisis IA visibles
- Opciones de acción disponibles

### TC-DOC-004: Descargar documento
**Objetivo**: Verificar descarga de documento
**Precondiciones**: Documento en sistema
**Pasos**:
1. Abrir detalles de documento
2. Click en "Descargar"
3. Confirmar descarga

**Resultado esperado**:
- Archivo descargado correctamente
- Formato original preservado
- Registro de descarga en auditoría

### TC-DOC-005: Eliminar documento
**Objetivo**: Verificar eliminación de documento
**Precondiciones**: Documento en sistema, usuario con permisos
**Pasos**:
1. Seleccionar documento
2. Click en "Eliminar"
3. Confirmar eliminación en modal

**Resultado esperado**:
- Documento eliminado
- Desaparece de lista
- Espacio liberado en storage
- Registro en auditoría

### TC-DOC-006: Compartir documento
**Objetivo**: Verificar compartir documento
**Precondiciones**: Documento en sistema
**Pasos**:
1. Abrir detalles de documento
2. Click en "Compartir"
3. Ingresar email destinatario
4. Seleccionar permisos (ver/editar)
5. Click en "Enviar invitación"

**Resultado esperado**:
- Email enviado al destinatario
- Link de acceso generado
- Permisos aplicados correctamente
- Documento visible en "Compartidos conmigo"

## 3. Búsqueda y Análisis con IA

### TC-SEARCH-001: Búsqueda simple por texto
**Objetivo**: Verificar búsqueda básica
**Precondiciones**: Documentos en sistema
**Pasos**:
1. Ingresar término en barra de búsqueda
2. Presionar Enter o click en buscar
3. Revisar resultados

**Resultado esperado**:
- Resultados relevantes mostrados
- Highlighting de términos encontrados
- Ordenados por relevancia
- Contador de resultados

### TC-SEARCH-002: Búsqueda semántica
**Objetivo**: Verificar búsqueda por significado
**Precondiciones**: Documentos procesados con embeddings
**Pasos**:
1. Toggle "Búsqueda semántica" activado
2. Ingresar consulta en lenguaje natural
3. Ejecutar búsqueda

**Resultado esperado**:
- Resultados basados en significado
- Score de similitud visible
- Resultados contextuales
- Explicación de relevancia

### TC-SEARCH-003: Filtros de búsqueda
**Objetivo**: Verificar aplicación de filtros
**Precondiciones**: Documentos variados
**Pasos**:
1. Ejecutar búsqueda inicial
2. Aplicar filtro por fecha
3. Aplicar filtro por tipo
4. Aplicar filtro por etiquetas

**Resultado esperado**:
- Filtros aplicados correctamente
- Resultados actualizados
- Contador refleja filtros
- Filtros visibles y removibles

### TC-SEARCH-004: Análisis de documento con IA
**Objetivo**: Verificar análisis automático
**Precondiciones**: Documento subido
**Pasos**:
1. Subir nuevo documento
2. Esperar procesamiento
3. Ver sección "Análisis IA"

**Resultado esperado**:
- Resumen generado
- Etiquetas sugeridas
- Entidades identificadas
- Categoría asignada

## 4. Firmas Digitales

### TC-SIGN-001: Crear solicitud de firma
**Objetivo**: Verificar creación de solicitud
**Precondiciones**: Documento PDF, proveedor configurado
**Pasos**:
1. Seleccionar documento
2. Click "Solicitar firma"
3. Agregar firmantes (email, nombre)
4. Definir orden de firma
5. Agregar mensaje opcional
6. Enviar solicitud

**Resultado esperado**:
- Solicitud creada
- Emails enviados a firmantes
- Estado "Pendiente" visible
- Timeline de firma iniciado

### TC-SIGN-002: Firmar documento
**Objetivo**: Verificar proceso de firma
**Precondiciones**: Solicitud de firma recibida
**Pasos**:
1. Abrir email de solicitud
2. Click en link de firma
3. Revisar documento
4. Aplicar firma en campos indicados
5. Confirmar firma

**Resultado esperado**:
- Firma aplicada correctamente
- Certificado generado
- Notificación al solicitante
- Estado actualizado

### TC-SIGN-003: Rechazar solicitud de firma
**Objetivo**: Verificar rechazo de firma
**Precondiciones**: Solicitud pendiente
**Pasos**:
1. Abrir solicitud de firma
2. Click en "Rechazar"
3. Ingresar motivo
4. Confirmar rechazo

**Resultado esperado**:
- Solicitud marcada como rechazada
- Notificación al solicitante
- Motivo visible en timeline
- Opción de reenviar

### TC-SIGN-004: Tracking de firmas
**Objetivo**: Verificar seguimiento de proceso
**Precondiciones**: Solicitud en proceso
**Pasos**:
1. Ir a "Firmas digitales"
2. Ver lista de solicitudes
3. Click en solicitud activa
4. Revisar timeline

**Resultado esperado**:
- Estados visibles por firmante
- Fechas y horas registradas
- Acciones disponibles según estado
- Historial completo

## 5. Agentes de IA

### TC-AGENT-001: Listar agentes disponibles
**Objetivo**: Verificar visualización de agentes
**Precondiciones**: Usuario autenticado
**Pasos**:
1. Navegar a sección "Agentes IA"
2. Revisar lista de agentes
3. Verificar información mostrada

**Resultado esperado**:
- Lista de agentes visibles
- Tipos y descripciones
- Estados (activo/inactivo)
- Contador de agentes

### TC-AGENT-002: Iniciar conversación con agente
**Objetivo**: Verificar interacción con agente
**Precondiciones**: Agente activo disponible
**Pasos**:
1. Seleccionar agente de la lista
2. Click en "Nueva conversación"
3. Escribir mensaje inicial
4. Enviar mensaje

**Resultado esperado**:
- Conversación iniciada
- Mensaje enviado
- Respuesta del agente recibida
- Historial visible

### TC-AGENT-003: Análisis de documento con agente
**Objetivo**: Verificar análisis especializado
**Precondiciones**: Documento y agente analyzer
**Pasos**:
1. Seleccionar documento
2. Click "Analizar con IA"
3. Seleccionar tipo de análisis
4. Iniciar análisis

**Resultado esperado**:
- Análisis iniciado
- Progreso visible
- Resultados estructurados
- Opción de exportar resultados

### TC-AGENT-004: Historial de conversaciones
**Objetivo**: Verificar persistencia de chats
**Precondiciones**: Conversaciones previas
**Pasos**:
1. Ir a agente usado previamente
2. Ver lista de conversaciones
3. Seleccionar conversación anterior
4. Continuar conversación

**Resultado esperado**:
- Historial completo visible
- Contexto mantenido
- Puede continuar chat
- Búsqueda en historial funciona

## 6. Gestión de Equipo/Tenant

### TC-TEAM-001: Invitar miembro al equipo
**Objetivo**: Verificar invitación de usuarios
**Precondiciones**: Usuario admin
**Pasos**:
1. Ir a Configuración > Equipo
2. Click "Invitar miembro"
3. Ingresar email
4. Seleccionar rol
5. Enviar invitación

**Resultado esperado**:
- Invitación enviada
- Email con link de unión
- Pendiente en lista
- Expiración en 7 días

### TC-TEAM-002: Aceptar invitación
**Objetivo**: Verificar unión al equipo
**Precondiciones**: Invitación recibida
**Pasos**:
1. Abrir email de invitación
2. Click en link
3. Crear cuenta o login
4. Confirmar unión

**Resultado esperado**:
- Usuario agregado al equipo
- Acceso a recursos compartidos
- Rol asignado correctamente
- Notificación al admin

### TC-TEAM-003: Gestionar permisos
**Objetivo**: Verificar cambio de roles
**Precondiciones**: Múltiples usuarios en equipo
**Pasos**:
1. Ir a gestión de equipo
2. Seleccionar usuario
3. Cambiar rol
4. Guardar cambios

**Resultado esperado**:
- Rol actualizado
- Permisos aplicados inmediatamente
- Registro en auditoría
- Notificación al usuario

### TC-TEAM-004: Remover miembro
**Objetivo**: Verificar eliminación de acceso
**Precondiciones**: Usuario en equipo
**Pasos**:
1. Seleccionar usuario
2. Click "Remover del equipo"
3. Confirmar acción
4. Verificar eliminación

**Resultado esperado**:
- Usuario removido
- Acceso revocado inmediatamente
- Documentos propios preservados
- Notificación enviada

## 7. Configuración y Administración

### TC-CONFIG-001: Configurar proveedor de firma
**Objetivo**: Verificar setup de proveedor
**Precondiciones**: Usuario admin
**Pasos**:
1. Ir a Admin > Proveedores de firma
2. Click "Agregar proveedor"
3. Seleccionar tipo (DocuSign/Adobe)
4. Ingresar credenciales API
5. Probar conexión
6. Guardar configuración

**Resultado esperado**:
- Proveedor configurado
- Conexión exitosa
- Disponible para firmas
- Credenciales encriptadas

### TC-CONFIG-002: Ver uso y límites
**Objetivo**: Verificar monitoreo de uso
**Precondiciones**: Actividad en sistema
**Pasos**:
1. Ir a Configuración > Uso
2. Revisar métricas
3. Ver gráficos de tendencia

**Resultado esperado**:
- Storage usado/disponible
- Documentos procesados
- Usuarios activos
- Alertas si cerca del límite

### TC-CONFIG-003: Exportar datos
**Objetivo**: Verificar exportación
**Precondiciones**: Datos en sistema
**Pasos**:
1. Ir a Configuración > Exportar
2. Seleccionar tipo de datos
3. Elegir formato (CSV/JSON)
4. Iniciar exportación

**Resultado esperado**:
- Exportación iniciada
- Email con link de descarga
- Datos completos y formateados
- Registro de exportación

## 8. Notificaciones

### TC-NOTIF-001: Recibir notificaciones
**Objetivo**: Verificar sistema de notificaciones
**Precondiciones**: Acciones que generan notificaciones
**Pasos**:
1. Realizar acción (subir documento)
2. Ver icono de notificación
3. Click para ver lista
4. Marcar como leída

**Resultado esperado**:
- Notificación aparece en tiempo real
- Contador actualizado
- Puede marcar como leída
- Historial persistente

### TC-NOTIF-002: Configurar preferencias
**Objetivo**: Verificar personalización
**Precondiciones**: Usuario autenticado
**Pasos**:
1. Ir a Configuración > Notificaciones
2. Toggle tipos de notificación
3. Guardar preferencias

**Resultado esperado**:
- Preferencias guardadas
- Solo recibe tipos seleccionados
- Aplicado inmediatamente

## Notas de Ejecución

### Prioridad de Testing
1. **Alta**: Autenticación, Subida de documentos, Búsqueda
2. **Media**: Firmas digitales, Agentes IA, Compartir
3. **Baja**: Exportación, Notificaciones, Configuración avanzada

### Ambientes de Prueba
- **Local**: Docker compose desarrollo
- **Staging**: Ambiente pre-producción
- **Producción**: Solo smoke tests

### Datos de Prueba
- Usuarios: test1@example.com, test2@example.com
- Documentos: PDFs de prueba en `/tests/fixtures`
- API Keys: Usar credenciales de prueba

### Automatización
- Framework recomendado: Playwright/Cypress para E2E
- Jest para pruebas unitarias
- Postman/Newman para APIs