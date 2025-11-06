#!/usr/bin/env python3
"""
Script para verificar la configuración de Stripe
Ejecutar: python scripts/verify_stripe_config.py
"""

import os
import sys
import stripe
from app.core.config import settings

def verify_stripe_config():
    """Verificar configuración de Stripe"""
    print("🔍 Verificando configuración de Stripe...")
    
    # Verificar variables de entorno
    required_vars = [
        'STRIPE_SECRET_KEY',
        'STRIPE_BASIC_PRICE_ID',
        'STRIPE_PRO_PRICE_ID', 
        'STRIPE_PRO_YEARLY_PRICE_ID'
    ]
    
    missing_vars = []
    for var in required_vars:
        if not getattr(settings, var, None):
            missing_vars.append(var)
    
    if missing_vars:
        print(f"❌ Variables faltantes: {', '.join(missing_vars)}")
        return False
    
    # Configurar Stripe
    stripe.api_key = settings.STRIPE_SECRET_KEY
    
    try:
        # Verificar conexión
        stripe.Account.retrieve()
        print("✅ Conexión con Stripe establecida")
        
        # Verificar Price IDs
        price_ids = {
            'Basic Monthly': settings.STRIPE_BASIC_PRICE_ID,
            'Pro Monthly': settings.STRIPE_PRO_PRICE_ID,
            'Pro Yearly': settings.STRIPE_PRO_YEARLY_PRICE_ID,
        }
        
        # Solo verificar Enterprise si está configurado
        if hasattr(settings, 'STRIPE_ENTERPRISE_PRICE_ID') and settings.STRIPE_ENTERPRISE_PRICE_ID:
            price_ids['Enterprise Monthly'] = settings.STRIPE_ENTERPRISE_PRICE_ID
        
        for name, price_id in price_ids.items():
            try:
                price = stripe.Price.retrieve(price_id)
                amount = price.unit_amount / 100
                currency = price.currency.upper()
                interval = price.recurring.interval if price.recurring else 'one-time'
                
                print(f"✅ {name}: {currency} ${amount:.2f}/{interval}")
                print(f"   ID: {price_id}")
                print(f"   Product: {price.product}")
                print()
                
            except stripe.error.InvalidRequestError:
                print(f"❌ {name}: Price ID inválido - {price_id}")
                return False
        
        print("🎉 ¡Configuración de Stripe verificada exitosamente!")
        return True
        
    except stripe.error.AuthenticationError:
        print("❌ Clave de API de Stripe inválida")
        return False
    except Exception as e:
        print(f"❌ Error: {str(e)}")
        return False

def main():
    """Función principal"""
    success = verify_stripe_config()
    return 0 if success else 1

if __name__ == "__main__":
    sys.exit(main())