#!/usr/bin/env python3
"""
Direct Elasticsearch Reindexing Script using Apache Tika.

This script bypasses the complex service layer and directly:
1. Gets documents from PostgreSQL
2. Downloads files from GCS
3. Extracts text using Tika
4. Indexes directly in Elasticsearch

Usage:
    docker exec docker-api-1 python /app/scripts/reindex_elasticsearch_tika.py --tenant-id <tenant_id>
"""
import argparse
import sys
import os
import logging
from datetime import datetime

import httpx
from sqlalchemy import create_engine, text
from elasticsearch import Elasticsearch, exceptions as es_exceptions

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Configuration from environment
DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql://nexus_user:nexus_password@db:5432/nexus_db")
ELASTICSEARCH_URL = os.environ.get("ELASTICSEARCH_URL", "http://elasticsearch:9200")
TIKA_URL = os.environ.get("TIKA_URL", "http://tika:9998")
STORAGE_SERVICE_URL = os.environ.get("STORAGE_SERVICE_URL", "http://storage-service:8000")
MICROSERVICES_API_KEY = os.environ.get("MICROSERVICES_API_KEY", "dev_microservice_key_12345")


def get_documents(engine, tenant_id: str) -> list:
    """Get all documents for a tenant from PostgreSQL."""
    query = text("""
        SELECT id, title, filename, file_path, file_type, description,
               category, created_at, updated_at
        FROM documents
        WHERE tenant_id = :tenant_id
        ORDER BY created_at DESC
    """)

    with engine.connect() as conn:
        result = conn.execute(query, {"tenant_id": tenant_id})
        documents = []
        for row in result:
            documents.append({
                "id": str(row.id),
                "title": row.title,
                "filename": row.filename,
                "file_path": row.file_path,
                "file_type": row.file_type,
                "description": row.description,
                "category": row.category,
                "created_at": row.created_at.isoformat() if row.created_at else None,
                "updated_at": row.updated_at.isoformat() if row.updated_at else None,
            })
        return documents


def get_tenant_bucket(engine, tenant_id: str) -> str:
    """Get bucket name for tenant from PostgreSQL."""
    query = text("SELECT bucket_name FROM tenants WHERE id = :tenant_id")
    with engine.connect() as conn:
        result = conn.execute(query, {"tenant_id": tenant_id})
        row = result.fetchone()
        if row:
            return row[0]
        raise Exception(f"Tenant {tenant_id} not found")


def download_file_gcs(tenant_id: str, file_path: str) -> bytes:
    """Download file directly from GCS, trying multiple bucket/path patterns."""
    from google.cloud import storage as gcs

    # Use credentials from environment or mounted path
    credentials_path = os.environ.get("GCS_CREDENTIALS", "/app/credentials/nexusdocs360-pre-7d2cb195adc7.json")

    if os.path.exists(credentials_path):
        client = gcs.Client.from_service_account_json(credentials_path)
    else:
        client = gcs.Client()

    # Try multiple bucket patterns
    bucket_patterns = [
        f"nexus-documents-dev-{tenant_id}",  # Pattern 1: nexus-documents-dev-{tenant_id}
        f"org-{tenant_id}",  # Pattern 2
    ]

    # For each bucket, try multiple path patterns
    for bucket_name in bucket_patterns:
        bucket = client.bucket(bucket_name)
        if not bucket.exists():
            continue

        # List blobs to find the file
        prefix = f"tenant-{tenant_id}/"
        blobs = list(bucket.list_blobs(prefix=prefix))

        for blob in blobs:
            if blob.name.endswith(f"/{file_path}") or blob.name == file_path:
                logger.info(f"  Found file at: {bucket_name}/{blob.name}")
                return blob.download_as_bytes()

        # Also try direct path
        blob = bucket.blob(file_path)
        if blob.exists():
            return blob.download_as_bytes()

    raise Exception(f"File not found in any bucket: {file_path}")


