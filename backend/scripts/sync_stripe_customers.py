#!/usr/bin/env python3
"""
Script para sincronizar customers de Stripe con usuarios de la base de datos
"""
import asyncio
import stripe
from app.core.config import settings
from app.db.async_database import AsyncSessionLocal
from app.db.models import User
from sqlalchemy import select

# Configurar Stripe
stripe.api_key = settings.STRIPE_SECRET_KEY

async def sync_stripe_customers():
    """Sincronizar customers de Stripe con usuarios en BD"""
    print("🔄 Sincronizando customers de Stripe...")
    print(f"🔑 Usando Stripe API: {stripe.api_key[:20]}...{stripe.api_key[-4:]}")
    print("-" * 60)
    
    async with AsyncSessionLocal() as db:
        # Obtener todos los usuarios
        result = await db.execute(select(User))
        users = result.scalars().all()
        
        print(f"📊 Encontrados {len(users)} usuarios en la base de datos")
        print("-" * 60)
        
        for user in users:
            print(f"👤 Usuario: {user.email}")
            print(f"   ID: {user.id}")
            print(f"   Clerk ID: {user.clerk_user_id}")
            print(f"   Stripe Customer ID: {user.stripe_customer_id}")
            
            if user.stripe_customer_id:
                # Verificar si el customer existe en Stripe
                try:
                    customer = stripe.Customer.retrieve(user.stripe_customer_id)
                    print(f"   ✅ Customer existe en Stripe")
                    print(f"   📧 Email en Stripe: {customer.email}")
                    print(f"   📅 Creado: {customer.created}")
                    
                    # Verificar si el email coincide
                    if customer.email != user.email:
                        print(f"   ⚠️ Email no coincide, actualizando...")
                        stripe.Customer.modify(
                            user.stripe_customer_id,
                            email=user.email,
                            name=user.full_name or user.email.split('@')[0]
                        )
                        print(f"   ✅ Email actualizado en Stripe")
                        
                except stripe.error.InvalidRequestError as e:
                    if "No such customer" in str(e):
                        print(f"   ❌ Customer no existe en Stripe: {user.stripe_customer_id}")
                        print(f"   🔧 Creando nuevo customer...")
                        
                        # Crear nuevo customer
                        new_customer = stripe.Customer.create(
                            email=user.email,
                            name=user.full_name or user.email.split('@')[0],
                            metadata={
                                'user_id': str(user.id),
                                'clerk_user_id': user.clerk_user_id,
                                'created_from': 'sync_script'
                            }
                        )
                        
                        # Actualizar en la base de datos
                        user.stripe_customer_id = new_customer.id
                        await db.commit()
                        
                        print(f"   ✅ Nuevo customer creado: {new_customer.id}")
                    else:
                        print(f"   ❌ Error de Stripe: {str(e)}")
                        
            else:
                print(f"   ℹ️ No tiene Stripe Customer ID")
                print(f"   🔧 Creando customer...")
                
                # Crear customer en Stripe
                customer = stripe.Customer.create(
                    email=user.email,
                    name=user.full_name or user.email.split('@')[0],
                    metadata={
                        'user_id': str(user.id),
                        'clerk_user_id': user.clerk_user_id,
                        'created_from': 'sync_script'
                    }
                )
                
                # Actualizar en la base de datos
                user.stripe_customer_id = customer.id
                await db.commit()
                
                print(f"   ✅ Customer creado: {customer.id}")
            
            print("-" * 60)
        
        print("🏁 Sincronización completada")

async def list_stripe_customers():
    """Listar customers en Stripe para debugging"""
    print("📋 Listando customers en Stripe...")
    print("-" * 60)
    
    try:
        customers = stripe.Customer.list(limit=10)
        
        if not customers.data:
            print("❌ No hay customers en Stripe")
            return
            
        for customer in customers.data:
            print(f"🏷️ Customer ID: {customer.id}")
            print(f"📧 Email: {customer.email}")
            print(f"👤 Nombre: {customer.name}")
            print(f"📅 Creado: {customer.created}")
            if customer.metadata:
                print(f"🏷️ Metadata: {customer.metadata}")
            print("-" * 40)
            
    except Exception as e:
        print(f"❌ Error listando customers: {str(e)}")

async def main():
    """Función principal"""
    print("🚀 Iniciando sincronización de Stripe customers...")
    
    # Primero listar customers existentes
    await list_stripe_customers()
    
    print("\n" + "="*60)
    
    # Luego sincronizar usuarios
    await sync_stripe_customers()

if __name__ == "__main__":
    asyncio.run(main())