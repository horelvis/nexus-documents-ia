#!/usr/bin/env python3
"""
Quick database connection test for NexusDocs360
Tests connection to Cloud SQL PostgreSQL instance
"""

import os
import sys
import subprocess
from urllib.parse import urlparse

def get_secret(secret_name, project_id="nexusdocs360-pre"):
    """Get secret value from Google Secret Manager"""
    try:
        result = subprocess.run(
            ["gcloud", "secrets", "versions", "access", "latest", 
             f"--secret={secret_name}", f"--project={project_id}"],
            capture_output=True, text=True, check=True
        )
        return result.stdout.strip()
    except subprocess.CalledProcessError:
        return None

def test_connection():
    """Test database connection"""
    # Try to import psycopg2
    try:
        import psycopg2
        from psycopg2 import OperationalError
    except ImportError:
        print("❌ psycopg2 not installed")
        print("   Install with: pip install psycopg2-binary")
        return False
    
    # Get connection details
    print("📊 Getting database credentials...")
    
    # First try environment variables
    db_url = os.getenv('DATABASE_URL')
    if db_url:
        print("✅ Using DATABASE_URL from environment")
        parsed = urlparse(db_url)
        db_config = {
            'host': parsed.hostname,
            'port': parsed.port or 5432,
            'database': parsed.path[1:],  # Remove leading /
            'user': parsed.username,
            'password': parsed.password
        }
    else:
        # Get from secrets
        db_user = get_secret('db-user-pre') or 'nexus_user_pre'
        db_pass = get_secret('db-pass-pre')
        db_name = get_secret('db-name-pre') or 'nexusdocs360_pre'
        db_host = get_secret('db-host-pre') or 'localhost'
        
        if not db_pass:
            print("❌ Could not retrieve database password from secrets")
            return False
        
        db_config = {
            'host': db_host,
            'port': 5432,
            'database': db_name,
            'user': db_user,
            'password': db_pass
        }
    
    print(f"   Host: {db_config['host']}")
    print(f"   Port: {db_config['port']}")
    print(f"   Database: {db_config['database']}")
    print(f"   User: {db_config['user']}")
    
    # Test connection
    print("\n🔗 Testing connection...")
    try:
        conn = psycopg2.connect(**db_config, connect_timeout=10)
        cur = conn.cursor()
        
        # Get version
        cur.execute("SELECT version();")
        version = cur.fetchone()[0]
        print(f"✅ Connection successful!")
        print(f"   {version}")
        
        # Check if database is empty
        cur.execute("""
            SELECT COUNT(*) 
            FROM information_schema.tables 
            WHERE table_schema = 'public';
        """)
        table_count = cur.fetchone()[0]
        
        if table_count == 0:
            print("\n📝 Database is empty. Need to run migrations.")
            print("   Run: cd backend && alembic upgrade head")
        else:
            print(f"\n📊 Database has {table_count} tables")
            
            # List some tables
            cur.execute("""
                SELECT table_name 
                FROM information_schema.tables 
                WHERE table_schema = 'public' 
                ORDER BY table_name 
                LIMIT 10;
            """)
            tables = cur.fetchall()
            print("   Tables:")
            for table in tables:
                print(f"     - {table[0]}")
        
        cur.close()
        conn.close()
        return True
        
    except OperationalError as e:
        print(f"❌ Connection failed: {e}")
        print("\n💡 Troubleshooting:")
        if "could not connect to server" in str(e):
            print("   1. If using direct connection, check if your IP is authorized")
            print("   2. If using proxy, make sure it's running:")
            print("      ./setup-cloudsql-proxy.sh")
        elif "password authentication failed" in str(e):
            print("   1. Check database credentials in Google Secret Manager")
            print("   2. Verify user exists in Cloud SQL instance")
        return False

if __name__ == "__main__":
    print("🔍 NexusDocs360 Database Connection Test")
    print("=" * 40)
    
    success = test_connection()
    
    if success:
        print("\n✅ All tests passed!")
    else:
        print("\n❌ Connection test failed")
        sys.exit(1)