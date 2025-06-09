#!/usr/bin/env python3
"""
Script para limpiar datos de desarrollo de la base de datos.
USO: python scripts/clean_dev_data.py [options]

PELIGRO: Este script puede eliminar datos. Úsalo solo en desarrollo.
"""

import argparse
import sys
from typing import Optional

from sqlalchemy.orm import Session
from app.db.database import get_db
from app.db.models import User, UserProfile, Subscription, UserImage, Document, Tenant


def clean_user_by_email(db: Session, email: str) -> bool:
    """Elimina un usuario específico por email"""
    user = db.query(User).filter(User.email == email).first()
    
    if not user:
        print(f"❌ Usuario con email {email} no encontrado")
        return False
    
    print(f"🚨 Eliminando usuario: {user.email} (ID: {user.id})")
    
    try:
        # Eliminar datos relacionados explícitamente
        db.query(UserProfile).filter(UserProfile.user_id == user.id).delete()
        db.query(Subscription).filter(Subscription.user_id == user.id).delete()
        db.query(UserImage).filter(UserImage.user_id == user.id).delete()
        
        # Eliminar documentos del usuario
        db.query(Document).filter(Document.created_by == user.id).delete()
        
        # Eliminar el usuario
        db.delete(user)
        db.commit()
        
        print(f"✅ Usuario {email} eliminado exitosamente")
        return True
        
    except Exception as e:
        print(f"❌ Error eliminando usuario: {str(e)}")
        db.rollback()
        return False


def reset_user_onboarding(db: Session, email: str) -> bool:
    """Resetea el onboarding de un usuario específico"""
    user = db.query(User).filter(User.email == email).first()
    
    if not user:
        print(f"❌ Usuario con email {email} no encontrado")
        return False
    
    print(f"🔄 Reseteando onboarding para: {user.email}")
    
    try:
        # Resetear onboarding
        user.onboarding_completed = False
        
        # Eliminar perfil existente
        existing_profile = db.query(UserProfile).filter(UserProfile.user_id == user.id).first()
        if existing_profile:
            db.delete(existing_profile)
            print(f"🗑️ Perfil eliminado")
        
        db.commit()
        
        print(f"✅ Onboarding reseteado para {email}")
        return True
        
    except Exception as e:
        print(f"❌ Error reseteando onboarding: {str(e)}")
        db.rollback()
        return False


def list_users(db: Session, tenant_name: Optional[str] = None):
    """Lista usuarios en la base de datos"""
    query = db.query(User)
    
    if tenant_name:
        query = query.join(Tenant).filter(Tenant.name == tenant_name)
    
    users = query.all()
    
    print(f"\n📋 Usuarios encontrados: {len(users)}")
    print("-" * 80)
    
    for user in users:
        profile = db.query(UserProfile).filter(UserProfile.user_id == user.id).first()
        subscription = db.query(Subscription).filter(Subscription.user_id == user.id).first()
        
        print(f"Email: {user.email}")
        print(f"  ID: {user.id}")
        print(f"  Nombre: {user.full_name or 'N/A'}")
        print(f"  Onboarding: {'✅' if user.onboarding_completed else '❌'}")
        print(f"  Clerk ID: {user.clerk_user_id or 'N/A'}")
        print(f"  Perfil: {'✅' if profile else '❌'}")
        if profile:
            print(f"    Plan: {profile.selected_plan or 'N/A'}")
            print(f"    Empresa: {profile.company_name or 'N/A'}")
        print(f"  Suscripción: {'✅' if subscription else '❌'}")
        if subscription:
            print(f"    Estado: {subscription.status}")
            print(f"    Plan: {subscription.stripe_plan_id}")
        print("-" * 40)


def clean_all_dev_data(db: Session, confirm: bool = False):
    """Elimina todos los datos de desarrollo (excepto superusuarios)"""
    if not confirm:
        print("⚠️  Para confirmar, usa --confirm")
        return
    
    print("🚨 ELIMINANDO TODOS LOS DATOS DE DESARROLLO...")
    
    try:
        # Eliminar usuarios no superusuarios
        users = db.query(User).filter(User.is_superuser == False).all()
        
        print(f"Encontrados {len(users)} usuarios no-admin para eliminar")
        
        for user in users:
            print(f"Eliminando: {user.email}")
            
            # Eliminar datos relacionados
            db.query(UserProfile).filter(UserProfile.user_id == user.id).delete()
            db.query(Subscription).filter(Subscription.user_id == user.id).delete()
            db.query(UserImage).filter(UserImage.user_id == user.id).delete()
            db.query(Document).filter(Document.created_by == user.id).delete()
            
            # Eliminar usuario
            db.delete(user)
        
        db.commit()
        print("✅ Datos de desarrollo eliminados")
        
    except Exception as e:
        print(f"❌ Error: {str(e)}")
        db.rollback()


def main():
    parser = argparse.ArgumentParser(description='Herramientas de limpieza para desarrollo')
    parser.add_argument('--list', action='store_true', help='Listar usuarios')
    parser.add_argument('--delete-user', type=str, help='Eliminar usuario por email')
    parser.add_argument('--reset-onboarding', type=str, help='Resetear onboarding de usuario por email')
    parser.add_argument('--clean-all', action='store_true', help='Eliminar todos los datos de desarrollo')
    parser.add_argument('--confirm', action='store_true', help='Confirmar acciones destructivas')
    parser.add_argument('--tenant', type=str, help='Filtrar por tenant')
    
    args = parser.parse_args()
    
    # Obtener sesión de base de datos
    db_gen = get_db()
    db = next(db_gen)
    
    try:
        if args.list:
            list_users(db, args.tenant)
        elif args.delete_user:
            clean_user_by_email(db, args.delete_user)
        elif args.reset_onboarding:
            reset_user_onboarding(db, args.reset_onboarding)
        elif args.clean_all:
            clean_all_dev_data(db, args.confirm)
        else:
            parser.print_help()
            
    finally:
        db.close()


if __name__ == "__main__":
    main()