#!/bin/bash
# Test PostgreSQL database connection for NexusDocs360 PRE environment
# Supports both Cloud SQL Proxy and direct connection methods

set -e

# Configuration
PROJECT_ID="nexusdocs360-pre"
INSTANCE_NAME="nexusdocuments360db"
REGION="europe-west1"
CONNECTION_NAME="nexusdocs360-pre:europe-west1:nexusdocuments360db"

echo "🔍 Testing PostgreSQL Database Connection"
echo "   Instance: $INSTANCE_NAME"
echo "   Connection: $CONNECTION_NAME"
echo ""

# Get credentials from secrets
echo "📊 Getting database credentials..."
DB_USER=$(gcloud secrets versions access latest --secret=db-user-pre --project=$PROJECT_ID 2>/dev/null || echo "")
DB_NAME=$(gcloud secrets versions access latest --secret=db-name-pre --project=$PROJECT_ID 2>/dev/null || echo "")
DB_PASS=$(gcloud secrets versions access latest --secret=db-pass-pre --project=$PROJECT_ID 2>/dev/null || echo "")
DB_HOST=$(gcloud secrets versions access latest --secret=db-host-pre --project=$PROJECT_ID 2>/dev/null || echo "")

if [ -z "$DB_USER" ] || [ -z "$DB_NAME" ] || [ -z "$DB_PASS" ]; then
    echo "❌ Failed to retrieve database credentials from secrets"
    echo "   Please check that the following secrets exist:"
    echo "   - db-user-pre"
    echo "   - db-name-pre"
    echo "   - db-pass-pre"
    exit 1
fi

echo "✅ Credentials retrieved successfully"
echo "   User: $DB_USER"
echo "   Database: $DB_NAME"
echo ""

# Method 1: Direct connection using public IP
echo "📡 Method 1: Direct Connection (Public IP)"
echo "============================================"

# Get public IP
PUBLIC_IP=$(gcloud sql instances describe $INSTANCE_NAME --project=$PROJECT_ID --format="value(ipAddresses[0].ipAddress)")
echo "   Public IP: $PUBLIC_IP"

# Check if psql is installed
if ! command -v psql &> /dev/null; then
    echo "❌ psql command not found. Please install PostgreSQL client:"
    echo "   macOS: brew install postgresql"
    echo "   Ubuntu: sudo apt-get install postgresql-client"
    echo ""
else
    echo "🔐 Testing direct connection..."
    # Create temporary pgpass file for authentication
    PGPASSFILE=$(mktemp)
    chmod 600 $PGPASSFILE
    echo "$PUBLIC_IP:5432:$DB_NAME:$DB_USER:$DB_PASS" > $PGPASSFILE
    
    # Test connection
    export PGPASSFILE
    if psql -h $PUBLIC_IP -U $DB_USER -d $DB_NAME -c "SELECT version();" 2>/dev/null; then
        echo "✅ Direct connection successful!"
    else
        echo "❌ Direct connection failed"
        echo "   Note: You may need to add your IP to the authorized networks"
        echo "   Run: gcloud sql instances patch $INSTANCE_NAME --authorized-networks=YOUR_IP --project=$PROJECT_ID"
    fi
    rm -f $PGPASSFILE
fi
echo ""

# Method 2: Cloud SQL Proxy
echo "🔌 Method 2: Cloud SQL Proxy"
echo "============================"

# Check if cloud_sql_proxy is installed
if ! command -v cloud_sql_proxy &> /dev/null && ! command -v cloud-sql-proxy &> /dev/null; then
    echo "❌ Cloud SQL Proxy not installed"
    echo ""
    echo "📦 To install Cloud SQL Proxy:"
    echo ""
    echo "macOS:"
    echo "  curl -o cloud-sql-proxy https://dl.google.com/cloudsql/cloud_sql_proxy.darwin.amd64"
    echo "  chmod +x cloud-sql-proxy"
    echo "  sudo mv cloud-sql-proxy /usr/local/bin/"
    echo ""
    echo "Linux:"
    echo "  curl -o cloud-sql-proxy https://dl.google.com/cloudsql/cloud_sql_proxy.linux.amd64"
    echo "  chmod +x cloud-sql-proxy"
    echo "  sudo mv cloud-sql-proxy /usr/local/bin/"
    echo ""
