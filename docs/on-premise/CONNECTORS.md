# Enterprise Connectors Guide

This guide covers configuring enterprise content connectors for NouxCubeIA on-premise deployments.

## Supported Connectors

| Connector | Status | Description | Adapter |
|-----------|--------|-------------|---------|
| Alfresco 7.x | Full support | Enterprise ECM with CMIS/REST API | `core/connectors/adapters/alfresco.py` |
| Google Drive | Full support | Google Workspace Drive via OAuth2 | `core/connectors/adapters/google_drive.py` |
| SharePoint / OneDrive | MCP-based | Via MCP server (`mcp-onedrive` container) | MCP protocol |
| BOE Legislation | Script-based | Spanish Official Gazette downloader (roadmap: convert to connector) | `backend/scripts/boe_legislation_downloader.py` |

---

## Connector Operations (CLI)

Connector sync is managed via `backend/docker/onboarding.sh`:

```bash
cd backend/docker

# List all connectors and their status:
./onboarding.sh status

# Trigger sync for ONE connector by ID:
./onboarding.sh sync <connector-id>

# Trigger sync for ALL active connectors (onboarding mode):
./onboarding.sh sync-all

# Download BOE legislation (preset-based):
./onboarding.sh boe <preset-name>
```

The HTTP API endpoints (`POST /api/v1/connectors/{id}/sync`, etc.) are also available for programmatic control — see the API section below.

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                     Connector Architecture                                   │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ┌──────────────────┐     ┌──────────────────┐     ┌──────────────────┐    │
│  │    External      │     │    Connector     │     │   NouxCubeIA   │    │
│  │    Sources       │◀───▶│    Service       │────▶│    Backend       │    │
│  │                  │     │                  │     │                  │    │
│  │  ┌────────────┐  │     │  ┌────────────┐  │     │  ┌────────────┐  │    │
│  │  │  Alfresco  │  │     │  │    MCP     │  │     │  │ IndexedDoc │  │    │
│  │  │  Database  │  │     │  │  Servers   │  │     │  │  Storage   │  │    │
│  │  │ SharePoint │  │     │  │            │  │     │  │            │  │    │
│  │  │ FileSystem │  │     │  │ - Alfresco │  │     │  │ - Weaviate │  │    │
│  │  └────────────┘  │     │  │ - Database │  │     │  │ - Postgres │  │    │
│  │                  │     │  │ - SharePt  │  │     │  │            │  │    │
│  └──────────────────┘     │  └────────────┘  │     │  └────────────┘  │    │
│                           │                  │     │                  │    │
│                           └──────────────────┘     └──────────────────┘    │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Alfresco 7.x Connector

### Overview

The Alfresco connector provides bi-directional sync between Alfresco Content Services and NouxCubeIA, enabling:
- Real-time document synchronization
- Metadata mapping
- Permission inheritance
- Version history preservation

### Prerequisites

- Alfresco Content Services 7.0+
- Alfresco Search Services (Solr)
- Network access from NouxCubeIA to Alfresco API

### Configuration

```bash
# backend/docker/.env

# Alfresco Connection
ALFRESCO_ENABLED=true
ALFRESCO_BASE_URL=https://alfresco.company.com
ALFRESCO_API_PATH=/alfresco/api/-default-/public/alfresco/versions/1

# Authentication (choose one)
ALFRESCO_AUTH_TYPE=basic  # or: oauth2, ticket

# Basic Auth
ALFRESCO_USERNAME=admin
ALFRESCO_PASSWORD=admin

# OAuth2 (for Alfresco Identity Service)
# ALFRESCO_OAUTH2_TOKEN_URL=https://alfresco.company.com/auth/realms/alfresco/protocol/openid-connect/token
# ALFRESCO_OAUTH2_CLIENT_ID=nexusdocs
# ALFRESCO_OAUTH2_CLIENT_SECRET=secret

# Sync Configuration
ALFRESCO_SYNC_INTERVAL_MINUTES=15
ALFRESCO_SYNC_BATCH_SIZE=100
ALFRESCO_SYNC_FOLDERS=/Company Home/Shared,/Company Home/Sites
```

### MCP Alfresco Server

The MCP (Model Context Protocol) Alfresco server allows Emma AI to directly interact with Alfresco:

