#!/usr/bin/env python3
"""
Create Stripe Products and Prices for NouxCubeIA
This script creates the products in Stripe with proper trial configuration
"""

import os
import sys
import stripe
from dotenv import load_dotenv

# Load environment variables
# Try to load from parent directory first (backend/.env)
env_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), '.env')
if os.path.exists(env_path):
    load_dotenv(env_path)
    print(f"✓ Loaded .env from: {env_path}")
else:
    load_dotenv()
    print("⚠️  Loading .env from default location")

# Configure Stripe
stripe.api_key = os.getenv("STRIPE_SECRET_KEY")

if not stripe.api_key:
    print("❌ Error: STRIPE_SECRET_KEY not found in environment variables")
    print(f"   Searched in: {env_path if os.path.exists(env_path) else 'default .env location'}")
    sys.exit(1)

# Debug info  
actual_key = stripe.api_key
if actual_key and len(actual_key) > 30:
    print(f"✓ Stripe API key loaded (length: {len(actual_key)}, ends with: ...{actual_key[-4:]})")
else:
    print(f"✓ Stripe API key loaded (starts with: {actual_key[:20] if actual_key else 'NOT SET'}...)")

# Product definitions
PRODUCTS = {
    "basic": {
        "name": "NouxCubeIA Basic",
        "description": "Plan esencial para uso personal",
        "metadata": {
            "plan_id": "basic",
            "max_users": "1",
            "max_documents": "500",
            "storage_gb": "10",
            "features": "basic_ai,document_analysis"
        }
    },
    "pro": {
        "name": "NouxCubeIA Pro",
        "description": "Plan profesional para equipos en crecimiento",
        "metadata": {
            "plan_id": "pro",
            "max_users": "10",
            "max_documents": "unlimited",
            "storage_gb": "100",
            "features": "advanced_ai,digital_signatures,api_access,integrations",
            "trial_days": "14"  # Pro plan offers 14-day trial
        }
    }
    # Note: Enterprise plan removed - handled by sales team
    # Note: Starter/Free plan removed - trial is now part of Pro plan
}

# Price definitions
PRICES = {
    "basic": {
        "monthly": {
            "unit_amount": 2900,  # $29.00
            "currency": "usd",
            "recurring": {
                "interval": "month"
            },
            "metadata": {
                "billing_period": "monthly",
                "plan_id": "basic"
            }
        }
    },
    "pro": {
        "monthly": {
            "unit_amount": 6000,  # $60.00
            "currency": "usd",
            "recurring": {
                "interval": "month",
                "trial_period_days": 14  # 14-day trial for Pro plan
            },
            "metadata": {
                "billing_period": "monthly",
                "plan_id": "pro",
                "has_trial": "true"
            }
        },
        "yearly": {
            "unit_amount": 60000,  # $600.00 ($50.00/month)
            "currency": "usd",
            "recurring": {
                "interval": "year",
                "trial_period_days": 14  # 14-day trial for yearly too
            },
            "metadata": {
                "billing_period": "yearly",
                "plan_id": "pro",
                "monthly_equivalent": "50.00",
                "has_trial": "true",
                "discount_percentage": "17"  # ~17% discount
            }
        }
    }
    # Note: Enterprise plan removed - handled by sales team
    # Note: Starter/Free plan removed - trial is now part of Pro plan
}


def create_or_update_product(product_id, product_data):
    """Create or update a Stripe product"""
    try:
        # Try to retrieve existing product
        existing_products = stripe.Product.list(limit=100)
        existing_product = None
        
        for product in existing_products.data:
            if product.metadata.get("plan_id") == product_data["metadata"]["plan_id"]:
                existing_product = product
                break
        
        if existing_product:
            # Update existing product
            product = stripe.Product.modify(
                existing_product.id,
                name=product_data["name"],
                description=product_data["description"],
                metadata=product_data["metadata"]
            )
            print(f"✅ Updated product: {product.name} (ID: {product.id})")
        else:
            # Create new product
            product = stripe.Product.create(
                name=product_data["name"],
                description=product_data["description"],
                metadata=product_data["metadata"]
            )
            print(f"✅ Created product: {product.name} (ID: {product.id})")
        
        return product
    
    except stripe.error.StripeError as e:
        print(f"❌ Error creating/updating product {product_id}: {str(e)}")
        return None


