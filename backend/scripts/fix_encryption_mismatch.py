#!/usr/bin/env python3
"""
Fix encryption key mismatch for signature providers
"""
import os
import sys
import json
import asyncio
from uuid import UUID
from datetime import datetime

# Add parent directory to path
sys.path.append('..')

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from cryptography.fernet import Fernet, InvalidToken

from app.db.async_database import AsyncSessionLocal
from app.db.models import SignatureProvider
from app.core.config import settings


async def check_and_fix_providers():
    """Check all providers and fix encryption issues"""
    async with AsyncSessionLocal() as db:
        # Get current encryption key
        current_key = getattr(settings, 'SIGNATURE_ENCRYPTION_KEY', None)
        
        if not current_key:
            print("❌ No SIGNATURE_ENCRYPTION_KEY found in environment")
            print("\n1. Generate a key:")
            print("   python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())'")
            print("\n2. Add to .env:")
            print("   SIGNATURE_ENCRYPTION_KEY=<generated-key>")
            print("\n3. Restart services and re-run this script")
            return
        
        print(f"✅ Using encryption key: {current_key[:10]}...")
        
        # Create Fernet instance
        try:
            fernet = Fernet(current_key.encode() if isinstance(current_key, str) else current_key)
        except Exception as e:
            print(f"❌ Invalid encryption key format: {e}")
            return
        
        # Get all providers
        result = await db.execute(select(SignatureProvider))
        providers = result.scalars().all()
        
        if not providers:
            print("No signature providers found")
            return
        
        print(f"\nFound {len(providers)} providers")
        print("-" * 50)
        
        for provider in providers:
            print(f"\n📦 Provider: {provider.display_name} ({provider.provider_name})")
            print(f"   ID: {provider.id}")
            print(f"   Active: {provider.is_active}")
            
            if not provider.encrypted_credentials:
                print("   ⚠️  No credentials stored")
                continue
            
            # Try to decrypt
            try:
                decrypted = fernet.decrypt(provider.encrypted_credentials)
                credentials = json.loads(decrypted.decode())
                print("   ✅ Credentials are valid")
                print(f"   Keys: {list(credentials.keys())}")
                
            except InvalidToken:
                print("   ❌ ENCRYPTION MISMATCH - Cannot decrypt with current key")
                print("   This provider needs to be reconfigured")
                
                # Option to clear invalid credentials
                if input("\n   Clear invalid credentials? (y/n): ").lower() == 'y':
                    provider.encrypted_credentials = None
                    provider.is_active = False
                    await db.commit()
                    print("   ✅ Cleared invalid credentials and deactivated provider")
                    print("   ⚠️  Please reconfigure this provider from the admin panel")
                
            except Exception as e:
                print(f"   ❌ Error: {e}")
        
        print("\n" + "=" * 50)
        print("Summary:")
        print("- Providers with encryption mismatches need to be reconfigured")
        print("- Go to Admin → Signature Providers in the frontend")
        print("- Edit each affected provider and re-enter the API credentials")


async def reset_all_providers():
    """Reset all providers (use with caution)"""
    if input("⚠️  This will clear ALL provider credentials. Continue? (yes/no): ") != "yes":
        print("Cancelled")
        return
    
    async with AsyncSessionLocal() as db:
        # Clear all credentials
        await db.execute(
            update(SignatureProvider).values(
                encrypted_credentials=None,
                is_active=False
            )
        )
        await db.commit()
        
        print("✅ All provider credentials cleared")
        print("⚠️  You need to reconfigure all providers from the admin panel")


async def show_encryption_info():
    """Show current encryption configuration"""
    print("🔐 Encryption Configuration")
    print("=" * 50)
    
    # Check environment
    key = getattr(settings, 'SIGNATURE_ENCRYPTION_KEY', None)
    if key:
        print(f"✅ SIGNATURE_ENCRYPTION_KEY is set: {key[:10]}...")
        
        # Test key validity
        try:
            fernet = Fernet(key.encode() if isinstance(key, str) else key)
            test_data = b"test"
            encrypted = fernet.encrypt(test_data)
            decrypted = fernet.decrypt(encrypted)
            print("✅ Encryption key is valid and working")
        except Exception as e:
            print(f"❌ Encryption key is invalid: {e}")
    else:
        print("❌ SIGNATURE_ENCRYPTION_KEY is NOT set")
        print("\nTo generate a new key:")
        print("python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())'")


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Fix encryption issues with signature providers")
    parser.add_argument('--reset-all', action='store_true', help='Reset all provider credentials')
    parser.add_argument('--info', action='store_true', help='Show encryption configuration')
    
    args = parser.parse_args()
    
    if args.reset_all:
        asyncio.run(reset_all_providers())
    elif args.info:
        asyncio.run(show_encryption_info())
    else:
        asyncio.run(check_and_fix_providers())