```yaml
# docker-compose.yml

mcp-alfresco:
  image: nexusdocs/mcp-alfresco:latest
  environment:
    MCP_SERVER_PORT: 8090
    ALFRESCO_BASE_URL: ${ALFRESCO_BASE_URL}
    ALFRESCO_USERNAME: ${ALFRESCO_USERNAME}
    ALFRESCO_PASSWORD: ${ALFRESCO_PASSWORD}
  ports:
    - "8090:8090"
```

### Available MCP Tools

| Tool | Description |
|------|-------------|
| `alfresco_search` | Search documents in Alfresco |
| `alfresco_get_document` | Retrieve document content |
| `alfresco_get_metadata` | Get document metadata |
| `alfresco_list_folder` | List folder contents |
| `alfresco_get_versions` | Get document version history |
| `alfresco_upload` | Upload document to Alfresco |

### Metadata Mapping

```python
# backend/core/connectors/adapters/alfresco.py

# NOTE: ALFRESCO_TO_NEXUSDOCS is the current name in the adapter code.
# "NEXUSDOCS" is stale product naming — tech debt to rename to ALFRESCO_TO_NOUXCUBE.
ALFRESCO_TO_NEXUSDOCS = {
    "cm:title": "title",
    "cm:description": "description",
    "cm:author": "author",
    "cm:created": "created_at",
    "cm:modified": "updated_at",
    "cm:creator": "created_by",
    # Custom properties
    "acme:contractNumber": "contract_number",
    "acme:clientName": "client_name",
}
```

### Sync Modes

| Mode | Description | Use Case |
|------|-------------|----------|
| `full` | Full re-sync of all documents | Initial setup |
| `incremental` | Only sync changes since last run | Regular sync |
| `selective` | Sync specific folders only | Limited scope |

---

## Google Drive Connector

### Overview

The Google Drive connector indexes documents from Google Workspace Drive via OAuth2. The adapter is at `backend/core/connectors/adapters/google_drive.py`.

### Prerequisites

- Google Cloud project with the Drive API enabled
- OAuth2 client credentials (client ID + secret) — configured on the `mcp-google-drive` container

### Configuration

```bash
# Set on the mcp-google-drive container (docker-compose.onpremise.yml)

GOOGLE_OAUTH_CLIENT_ID=your-client-id.apps.googleusercontent.com
GOOGLE_OAUTH_CLIENT_SECRET=your-client-secret
GOOGLE_OAUTH_REDIRECT_URI=https://nexusdocs.company.com/oauth/google/callback
GOOGLE_OAUTH_SCOPES=https://www.googleapis.com/auth/drive.readonly

# Encryption key for storing OAuth tokens in the database:
CREDENTIALS_ENCRYPTION_KEY=<fernet-key>

# Set on the main backend:
GOOGLE_DRIVE_ENCRYPTION_KEY=<same-fernet-key>
```

> TODO: Full per-connector env var reference is in
> `backend/microservices/mcp-google-drive-server/app/core/config.py`. Check that file for the authoritative list.

### Auth Flow

Users authorize via OAuth2 (three-legged flow). The MCP server exchanges the authorization code for access/refresh tokens, encrypts them with the Fernet key, and stores them in PostgreSQL. Token refresh is handled automatically.

---

## Database Connector

### Overview

> **NOT IMPLEMENTED** — The Database (SQL) connector does not exist in the active codebase.
> The section below is retained as a design reference only.

The Database connector allows indexing documents stored in SQL databases, supporting:
- PostgreSQL, MySQL, SQL Server, Oracle
- Binary document columns (BLOB/BYTEA)
- File path references
- Custom metadata extraction

### Configuration

```bash
# backend/docker/.env

# Database Connector
DB_CONNECTOR_ENABLED=true

# Source Database Connection
DB_CONNECTOR_TYPE=postgresql  # or: mysql, sqlserver, oracle
DB_CONNECTOR_HOST=legacy-db.company.com
DB_CONNECTOR_PORT=5432
DB_CONNECTOR_DATABASE=documents
DB_CONNECTOR_USERNAME=reader
DB_CONNECTOR_PASSWORD=reader_password

# Sync Configuration
DB_CONNECTOR_SYNC_INTERVAL_MINUTES=30
DB_CONNECTOR_BATCH_SIZE=50
```

### Document Query Configuration

