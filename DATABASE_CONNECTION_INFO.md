# Database Connection Information - NexusDocs360 PRE

## Cloud SQL Instance Details
- **Instance Name**: nexusdocuments360db
- **Connection Name**: nexusdocs360-pre:europe-west1:nexusdocuments360db
- **Public IP**: 146.148.14.195
- **Region**: europe-west1
- **PostgreSQL Version**: 17

## Database Credentials
- **Database Name**: nexusdocs360_pre
- **Username**: nexus_user_pre
- **Password**: (stored in Secret Manager: db-pass-pre)

## Connection Methods

### 1. Direct Connection (Development Only)
```bash
# Connection string
postgresql://nexus_user_pre:<password>@146.148.14.195:5432/nexusdocs360_pre

# Using psql
psql -h 146.148.14.195 -U nexus_user_pre -d nexusdocs360_pre
```

### 2. Cloud SQL Proxy (Recommended)
```bash
# Install Cloud SQL Proxy
curl -o cloud-sql-proxy https://dl.google.com/cloudsql/cloud_sql_proxy.darwin.amd64
chmod +x cloud-sql-proxy
sudo mv cloud-sql-proxy /usr/local/bin/

# Run proxy
cloud-sql-proxy --port=5432 nexusdocs360-pre:europe-west1:nexusdocuments360db

# Connect via localhost
psql -h localhost -p 5432 -U nexus_user_pre -d nexusdocs360_pre
```

### 3. From Cloud Run (Using VPC)
Services deployed to Cloud Run use the VPC connector and connect using the private IP.

## Python Connection Example
```python
import psycopg2

# Get password from Secret Manager
password = get_secret('db-pass-pre')

# Connect
conn = psycopg2.connect(
    host="146.148.14.195",  # or "localhost" if using proxy
    port=5432,
    database="nexusdocs360_pre",
    user="nexus_user_pre",
    password=password
)
```

## Environment Variables
```bash
# For local development with proxy
export DATABASE_URL="postgresql://nexus_user_pre:<password>@localhost:5432/nexusdocs360_pre"
export ASYNC_DATABASE_URL="postgresql+asyncpg://nexus_user_pre:<password>@localhost:5432/nexusdocs360_pre"

# For direct connection
export DATABASE_URL="postgresql://nexus_user_pre:<password>@146.148.14.195:5432/nexusdocs360_pre"
```

## Security Notes
1. **Your IP is authorized**: 88.22.165.139
2. **For production**: Always use Cloud SQL Proxy or VPC connector
3. **SSL**: Consider enabling SSL for encrypted connections
4. **Secrets**: Password is stored in Google Secret Manager

## Quick Test
```bash
# Test connection
./test_db_quick.py

# Or use the comprehensive test
./test-database-connection.sh
```

## Next Steps
1. Run database migrations safely: `cd backend && python scripts/alembic_safe_migrate.py`
2. Set up Cloud SQL Proxy for local development
3. Configure backend .env file with correct credentials