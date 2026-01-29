"""HTTP clients for external service communication"""

from .weaviate_client import WeaviateClient, get_weaviate_client
from .knowledge_tree_client import KnowledgeTreeClient, get_knowledge_tree_client
from .text_extraction_client import TextExtractionClient, get_text_extraction_client, close_text_extraction_client

__all__ = [
    "WeaviateClient",
    "get_weaviate_client",
    "KnowledgeTreeClient",
    "get_knowledge_tree_client",
    "TextExtractionClient",
    "get_text_extraction_client",
    "close_text_extraction_client",
]
