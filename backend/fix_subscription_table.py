#!/usr/bin/env python3
"""
Script to fix subscription table schema issues
"""
import os
import sys
import logging
from sqlalchemy import create_engine, text, inspect

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def fix_subscription_table():
    """Fix subscription table schema"""
    try:
        # Import settings
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from app.core.config import settings
        
        # Create engine
        engine = create_engine(settings.DATABASE_URL)
        
        with engine.begin() as conn:
            # Check existing columns
            inspector = inspect(engine)
            if 'subscriptions' in inspector.get_table_names():
                columns = [col['name'] for col in inspector.get_columns('subscriptions')]
                logger.info(f"Current columns in subscriptions table: {columns}")
                
                # Step 1: Make plan_id nullable if it exists
                if 'plan_id' in columns:
                    logger.info("Making plan_id nullable...")
                    conn.execute(text("ALTER TABLE subscriptions ALTER COLUMN plan_id DROP NOT NULL"))
                    
                # Step 2: Update any NULL stripe_plan_id values from plan_id
                if 'plan_id' in columns and 'stripe_plan_id' in columns:
                    logger.info("Copying plan_id values to stripe_plan_id where NULL...")
                    conn.execute(text("""
                        UPDATE subscriptions 
                        SET stripe_plan_id = plan_id 
                        WHERE stripe_plan_id IS NULL AND plan_id IS NOT NULL
                    """))
                
                # Step 3: Drop the old plan_id column
                if 'plan_id' in columns:
                    logger.info("Dropping plan_id column...")
                    # First drop any foreign key constraints
                    constraints = inspector.get_foreign_keys('subscriptions')
                    for constraint in constraints:
                        if 'plan_id' in constraint['constrained_columns']:
                            logger.info(f"Dropping constraint: {constraint['name']}")
                            conn.execute(text(f"ALTER TABLE subscriptions DROP CONSTRAINT {constraint['name']}"))
                    
                    # Then drop the column
                    conn.execute(text("ALTER TABLE subscriptions DROP COLUMN IF EXISTS plan_id"))
                
                # Verify the changes
                inspector = inspect(engine)
                columns_after = [col['name'] for col in inspector.get_columns('subscriptions')]
                logger.info(f"Columns after fix: {columns_after}")
                
                logger.info("✅ Subscription table fixed successfully!")
            else:
                logger.warning("Subscriptions table not found!")
                
    except Exception as e:
        logger.error(f"Error fixing subscription table: {e}")
        raise

if __name__ == "__main__":
    fix_subscription_table()