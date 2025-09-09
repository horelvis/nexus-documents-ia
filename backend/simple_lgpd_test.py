#!/usr/bin/env python3
"""
Simple LGPD Test - Basic functionality verification
"""
import asyncio
import asyncpg
import json
from datetime import datetime
from uuid import uuid4

async def test_lgpd_table_exists():
    """Test that LGPD deletion audit table exists and is accessible"""
    try:
        conn = await asyncpg.connect("postgresql://postgres:password@db:5432/nexus_db")
        
        # Test 1: Check if table exists
        result = await conn.fetchval("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables 
                WHERE table_name = 'lgpd_deletion_audits'
            )
        """)
        
        if not result:
            print("❌ FAILED: LGPD deletion audit table does not exist")
            return False
            
        print("✅ LGPD deletion audit table exists")
        
        # Test 2: Check table structure
        columns = await conn.fetch("""
            SELECT column_name, data_type, is_nullable
            FROM information_schema.columns 
            WHERE table_name = 'lgpd_deletion_audits'
            ORDER BY ordinal_position
        """)
        
        expected_columns = {
            'id', 'user_id', 'user_email', 'requested_by', 'tenant_id', 
            'reason', 'status', 'started_at', 'completed_at', 'deletion_summary',
            'total_records_deleted', 'anonymized_records', 'lgpd_article', 
            'deletion_method', 'created_at'
        }
        
        actual_columns = {col['column_name'] for col in columns}
        
        if not expected_columns.issubset(actual_columns):
            missing = expected_columns - actual_columns
            print(f"❌ FAILED: Missing columns: {missing}")
            return False
            
        print(f"✅ Table structure correct ({len(columns)} columns)")
        
        # Test 3: Test indexes exist
        indexes = await conn.fetch("""
            SELECT indexname FROM pg_indexes 
            WHERE tablename = 'lgpd_deletion_audits'
        """)
        
        index_names = {idx['indexname'] for idx in indexes}
        expected_indexes = {
            'idx_lgpd_deletions_tenant_status',
            'idx_lgpd_deletions_user_date', 
            'idx_lgpd_deletions_user_id'
        }
        
        if not expected_indexes.issubset(index_names):
            missing = expected_indexes - index_names
            print(f"❌ FAILED: Missing indexes: {missing}")
            return False
            
        print(f"✅ All indexes present ({len(index_names)} total)")
        
        # Test 4: Test basic CRUD operations
        test_id = uuid4()
        test_user_id = uuid4()
        test_tenant_id = uuid4()
        test_requested_by = uuid4()
        
        # Insert test record
        await conn.execute("""
            INSERT INTO lgpd_deletion_audits 
            (id, user_id, user_email, requested_by, tenant_id, reason, status, started_at, lgpd_article, deletion_method)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
        """, test_id, test_user_id, "test@example.com", test_requested_by, test_tenant_id, 
             "Test deletion", "pending", datetime.now(), "Article 18", "complete_data_destruction")
        
        # Read test record
        record = await conn.fetchrow("""
            SELECT * FROM lgpd_deletion_audits WHERE id = $1
        """, test_id)
        
        if not record:
            print("❌ FAILED: Could not insert/read test record")
            return False
            
        print("✅ Basic CRUD operations work")
        
        # Update test record
        await conn.execute("""
            UPDATE lgpd_deletion_audits 
            SET status = $1, completed_at = $2, total_records_deleted = $3
            WHERE id = $4
        """, "completed", datetime.now(), 5, test_id)
        
        # Verify update
        updated_record = await conn.fetchrow("""
            SELECT status, total_records_deleted FROM lgpd_deletion_audits WHERE id = $1
        """, test_id)
        
        if updated_record['status'] != 'completed' or updated_record['total_records_deleted'] != 5:
            print("❌ FAILED: Update operation failed")
            return False
            
        print("✅ Update operations work")
        
        # Clean up test record
        await conn.execute("DELETE FROM lgpd_deletion_audits WHERE id = $1", test_id)
        
        # Verify cleanup
        cleanup_check = await conn.fetchrow("SELECT * FROM lgpd_deletion_audits WHERE id = $1", test_id)
        if cleanup_check:
            print("❌ FAILED: Cleanup failed")
            return False
            
        print("✅ Delete operations work")
        
        await conn.close()
        return True
        
    except Exception as e:
        print(f"❌ FAILED: Database error: {e}")
        return False

async def main():
    print("🧪 Simple LGPD Compliance Test")
    print("=" * 40)
    
    success = await test_lgpd_table_exists()
    
    if success:
        print("\n🎉 LGPD Database Infrastructure Test PASSED!")
        print("\nVerified:")
        print("- ✅ LGPD deletion audit table exists")  
        print("- ✅ Table has correct structure")
        print("- ✅ Required indexes are present")
        print("- ✅ Basic CRUD operations work")
        print("- ✅ Data integrity maintained")
        print("\n📋 Next Steps:")
        print("- Start API containers to test full deletion service")
        print("- Run frontend to test user deletion dialog")
        print("- Verify external service integrations")
    else:
        print("\n❌ LGPD Database Infrastructure Test FAILED!")
        print("- Database setup needs attention")
        return 1
    
    return 0

if __name__ == "__main__":
    exit_code = asyncio.run(main())
    exit(exit_code)