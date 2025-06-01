"""
Initialize default agents and tools
"""
import asyncio
import sys
import os

# Add the parent directory to the path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy.orm import Session
from app.db.database import get_db
from app.db.models import AgentTool, Tenant, User
from app.services.agent_service import AgentService
from app.schemas.agent import AgentCreate


def init_default_tools(db: Session):
    """Inicializar herramientas por defecto"""
    
    default_tools = [
        {
            "name": "create_signature_request",
            "description": "Crear una nueva solicitud de firma digital",
            "tool_type": "internal",
            "configuration_schema": {
                "type": "object",
                "properties": {
                    "title": {"type": "string", "description": "Título de la solicitud"},
                    "signers": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "name": {"type": "string"},
                                "email": {"type": "string", "format": "email"}
                            }
                        }
                    },
                    "document_name": {"type": "string"}
                },
                "required": ["title", "signers", "document_name"]
            },
            "requires_admin": False,
            "is_tenant_specific": True
        },
        {
            "name": "get_signature_status",
            "description": "Consultar el estado de una solicitud de firma",
            "tool_type": "internal",
            "configuration_schema": {
                "type": "object",
                "properties": {
                    "request_id": {"type": "string", "description": "ID de la solicitud"}
                },
                "required": ["request_id"]
            },
            "requires_admin": False,
            "is_tenant_specific": True
        },
        {
            "name": "list_signature_requests",
            "description": "Listar solicitudes de firma del usuario",
            "tool_type": "internal",
            "configuration_schema": {
                "type": "object",
                "properties": {
                    "status": {"type": "string", "description": "Filtrar por estado"},
                    "limit": {"type": "integer", "minimum": 1, "maximum": 100}
                }
            },
            "requires_admin": False,
            "is_tenant_specific": True
        },
        {
            "name": "send_signature_request",
            "description": "Enviar solicitud de firma a los firmantes",
            "tool_type": "internal",
            "configuration_schema": {
                "type": "object",
                "properties": {
                    "request_id": {"type": "string", "description": "ID de la solicitud"}
                },
                "required": ["request_id"]
            },
            "requires_admin": False,
            "is_tenant_specific": True
        },
        {
            "name": "download_signed_document",
            "description": "Descargar documento firmado",
            "tool_type": "internal",
            "configuration_schema": {
                "type": "object",
                "properties": {
                    "request_id": {"type": "string", "description": "ID de la solicitud"}
                },
                "required": ["request_id"]
            },
            "requires_admin": False,
            "is_tenant_specific": True
        },
        {
            "name": "search_documents",
            "description": "Buscar documentos usando búsqueda semántica",
            "tool_type": "internal",
            "configuration_schema": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Consulta de búsqueda"},
                    "limit": {"type": "integer", "minimum": 1, "maximum": 20}
                },
                "required": ["query"]
            },
            "requires_admin": False,
            "is_tenant_specific": True
        },
        {
            "name": "calculate",
            "description": "Realizar cálculos matemáticos básicos",
            "tool_type": "internal",
            "configuration_schema": {
                "type": "object",
                "properties": {
                    "expression": {"type": "string", "description": "Expresión matemática"}
                },
                "required": ["expression"]
            },
            "requires_admin": False,
            "is_tenant_specific": False
        },
        {
            "name": "analyze_document",
            "description": "Analizar contenido de documentos con IA",
            "tool_type": "internal",
            "configuration_schema": {
                "type": "object",
                "properties": {
                    "document_content": {"type": "string"},
                    "analysis_type": {
                        "type": "string",
                        "enum": ["summary", "keywords", "sentiment", "general"]
                    }
                },
                "required": ["document_content"]
            },
            "requires_admin": False,
            "is_tenant_specific": True
        }
    ]
    
    for tool_data in default_tools:
        # Verificar si ya existe
        existing = db.query(AgentTool).filter(
            AgentTool.name == tool_data["name"]
        ).first()
        
        if not existing:
            tool = AgentTool(**tool_data)
            db.add(tool)
            print(f"✅ Herramienta '{tool_data['name']}' creada")
        else:
            print(f"⚠️ Herramienta '{tool_data['name']}' ya existe")
    
    db.commit()


