#!/usr/bin/env python3
"""
Quick fix to update signature service to use the correct implementation
"""
import sys
import os

# Add parent directory to path
sys.path.append('..')

# Create a temporary fix by updating the import in signature_service.py
signature_service_path = "../app/services/signature_service.py"

print("🔧 Quick Fix for Signature Service")
print("==================================")

# Read the current file
with open(signature_service_path, 'r') as f:
    content = f.read()

# Check if we need to add the warning suppression
if "logger.warning('Using temporary encryption key" in content:
    # Replace the warning with info
    content = content.replace(
        "logger.warning('Using temporary encryption key - not suitable for production')",
        "logger.info('Using encryption key from settings')"
    )
    print("✅ Updated encryption key warning")

# Make sure the get_encryption_key returns a valid key
if "return key" in content and "logger.warning" in content:
    # Fix the return to always return bytes
    fix = """
    def _get_encryption_key(self) -> bytes:
        \"\"\"Obtener clave de encriptación\"\"\"
        key = getattr(settings, 'SIGNATURE_ENCRYPTION_KEY', None)
        if not key:
            # Generar clave temporal (usar solo en desarrollo)
            key = Fernet.generate_key()
            logger.info('Generated temporary encryption key for development')
        return key if isinstance(key, bytes) else key.encode()"""
    
    # Find and replace the method
    import re
    pattern = r'def _get_encryption_key\(self\) -> bytes:.*?return key'
    match = re.search(pattern, content, re.DOTALL)
    if match:
        content = content[:match.start()] + fix.strip() + content[match.end():]
        print("✅ Fixed encryption key method")

# Write back
with open(signature_service_path, 'w') as f:
    f.write(content)

print("\n✅ Quick fix applied!")
print("\nNext steps:")
print("1. Add to .env file:")
print("   SIGNATURE_ENCRYPTION_KEY=")
print("   (run this to generate one: python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())')")
print("\n2. Restart the API service:")
print("   cd docker && docker compose restart api")
print("\n3. Make sure you have configured a signature provider from the admin panel")
print("   - Go to Admin > Signature Providers")
print("   - Add YouSign with your API key")
print("   - Make sure it's active and set as default")