#!/usr/bin/env python3
"""
Script para limpiar usuarios duplicados por email.
CUIDADO: Este script modifica la base de datos. Usar con precaución.
"""
import asyncio
import logging
from typing import List, Dict
from datetime import datetime
from sqlalchemy import select, func, delete
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.async_database import AsyncSessionLocal
from app.db.models import User, Document, UserImage

# Configurar logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def find_duplicate_emails() -> List[Dict]:
    """Encontrar emails duplicados y sus usuarios"""
    async with AsyncSessionLocal() as db:
        try:
            # Buscar emails con más de un usuario
            result = await db.execute(
                select(
                    User.email,
                    func.count(User.id).label('count')
                )
                .group_by(User.email)
                .having(func.count(User.id) > 1)
            )
            
            duplicates = []
            for row in result.all():
                email = row.email
                
                # Obtener todos los usuarios con este email
                users_result = await db.execute(
                    select(User)
                    .filter(User.email == email)
                    .order_by(User.created_at.asc())  # Ordenar por fecha de creación
                )
                users = users_result.scalars().all()
                
                duplicates.append({
                    'email': email,
                    'users': users,
                    'count': len(users)
                })
            
            return duplicates
            
        except Exception as e:
            logger.error(f"Error finding duplicates: {str(e)}")
            return []

def choose_user_to_keep(users: List[User]) -> User:
    """
    Decidir cuál usuario mantener basado en criterios de prioridad:
    1. Usuario con más datos completos (Clerk ID, Stripe ID)
    2. Usuario más activo (onboarding completo, documentos)
    3. Usuario más antiguo
    """
    scored_users = []
    
    for user in users:
        score = 0
        
        # +10 puntos por tener Clerk ID
        if user.clerk_user_id:
            score += 10
        
        # +5 puntos por tener Stripe ID
        if user.stripe_customer_id:
            score += 5
        
        # +3 puntos por onboarding completo
        if user.onboarding_completed:
            score += 3
        
        # +2 puntos por estar activo
        if user.is_active:
            score += 2
        
        # +1 punto por ser superuser
        if user.is_superuser:
            score += 1
        
        # Bonus por antigüedad (días desde creación / 10)
        if user.created_at:
            days_old = (datetime.utcnow() - user.created_at.replace(tzinfo=None)).days
            score += days_old / 10
        
        scored_users.append((user, score))
    
    # Ordenar por score descendente
    scored_users.sort(key=lambda x: x[1], reverse=True)
    
    logger.info(f"Usuario seleccionado para mantener:")
    winner = scored_users[0][0]
    logger.info(f"  ID: {winner.id}")
    logger.info(f"  Score: {scored_users[0][1]}")
    logger.info(f"  Clerk ID: {winner.clerk_user_id}")
    logger.info(f"  Stripe ID: {winner.stripe_customer_id}")
    logger.info(f"  Onboarding: {winner.onboarding_completed}")
    logger.info(f"  Activo: {winner.is_active}")
    
    return winner

async def merge_user_data(keeper: User, duplicates: List[User], db: AsyncSession):
    """Transferir datos importantes de usuarios duplicados al usuario que se mantiene"""
    for duplicate in duplicates:
        if duplicate.id == keeper.id:
            continue
        
        logger.info(f"Transfiriendo datos de {duplicate.id} a {keeper.id}...")
        
        # Transferir documentos
        doc_result = await db.execute(
            select(func.count(Document.id))
            .filter(Document.created_by == duplicate.id)
        )
        doc_count = doc_result.scalar() or 0
        
        if doc_count > 0:
            logger.info(f"  Transfiriendo {doc_count} documentos...")
            await db.execute(
                Document.__table__.update()
                .where(Document.created_by == duplicate.id)
                .values(created_by=keeper.id)
            )
        
        # Actualizar información del usuario principal si es más completa
        updated = False
        
        if not keeper.full_name and duplicate.full_name:
            keeper.full_name = duplicate.full_name
            updated = True
            logger.info(f"  Actualizando nombre: {duplicate.full_name}")
        
        if not keeper.clerk_user_id and duplicate.clerk_user_id:
            keeper.clerk_user_id = duplicate.clerk_user_id
            updated = True
            logger.info(f"  Actualizando Clerk ID: {duplicate.clerk_user_id}")
        
        if not keeper.stripe_customer_id and duplicate.stripe_customer_id:
            keeper.stripe_customer_id = duplicate.stripe_customer_id
            updated = True
            logger.info(f"  Actualizando Stripe ID: {duplicate.stripe_customer_id}")
        
        if not keeper.onboarding_completed and duplicate.onboarding_completed:
            keeper.onboarding_completed = duplicate.onboarding_completed
            updated = True
            logger.info(f"  Actualizando onboarding: {duplicate.onboarding_completed}")
        
        if updated:
            logger.info(f"  Usuario principal actualizado")

