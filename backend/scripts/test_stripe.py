#!/usr/bin/env python3
"""Test Stripe connection"""

import os
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
import stripe

# Load environment variables
env_path = Path(__file__).parent.parent / '.env'
print(f"Loading .env from: {env_path}")
load_dotenv(env_path, override=True)

# Get the key
stripe_key = os.getenv("STRIPE_SECRET_KEY")
print(f"Key from env: {stripe_key[:20] if stripe_key else 'NOT FOUND'}...")
print(f"Key length: {len(stripe_key) if stripe_key else 0}")

# Set the key
stripe.api_key = stripe_key

# Test connection
try:
    account = stripe.Account.retrieve()
    print(f"\n✅ Success! Connected to Stripe account: {account.id}")
    
    # List existing products
    products = stripe.Product.list(limit=10)
    print(f"\nExisting products: {len(products.data)}")
    for product in products.data:
        print(f"  - {product.name} (ID: {product.id})")
        
except Exception as e:
    print(f"\n❌ Error: {e}")