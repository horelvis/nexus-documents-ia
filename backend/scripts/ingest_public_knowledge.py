#!/usr/bin/env python3
"""
Public Knowledge Base Ingestion Script
Supports: BOE, EUR-Lex, local files (PDF, DOCX, TXT)
"""
import argparse
import asyncio
import httpx
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional
from urllib.parse import quote_plus

# Add parent directory for imports
sys.path.insert(0, str(Path(__file__).parent.parent))


class PublicKnowledgeIngester:
    """Ingests documents into the public knowledge base"""

    def __init__(self, api_url: str, api_key: str):
        self.api_url = api_url.rstrip('/')
        self.api_key = api_key
        self.headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}"
        }

    async def add_document(self, document: Dict[str, Any]) -> Dict[str, Any]:
        """Add a single document to the public knowledge base"""
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                f"{self.api_url}/public-knowledge/documents",
                headers=self.headers,
                json=document
            )
            response.raise_for_status()
            return response.json()

    async def batch_add_documents(self, documents: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Add multiple documents in batch"""
        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.post(
                f"{self.api_url}/public-knowledge/documents/batch",
                headers=self.headers,
                json=documents
            )
            response.raise_for_status()
            return response.json()


class BOEIngester:
    """Ingests documents from BOE (Boletín Oficial del Estado)"""

    BASE_URL = "https://www.boe.es"
    API_URL = "https://www.boe.es/datosabiertos/api"

    def __init__(self, ingester: PublicKnowledgeIngester):
        self.ingester = ingester

    async def search_boe(
        self,
        query: str,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """Search BOE for documents"""
        params = {
            "q": query,
            "coleccion": "legislacion",
            "page_size": limit
        }
        if date_from:
            params["fecha_publicacion_desde"] = date_from
        if date_to:
            params["fecha_publicacion_hasta"] = date_to

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(
                f"{self.API_URL}/buscar",
                params=params
            )
            if response.status_code == 200:
                return response.json().get("data", [])
            return []

    async def get_document_content(self, boe_id: str) -> Optional[Dict[str, Any]]:
        """Get full document content from BOE"""
        async with httpx.AsyncClient(timeout=30.0) as client:
            # Get document metadata
            response = await client.get(f"{self.API_URL}/documento/{boe_id}")
            if response.status_code != 200:
                return None

            data = response.json().get("data", {})

            # Get text content
            text_url = f"{self.BASE_URL}/diario_boe/txt.php?id={boe_id}"
            text_response = await client.get(text_url)
            content = ""
            if text_response.status_code == 200:
                content = text_response.text

            return {
                "boe_id": boe_id,
                "title": data.get("titulo", ""),
                "content": content,
                "publication_date": data.get("fecha_publicacion"),
                "department": data.get("departamento"),
                "section": data.get("seccion"),
                "url": f"{self.BASE_URL}/diario_boe/txt.php?id={boe_id}"
            }

    async def ingest_by_query(
        self,
        query: str,
        category: str = "legislation",
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """Search BOE and ingest matching documents"""
        results = await self.search_boe(query, limit=limit)
        ingested = []

        for result in results:
            boe_id = result.get("id", "")
            if not boe_id:
                continue

            doc_data = await self.get_document_content(boe_id)
            if not doc_data or not doc_data.get("content"):
                print(f"  Skipping {boe_id}: no content")
                continue

            document = {
                "title": doc_data["title"],
                "content": doc_data["content"],
                "summary": doc_data["title"][:500],
                "category": category,
                "jurisdiction": "es",
                "legal_reference": f"BOE-{boe_id}",
                "source_url": doc_data["url"],
                "source_name": "BOE",
                "keywords": [query] + doc_data["title"].split()[:5],
                "verified": True
            }

            if doc_data.get("publication_date"):
                try:
                    document["publication_date"] = datetime.strptime(
                        doc_data["publication_date"], "%Y-%m-%d"
                    ).isoformat() + "Z"
                except:
                    pass

            try:
                result = await self.ingester.add_document(document)
                print(f"  Ingested: {document['title'][:60]}...")
                ingested.append(result)
            except Exception as e:
                print(f"  Error ingesting {boe_id}: {e}")

        return ingested

    async def ingest_by_id(self, boe_id: str, category: str = "legislation") -> Optional[Dict[str, Any]]:
        """Ingest a specific BOE document by ID"""
        doc_data = await self.get_document_content(boe_id)
        if not doc_data:
            print(f"Document {boe_id} not found")
            return None

        document = {
            "title": doc_data["title"],
            "content": doc_data["content"],
            "summary": doc_data["title"][:500],
            "category": category,
            "jurisdiction": "es",
            "legal_reference": f"BOE-{boe_id}",
            "source_url": doc_data["url"],
            "source_name": "BOE",
            "keywords": doc_data["title"].split()[:10],
            "verified": True
        }

        if doc_data.get("publication_date"):
            try:
                document["publication_date"] = datetime.strptime(
                    doc_data["publication_date"], "%Y-%m-%d"
                ).isoformat() + "Z"
            except:
                pass

        return await self.ingester.add_document(document)


class EURLexIngester:
    """Ingests documents from EUR-Lex (European Union Law)"""

    BASE_URL = "https://eur-lex.europa.eu"
    SEARCH_URL = "https://eur-lex.europa.eu/search.html"

    def __init__(self, ingester: PublicKnowledgeIngester):
        self.ingester = ingester

    async def get_document_by_celex(self, celex: str) -> Optional[Dict[str, Any]]:
        """Get document content by CELEX number"""
        # EUR-Lex API endpoint for document
        url = f"{self.BASE_URL}/legal-content/ES/TXT/?uri=CELEX:{celex}"

        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
            response = await client.get(url)
            if response.status_code != 200:
                return None

            # Parse HTML content (simplified)
            content = response.text

            # Extract title from HTML
            title_match = re.search(r'<title>([^<]+)</title>', content)
            title = title_match.group(1) if title_match else celex

            # Extract main text content (simplified)
            text_content = re.sub(r'<[^>]+>', ' ', content)
            text_content = re.sub(r'\s+', ' ', text_content).strip()

            return {
                "celex": celex,
                "title": title,
                "content": text_content[:100000],  # Limit content size
                "url": url
            }

    async def ingest_by_celex(
        self,
        celex: str,
        category: str = "regulation"
    ) -> Optional[Dict[str, Any]]:
        """Ingest a specific EUR-Lex document by CELEX number"""
        doc_data = await self.get_document_by_celex(celex)
        if not doc_data:
            print(f"Document {celex} not found")
            return None

        # Determine category from CELEX
        if celex.startswith("3") and "R" in celex:
            category = "regulation"
        elif celex.startswith("3") and "L" in celex:
            category = "legislation"
        elif celex.startswith("6"):
            category = "jurisprudence"

        document = {
            "title": doc_data["title"],
            "content": doc_data["content"],
            "summary": doc_data["title"][:500],
            "category": category,
            "jurisdiction": "eu",
            "legal_reference": f"CELEX:{celex}",
            "source_url": doc_data["url"],
            "source_name": "EUR-Lex",
            "keywords": doc_data["title"].split()[:10],
            "verified": True
        }

        return await self.ingester.add_document(document)


class LocalFileIngester:
    """Ingests documents from local files"""

    def __init__(self, ingester: PublicKnowledgeIngester, textextract_url: str = None):
        self.ingester = ingester
        self.textextract_url = textextract_url or "http://textextract-service:8000"

    async def extract_text(self, file_path: str) -> Optional[str]:
        """Extract text from file using textextract service"""
        path = Path(file_path)
        if not path.exists():
            print(f"File not found: {file_path}")
            return None

        suffix = path.suffix.lower()

        # Plain text files
        if suffix in [".txt", ".md"]:
            return path.read_text(encoding="utf-8", errors="ignore")

        # Use textextract service for PDF, DOCX, etc.
        async with httpx.AsyncClient(timeout=120.0) as client:
            with open(file_path, "rb") as f:
                files = {"file": (path.name, f, "application/octet-stream")}
                response = await client.post(
                    f"{self.textextract_url}/extract",
                    files=files
                )
                if response.status_code == 200:
                    return response.json().get("text", "")
                else:
                    print(f"Text extraction failed: {response.status_code}")
                    return None

    async def ingest_file(
        self,
        file_path: str,
        category: str = "reference",
        jurisdiction: str = "es",
        metadata: Optional[Dict[str, Any]] = None
    ) -> Optional[Dict[str, Any]]:
        """Ingest a single file"""
        path = Path(file_path)
        content = await self.extract_text(file_path)

        if not content:
            print(f"Could not extract text from {file_path}")
            return None

        metadata = metadata or {}

        document = {
            "title": metadata.get("title", path.stem.replace("_", " ").replace("-", " ")),
            "content": content,
            "summary": content[:500] if len(content) > 500 else content,
            "category": category,
            "jurisdiction": jurisdiction,
            "legal_reference": metadata.get("legal_reference", ""),
            "source_url": metadata.get("source_url", ""),
            "source_name": metadata.get("source_name", "Local File"),
            "keywords": metadata.get("keywords", []),
            "verified": metadata.get("verified", False)
        }

        return await self.ingester.add_document(document)

    async def ingest_directory(
        self,
        directory: str,
        category: str = "reference",
        jurisdiction: str = "es",
        recursive: bool = False
    ) -> List[Dict[str, Any]]:
        """Ingest all supported files from a directory"""
        supported_extensions = {".pdf", ".docx", ".doc", ".txt", ".md", ".rtf"}
        dir_path = Path(directory)

        if not dir_path.is_dir():
            print(f"Directory not found: {directory}")
            return []

        if recursive:
            files = [f for f in dir_path.rglob("*") if f.suffix.lower() in supported_extensions]
        else:
            files = [f for f in dir_path.iterdir() if f.suffix.lower() in supported_extensions]

        ingested = []
        for file_path in files:
            print(f"Processing: {file_path.name}")
            try:
                result = await self.ingest_file(
                    str(file_path),
                    category=category,
                    jurisdiction=jurisdiction
                )
                if result:
                    ingested.append(result)
                    print(f"  Ingested: {result.get('title', 'Unknown')[:50]}...")
            except Exception as e:
                print(f"  Error: {e}")

        return ingested


async def main():
    parser = argparse.ArgumentParser(
        description="Ingest documents into the Public Knowledge Base",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Ingest from BOE by search query
  python ingest_public_knowledge.py boe --query "protección de datos" --limit 5

  # Ingest specific BOE document
  python ingest_public_knowledge.py boe --id BOE-A-2018-16673

  # Ingest from EUR-Lex by CELEX number
  python ingest_public_knowledge.py eurlex --celex 32016R0679

  # Ingest local file
  python ingest_public_knowledge.py file --path /path/to/document.pdf --category legislation

  # Ingest directory of files
  python ingest_public_knowledge.py directory --path /path/to/docs --recursive
        """
    )

    parser.add_argument(
        "--api-url",
        default=os.getenv("WEAVIATE_SERVICE_URL", "http://localhost:8000"),
        help="Weaviate service URL"
    )
    parser.add_argument(
        "--api-key",
        default=os.getenv("MICROSERVICES_API_KEY", "dev_microservice_key_12345"),
        help="API key for authentication"
    )

    subparsers = parser.add_subparsers(dest="source", help="Document source")

    # BOE subcommand
    boe_parser = subparsers.add_parser("boe", help="Ingest from BOE")
    boe_parser.add_argument("--query", help="Search query")
    boe_parser.add_argument("--id", help="Specific BOE document ID")
    boe_parser.add_argument("--limit", type=int, default=10, help="Max documents to ingest")
    boe_parser.add_argument("--category", default="legislation", help="Document category")

    # EUR-Lex subcommand
    eurlex_parser = subparsers.add_parser("eurlex", help="Ingest from EUR-Lex")
    eurlex_parser.add_argument("--celex", required=True, help="CELEX number")
    eurlex_parser.add_argument("--category", default="regulation", help="Document category")

    # File subcommand
    file_parser = subparsers.add_parser("file", help="Ingest local file")
    file_parser.add_argument("--path", required=True, help="File path")
    file_parser.add_argument("--category", default="reference", help="Document category")
    file_parser.add_argument("--jurisdiction", default="es", help="Jurisdiction")
    file_parser.add_argument("--title", help="Document title")

    # Directory subcommand
    dir_parser = subparsers.add_parser("directory", help="Ingest directory of files")
    dir_parser.add_argument("--path", required=True, help="Directory path")
    dir_parser.add_argument("--category", default="reference", help="Document category")
    dir_parser.add_argument("--jurisdiction", default="es", help="Jurisdiction")
    dir_parser.add_argument("--recursive", action="store_true", help="Process subdirectories")

    args = parser.parse_args()

    if not args.source:
        parser.print_help()
        return

    # Initialize ingester
    ingester = PublicKnowledgeIngester(args.api_url, args.api_key)

    if args.source == "boe":
        boe = BOEIngester(ingester)
        if args.id:
            print(f"Ingesting BOE document: {args.id}")
            result = await boe.ingest_by_id(args.id, args.category)
            if result:
                print(f"Success: {result.get('title', 'Unknown')}")
        elif args.query:
            print(f"Searching BOE for: {args.query}")
            results = await boe.ingest_by_query(args.query, args.category, args.limit)
            print(f"Ingested {len(results)} documents")
        else:
            print("Error: --query or --id required for BOE source")

    elif args.source == "eurlex":
        eurlex = EURLexIngester(ingester)
        print(f"Ingesting EUR-Lex document: {args.celex}")
        result = await eurlex.ingest_by_celex(args.celex, args.category)
        if result:
            print(f"Success: {result.get('title', 'Unknown')}")

    elif args.source == "file":
        local = LocalFileIngester(ingester)
        metadata = {}
        if args.title:
            metadata["title"] = args.title
        print(f"Ingesting file: {args.path}")
        result = await local.ingest_file(
            args.path,
            category=args.category,
            jurisdiction=args.jurisdiction,
            metadata=metadata
        )
        if result:
            print(f"Success: {result.get('title', 'Unknown')}")

    elif args.source == "directory":
        local = LocalFileIngester(ingester)
        print(f"Ingesting directory: {args.path}")
        results = await local.ingest_directory(
            args.path,
            category=args.category,
            jurisdiction=args.jurisdiction,
            recursive=args.recursive
        )
        print(f"Ingested {len(results)} documents")


if __name__ == "__main__":
    asyncio.run(main())
