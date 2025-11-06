#!/usr/bin/env python3
"""
Script para verificar usuarios duplicados por email en la base de datos.
"""
import asyncio
import logging
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.async_database import AsyncSessionLocal
from app.db.models import User

# Configurar logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def check_duplicate_users():
    """Verificar usuarios duplicados por email"""
    logger.info("🔍 Iniciando verificación de usuarios duplicados...")
    
    async with AsyncSessionLocal() as db:
        try:
            # Buscar emails duplicados
            result = await db.execute(
                select(
                    User.email, 
                    func.count(User.id).label('count')
                )
                .group_by(User.email)
                .having(func.count(User.id) > 1)
            )
            
            duplicates = result.all()
            
            if not duplicates:
                logger.info("✅ No se encontraron emails duplicados")
                return []
            
            logger.warning(f"⚠️ Se encontraron {len(duplicates)} emails duplicados:")
            
            duplicate_details = []
            for duplicate in duplicates:
                email = duplicate.email
                count = duplicate.count
                
                # Obtener detalles de todos los usuarios con este email
                users_result = await db.execute(
                    select(User).filter(User.email == email)
                )
                users = users_result.scalars().all()
                
                logger.warning(f"  📧 Email: {email} ({count} usuarios)")
                
                user_details = []
                for user in users:
                    user_info = {
                        'id': str(user.id),
                        'email': user.email,
                        'full_name': user.full_name,
                        'clerk_user_id': user.clerk_user_id,
                        'stripe_customer_id': user.stripe_customer_id,
                        'tenant_id': str(user.tenant_id),
                        'is_active': user.is_active,
                        'created_at': user.created_at,
                        'onboarding_completed': user.onboarding_completed
                    }
                    user_details.append(user_info)
                    
                    logger.warning(f"    👤 ID: {user.id}")
                    logger.warning(f"       Nombre: {user.full_name}")
                    logger.warning(f"       Clerk ID: {user.clerk_user_id}")
                    logger.warning(f"       Stripe ID: {user.stripe_customer_id}")
                    logger.warning(f"       Tenant: {user.tenant_id}")
                    logger.warning(f"       Activo: {user.is_active}")
                    logger.warning(f"       Creado: {user.created_at}")
                    logger.warning(f"       Onboarding: {user.onboarding_completed}")
                    logger.warning("    " + "-" * 40)
                
                duplicate_details.append({
                    'email': email,
                    'count': count,
                    'users': user_details
                })
            
            return duplicate_details
            
        except Exception as e:
            logger.error(f"❌ Error al verificar duplicados: {str(e)}")
            return []

async def check_clerk_user_id_duplicates():
    """Verificar clerk_user_id duplicados"""
    logger.info("🔍 Verificando clerk_user_id duplicados...")
    
    async with AsyncSessionLocal() as db:
        try:
            # Buscar clerk_user_id duplicados (excluyendo NULL)
            result = await db.execute(
                select(
                    User.clerk_user_id, 
                    func.count(User.id).label('count')
                )
                .filter(User.clerk_user_id.isnot(None))
                .group_by(User.clerk_user_id)
                .having(func.count(User.id) > 1)
            )
            
            duplicates = result.all()
            
            if not duplicates:
                logger.info("✅ No se encontraron clerk_user_id duplicados")
                return []
            
            logger.warning(f"⚠️ Se encontraron {len(duplicates)} clerk_user_id duplicados:")
            
            for duplicate in duplicates:
                clerk_id = duplicate.clerk_user_id
                count = duplicate.count
                
                logger.warning(f"  🆔 Clerk ID: {clerk_id} ({count} usuarios)")
                
                # Obtener detalles
                users_result = await db.execute(
                    select(User).filter(User.clerk_user_id == clerk_id)
                )
                users = users_result.scalars().all()
                
                for user in users:
                    logger.warning(f"    👤 Usuario: {user.email} (ID: {user.id})")
            
            return duplicates
            
        except Exception as e:
            logger.error(f"❌ Error al verificar clerk_user_id duplicados: {str(e)}")
            return []

async def get_user_statistics():
    """Obtener estadísticas generales de usuarios"""
    logger.info("📊 Obteniendo estadísticas de usuarios...")
    
    async with AsyncSessionLocal() as db:
        try:
            # Total de usuarios
            total_result = await db.execute(select(func.count(User.id)))
            total_users = total_result.scalar()
            
            # Usuarios activos
            active_result = await db.execute(
                select(func.count(User.id)).filter(User.is_active == True)
            )
            active_users = active_result.scalar()
            
            # Usuarios con Clerk ID
            clerk_result = await db.execute(
                select(func.count(User.id)).filter(User.clerk_user_id.isnot(None))
            )
            users_with_clerk = clerk_result.scalar()
            
            # Usuarios sin Clerk ID
            no_clerk_result = await db.execute(
                select(func.count(User.id)).filter(User.clerk_user_id.is_(None))
            )
            users_without_clerk = no_clerk_result.scalar()
            
            # Usuarios con Stripe ID
            stripe_result = await db.execute(
                select(func.count(User.id)).filter(User.stripe_customer_id.isnot(None))
            )
            users_with_stripe = stripe_result.scalar()
            
            logger.info(f"📈 Estadísticas de usuarios:")
            logger.info(f"   Total de usuarios: {total_users}")
            logger.info(f"   Usuarios activos: {active_users}")
            logger.info(f"   Con Clerk ID: {users_with_clerk}")
            logger.info(f"   Sin Clerk ID: {users_without_clerk}")
            logger.info(f"   Con Stripe ID: {users_with_stripe}")
            
            return {
                'total_users': total_users,
                'active_users': active_users,
                'users_with_clerk': users_with_clerk,
                'users_without_clerk': users_without_clerk,
                'users_with_stripe': users_with_stripe
            }
            
        except Exception as e:
            logger.error(f"❌ Error al obtener estadísticas: {str(e)}")
            return {}

async def main():
    """Función principal"""
    logger.info("🚀 Iniciando verificación de integridad de usuarios...")
    
    # Obtener estadísticas
    stats = await get_user_statistics()
    
    # Verificar duplicados por email
    email_duplicates = await check_duplicate_users()
    
    # Verificar duplicados por clerk_user_id
    clerk_duplicates = await check_clerk_user_id_duplicates()
    
    logger.info("🏁 Verificación completada")
    
    if email_duplicates or clerk_duplicates:
        logger.warning("⚠️ Se encontraron problemas de integridad!")
        logger.warning("💡 Considera ejecutar un script de limpieza para resolver duplicados")
    else:
        logger.info("✅ No se encontraron problemas de integridad")
    
    return {
        'statistics': stats,
        'email_duplicates': email_duplicates,
        'clerk_duplicates': clerk_duplicates
    }

if __name__ == "__main__":
    result = asyncio.run(main())
    
    # Imprimir resumen
    print("\n" + "="*60)
    print("RESUMEN DE VERIFICACIÓN")
    print("="*60)
    
    if result['email_duplicates']:
        print(f"⚠️  Emails duplicados: {len(result['email_duplicates'])}")
    else:
        print("✅ Sin emails duplicados")
    
    if result['clerk_duplicates']:
        print(f"⚠️  Clerk IDs duplicados: {len(result['clerk_duplicates'])}")
    else:
        print("✅ Sin Clerk IDs duplicados")
    
    if result['statistics']:
        print(f"📊 Total usuarios: {result['statistics'].get('total_users', 'N/A')}")
        print(f"👥 Usuarios activos: {result['statistics'].get('active_users', 'N/A')}")
    
    print("="*60)