else
    echo "✅ Cloud SQL Proxy is installed"
    echo ""
    echo "To use Cloud SQL Proxy:"
    echo "1. Start the proxy in a separate terminal:"
    echo "   cloud-sql-proxy --port=5432 $CONNECTION_NAME"
    echo ""
    echo "2. Connect using localhost:"
    echo "   psql -h localhost -p 5432 -U $DB_USER -d $DB_NAME"
    echo ""
fi

# Method 3: Python connection test
echo "🐍 Method 3: Python Connection Test"
echo "==================================="

# Create Python test script
cat > /tmp/test_db_connection.py << EOF
import os
import sys

try:
    import psycopg2
    from psycopg2 import OperationalError
except ImportError:
    print("❌ psycopg2 not installed")
    print("   Install with: pip install psycopg2-binary")
    sys.exit(1)

# Connection parameters
DB_USER = "$DB_USER"
DB_PASS = "$DB_PASS"
DB_NAME = "$DB_NAME"
DB_HOST = "$PUBLIC_IP"
DB_PORT = "5432"

print("🔗 Testing PostgreSQL connection from Python...")

try:
    # Establish connection
    conn = psycopg2.connect(
        host=DB_HOST,
        port=DB_PORT,
        database=DB_NAME,
        user=DB_USER,
        password=DB_PASS,
        connect_timeout=10
    )
    
    # Create cursor
    cur = conn.cursor()
    
    # Test query
    cur.execute("SELECT version();")
    version = cur.fetchone()[0]
    print(f"✅ Connection successful!")
    print(f"   PostgreSQL version: {version}")
    
    # Get database size
    cur.execute("SELECT pg_database_size(current_database());")
    db_size = cur.fetchone()[0]
    print(f"   Database size: {db_size / 1024 / 1024:.2f} MB")
    
    # List tables
    cur.execute("""
        SELECT table_name 
        FROM information_schema.tables 
        WHERE table_schema = 'public' 
        ORDER BY table_name;
    """)
    tables = cur.fetchall()
    
    if tables:
        print(f"   Tables found: {len(tables)}")
        for table in tables[:5]:  # Show first 5 tables
            print(f"     - {table[0]}")
        if len(tables) > 5:
            print(f"     ... and {len(tables) - 5} more")
    else:
        print("   No tables found (empty database)")
    
    # Close connection
    cur.close()
    conn.close()
    
except OperationalError as e:
    print(f"❌ Connection failed: {e}")
    print("\n💡 Troubleshooting tips:")
    print("   1. Check if your IP is authorized:")
    print(f"      gcloud sql instances patch {os.environ.get('INSTANCE_NAME', '$INSTANCE_NAME')} \\")
    print("        --authorized-networks=YOUR_PUBLIC_IP \\")
    print(f"        --project={os.environ.get('PROJECT_ID', '$PROJECT_ID')}")
    print("   2. Verify credentials are correct")
    print("   3. Ensure the instance is running")
    sys.exit(1)

EOF

# Check if Python and psycopg2 are available
if command -v python3 &> /dev/null; then
    echo "Running Python connection test..."
    python3 /tmp/test_db_connection.py
else
    echo "❌ Python 3 not found. Skipping Python test."
fi
rm -f /tmp/test_db_connection.py

echo ""
echo "📋 Connection Summary"
echo "===================="
echo "Instance: $CONNECTION_NAME"
echo "Public IP: $PUBLIC_IP"
echo "Database: $DB_NAME"
echo "User: $DB_USER"
echo ""
echo "🔧 Connection Strings:"
echo "   Direct: postgresql://$DB_USER:****@$PUBLIC_IP:5432/$DB_NAME"
echo "   Proxy:  postgresql://$DB_USER:****@localhost:5432/$DB_NAME"
echo ""
echo "📚 Next Steps:"
echo "   1. If connection fails, authorize your IP:"
echo "      gcloud sql instances patch $INSTANCE_NAME --authorized-networks=<YOUR_IP> --project=$PROJECT_ID"
echo "   2. For production, use Cloud SQL Proxy or VPC connector"
echo "   3. Consider enabling SSL for secure connections"