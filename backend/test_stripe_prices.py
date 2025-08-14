#!/usr/bin/env python3
"""
Script rápido para probar los nuevos precios de Stripe
"""
import stripe
import os
from dotenv import load_dotenv

# Cargar variables de entorno
load_dotenv()

# Configurar Stripe
stripe.api_key = os.getenv("STRIPE_SECRET_KEY")

# Nuevos precios
prices_to_test = {
    "STRIPE_BASIC_PRICE_ID": "price_1Rw1ngR8hZSzPrz7IopIiINp",
    "STRIPE_PRO_PRICE_ID": "price_1Rw1ngR8hZSzPrz73m6W8EJ6", 
    "STRIPE_PRO_YEARLY_PRICE_ID": "price_1Rw1nhR8hZSzPrz7wwJjQyDY"
}

print("🔍 Probando nuevos precios de Stripe...")
print(f"API Key: {stripe.api_key[:20]}...{stripe.api_key[-4:] if stripe.api_key else 'NOT SET'}")
print("-" * 60)

for name, price_id in prices_to_test.items():
    try:
        price = stripe.Price.retrieve(price_id)
        print(f"✅ {name}: {price_id}")
        print(f"   Producto: {price.product}")
        print(f"   Precio: ${price.unit_amount/100:.2f}")
        print(f"   Moneda: {price.currency}")
        print(f"   Intervalo: {price.recurring.interval if price.recurring else 'one-time'}")
        
        # Obtener información del producto
        try:
            product = stripe.Product.retrieve(price.product)
            print(f"   Nombre: {product.name}")
            if product.metadata:
                print(f"   Metadata: {product.metadata}")
        except:
            pass
            
        print("-" * 60)
        
    except stripe.error.StripeError as e:
        print(f"❌ {name}: {price_id}")
        print(f"   Error: {str(e)}")
        print("-" * 60)

print("🏁 Prueba completada")