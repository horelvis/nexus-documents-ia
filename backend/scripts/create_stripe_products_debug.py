#!/usr/bin/env python3
"""Debug version of create_stripe_products.py"""

import os
import sys
import stripe
from dotenv import load_dotenv

# Load environment variables
env_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), '.env')
if os.path.exists(env_path):
    load_dotenv(env_path, override=True)
    print(f"✓ Loaded .env from: {env_path}")

# Configure Stripe
stripe_key_from_env = os.getenv("STRIPE_SECRET_KEY")
print(f"Key from os.getenv: {stripe_key_from_env[:30] if stripe_key_from_env else 'NOT FOUND'}...")
print(f"Key length: {len(stripe_key_from_env) if stripe_key_from_env else 0}")

stripe.api_key = stripe_key_from_env
print(f"stripe.api_key after assignment: {stripe.api_key[:30] if stripe.api_key else 'NOT SET'}...")

# Test connection
try:
    account = stripe.Account.retrieve()
    print(f"\n✅ Connection successful! Account: {account.id}")
except Exception as e:
    print(f"\n❌ Connection error: {e}")
    print(f"Error type: {type(e)}")
    
# Now run the actual product creation from the original script
print("\n" + "="*50)
print("Now importing and running the original script functions...")
print("="*50 + "\n")

# Import after setting stripe.api_key
from create_stripe_products import PRODUCTS, PRICES, create_or_update_product, create_or_update_price

# Create products
for product_id, product_data in PRODUCTS.items():
    print(f"\nCreating product: {product_id}")
    product = create_or_update_product(product_id, product_data)
    if product:
        print(f"  Product created/updated: {product.id}")
        
        # Create prices
        if product_id in PRICES:
            for price_type, price_data in PRICES[product_id].items():
                print(f"  Creating price: {price_type}")
                price = create_or_update_price(product, price_type, price_data)
                if price:
                    print(f"    Price ID: {price.id}")