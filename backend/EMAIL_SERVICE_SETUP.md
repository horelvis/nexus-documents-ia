# Email Service Setup Guide

Este documento explica cómo configurar el servicio de notificaciones por correo electrónico en el proyecto.

## Librerías Utilizadas

### 1. **FastAPI-Mail** (Principal)
```bash
pip install fastapi-mail
```

FastAPI-Mail es la librería principal que utilizamos para enviar correos electrónicos. Características:
- Integración nativa con FastAPI
- Soporte para plantillas HTML
- Envío asíncrono
- Soporte para múltiples proveedores SMTP
- Adjuntos y contenido embebido

### 2. **Jinja2** (Plantillas)
```bash
pip install jinja2
```

Utilizamos Jinja2 para renderizar las plantillas HTML de los correos.

## Configuración

### Variables de Entorno

Agrega estas variables a tu archivo `.env`:

```env
# Email Configuration
MAIL_USERNAME=tu_email@gmail.com
MAIL_PASSWORD=tu_contraseña_de_aplicación
MAIL_FROM=noreply@tudominio.com
MAIL_FROM_NAME=Nexus Document Management
MAIL_PORT=587
MAIL_SERVER=smtp.gmail.com
MAIL_STARTTLS=True
MAIL_SSL_TLS=False
MAIL_USE_CREDENTIALS=True
MAIL_VALIDATE_CERTS=True
```

### Configuración para Gmail

1. Habilita la autenticación de 2 factores en tu cuenta de Gmail
2. Genera una contraseña de aplicación:
   - Ve a https://myaccount.google.com/security
   - Busca "Contraseñas de aplicaciones"
   - Genera una nueva contraseña para "Correo"
   - Usa esta contraseña en `MAIL_PASSWORD`

### Configuración para otros proveedores

#### SendGrid
```env
MAIL_SERVER=smtp.sendgrid.net
MAIL_PORT=587
MAIL_USERNAME=apikey
MAIL_PASSWORD=tu_api_key_de_sendgrid
```

#### Mailgun
```env
MAIL_SERVER=smtp.mailgun.org
MAIL_PORT=587
MAIL_USERNAME=tu_usuario@mailgun
MAIL_PASSWORD=tu_contraseña_mailgun
```

#### Amazon SES
```env
MAIL_SERVER=email-smtp.region.amazonaws.com
MAIL_PORT=587
MAIL_USERNAME=tu_smtp_username
MAIL_PASSWORD=tu_smtp_password
```

## Estructura del Servicio

```
backend/
├── app/
│   ├── services/
│   │   └── email_service.py      # Servicio principal de email
│   └── templates/
│       └── email/
│           ├── base.html         # Plantilla base
│           ├── user_invitation.html
│           ├── team_invitation.html
│           ├── password_reset.html
│           ├── welcome.html
│           └── document_shared.html
```

## Uso del Servicio

### Ejemplo 1: Enviar invitación de usuario
```python
from app.services.email_service import email_service

# En un endpoint async
await email_service.send_user_invitation(
    email="nuevo@usuario.com",
    inviter_name="Admin",
    tenant_name="Mi Empresa",
    invitation_link="https://app.com/invite/abc123",
    role="user"
)

# En un endpoint sync (como en el proyecto actual)
import asyncio
loop = asyncio.new_event_loop()
asyncio.set_event_loop(loop)
result = loop.run_until_complete(
    email_service.send_user_invitation(...)
)
```

### Ejemplo 2: Enviar correo masivo
```python
await email_service.send_bulk_email(
    recipients=["user1@email.com", "user2@email.com"],
    subject="Actualización importante",
    template_name="newsletter",
    context={
        "title": "Nuevas características",
        "content": "..."
    }
)
```

## Crear Nuevas Plantillas

1. Crea un archivo HTML en `app/templates/email/`
2. Extiende de `base.html`:
```html
{% extends "base.html" %}

{% block title %}Mi título{% endblock %}

{% block content %}
<h2>Mi contenido</h2>
<p>{{ variable }}</p>
{% endblock %}
```

3. Agrega un método en `email_service.py`:
```python
@staticmethod
async def send_mi_notificacion(email: str, **kwargs) -> bool:
    template = env.get_template("mi_plantilla.html")
    html_content = template.render(**kwargs)
    # ... enviar email
```

## Alternativas Open Source

### 1. **Python-emails**
```bash
pip install emails
```
- Más ligero que FastAPI-Mail
- Soporte para plantillas inline
- Bueno para casos simples

### 2. **Yagmail**
```bash
pip install yagmail
```
- Específico para Gmail
- Muy fácil de usar
- Menos configuración

### 3. **Flask-Mail** (adaptable)
```bash
pip install flask-mail
```
- Si prefieres sintaxis similar a Flask
- Puede adaptarse para FastAPI

### 4. **Django Email** (si usas Django)
- Integrado en Django
- Muy robusto
- Muchas características

## Troubleshooting

### Error: "Authentication failed"
- Verifica que estés usando una contraseña de aplicación, no tu contraseña normal
- Asegúrate de que la autenticación de 2 factores esté habilitada

### Error: "Connection refused"
- Verifica el puerto y servidor SMTP
- Algunos proveedores requieren SSL/TLS en lugar de STARTTLS

### Los correos llegan a spam
- Configura SPF, DKIM y DMARC en tu dominio
- Usa un servicio dedicado como SendGrid o Mailgun
- Evita palabras que activen filtros de spam

## Testing

Para probar sin enviar correos reales:

1. Usa MailHog (incluido en Docker):
```env
MAIL_SERVER=mailhog
MAIL_PORT=1025
MAIL_USE_CREDENTIALS=False
MAIL_STARTTLS=False
```

2. Accede a http://localhost:8025 para ver los correos

## Mejores Prácticas

1. **Nunca hardcodees credenciales** - Usa variables de entorno
2. **Usa plantillas** - Facilita el mantenimiento
3. **Maneja errores** - Los correos pueden fallar
4. **Limita la tasa** - Evita ser marcado como spam
5. **Logs detallados** - Para debugging
6. **Prueba localmente** - Usa MailHog o similar