```yaml
# backend/connectors/database/queries.yaml

documents:
  query: |
    SELECT
      id,
      file_name,
      file_content,  -- BLOB/BYTEA column
      mime_type,
      created_at,
      updated_at,
      department,
      document_type
    FROM documents
    WHERE updated_at > :last_sync_time
    ORDER BY updated_at ASC
    LIMIT :batch_size

  id_column: id
  content_column: file_content
  filename_column: file_name
  mime_type_column: mime_type

  metadata_mapping:
    department: department
    document_type: doc_type
```

### File Path Mode

For databases storing file paths instead of content:

```yaml
documents:
  query: |
    SELECT id, file_path, metadata FROM documents

  content_mode: file_path  # Read content from filesystem
  file_path_column: file_path
  file_base_path: /mnt/documents  # Base path for relative paths
```

### MCP Database Server

```yaml
# docker-compose.yml

mcp-database:
  image: nexusdocs/mcp-database:latest
  environment:
    MCP_SERVER_PORT: 8091
    DB_TYPE: postgresql
    DB_HOST: ${DB_CONNECTOR_HOST}
    DB_PORT: ${DB_CONNECTOR_PORT}
    DB_NAME: ${DB_CONNECTOR_DATABASE}
    DB_USER: ${DB_CONNECTOR_USERNAME}
    DB_PASSWORD: ${DB_CONNECTOR_PASSWORD}
  ports:
    - "8091:8091"
```

---

## SharePoint Online Connector

### Overview

The SharePoint connector syncs documents from SharePoint Online sites and libraries.

### Prerequisites

- Azure AD App Registration with SharePoint permissions
- SharePoint Online license

### Azure AD App Configuration

Required API Permissions:
- `Sites.Read.All` (Application)
- `Files.Read.All` (Application)

### Configuration

```bash
# backend/docker/.env

# SharePoint Connector
SHAREPOINT_ENABLED=true

# Azure AD Authentication
SHAREPOINT_TENANT_ID=your-tenant-id
SHAREPOINT_CLIENT_ID=your-client-id
SHAREPOINT_CLIENT_SECRET=your-client-secret

# SharePoint Configuration
SHAREPOINT_SITE_URL=https://company.sharepoint.com/sites/Documents
SHAREPOINT_LIBRARIES=Shared Documents,Legal Documents

# Sync Configuration
SHAREPOINT_SYNC_INTERVAL_MINUTES=30
SHAREPOINT_INCLUDE_VERSIONS=true
```

### Filtering Documents

```bash
# Only sync specific file types
SHAREPOINT_FILE_EXTENSIONS=.pdf,.docx,.xlsx,.pptx

# Exclude folders
SHAREPOINT_EXCLUDE_FOLDERS=Archive,Temp,Draft

# Date filter (sync documents modified after)
SHAREPOINT_SYNC_AFTER_DATE=2024-01-01
```

---

## File System Connector

### Overview

The File System connector watches local directories for new or modified documents.

### Configuration

```bash
# backend/docker/.env

# File System Connector
FILESYSTEM_ENABLED=true
FILESYSTEM_WATCH_PATHS=/mnt/documents,/mnt/scanned
FILESYSTEM_SYNC_INTERVAL_MINUTES=5
FILESYSTEM_FILE_EXTENSIONS=.pdf,.docx,.xlsx,.jpg,.png

# Processing
FILESYSTEM_MOVE_PROCESSED=true
FILESYSTEM_PROCESSED_PATH=/mnt/documents/processed
```

### Docker Volume Mount

```yaml
# docker-compose.yml

services:
  backend:
    volumes:
      - /path/to/documents:/mnt/documents:ro
      - /path/to/scanned:/mnt/scanned:ro
```

---

## Connector ACL — `default_document_roles`

Every connector carries a `default_document_roles: ARRAY(String)` field (PostgreSQL). When the connector syncs a document, these roles are copied into the document's `roles` field, which drives the `filter_visible_to_user()` ACL query (see [ACL_SYSTEM.md](../architecture/ACL_SYSTEM.md)).

- **Default**: `["EVERYONE"]` — document visible to any authenticated user.
- **Typical values**: `["LEGAL"]`, `["HR", "FINANCE"]`, `["EVERYONE"]`, etc.
- Role IDs must match canonical roles from `backend/app/config/role_mapping.yaml`.

