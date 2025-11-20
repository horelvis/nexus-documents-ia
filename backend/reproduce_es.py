import asyncio
import logging
from elasticsearch import AsyncElasticsearch

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

ELASTICSEARCH_URL = "http://localhost:9200"
INDEX_NAME = "test_reproduction_index"

async def main():
    client = AsyncElasticsearch(ELASTICSEARCH_URL)
    
    try:
        # 1. Delete index if exists
        if await client.indices.exists(index=INDEX_NAME):
            await client.indices.delete(index=INDEX_NAME)
            logger.info(f"Deleted existing index {INDEX_NAME}")

        # 2. Create index with the SUSPECT MAPPING
        mapping = {
            "mappings": {
                "properties": {
                    "doc_id": {"type": "keyword"},
                    "title": {
                        "type": "text",
                        # SUSPECT: keyword tokenizer prevents partial matches
                        "analyzer": "filename_analyzer", 
                        "fields": {
                            "keyword": {"type": "keyword"}
                        }
                    },
                    "content": {
                        "type": "text",
                        "analyzer": "content_analyzer"
                    },
                    "description": {
                        "type": "text",
                        "analyzer": "content_analyzer"
                    },
                    # Simplified for test
                    "tenant_id": {"type": "keyword"}
                }
            },
            "settings": {
                "number_of_shards": 1,
                "number_of_replicas": 0,
                "analysis": {
                    "analyzer": {
                        "filename_analyzer": {
                            "type": "custom",
                            "tokenizer": "keyword", # <--- THE CULPRIT FOR TITLES?
                            "filter": ["lowercase", "filename_filter"]
                        },
                        "content_analyzer": {
                            "type": "custom",
                            "tokenizer": "standard",
                            "filter": ["lowercase", "stop"]
                        }
                    },
                    "filter": {
                        "filename_filter": {
                            "type": "pattern_replace",
                            "pattern": "[_.-]",
                            "replacement": " "
                        }
                    }
                }
            }
        }
        
        await client.indices.create(index=INDEX_NAME, body=mapping)
        logger.info(f"Created index {INDEX_NAME} with suspect mapping")

        # 3. Index a document
        doc = {
            "doc_id": "1",
            "title": "Documento de Prueba",
            "content": "Vamos a optimizar búsqueda semántica en este documento de contenido. También palabras cortas como el, la, de.",
            "description": "Descripción breve",
            "tenant_id": "test"
        }
        await client.index(index=INDEX_NAME, id="1", body=doc, refresh=True)
        logger.info("Indexed test document")

        # 4. Test Searches
        queries = [
            ("optimizar búsqueda semántica", ["content"]), # Phrase search on content
            ("optimizar", ["content"]), # Single word on content
            ("búsqueda", ["content"]), # Single word on content
            ("Prueba", ["title"]), # Partial word on title (Expected FAIL with keyword tokenizer)
            ("Documento de Prueba", ["title"]), # Full title (Expected PASS)
            ("Documento", ["title"]), # Partial word matching start (Expected FAIL with keyword tokenizer)
        ]

        logger.info("-" * 50)
        for query_text, fields in queries:
            logger.info(f"Testing query: '{query_text}' on fields {fields}")
            
            search_body = {
                "query": {
                    "multi_match": {
                        "query": query_text,
                        "fields": fields,
                        "type": "best_fields"
                    }
                }
            }
            
            response = await client.search(index=INDEX_NAME, body=search_body)
            hits = response['hits']['total']['value']
            logger.info(f"Hits: {hits}")
            if hits > 0:
                logger.info("✅ FOUND")
            else:
                logger.info("❌ NOT FOUND")
            logger.info("-" * 50)

        # 5. Analyze Tokens (Why does content fail?)
        logger.info("Analyzing 'optimizar búsqueda semántica' with content_analyzer:")
        tokens = await client.indices.analyze(index=INDEX_NAME, body={
            "analyzer": "content_analyzer",
            "text": "optimizar búsqueda semántica"
        })
        token_list = [t['token'] for t in tokens['tokens']]
        logger.info(f"Tokens: {token_list}")

    finally:
        await client.close()

if __name__ == "__main__":
    asyncio.run(main())
