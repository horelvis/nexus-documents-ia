#!/usr/bin/env python3
"""
Simple script to fix subscription table - just make plan_id nullable
"""
import os
import sys
import logging
from sqlalchemy import create_engine, text

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def fix_subscription_table():
    """Fix subscription table by making plan_id nullable"""
    try:
        # Import settings
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from app.core.config import settings
        
        # Create engine
        engine = create_engine(settings.SQLALCHEMY_DATABASE_URI)
        
        with engine.begin() as conn:
            logger.info("Making plan_id nullable if it exists...")
            
            # Simple fix - just make plan_id nullable
            # This will allow inserts to succeed
            conn.execute(text("""
                ALTER TABLE subscriptions 
                ALTER COLUMN plan_id DROP NOT NULL
            """))
            
            logger.info("✅ Fixed! plan_id is now nullable")
            
            # Optional: Set default value for stripe_plan_id
            logger.info("Setting default for stripe_plan_id...")
            conn.execute(text("""
                UPDATE subscriptions 
                SET stripe_plan_id = COALESCE(stripe_plan_id, plan_id, 'pro')
                WHERE stripe_plan_id IS NULL
            """))
            
            logger.info("✅ All done!")
                
    except Exception as e:
        logger.error(f"Error: {e}")
        # If plan_id doesn't exist, that's fine
        if "column \"plan_id\" of relation \"subscriptions\" does not exist" in str(e):
            logger.info("✅ No fix needed - plan_id column doesn't exist")
        else:
            raise

if __name__ == "__main__":
    fix_subscription_table()