Example — create a connector that tags its docs as `LEGAL` by default:
```json
POST /api/v1/connectors
{
  "name": "Alfresco Legal",
  "connector_type": "alfresco",
  "config": { ... },
  "default_document_roles": ["LEGAL"]
}
```

---

## SharePoint / OneDrive (MCP-based)

Microsoft 365 services are integrated via [MCP (Model Context Protocol)](https://modelcontextprotocol.io/) servers rather than direct adapters in `core/connectors/adapters/`. Running containers:
- `docker-mcp-onedrive-1` — OneDrive MCP server
- `docker-mcp-alfresco-1` — Alfresco MCP (alternative to direct adapter)
- `docker-mcp-google-drive-1` — Google Drive MCP (alternative to direct adapter)

The Emma agent invokes these via the `query_connector` tool. Configuration lives per-container in their respective docker-compose entries in `docker-compose.onpremise.yml` (environment variables for OAuth tokens, base URLs, etc.).

> **Note**: For SharePoint/OneDrive, there is no direct adapter in `core/connectors/adapters/`. All Microsoft 365 connectivity goes through the MCP server. The `SHAREPOINT_*` env vars described in an older section of this document are placeholder patterns only — verify actual variables against the `mcp-onedrive` container config in `docker-compose.onpremise.yml`.

---

## Sync Management API

### Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/v1/connectors` | GET | List all connectors and status |
| `/api/v1/connectors/{id}/sync` | POST | Trigger manual sync |
| `/api/v1/connectors/{id}/status` | GET | Get sync status |
| `/api/v1/connectors/{id}/logs` | GET | Get sync logs |

### Example: Trigger Sync

```bash
curl -X POST https://nexusdocs.company.com/api/v1/connectors/alfresco/sync \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "mode": "incremental",
    "folders": ["/Company Home/Shared"]
  }'
```

### Example: Check Status

```bash
curl https://nexusdocs.company.com/api/v1/connectors/alfresco/status \
  -H "Authorization: Bearer $TOKEN"

# Response:
{
  "connector": "alfresco",
  "status": "syncing",
  "last_sync": "2026-01-24T10:00:00Z",
  "documents_synced": 1523,
  "documents_pending": 47,
  "errors": 0
}
```

---

## Error Handling

### Retry Configuration

```bash
# Retry settings
CONNECTOR_RETRY_ATTEMPTS=3
CONNECTOR_RETRY_DELAY_SECONDS=60
CONNECTOR_RETRY_BACKOFF_MULTIPLIER=2

# Error notifications
CONNECTOR_ERROR_WEBHOOK=https://hooks.slack.com/services/xxx
CONNECTOR_ERROR_EMAIL=admin@company.com
```

### Common Errors

| Error | Cause | Solution |
|-------|-------|----------|
| `Connection refused` | Network/firewall issue | Check connectivity |
| `401 Unauthorized` | Invalid credentials | Verify credentials |
| `403 Forbidden` | Insufficient permissions | Check API permissions |
| `Timeout` | Large files or slow network | Increase timeout |

---

## Performance Tuning

### Batch Size

```bash
# Adjust based on document size and network
CONNECTOR_BATCH_SIZE=100  # Small documents
CONNECTOR_BATCH_SIZE=25   # Large documents (>10MB avg)
```

### Parallel Processing

```bash
# Enable parallel sync workers
CONNECTOR_PARALLEL_WORKERS=4
CONNECTOR_QUEUE_SIZE=1000
```

### Memory Settings

```bash
# For large documents
CONNECTOR_MAX_DOCUMENT_SIZE_MB=100
CONNECTOR_MEMORY_BUFFER_MB=512
```

---

## Monitoring

### Prometheus Metrics

```
# Connector metrics (exposed at /metrics)
connector_sync_total{connector="alfresco",status="success"}
connector_sync_duration_seconds{connector="alfresco"}
connector_documents_processed{connector="alfresco"}
connector_errors_total{connector="alfresco",error_type="network"}
```

### Grafana Dashboard

Import the provided dashboard: `grafana/connectors-dashboard.json`

---

## Related Documentation

- [AUTHENTICATION.md](./AUTHENTICATION.md) - Authentication setup
- [MODULAR_ARCHITECTURE.md](../architecture/MODULAR_ARCHITECTURE.md) - On-Premise architecture
- [README-ONPREMISE.md](../../README-ONPREMISE.md) - Main on-premise guide
