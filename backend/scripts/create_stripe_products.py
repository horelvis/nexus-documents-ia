#!/usr/bin/env python3
"""
Script para crear productos y precios en Stripe para Nexus
Ejecutar: python scripts/create_stripe_products.py
"""

import os
import sys
import stripe
from typing import Dict, Any

# Configuración de Stripe
stripe.api_key = os.getenv("STRIPE_SECRET_KEY")

if not stripe.api_key:
    print("❌ Error: STRIPE_SECRET_KEY no está configurado en las variables de entorno")
    sys.exit(1)

def create_product_and_prices() -> Dict[str, Any]:
    """Crear productos y precios en Stripe"""
    results = {
        "products": {},
        "prices": {},
        "errors": []
    }
    
    # Definir productos
    products_config = [
        {
            "id": "nexus_free",
            "name": "Nexus Free",
            "description": "Plan gratuito para comenzar con gestión documental básica",
            "metadata": {
                "plan_type": "free",
                "features": "100 documents, 1GB storage, basic search, 1 user"
            }
        },
        {
            "id": "nexus_pro", 
            "name": "Nexus Pro",
            "description": "Plan profesional con IA avanzada y funcionalidades premium",
            "metadata": {
                "plan_type": "pro",
                "features": "Unlimited documents, 100GB storage, AI search, signatures, 10 users, API access"
            }
        },
        {
            "id": "nexus_enterprise",
            "name": "Nexus Enterprise", 
            "description": "Plan empresarial con todas las funcionalidades y soporte dedicado",
            "metadata": {
                "plan_type": "enterprise",
                "features": "Unlimited everything, 1TB storage, advanced AI, custom integrations, unlimited users, SLA"
            }
        }
    ]
    
    # Definir precios (solo para planes de pago)
    prices_config = [
        {
            "product_id": "nexus_pro",
            "unit_amount": 2900,  # $29.00 USD
            "currency": "usd",
            "recurring_interval": "month",
            "nickname": "Pro Monthly",
            "lookup_key": "nexus_pro_monthly"
        },
        {
            "product_id": "nexus_pro", 
            "unit_amount": 29000,  # $290.00 USD (yearly discount)
            "currency": "usd",
            "recurring_interval": "year",
            "nickname": "Pro Yearly",
            "lookup_key": "nexus_pro_yearly"
        },
        {
            "product_id": "nexus_enterprise",
            "unit_amount": 9900,  # $99.00 USD
            "currency": "usd", 
            "recurring_interval": "month",
            "nickname": "Enterprise Monthly",
            "lookup_key": "nexus_enterprise_monthly"
        },
        {
            "product_id": "nexus_enterprise",
            "unit_amount": 99000,  # $990.00 USD (yearly discount)
            "currency": "usd",
            "recurring_interval": "year", 
            "nickname": "Enterprise Yearly",
            "lookup_key": "nexus_enterprise_yearly"
        }
    ]
    
    print("🚀 Creando productos en Stripe...")
    
    # Crear productos
    for product_config in products_config:
        try:
            # Verificar si el producto ya existe
            existing_products = stripe.Product.list(limit=100)
            existing_product = None
            
            for existing in existing_products.data:
                if existing.metadata.get("plan_type") == product_config["metadata"]["plan_type"]:
                    existing_product = existing
                    break
            
            if existing_product:
                print(f"✅ Producto {product_config['name']} ya existe: {existing_product.id}")
                results["products"][product_config["id"]] = existing_product
            else:
                product = stripe.Product.create(
                    name=product_config["name"],
                    description=product_config["description"],
                    metadata=product_config["metadata"]
                )
                print(f"✅ Producto creado: {product_config['name']} - {product.id}")
                results["products"][product_config["id"]] = product
                
        except Exception as e:
            error_msg = f"Error creando producto {product_config['name']}: {str(e)}"
            print(f"❌ {error_msg}")
            results["errors"].append(error_msg)
    
    print("\n💰 Creando precios en Stripe...")
    
    # Crear precios
    for price_config in prices_config:
        try:
            product_id = results["products"][price_config["product_id"]].id
            
            # Verificar si el precio ya existe
            existing_prices = stripe.Price.list(product=product_id, limit=100)
            existing_price = None
            
            for existing in existing_prices.data:
                if (existing.lookup_key == price_config["lookup_key"] or
                    (existing.nickname == price_config["nickname"] and 
                     existing.unit_amount == price_config["unit_amount"])):
                    existing_price = existing
                    break
            
            if existing_price:
                print(f"✅ Precio {price_config['nickname']} ya existe: {existing_price.id}")
                results["prices"][price_config["lookup_key"]] = existing_price
            else:
                price = stripe.Price.create(
                    product=product_id,
                    unit_amount=price_config["unit_amount"],
                    currency=price_config["currency"],
                    recurring={
                        "interval": price_config["recurring_interval"]
                    },
                    nickname=price_config["nickname"],
                    lookup_key=price_config["lookup_key"]
                )
                print(f"✅ Precio creado: {price_config['nickname']} - {price.id}")
                results["prices"][price_config["lookup_key"]] = price
                
        except Exception as e:
            error_msg = f"Error creando precio {price_config['nickname']}: {str(e)}"
            print(f"❌ {error_msg}")
            results["errors"].append(error_msg)
    
    return results

