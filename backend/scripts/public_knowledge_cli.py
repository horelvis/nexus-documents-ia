#!/usr/bin/env python3
"""
Public Knowledge Base CLI
Complete management tool for the public knowledge base
"""
import argparse
import asyncio
import httpx
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional


class PublicKnowledgeCLI:
    """CLI for managing the public knowledge base"""

    def __init__(self, api_url: str, api_key: str):
        self.api_url = api_url.rstrip('/')
        self.api_key = api_key
        self.headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}"
        }

    async def health(self) -> dict:
        """Check service health"""
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(f"{self.api_url}/public-knowledge/health")
            return response.json()

    async def stats(self) -> dict:
        """Get statistics"""
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(f"{self.api_url}/public-knowledge/stats")
            return response.json()

    async def categories(self) -> dict:
        """List categories"""
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(f"{self.api_url}/public-knowledge/categories")
            return response.json()

    async def jurisdictions(self) -> dict:
        """List jurisdictions"""
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(f"{self.api_url}/public-knowledge/jurisdictions")
            return response.json()

    async def search(
        self,
        query: str,
        limit: int = 10,
        categories: Optional[list] = None,
        jurisdictions: Optional[list] = None,
        verified_only: bool = False
    ) -> dict:
        """Search documents"""
        payload = {
            "query": query,
            "limit": limit,
            "verified_only": verified_only,
            "search_type": "hybrid"
        }
        if categories:
            payload["categories"] = categories
        if jurisdictions:
            payload["jurisdictions"] = jurisdictions

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{self.api_url}/public-knowledge/search",
                json=payload
            )
            return response.json()

    async def get_document(self, doc_id: str) -> dict:
        """Get a document by ID"""
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                f"{self.api_url}/public-knowledge/documents/{doc_id}"
            )
            if response.status_code == 404:
                return {"error": "Document not found"}
            return response.json()

    async def add_document(self, document: dict) -> dict:
        """Add a document"""
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                f"{self.api_url}/public-knowledge/documents",
                headers=self.headers,
                json=document
            )
            response.raise_for_status()
            return response.json()

    async def delete_document(self, doc_id: str) -> dict:
        """Delete a document"""
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.delete(
                f"{self.api_url}/public-knowledge/documents/{doc_id}",
                headers=self.headers
            )
            if response.status_code == 404:
                return {"error": "Document not found"}
            return response.json()

    async def add_from_json(self, json_file: str) -> dict:
        """Add documents from JSON file"""
        with open(json_file, 'r', encoding='utf-8') as f:
            data = json.load(f)

        if isinstance(data, list):
            async with httpx.AsyncClient(timeout=120.0) as client:
                response = await client.post(
                    f"{self.api_url}/public-knowledge/documents/batch",
                    headers=self.headers,
                    json=data
                )
                return response.json()
        else:
            return await self.add_document(data)


def print_json(data: dict, indent: int = 2):
    """Pretty print JSON data"""
    print(json.dumps(data, indent=indent, ensure_ascii=False, default=str))


def print_search_results(results: dict):
    """Pretty print search results"""
    print(f"\nQuery: {results.get('query', '')}")
    print(f"Total results: {results.get('total_results', 0)}")
    print(f"Search time: {results.get('search_time_ms', 0)}ms")
    print("-" * 60)

    for i, doc in enumerate(results.get("results", []), 1):
        print(f"\n{i}. {doc.get('title', 'Sin título')}")
        print(f"   Category: {doc.get('category', '')} | Jurisdiction: {doc.get('jurisdiction', '')}")
        if doc.get('legal_reference'):
            print(f"   Reference: {doc['legal_reference']}")
        if doc.get('similarity_score'):
            print(f"   Score: {doc['similarity_score']:.2f}")
        if doc.get('summary'):
            print(f"   Summary: {doc['summary'][:150]}...")


def print_stats(stats: dict):
    """Pretty print statistics"""
    print("\n=== Public Knowledge Base Statistics ===")
    print(f"Total documents: {stats.get('total_documents', 0)}")
    print(f"Verified documents: {stats.get('verified_count', 0)}")
    print(f"Last updated: {stats.get('last_updated', 'Unknown')}")

    by_category = stats.get('documents_by_category', {})
    if by_category:
        print("\nBy Category:")
        for cat, count in by_category.items():
            print(f"  - {cat}: {count}")

    by_jurisdiction = stats.get('documents_by_jurisdiction', {})
    if by_jurisdiction:
        print("\nBy Jurisdiction:")
        for jur, count in by_jurisdiction.items():
            print(f"  - {jur}: {count}")


