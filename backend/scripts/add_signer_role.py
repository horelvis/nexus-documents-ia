#!/usr/bin/env python3
"""
Add role field to signature_request_signers table
"""
import asyncio
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text
import sys
sys.path.append('..')

from app.core.config import settings

async def add_role_field():
    """Add role field to signature_request_signers table"""
    engine = create_async_engine(settings.ASYNC_DATABASE_URL)
    
    async with engine.begin() as conn:
        # Check if column already exists
        result = await conn.execute(text("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name = 'signature_request_signers' 
            AND column_name = 'role'
        """))
        
        if result.rowcount > 0:
            print("✅ Column 'role' already exists in signature_request_signers table")
        else:
            # Add the column
            await conn.execute(text("""
                ALTER TABLE signature_request_signers 
                ADD COLUMN role VARCHAR(20) NOT NULL DEFAULT 'signer'
            """))
            print("✅ Added 'role' column to signature_request_signers table")
    
    await engine.dispose()

if __name__ == "__main__":
    asyncio.run(add_role_field())