def download_file(tenant_id: str, file_path: str) -> bytes:
    """Download file - try storage service first, then GCS directly."""
    # Try storage service first
    url = f"{STORAGE_SERVICE_URL}/api/v1/storage/download/{tenant_id}/{file_path}"

    try:
        with httpx.Client(timeout=60) as client:
            response = client.get(
                url,
                headers={"X-API-Key": MICROSERVICES_API_KEY}
            )
            if response.status_code == 200:
                return response.content
    except Exception as e:
        logger.warning(f"Storage service failed: {e}")

    # Fallback to direct GCS download
    logger.info(f"  Trying direct GCS download...")
    return download_file_gcs(tenant_id, file_path)


def extract_text_tika(file_content: bytes, filename: str) -> str:
    """Extract text from file using Apache Tika."""
    # Determine content type
    ext = filename.split('.')[-1].lower() if '.' in filename else ''
    content_types = {
        'pdf': 'application/pdf',
        'doc': 'application/msword',
        'docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
        'txt': 'text/plain',
        'xlsx': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        'xls': 'application/vnd.ms-excel',
        'pptx': 'application/vnd.openxmlformats-officedocument.presentationml.presentation',
        'ppt': 'application/vnd.ms-powerpoint',
    }
    content_type = content_types.get(ext, 'application/octet-stream')

    with httpx.Client(timeout=120) as client:
        response = client.put(
            f"{TIKA_URL}/tika",
            content=file_content,
            headers={
                "Content-Type": content_type,
                "Accept": "text/plain"
            }
        )
        response.raise_for_status()
        return response.text.strip()


def create_es_index(es_client: Elasticsearch, index_name: str):
    """Create Elasticsearch index if it doesn't exist."""
    if not es_client.indices.exists(index=index_name):
        mapping = {
            "settings": {
                "number_of_shards": 1,
                "number_of_replicas": 0,
                "analysis": {
                    "analyzer": {
                        "spanish_analyzer": {
                            "type": "custom",
                            "tokenizer": "standard",
                            "filter": ["lowercase", "spanish_stemmer"]
                        }
                    },
                    "filter": {
                        "spanish_stemmer": {
                            "type": "stemmer",
                            "language": "spanish"
                        }
                    }
                }
            },
            "mappings": {
                "properties": {
                    "doc_id": {"type": "keyword"},
                    "tenant_id": {"type": "keyword"},
                    "title": {"type": "text", "analyzer": "spanish_analyzer"},
                    "description": {"type": "text", "analyzer": "spanish_analyzer"},
                    "content": {"type": "text", "analyzer": "spanish_analyzer"},
                    "filename": {"type": "keyword"},
                    "file_type": {"type": "keyword"},
                    "category": {"type": "keyword"},
                    "created_at": {"type": "date"},
                    "updated_at": {"type": "date"},
                    "indexed_at": {"type": "date"}
                }
            }
        }
        es_client.indices.create(index=index_name, body=mapping)
        logger.info(f"Created index: {index_name}")


def index_document(es_client: Elasticsearch, index_name: str, doc: dict, content: str, tenant_id: str):
    """Index a document in Elasticsearch."""
    es_doc = {
        "doc_id": doc["id"],
        "tenant_id": tenant_id,
        "title": doc["title"] or doc["filename"],
        "description": doc.get("description") or "",
        "content": content,
        "filename": doc["filename"],
        "file_type": doc["file_type"],
        "category": doc.get("category"),
        "created_at": doc.get("created_at"),
        "updated_at": doc.get("updated_at"),
        "indexed_at": datetime.utcnow().isoformat()
    }

    es_client.index(
        index=index_name,
        id=doc["id"],
        document=es_doc
    )