async def delete_duplicate_user(user: User, db: AsyncSession):
    """Eliminar usuario duplicado y datos relacionados"""
    logger.info(f"Eliminando usuario duplicado: {user.id}")
    
    # Eliminar imagen de usuario si existe
    await db.execute(
        delete(UserImage).where(UserImage.user_id == user.id)
    )
    
    # Eliminar el usuario (las relaciones cascade deberían manejar el resto)
    await db.delete(user)

async def cleanup_email_duplicates(dry_run: bool = True):
    """Limpiar usuarios duplicados por email"""
    logger.info(f"🧹 Iniciando limpieza de usuarios duplicados (dry_run={dry_run})...")
    
    duplicates = await find_duplicate_emails()
    
    if not duplicates:
        logger.info("✅ No se encontraron emails duplicados")
        return
    
    logger.warning(f"⚠️ Se encontraron {len(duplicates)} emails con duplicados")
    
    async with AsyncSessionLocal() as db:
        try:
            for duplicate_group in duplicates:
                email = duplicate_group['email']
                users = duplicate_group['users']
                
                logger.info(f"\n📧 Procesando email: {email} ({len(users)} usuarios)")
                
                # Elegir usuario a mantener
                keeper = choose_user_to_keep(users)
                to_delete = [u for u in users if u.id != keeper.id]
                
                logger.info(f"👤 Manteniendo usuario: {keeper.id}")
                logger.info(f"🗑️ Eliminando usuarios: {[str(u.id) for u in to_delete]}")
                
                if not dry_run:
                    # Transferir datos importantes
                    await merge_user_data(keeper, to_delete, db)
                    
                    # Eliminar usuarios duplicados
                    for user_to_delete in to_delete:
                        await delete_duplicate_user(user_to_delete, db)
                    
                    await db.commit()
                    logger.info("✅ Limpieza completada para este email")
                else:
                    logger.info("🔍 DRY RUN: No se realizaron cambios")
            
            if not dry_run:
                logger.info("🏁 Limpieza de duplicados completada")
            else:
                logger.info("🏁 Análisis de duplicados completado (DRY RUN)")
                
        except Exception as e:
            await db.rollback()
            logger.error(f"❌ Error durante limpieza: {str(e)}")
            raise

async def main():
    """Función principal"""
    import sys
    
    # Verificar argumentos
    dry_run = True
    if len(sys.argv) > 1 and sys.argv[1] == "--execute":
        dry_run = False
        logger.warning("🚨 MODO EJECUCIÓN ACTIVADO - Los cambios serán permanentes")
        
        # Confirmación adicional
        response = input("¿Estás seguro de que quieres proceder? (escribe 'CONFIRMAR'): ")
        if response != "CONFIRMAR":
            logger.info("Operación cancelada por el usuario")
            return
    else:
        logger.info("🔍 MODO DRY RUN - Los cambios no serán aplicados")
        logger.info("Para aplicar cambios reales, ejecuta: python scripts/cleanup_duplicate_users.py --execute")
    
    await cleanup_email_duplicates(dry_run=dry_run)

if __name__ == "__main__":
    asyncio.run(main())