async def main():
    parser = argparse.ArgumentParser(
        description="Public Knowledge Base CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Check health
  python public_knowledge_cli.py health

  # Get statistics
  python public_knowledge_cli.py stats

  # List categories
  python public_knowledge_cli.py categories

  # Search documents
  python public_knowledge_cli.py search "protección de datos"
  python public_knowledge_cli.py search "RGPD" --category legislation --jurisdiction eu

  # Get specific document
  python public_knowledge_cli.py get <document-id>

  # Add document from JSON
  python public_knowledge_cli.py add --json document.json

  # Add document inline
  python public_knowledge_cli.py add --title "Test Doc" --content "Content..." --category legislation

  # Delete document
  python public_knowledge_cli.py delete <document-id>
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
    parser.add_argument(
        "--output", "-o",
        choices=["json", "pretty"],
        default="pretty",
        help="Output format"
    )

    subparsers = parser.add_subparsers(dest="command", help="Command")

    # Health command
    subparsers.add_parser("health", help="Check service health")

    # Stats command
    subparsers.add_parser("stats", help="Get statistics")

    # Categories command
    subparsers.add_parser("categories", help="List categories")

    # Jurisdictions command
    subparsers.add_parser("jurisdictions", help="List jurisdictions")

    # Search command
    search_parser = subparsers.add_parser("search", help="Search documents")
    search_parser.add_argument("query", help="Search query")
    search_parser.add_argument("--limit", "-l", type=int, default=10, help="Max results")
    search_parser.add_argument("--category", "-c", action="append", help="Filter by category")
    search_parser.add_argument("--jurisdiction", "-j", action="append", help="Filter by jurisdiction")
    search_parser.add_argument("--verified", action="store_true", help="Only verified documents")

    # Get command
    get_parser = subparsers.add_parser("get", help="Get document by ID")
    get_parser.add_argument("id", help="Document ID")

    # Add command
    add_parser = subparsers.add_parser("add", help="Add document")
    add_parser.add_argument("--json", help="JSON file with document(s)")
    add_parser.add_argument("--title", help="Document title")
    add_parser.add_argument("--content", help="Document content")
    add_parser.add_argument("--category", default="reference", help="Category")
    add_parser.add_argument("--jurisdiction", default="es", help="Jurisdiction")
    add_parser.add_argument("--legal-reference", help="Legal reference")
    add_parser.add_argument("--keywords", help="Keywords (comma-separated)")

    # Delete command
    delete_parser = subparsers.add_parser("delete", help="Delete document")
    delete_parser.add_argument("id", help="Document ID")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return

    cli = PublicKnowledgeCLI(args.api_url, args.api_key)
    output_json = args.output == "json"

    try:
        if args.command == "health":
            result = await cli.health()
            if output_json:
                print_json(result)
            else:
                status = result.get("status", "unknown")
                print(f"Status: {status}")
                if status == "healthy":
                    print(f"Service: {result.get('service', '')}")
                    print(f"Collection: {result.get('collection', '')}")

        elif args.command == "stats":
            result = await cli.stats()
            if output_json:
                print_json(result)
            else:
                print_stats(result)

        elif args.command == "categories":
            result = await cli.categories()
            if output_json:
                print_json(result)
            else:
                print("\nAvailable Categories:")
                for cat in result.get("categories", []):
                    print(f"  - {cat['value']}: {cat['description']}")

        elif args.command == "jurisdictions":
            result = await cli.jurisdictions()
            if output_json:
                print_json(result)
            else:
                print("\nAvailable Jurisdictions:")
                for jur in result.get("jurisdictions", []):
                    print(f"  - {jur['value']}: {jur['description']}")

        elif args.command == "search":
            result = await cli.search(
                args.query,
                limit=args.limit,
                categories=args.category,
                jurisdictions=args.jurisdiction,
                verified_only=args.verified
            )
            if output_json:
                print_json(result)
            else:
                print_search_results(result)

        elif args.command == "get":
            result = await cli.get_document(args.id)
            print_json(result)

        elif args.command == "add":
            if args.json:
                result = await cli.add_from_json(args.json)
            elif args.title and args.content:
                document = {
                    "title": args.title,
                    "content": args.content,
                    "category": args.category,
                    "jurisdiction": args.jurisdiction,
                }
                if args.legal_reference:
                    document["legal_reference"] = args.legal_reference
                if args.keywords:
                    document["keywords"] = [k.strip() for k in args.keywords.split(",")]
                result = await cli.add_document(document)
            else:
                print("Error: --json or (--title and --content) required")
                return

            if output_json:
                print_json(result)
            else:
                print(f"Document added: {result.get('id', 'Unknown')}")
                print(f"Title: {result.get('title', '')}")

        elif args.command == "delete":
            result = await cli.delete_document(args.id)
            if output_json:
                print_json(result)
            else:
                if "error" in result:
                    print(f"Error: {result['error']}")
                else:
                    print(f"Document deleted: {args.id}")

    except httpx.HTTPStatusError as e:
        print(f"HTTP Error: {e.response.status_code}")
        try:
            print_json(e.response.json())
        except:
            print(e.response.text)
    except Exception as e:
        print(f"Error: {e}")


if __name__ == "__main__":
    asyncio.run(main())
