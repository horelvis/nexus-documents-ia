# scripts/configure_stripe_portal.py
"""
Script para configurar el Customer Portal de Stripe una sola vez.
Ejecutar después de desplegar el backend.
"""

import stripe
import os
from typing import Dict, Any

# Configurar Stripe
stripe.api_key = os.getenv("STRIPE_SECRET_KEY")
FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:3000")

def configure_customer_portal() -> Dict[str, Any]:
    """
    Configura el Customer Portal de Stripe con todas las opciones necesarias.
    """
    try:
        print("🔧 Configurando Customer Portal de Stripe...")
        
        configuration = stripe.billing_portal.Configuration.create(
            # Información de la empresa
            business_profile={
                "headline": "Gestiona tu suscripción",
                "privacy_policy_url": f"{FRONTEND_URL}/privacy",
                "terms_of_service_url": f"{FRONTEND_URL}/terms",
            },
            
            # Funciones habilitadas
            features={
                # Actualizar método de pago
                "payment_method_update": {
                    "enabled": True
                },
                
                # Cancelar suscripción
                "subscription_cancel": {
                    "enabled": True,
                    "mode": "at_period_end",  # Cancelar al final del período de facturación
                    "cancellation_reason": {
                        "enabled": True,
                        "options": [
                            "too_expensive",        # Muy caro
                            "missing_features",     # Faltan funciones
                            "switched_service",     # Cambié a otro servicio
                            "unused",              # No lo uso
                            "other"                # Otro motivo
                        ]
                    }
                },
                
                # Actualizar suscripción (cambiar planes)
                "subscription_update": {
                    "enabled": True,
                    "default_allowed_updates": ["price", "promotion_code"],
                    "proration_behavior": "create_prorations"  # Crear prorrateos
                },
                
                # Historial de facturas
                "invoice_history": {
                    "enabled": True
                },
                
                # Actualizar información del cliente
                "customer_update": {
                    "enabled": True,
                    "allowed_updates": ["email", "address", "phone", "tax_id"]
                }
            },
            
            # URL por defecto de retorno
            default_return_url=f"{FRONTEND_URL}/dashboard/settings/billing"
        )
        
        print(f"✅ Customer Portal configurado exitosamente!")
        print(f"📋 Configuration ID: {configuration.id}")
        print(f"🔗 Business Profile: {configuration.business_profile}")
        print(f"⚙️  Features configuradas:")
        
        for feature_name, feature_config in configuration.features.items():
            if feature_config.get("enabled"):
                print(f"   - ✅ {feature_name}")
            else:
                print(f"   - ❌ {feature_name}")
        
        return {
            "success": True,
            "configuration_id": configuration.id,
            "message": "Customer Portal configurado exitosamente"
        }
        
    except stripe.error.InvalidRequestError as e:
        print(f"❌ Error de configuración: {e}")
        return {
            "success": False,
            "error": str(e),
            "message": "Error en la configuración. Verifica los parámetros."
        }
    
    except stripe.error.AuthenticationError as e:
        print(f"❌ Error de autenticación: {e}")
        return {
            "success": False,
            "error": str(e),
            "message": "Error de autenticación. Verifica STRIPE_SECRET_KEY."
        }
    
    except Exception as e:
        print(f"❌ Error inesperado: {e}")
        return {
            "success": False,
            "error": str(e),
            "message": "Error inesperado durante la configuración."
        }


def verify_existing_configuration():
    """
    Verifica si ya existe una configuración del Customer Portal.
    """
    try:
        print("🔍 Verificando configuraciones existentes...")
        
        configurations = stripe.billing_portal.Configuration.list(limit=10)
        
        if configurations.data:
            print(f"📋 Encontradas {len(configurations.data)} configuraciones:")
            for config in configurations.data:
                print(f"   - ID: {config.id}")
                print(f"     Activa: {'✅' if config.is_default else '❌'}")
                print(f"     Creada: {config.created}")
                if config.business_profile:
                    print(f"     Headline: {config.business_profile.get('headline', 'N/A')}")
                print()
            
            return configurations.data
        else:
            print("📭 No se encontraron configuraciones existentes.")
            return []
            
    except Exception as e:
        print(f"❌ Error verificando configuraciones: {e}")
        return []


def update_portal_configuration(configuration_id: str):
    """
    Actualiza una configuración existente del Customer Portal.
    """
    try:
        print(f"🔄 Actualizando configuración {configuration_id}...")
        
        configuration = stripe.billing_portal.Configuration.modify(
            configuration_id,
            business_profile={
                "headline": "Gestiona tu suscripción",
                "privacy_policy_url": f"{FRONTEND_URL}/privacy",
                "terms_of_service_url": f"{FRONTEND_URL}/terms",
            }
        )
        
        print(f"✅ Configuración actualizada exitosamente!")
        return configuration
        
    except Exception as e:
        print(f"❌ Error actualizando configuración: {e}")
        return None


def main():
    """
    Función principal para configurar el Customer Portal.
    """
    print("🚀 Iniciando configuración del Customer Portal de Stripe")
    print("=" * 60)
    
    # Verificar variables de entorno
    if not stripe.api_key:
        print("❌ Error: STRIPE_SECRET_KEY no está configurada")
        return
    
    print(f"🔑 Usando Stripe API Key: {stripe.api_key[:12]}...")
    print(f"🌐 Frontend URL: {FRONTEND_URL}")
    print()
    
    # Verificar configuraciones existentes
    existing_configs = verify_existing_configuration()
    
    if existing_configs:
        print("⚠️  Ya existen configuraciones del Customer Portal.")
        choice = input("¿Deseas crear una nueva configuración? (y/N): ").lower()
        
        if choice not in ['y', 'yes', 'sí', 's']:
            print("🛑 Cancelando configuración.")
            return
    
    # Crear nueva configuración
    result = configure_customer_portal()
    
    if result["success"]:
        print("\n" + "=" * 60)
        print("🎉 ¡Configuración completada!")
        print("\n📝 Próximos pasos:")
        print("1. Guarda el Configuration ID en tus variables de entorno (opcional)")
        print("2. Prueba el Customer Portal desde tu aplicación")
        print("3. Verifica que las URLs de retorno funcionen correctamente")
        print("\n💡 Notas:")
        print("- Los usuarios ahora pueden gestionar sus suscripciones directamente")
        print("- Todos los cambios se sincronizarán automáticamente via webhooks")
        print("- La configuración es global para toda tu cuenta de Stripe")
    else:
        print(f"\n❌ Configuración fallida: {result['message']}")
        if result.get("error"):
            print(f"Error técnico: {result['error']}")


if __name__ == "__main__":
    main()