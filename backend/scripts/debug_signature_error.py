#!/usr/bin/env python3
"""
Debug script for signature request sending error
"""
import os
import sys
import json
from uuid import UUID

# Add parent directory to path
sys.path.append('..')

from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from app.db.models import SignatureRequest, SignatureProvider
from app.core.config import settings


def check_signature_configuration():
    """Check signature service configuration"""
    print("🔍 Checking Signature Configuration...")
    print("=" * 50)
    
    # Check encryption key
    encryption_key = getattr(settings, 'SIGNATURE_ENCRYPTION_KEY', None)
    if encryption_key:
        print("✅ SIGNATURE_ENCRYPTION_KEY is set")
    else:
        print("❌ SIGNATURE_ENCRYPTION_KEY is NOT set - using temporary key")
        print("   Add to .env: SIGNATURE_ENCRYPTION_KEY=your-base64-encoded-fernet-key")
        print("   Generate one with: python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())'")
    
    # Check provider configurations
    print("\n📋 Checking provider API keys:")
    providers = ['DOCUSIGN', 'YOUSIGN', 'SIGNATURIT']
    
    for provider in providers:
        api_key = os.getenv(f'{provider}_API_KEY')
        if api_key:
            print(f"✅ {provider}_API_KEY is set")
        else:
            print(f"⚠️  {provider}_API_KEY is NOT set")
    
    return encryption_key is not None


def check_signature_request(request_id: str):
    """Check a specific signature request"""
    print(f"\n🔍 Checking Signature Request: {request_id}")
    print("=" * 50)
    
    # Create database connection
    engine = create_engine(settings.DATABASE_URL)
    
    with Session(engine) as db:
        # Get the request
        request = db.query(SignatureRequest).filter(
            SignatureRequest.id == UUID(request_id)
        ).first()
        
        if not request:
            print("❌ Signature request not found")
            return
        
        print(f"✅ Found request: {request.title}")
        print(f"   Status: {request.status}")
        print(f"   Provider ID: {request.provider_id}")
        print(f"   Created: {request.created_at}")
        
        # Check provider
        provider = db.query(SignatureProvider).filter(
            SignatureProvider.id == request.provider_id
        ).first()
        
        if not provider:
            print("❌ Provider not found!")
            return
        
        print(f"\n📦 Provider: {provider.provider_name}")
        print(f"   Active: {provider.is_active}")
        print(f"   Has credentials: {'Yes' if provider.encrypted_credentials else 'No'}")
        
        if provider.encrypted_credentials:
            try:
                # Try to decrypt credentials
                from cryptography.fernet import Fernet
                
                # Get encryption key
                key = getattr(settings, 'SIGNATURE_ENCRYPTION_KEY', None)
                if not key:
                    key = Fernet.generate_key()
                    print("   ⚠️  Using temporary encryption key")
                
                fernet = Fernet(key if isinstance(key, bytes) else key.encode())
                decrypted = fernet.decrypt(provider.encrypted_credentials)
                credentials = json.loads(decrypted.decode())
                
                print("   ✅ Credentials decrypted successfully")
                print(f"   Credential keys: {list(credentials.keys())}")
                
                # Check if required keys exist
                if provider.provider_name == 'docusign':
                    required = ['account_id', 'integration_key', 'user_id', 'private_key']
                elif provider.provider_name == 'yousign':
                    required = ['api_key']
                elif provider.provider_name == 'signaturit':
                    required = ['api_key']
                else:
                    required = []
                
                for key in required:
                    if key in credentials:
                        print(f"   ✅ {key} present")
                    else:
                        print(f"   ❌ {key} MISSING")
                        
            except Exception as e:
                print(f"   ❌ Failed to decrypt credentials: {e}")
        
        # Check signers
        print(f"\n👥 Signers: {len(request.signers)}")
        for signer in request.signers:
            print(f"   - {signer.name} ({signer.email})")


def generate_encryption_key():
    """Generate a new encryption key"""
    from cryptography.fernet import Fernet
    key = Fernet.generate_key()
    print("\n🔑 New Encryption Key Generated:")
    print(f"SIGNATURE_ENCRYPTION_KEY={key.decode()}")
    print("\nAdd this to your .env file")


def create_test_provider():
    """Create a test signature provider"""
    print("\n🏗️ Creating Test Provider...")
    
    from cryptography.fernet import Fernet
    
    # Get or generate encryption key
    key = getattr(settings, 'SIGNATURE_ENCRYPTION_KEY', None)
    if not key:
        key = Fernet.generate_key()
        print("⚠️  Using temporary key - set SIGNATURE_ENCRYPTION_KEY in .env")
    
    fernet = Fernet(key if isinstance(key, bytes) else key.encode())
    
    # Test credentials
    test_credentials = {
        "api_key": "test-api-key-12345",
        "environment": "sandbox"
    }
    
    encrypted = fernet.encrypt(json.dumps(test_credentials).encode())
    
    print(f"Provider: yousign (test)")
    print(f"Encrypted credentials: {encrypted[:50]}...")
    print("\nSQL to insert test provider:")
    print(f"""
INSERT INTO signature_providers (
    id, tenant_id, provider_name, display_name, 
    encrypted_credentials, configuration, is_active
) VALUES (
    gen_random_uuid(),
    (SELECT id FROM tenants LIMIT 1),
    'yousign',
    'YouSign Test',
    '\\x{encrypted.hex()}',
    '{{"environment": "sandbox"}}',
    true
);
""")


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Debug signature service issues")
    parser.add_argument('--request-id', help='Check specific signature request')
    parser.add_argument('--generate-key', action='store_true', help='Generate encryption key')
    parser.add_argument('--create-provider', action='store_true', help='Create test provider')
    
    args = parser.parse_args()
    
    if args.generate_key:
        generate_encryption_key()
    elif args.create_provider:
        create_test_provider()
    elif args.request_id:
        check_signature_configuration()
        check_signature_request(args.request_id)
    else:
        check_signature_configuration()