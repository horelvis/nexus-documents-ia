#!/usr/bin/env python3
"""
Script to add test users to the database for entity search testing
"""
import asyncio
import sys
from uuid import uuid4
from datetime import datetime

# Add parent directory to path
sys.path.append('..')

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.db.async_database import async_engine, AsyncSessionLocal
from app.db.models import User, Tenant
from app.core.security import get_password_hash


async def add_test_users():
    """Add test users to the database"""
    async with AsyncSessionLocal() as db:
        try:
            # Get the first tenant
            result = await db.execute(select(Tenant).limit(1))
            tenant = result.scalar_one_or_none()
            
            if not tenant:
                print("❌ No tenant found in database. Please create a tenant first.")
                return
            
            print(f"✅ Using tenant: {tenant.name} (ID: {tenant.id})")
            
            # Test users to add
            test_users = [
                {
                    "email": "john.doe@example.com",
                    "full_name": "John Doe",
                    "role": "user"
                },
                {
                    "email": "jane.smith@example.com", 
                    "full_name": "Jane Smith",
                    "role": "user"
                },
                {
                    "email": "jose.garcia@example.com",
                    "full_name": "José García",
                    "role": "user"
                },
                {
                    "email": "maria.sanchez@example.com",
                    "full_name": "María Sánchez",
                    "role": "user"
                },
                {
                    "email": "jonathan.williams@example.com",
                    "full_name": "Jonathan Williams",
                    "role": "admin"
                }
            ]
            
            for user_data in test_users:
                # Check if user already exists
                result = await db.execute(
                    select(User).where(User.email == user_data["email"])
                )
                existing_user = result.scalar_one_or_none()
                
                if existing_user:
                    print(f"⚠️  User {user_data['email']} already exists")
                    continue
                
                # Create new user
                new_user = User(
                    id=uuid4(),
                    email=user_data["email"],
                    full_name=user_data["full_name"],
                    hashed_password=get_password_hash("testpassword123"),
                    tenant_id=tenant.id,
                    role=user_data["role"],
                    is_active=True,
                    is_verified=True,
                    created_at=datetime.utcnow(),
                    updated_at=datetime.utcnow()
                )
                
                db.add(new_user)
                print(f"✅ Added user: {user_data['full_name']} ({user_data['email']})")
            
            await db.commit()
            print("\n✅ Test users added successfully!")
            
            # Show all users in tenant
            print(f"\n📋 All users in tenant '{tenant.name}':")
            result = await db.execute(
                select(User).where(User.tenant_id == tenant.id)
            )
            users = result.scalars().all()
            
            for user in users:
                print(f"   - {user.full_name or 'No name'} ({user.email})")
                
        except Exception as e:
            print(f"❌ Error: {e}")
            await db.rollback()
            raise


if __name__ == "__main__":
    print("🔧 Adding test users to database...")
    asyncio.run(add_test_users())