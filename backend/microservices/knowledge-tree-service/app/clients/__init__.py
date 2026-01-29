"""HTTP clients for external service communication"""

from .weaviate_client import WeaviateClient, get_weaviate_client

__all__ = ["WeaviateClient", "get_weaviate_client"]
