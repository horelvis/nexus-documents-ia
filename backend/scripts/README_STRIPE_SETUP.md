# Stripe Products Setup Guide

This guide explains how to set up Stripe products for NexusDocs360 with the new trial-based pricing structure.

## Overview

The pricing structure has been updated to:
- **Starter Plan**: 14-day free trial with Pro features (was "Free")
- **Pro Plan**: $29/month or $290/year
- **Enterprise Plan**: $99/month or $990/year

## Prerequisites

1. Stripe account (test or live mode)
2. Stripe Secret Key in your `.env` file:
   ```
   STRIPE_SECRET_KEY=sk_test_... # or sk_live_...
   ```

## Setup Instructions

### 1. Run the Product Creation Script

```bash
cd backend
python scripts/create_stripe_products.py
```

This script will:
- Create or update products in Stripe
- Set up pricing with proper trial configuration
- Display Product IDs for backend configuration

### 2. Update Backend Configuration

After running the script, update your backend configuration with the Product IDs shown in the output.

### 3. Features During Trial

During the 14-day trial period, users get:
- All Pro plan features
- Unlimited documents
- 100 GB storage
- AI and advanced analytics
- Digital signatures
- API access
- Up to 10 team members

After the trial expires:
- Users are downgraded to basic features
- They can upgrade to Pro or Enterprise to continue

### 4. Testing

To test the trial flow:
1. Sign up for a new account
2. Verify trial status in user dashboard
3. Check subscription status in Stripe dashboard
4. Test feature access during trial
5. Test post-trial limitations

## Important Notes

- The trial is completely free - no credit card required
- Users are automatically notified before trial expiration
- Trial can only be used once per account
- Enterprise plans should be handled through sales team

## Troubleshooting

If you encounter issues:
1. Verify your Stripe API key is correct
2. Check you're using the right mode (test/live)
3. Ensure products don't already exist with conflicting metadata
4. Review Stripe logs for detailed error messages

## Support

For questions about Stripe integration, contact the development team.