def create_or_update_price(product, price_type, price_data):
    """Create or update a Stripe price"""
    try:
        # Check if price already exists
        existing_prices = stripe.Price.list(
            product=product.id,
            limit=100
        )
        
        existing_price = None
        for price in existing_prices.data:
            if price.metadata.get("billing_period") == price_data["metadata"]["billing_period"]:
                existing_price = price
                break
        
        if existing_price and existing_price.active:
            print(f"  ℹ️  Price already exists: {price_type} - ${existing_price.unit_amount/100:.2f}")
            return existing_price
        
        # Create new price
        price = stripe.Price.create(
            product=product.id,
            **price_data
        )
        
        # Archive old price if it exists
        if existing_price:
            stripe.Price.modify(
                existing_price.id,
                active=False
            )
        
        trial_info = ""
        if price.recurring and hasattr(price.recurring, 'trial_period_days') and price.recurring.trial_period_days:
            trial_info = f" (includes {price.recurring.trial_period_days}-day trial)"
        
        print(f"  ✅ Created price: {price_type} - ${price.unit_amount/100:.2f}{trial_info}")
        print(f"     Price ID: {price.id}")
        return price
    
    except stripe.error.StripeError as e:
        print(f"  ❌ Error creating price {price_type}: {str(e)}")
        return None


def main():
    """Main function to create all products and prices"""
    print("🚀 Creating Stripe products and prices for NouxCubeIA...")
    print(f"   Using Stripe API in {'TEST' if 'test' in stripe.api_key else 'LIVE'} mode")
    print("")
    
    created_products = {}
    created_prices = {}  # Store created prices for final output
    
    # Create products
    for product_id, product_data in PRODUCTS.items():
        product = create_or_update_product(product_id, product_data)
        if product:
            created_products[product_id] = product
    
    print("")
    
    # Create prices
    for product_id, price_configs in PRICES.items():
        if product_id in created_products:
            product = created_products[product_id]
            print(f"Creating prices for {product.name}...")
            created_prices[product_id] = {}
            
            for price_type, price_data in price_configs.items():
                price = create_or_update_price(product, price_type, price_data)
                if price:
                    created_prices[product_id][price_type] = price
            
            print("")
    
    # Print summary
    print("\n📋 Summary:")
    print("=" * 50)
    
    for product_id, product in created_products.items():
        print(f"\n{product.name}:")
        print(f"  Product ID: {product.id}")
        print(f"  Metadata: {product.metadata}")
        
        # List active prices
        prices = stripe.Price.list(product=product.id, active=True, limit=10)
        for price in prices.data:
            interval = price.recurring.interval if price.recurring else "one-time"
            amount = f"${price.unit_amount/100:.2f}"
            trial = f" (with {price.recurring.trial_period_days}-day trial)" if price.recurring and price.recurring.trial_period_days else ""
            print(f"  - {interval}: {amount}{trial}")
    
    print("\n✅ All products and prices created successfully!")
    print("\n⚠️  Important: Update your .env file with these Price IDs:")
    print("\n# Stripe Price IDs")
    
    # Show actual price IDs
    if "basic" in created_prices and "monthly" in created_prices["basic"]:
        print(f"STRIPE_BASIC_PRICE_ID={created_prices['basic']['monthly'].id}")
    
    if "pro" in created_prices:
        if "monthly" in created_prices["pro"]:
            print(f"STRIPE_PRO_PRICE_ID={created_prices['pro']['monthly'].id}")
        if "yearly" in created_prices["pro"]:
            print(f"STRIPE_PRO_YEARLY_PRICE_ID={created_prices['pro']['yearly'].id}")
    
    print("\n# Note: The Pro plan includes a 14-day trial automatically")
    print("# No separate trial product needed - trial is configured in the Pro prices")


if __name__ == "__main__":
    main()