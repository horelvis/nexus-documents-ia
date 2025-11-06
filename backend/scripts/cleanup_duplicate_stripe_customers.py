#!/usr/bin/env python3
"""
Script para limpiar customers duplicados de Stripe causados por usuarios duplicados
"""
import asyncio
import stripe
from collections import defaultdict
from app.core.config import settings
from app.db.async_database import AsyncSessionLocal
from app.db.models import User
from sqlalchemy import select

# Configurar Stripe
stripe.api_key = settings.STRIPE_SECRET_KEY

async def find_duplicate_customers():
    """Encontrar customers duplicados por email en Stripe"""
    print("🔍 Buscando customers duplicados en Stripe...")
    print(f"🔑 Usando Stripe API: {stripe.api_key[:20]}...{stripe.api_key[-4:]}")
    print("-" * 60)
    
    customers_by_email = defaultdict(list)
    
    # Obtener todos los customers (paginado)
    has_more = True
    starting_after = None
    total_customers = 0
    
    while has_more:
        params = {'limit': 100}
        if starting_after:
            params['starting_after'] = starting_after
            
        customers = stripe.Customer.list(**params)
        total_customers += len(customers.data)
        
        for customer in customers.data:
            if customer.email:  # Solo procesar customers con email
                customers_by_email[customer.email].append(customer)
        
        has_more = customers.has_more
        if has_more:
            starting_after = customers.data[-1].id
    
    print(f"📊 Total de customers procesados: {total_customers}")
    
    # Encontrar duplicados
    duplicates = {
        email: customers 
        for email, customers in customers_by_email.items() 
        if len(customers) > 1
    }
    
    if duplicates:
        print(f"⚠️ Encontrados {len(duplicates)} emails con customers duplicados:")
        for email, customers in duplicates.items():
            print(f"\n📧 Email: {email} ({len(customers)} customers)")
            for customer in customers:
                print(f"   🏷️ Customer: {customer.id}")
                print(f"      Creado: {customer.created}")
                print(f"      Nombre: {customer.name}")
                if customer.metadata:
                    print(f"      Metadata: {customer.metadata}")
                
                # Verificar si tiene suscripciones activas
                subscriptions = stripe.Subscription.list(
                    customer=customer.id,
                    status='active'
                )
                if subscriptions.data:
                    print(f"      🔗 Suscripciones activas: {len(subscriptions.data)}")
                    for sub in subscriptions.data:
                        print(f"         - {sub.id}: {sub.status}")
                else:
                    print(f"      ⚪ Sin suscripciones activas")
    else:
        print("✅ No se encontraron customers duplicados")
    
    return duplicates

async def get_active_users_customers():
    """Obtener customers que están siendo usados por usuarios activos"""
    print("\n🔍 Verificando customers de usuarios activos...")
    
    active_customers = set()
    
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(User).filter(User.is_active == True))
        users = result.scalars().all()
        
        print(f"📊 Usuarios activos en BD: {len(users)}")
        
        for user in users:
            if user.stripe_customer_id:
                active_customers.add(user.stripe_customer_id)
                print(f"   👤 {user.email} → {user.stripe_customer_id}")
    
    print(f"🏷️ Total customers activos: {len(active_customers)}")
    return active_customers

def choose_customer_to_keep(customers):
    """Decidir qué customer mantener basado en criterios"""
    # Criterios de prioridad:
    # 1. Customer con suscripciones activas
    # 2. Customer más reciente
    # 3. Customer con metadata más completo
    
    scored_customers = []
    
    for customer in customers:
        score = 0
        
        # +100 puntos por suscripciones activas
        try:
            subscriptions = stripe.Subscription.list(
                customer=customer.id,
                status='active'
            )
            if subscriptions.data:
                score += 100
                print(f"      🔗 {customer.id}: +100 (tiene suscripciones activas)")
        except:
            pass
        
        # +10 puntos por metadata completo
        if customer.metadata and len(customer.metadata) > 0:
            score += 10
            print(f"      🏷️ {customer.id}: +10 (tiene metadata)")
        
        # +5 puntos por tener nombre
        if customer.name:
            score += 5
            print(f"      👤 {customer.id}: +5 (tiene nombre)")
        
        # Puntos por fecha (más reciente = mejor)
        # created es timestamp unix
        score += customer.created / 1000000  # Normalizar para que sea pequeño
        
        scored_customers.append((customer, score))
    
    # Ordenar por score descendente
    scored_customers.sort(key=lambda x: x[1], reverse=True)
    winner = scored_customers[0][0]
    
    print(f"   🏆 Customer seleccionado: {winner.id} (score: {scored_customers[0][1]:.2f})")
    return winner

async def cleanup_duplicate_customers(dry_run=True):
    """Limpiar customers duplicados"""
    print(f"\n🧹 Iniciando limpieza de customers duplicados (dry_run={dry_run})...")
    
    # Encontrar duplicados
    duplicates = await find_duplicate_customers()
    if not duplicates:
        return
    
    # Obtener customers de usuarios activos
    active_customers = await get_active_users_customers()
    
    print(f"\n📋 Plan de limpieza:")
    print("-" * 60)
    
    for email, customers in duplicates.items():
        print(f"\n📧 Procesando email: {email}")
        
        # Verificar cuáles están siendo usados por usuarios activos
        active_in_group = [c for c in customers if c.id in active_customers]
        inactive_in_group = [c for c in customers if c.id not in active_customers]
        
        print(f"   📊 Customers activos en BD: {len(active_in_group)}")
        print(f"   📊 Customers huérfanos: {len(inactive_in_group)}")
        
        if active_in_group:
            # Si hay customers activos, mantener el mejor de ellos
            keeper = choose_customer_to_keep(active_in_group)
            to_delete = [c for c in customers if c.id != keeper.id]
        else:
            # Si no hay activos, mantener el mejor general
            keeper = choose_customer_to_keep(customers)
            to_delete = [c for c in customers if c.id != keeper.id]
        
        print(f"   🏆 Mantener: {keeper.id}")
        print(f"   🗑️ Eliminar: {[c.id for c in to_delete]}")
        
        if not dry_run:
            # TODO: Transferir suscripciones si es necesario
            # TODO: Actualizar referencias en BD
            # TODO: Eliminar customers duplicados
            print("   ⚠️ ELIMINACIÓN REAL NO IMPLEMENTADA - usa dry_run=True por seguridad")
        else:
            print("   🔍 DRY RUN: No se realizaron cambios")

async def main():
    """Función principal"""
    import sys
    
    dry_run = True
    if len(sys.argv) > 1 and sys.argv[1] == "--execute":
        print("⚠️ MODO EJECUCIÓN NO DISPONIBLE POR SEGURIDAD")
        print("   Este script requiere revisión manual antes de ejecutar eliminaciones")
        return
    
    print("🚀 Iniciando análisis de customers duplicados...")
    print("🔍 MODO ANÁLISIS - Solo se reportarán problemas, no se harán cambios")
    
    await cleanup_duplicate_customers(dry_run=True)

if __name__ == "__main__":
    asyncio.run(main())