def display_results(results: Dict[str, Any]):
    """Mostrar resumen de resultados"""
    print("\n" + "="*60)
    print("📋 RESUMEN DE CONFIGURACIÓN")
    print("="*60)
    
    print("\n🏷️  PRODUCTOS CREADOS:")
    for product_id, product in results["products"].items():
        print(f"  • {product.name}")
        print(f"    ID: {product.id}")
        print(f"    Tipo: {product.metadata.get('plan_type', 'N/A')}")
        print()
    
    print("💳 PRECIOS CREADOS:")
    for lookup_key, price in results["prices"].items():
        amount = price.unit_amount / 100
        interval = price.recurring.interval if price.recurring else "one-time"
        print(f"  • {price.nickname}: ${amount:.2f} USD/{interval}")
        print(f"    ID: {price.id}")
        print(f"    Lookup Key: {lookup_key}")
        print()
    
    if results["errors"]:
        print("❌ ERRORES:")
        for error in results["errors"]:
            print(f"  • {error}")
        print()
    
    print("🔧 VARIABLES DE ENTORNO RECOMENDADAS:")
    pro_monthly = results["prices"].get("nexus_pro_monthly")
    enterprise_monthly = results["prices"].get("nexus_enterprise_monthly")
    
    if pro_monthly:
        print(f"STRIPE_PRO_PRICE_ID={pro_monthly.id}")
    if enterprise_monthly:
        print(f"STRIPE_ENTERPRISE_PRICE_ID={enterprise_monthly.id}")
    
    print("\n🎯 PRÓXIMOS PASOS:")
    print("1. Copiar los Price IDs a tus variables de entorno")
    print("2. Configurar webhooks en Stripe Dashboard")
    print("3. Probar el flujo de checkout completo")
    print("4. Configurar Customer Portal si es necesario")

def main():
    """Función principal"""
    print("🎯 Configurando productos y precios de Nexus en Stripe")
    print("="*60)
    
    try:
        # Verificar conexión con Stripe
        stripe.Account.retrieve()
        print("✅ Conexión con Stripe establecida")
        
        # Crear productos y precios
        results = create_product_and_prices()
        
        # Mostrar resultados
        display_results(results)
        
        if not results["errors"]:
            print("\n🎉 ¡Configuración completada exitosamente!")
        else:
            print(f"\n⚠️  Configuración completada con {len(results['errors'])} errores")
            return 1
            
    except stripe.error.AuthenticationError:
        print("❌ Error: Clave de API de Stripe inválida")
        return 1
    except stripe.error.StripeError as e:
        print(f"❌ Error de Stripe: {str(e)}")
        return 1
    except Exception as e:
        print(f"❌ Error inesperado: {str(e)}")
        return 1
    
    return 0

if __name__ == "__main__":
    sys.exit(main())