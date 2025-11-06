#!/usr/bin/env python3
"""
Get a valid Clerk authentication token for testing
This script helps obtain a session token from Clerk for API testing
"""
import os
import json
import requests
from typing import Optional
import subprocess

def get_clerk_env_vars():
    """Get Clerk environment variables from .env file"""
    env_vars = {}
    env_file = "/app/.env"  # Path inside container
    
    if os.path.exists(env_file):
        with open(env_file, 'r') as f:
            for line in f:
                if line.strip() and not line.startswith('#'):
                    if '=' in line:
                        key, value = line.strip().split('=', 1)
                        env_vars[key] = value.strip('"').strip("'")
    
    # Also check environment variables
    for key in ['CLERK_SECRET_KEY', 'NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY', 'CLERK_JWT_KEY']:
        if key in os.environ:
            env_vars[key] = os.environ[key]
    
    return env_vars

def get_session_from_frontend():
    """
    Get session token from frontend (if user is logged in)
    This requires the user to be logged in via the frontend
    """
    print("=" * 60)
    print("CLERK TOKEN RETRIEVAL OPTIONS")
    print("=" * 60)
    print("\nOption 1: Manual Token Extraction")
    print("-" * 40)
    print("1. Open your browser and go to: http://localhost:3000")
    print("2. Log in with your Clerk account")
    print("3. Open Developer Tools (F12)")
    print("4. Go to the Application/Storage tab")
    print("5. Find Cookies -> localhost:3000")
    print("6. Look for '__session' cookie")
    print("7. Copy the cookie value")
    print()
    
    token = input("Paste your __session cookie value here (or press Enter to skip): ").strip()
    
    if token:
        return token
    
    print("\nOption 2: Using Clerk CLI (if installed)")
    print("-" * 40)
    print("Run: clerk session list")
    print("Then use the session token from the active session")
    print()
    
    return None

def create_test_token_endpoint():
    """Create a temporary endpoint to get a test token"""
    endpoint_code = '''
@router.get("/test-token")
async def get_test_token():
    """Temporary endpoint to get a test token for development"""
    # This should only be enabled in development
    import os
    if os.getenv("ENVIRONMENT") != "development":
        raise HTTPException(status_code=403, detail="Only available in development")
    
    # Create a test token that bypasses Clerk in development
    test_user = {
        "id": "test_user_001",
        "email": "test@example.com",
        "tenant_id": "test_tenant_001"
    }
    
    return {"token": "test_token_12345", "user": test_user}
'''
    print("\nOption 3: Create Test Token Endpoint")
    print("-" * 40)
    print("You can temporarily add this endpoint to your API:")
    print(endpoint_code)
    print("\nAdd this to /backend/app/api/v1/auth.py temporarily")
    print()

def save_token_to_file(token: str):
    """Save token to a file for reuse"""
    token_file = "/tmp/clerk_token.txt"
    with open(token_file, 'w') as f:
        f.write(token)
    print(f"✅ Token saved to: {token_file}")
    print(f"   You can read it with: cat {token_file}")
    return token_file

def main():
    print("\n🔐 CLERK AUTHENTICATION TOKEN HELPER")
    print("=" * 60)
    
    # Check for existing token file
    token_file = "/tmp/clerk_token.txt"
    if os.path.exists(token_file):
        with open(token_file, 'r') as f:
            existing_token = f.read().strip()
        if existing_token:
            print(f"📄 Found existing token in {token_file}")
            use_existing = input("Use existing token? (y/n): ").lower()
            if use_existing == 'y':
                print(f"Token: {existing_token[:20]}...")
                return existing_token
    
    # Get Clerk configuration
    env_vars = get_clerk_env_vars()
    
    if 'CLERK_SECRET_KEY' in env_vars:
        print("✅ Clerk Secret Key found")
    else:
        print("⚠️  Clerk Secret Key not found in environment")
    
    # Try to get session token
    token = get_session_from_frontend()
    
    if token:
        save_token_to_file(token)
        print("\n✅ Token obtained successfully!")
        print("\nYou can now use this token in your tests by:")
        print("1. Setting the Authorization header: 'Bearer <token>'")
        print("2. Or setting the Cookie header: '__session=<token>'")
    else:
        print("\n❌ Could not obtain token automatically")
        create_test_token_endpoint()
        
        print("\nALTERNATIVE: Use the simple auth endpoint")
        print("-" * 40)
        print("The API has a simple auth endpoint at /api/v1/simple-auth/test-token")
        print("You can use it to get a test token for development")

if __name__ == "__main__":
    main()