def create_default_agents(db: Session):
    """Crear agentes por defecto para cada tenant"""
    
    agent_service = AgentService(db)
    
    # Obtener todos los tenants
    tenants = db.query(Tenant).all()
    
    for tenant in tenants:
        print(f"\n🏢 Procesando tenant: {tenant.name}")
        
        # Buscar un usuario administrador del tenant
        admin_user = db.query(User).filter(
            User.tenant_id == tenant.id,
            User.is_superuser == True
        ).first()
        
        if not admin_user:
            # Usar el primer usuario del tenant
            admin_user = db.query(User).filter(
                User.tenant_id == tenant.id
            ).first()
        
        if not admin_user:
            print(f"❌ No se encontraron usuarios para el tenant {tenant.name}")
            continue
        
        # Agente de Firma Digital
        signature_agent_data = AgentCreate(
            name="Asistente de Firma Digital",
            description="Agente especializado en la gestión de solicitudes de firma digital. Puede crear, enviar, consultar y gestionar firmas electrónicas.",
            type="digital_signature",
            configuration={
                "default_signature_type": "sequential",
                "notification_settings": {
                    "send_reminders": True,
                    "reminder_frequency_hours": 24
                },
                "security_level": "standard",
                "supported_file_types": ["pdf", "docx", "txt"]
            },
            tools=[
                "create_signature_request",
                "get_signature_status", 
                "list_signature_requests",
                "send_signature_request",
                "download_signed_document",
                "search_documents",
                "calculate"
            ],
            is_active=True,
            is_public=True
        )
        
        try:
            signature_agent = agent_service.create_agent(
                signature_agent_data,
                tenant.id,
                admin_user.id
            )
            print(f"✅ Agente de Firma Digital creado: {signature_agent.id}")
        except Exception as e:
            if "already exists" in str(e):
                print(f"⚠️ Agente de Firma Digital ya existe para {tenant.name}")
            else:
                print(f"❌ Error creando agente de firma: {str(e)}")
        
        # Agente Analizador de Documentos
        analyzer_agent_data = AgentCreate(
            name="Analizador de Documentos IA",
            description="Agente inteligente para análisis de documentos. Puede resumir, extraer palabras clave, analizar sentimientos y realizar búsquedas semánticas.",
            type="document_analyzer",
            configuration={
                "analysis_types": ["summary", "keywords", "sentiment", "general"],
                "language_settings": {
                    "primary_language": "es",
                    "supported_languages": ["es", "en", "fr"]
                },
                "confidence_threshold": 0.7,
                "max_document_size": 50000
            },
            tools=[
                "analyze_document",
                "search_documents",
                "calculate"
            ],
            is_active=True,
            is_public=True
        )
        
        try:
            analyzer_agent = agent_service.create_agent(
                analyzer_agent_data,
                tenant.id,
                admin_user.id
            )
            print(f"✅ Agente Analizador creado: {analyzer_agent.id}")
        except Exception as e:
            if "already exists" in str(e):
                print(f"⚠️ Agente Analizador ya existe para {tenant.name}")
            else:
                print(f"❌ Error creando agente analizador: {str(e)}")


def main():
    """Función principal"""
    print("🚀 Inicializando sistema de agentes...")
    
    # Obtener sesión de base de datos
    db_gen = get_db()
    db = next(db_gen)
    
    try:
        # Inicializar herramientas
        print("\n📦 Inicializando herramientas por defecto...")
        init_default_tools(db)
        
        # Crear agentes por defecto
        print("\n🤖 Creando agentes por defecto...")
        create_default_agents(db)
        
        print("\n✅ Inicialización completada exitosamente!")
        
    except Exception as e:
        print(f"\n❌ Error durante la inicialización: {str(e)}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()