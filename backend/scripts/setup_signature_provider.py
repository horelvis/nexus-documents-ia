#!/usr/bin/env python3
"""
Setup script for signature providers
"""
import os
import sys
import json
import asyncio
from uuid import uuid4
from datetime import datetime

# Add parent directory to path
sys.path.append('..')

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from cryptography.fernet import Fernet

from app.db.async_database import AsyncSessionLocal
from app.db.models import SignatureProvider, Tenant
from app.core.config import settings


async def setup_yousign_provider():
    """Setup YouSign provider with proper credentials"""
    async with AsyncSessionLocal() as db:
        try:
            # Get encryption key
            encryption_key = getattr(settings, 'SIGNATURE_ENCRYPTION_KEY', None)
            if not encryption_key:
                print("❌ SIGNATURE_ENCRYPTION_KEY not set in .env")
                print("\nGenerate one with:")
                print("python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())'")
                print("\nThen add to .env:")
                print("SIGNATURE_ENCRYPTION_KEY=<generated-key>")
                return
            
            # Get YouSign API key
            yousign_api_key = os.getenv('YOUSIGN_API_KEY')
            if not yousign_api_key:
                print("❌ YOUSIGN_API_KEY not set in .env")
                print("\nAdd to .env:")
                print("YOUSIGN_API_KEY=your-yousign-api-key")
                return
            
            # Get first tenant
            result = await db.execute(select(Tenant).limit(1))
            tenant = result.scalar_one_or_none()
            
            if not tenant:
                print("❌ No tenant found. Please create a tenant first.")
                return
            
            print(f"✅ Using tenant: {tenant.name}")
            
            # Check if YouSign provider already exists
            result = await db.execute(
                select(SignatureProvider).where(
                    SignatureProvider.tenant_id == tenant.id,
                    SignatureProvider.provider_name == 'yousign'
                )
            )
            existing_provider = result.scalar_one_or_none()
            
            if existing_provider:
                print("⚠️  YouSign provider already exists. Updating...")
                provider = existing_provider
            else:
                print("📝 Creating new YouSign provider...")
                provider = SignatureProvider(
                    id=uuid4(),
                    tenant_id=tenant.id,
                    provider_name='yousign',
                    display_name='YouSign',
                    created_at=datetime.utcnow(),
                    updated_at=datetime.utcnow()
                )
                db.add(provider)
            
            # Prepare credentials
            credentials = {
                "api_key": yousign_api_key
            }
            
            # Encrypt credentials
            fernet = Fernet(encryption_key.encode() if isinstance(encryption_key, str) else encryption_key)
            encrypted_credentials = fernet.encrypt(json.dumps(credentials).encode())
            
            # Update provider
            provider.encrypted_credentials = encrypted_credentials
            provider.configuration = {
                "environment": os.getenv('YOUSIGN_ENVIRONMENT', 'sandbox'),
                "webhook_secret": os.getenv('YOUSIGN_WEBHOOK_SECRET', ''),
                "default_signature_level": "electronic_signature",
                "default_authentication": "no_otp"
            }
            provider.is_active = True
            provider.updated_at = datetime.utcnow()
            
            await db.commit()
            
            print(f"✅ YouSign provider configured successfully!")
            print(f"   ID: {provider.id}")
            print(f"   Environment: {provider.configuration['environment']}")
            print(f"   Active: {provider.is_active}")
            
            # Test decryption
            print("\n🔍 Testing credential decryption...")
            decrypted = fernet.decrypt(provider.encrypted_credentials)
            test_creds = json.loads(decrypted.decode())
            print(f"✅ Credentials decrypted successfully")
            print(f"   API Key: {test_creds['api_key'][:10]}...")
            
        except Exception as e:
            print(f"❌ Error: {e}")
            await db.rollback()
            raise


async def list_providers():
    """List all signature providers"""
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(SignatureProvider).order_by(SignatureProvider.created_at.desc())
        )
        providers = result.scalars().all()
        
        if not providers:
            print("No signature providers found.")
            return
        
        print("\n📋 Signature Providers:")
        print("-" * 80)
        
        for provider in providers:
            print(f"\nProvider: {provider.display_name}")
            print(f"  ID: {provider.id}")
            print(f"  Type: {provider.provider_name}")
            print(f"  Active: {provider.is_active}")
            print(f"  Has Credentials: {'Yes' if provider.encrypted_credentials else 'No'}")
            if provider.configuration:
                print(f"  Environment: {provider.configuration.get('environment', 'N/A')}")
            print(f"  Created: {provider.created_at}")


async def test_provider(provider_id: str = None):
    """Test a signature provider"""
    async with AsyncSessionLocal() as db:
        if provider_id:
            result = await db.execute(
                select(SignatureProvider).where(SignatureProvider.id == provider_id)
            )
        else:
            # Get first active provider
            result = await db.execute(
                select(SignatureProvider).where(SignatureProvider.is_active == True).limit(1)
            )
        
        provider = result.scalar_one_or_none()
        
        if not provider:
            print("❌ No provider found")
            return
        
        print(f"\n🧪 Testing provider: {provider.display_name}")
        
        # Test credential decryption
        try:
            encryption_key = getattr(settings, 'SIGNATURE_ENCRYPTION_KEY', None)
            if not encryption_key:
                print("❌ SIGNATURE_ENCRYPTION_KEY not set")
                return
            
            fernet = Fernet(encryption_key.encode() if isinstance(encryption_key, str) else encryption_key)
            decrypted = fernet.decrypt(provider.encrypted_credentials)
            credentials = json.loads(decrypted.decode())
            
            print("✅ Credentials decrypted successfully")
            
            # Test API connection (if YouSign)
            if provider.provider_name == 'yousign':
                import httpx
                
                api_key = credentials.get('api_key')
                environment = provider.configuration.get('environment', 'sandbox')
                base_url = "https://api-sandbox.yousign.app/v3" if environment == 'sandbox' else "https://api.yousign.app/v3"
                
                print(f"\n🌐 Testing API connection to {base_url}...")
                
                headers = {
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json"
                }
                
                with httpx.Client() as client:
                    # Test endpoint - get user info
                    response = client.get(f"{base_url}/users", headers=headers)
                    
                    if response.status_code == 200:
                        print("✅ API connection successful!")
                        data = response.json()
                        print(f"   Total users: {data.get('meta', {}).get('total', 0)}")
                    else:
                        print(f"❌ API connection failed: {response.status_code}")
                        print(f"   Response: {response.text}")
            
        except Exception as e:
            print(f"❌ Test failed: {e}")


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Setup signature providers")
    parser.add_argument('--list', action='store_true', help='List all providers')
    parser.add_argument('--test', help='Test a provider (ID or leave empty for first active)')
    parser.add_argument('--setup-yousign', action='store_true', help='Setup YouSign provider')
    
    args = parser.parse_args()
    
    if args.list:
        asyncio.run(list_providers())
    elif args.test is not None:
        asyncio.run(test_provider(args.test if args.test else None))
    elif args.setup_yousign:
        asyncio.run(setup_yousign_provider())
    else:
        # Default action
        asyncio.run(setup_yousign_provider())