def update_document_status(engine, doc_id: str, status: int, error_msg: str = None):
    """Update document indexing status in PostgreSQL."""
    if error_msg:
        query = text("""
            UPDATE documents
            SET indexed = :status, indexing_error = :error_msg, updated_at = NOW()
            WHERE id = :doc_id
        """)
        params = {"doc_id": doc_id, "status": status, "error_msg": error_msg}
    else:
        query = text("""
            UPDATE documents
            SET indexed = :status, indexing_error = NULL, updated_at = NOW()
            WHERE id = :doc_id
        """)
        params = {"doc_id": doc_id, "status": status}

    with engine.connect() as conn:
        conn.execute(query, params)
        conn.commit()


def reindex_tenant(tenant_id: str, force: bool = False):
    """Reindex all documents for a tenant."""
    logger.info(f"Starting reindex for tenant: {tenant_id}")

    # Connect to services
    engine = create_engine(DATABASE_URL)
    es_client = Elasticsearch([ELASTICSEARCH_URL])

    # Check Tika is available
    try:
        with httpx.Client(timeout=10) as client:
            response = client.get(f"{TIKA_URL}/version")
            logger.info(f"Tika version: {response.text.strip()}")
    except Exception as e:
        logger.error(f"Tika not available: {e}")
        return

    # Get documents
    documents = get_documents(engine, tenant_id)
    logger.info(f"Found {len(documents)} documents to reindex")

    if not documents:
        logger.info("No documents found")
        return

    # Create/ensure index exists
    index_name = f"nexus_{tenant_id.replace('-', '_')}_documents"

    if force:
        # Delete existing index if force mode
        try:
            if es_client.indices.exists(index=index_name):
                es_client.indices.delete(index=index_name)
                logger.info(f"Deleted existing index: {index_name}")
        except Exception as e:
            logger.warning(f"Could not delete index: {e}")

    create_es_index(es_client, index_name)

    # Process documents
    success_count = 0
    error_count = 0

    for i, doc in enumerate(documents, 1):
        doc_id = doc["id"]
        filename = doc["filename"]
        file_path = doc["file_path"]

        logger.info(f"[{i}/{len(documents)}] Processing: {filename}")

        try:
            # Download file
            logger.info(f"  Downloading from: {file_path}")
            file_content = download_file(tenant_id, file_path)
            logger.info(f"  Downloaded: {len(file_content)} bytes")

            # Extract text with Tika
            logger.info(f"  Extracting text with Tika...")
            content = extract_text_tika(file_content, filename)
            logger.info(f"  Extracted: {len(content)} characters")

            # Show preview
            preview = content[:200].replace('\n', ' ')
            logger.info(f"  Preview: {preview}...")

            # Index in Elasticsearch
            logger.info(f"  Indexing in Elasticsearch...")
            index_document(es_client, index_name, doc, content, tenant_id)

            # Update status in PostgreSQL (2 = INDEXED)
            update_document_status(engine, doc_id, 2)

            success_count += 1
            logger.info(f"  SUCCESS")

        except Exception as e:
            error_count += 1
            error_msg = str(e)[:500]
            logger.error(f"  FAILED: {error_msg}")

            # Update status in PostgreSQL (3 = INDEXING_ERROR)
            update_document_status(engine, doc_id, 3, error_msg)

    # Summary
    logger.info("=" * 60)
    logger.info(f"REINDEX COMPLETE")
    logger.info(f"  Total documents: {len(documents)}")
    logger.info(f"  Success: {success_count}")
    logger.info(f"  Errors: {error_count}")
    logger.info("=" * 60)

    # Refresh index
    es_client.indices.refresh(index=index_name)

    # Show final count
    count = es_client.count(index=index_name)
    logger.info(f"Documents in index: {count['count']}")


def main():
    parser = argparse.ArgumentParser(description="Reindex documents in Elasticsearch using Tika")
    parser.add_argument("--tenant-id", required=True, help="Tenant ID to reindex")
    parser.add_argument("--force", action="store_true", help="Delete and recreate index")

    args = parser.parse_args()

    reindex_tenant(args.tenant_id, args.force)


if __name__ == "__main__":
    main()
