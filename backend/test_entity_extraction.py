#!/usr/bin/env python3
"""
Test script for entity extraction functionality
"""
import asyncio
import httpx
from app.services.langchain_client import LangChainClient
from app.core.config import settings

async def test_entity_extraction():
    """Test entity extraction with sample text."""
    
    # Sample text with various entities
    sample_text = """
    Apple Inc. announced today that Tim Cook, the company's CEO, will be meeting with 
    representatives from Microsoft Corporation in Seattle, Washington next week. 
    The meeting will also include Satya Nadella, Microsoft's CEO, and key executives 
    from both companies. They plan to discuss potential collaboration on AI initiatives.
    
    John Smith from the legal department and Sarah Johnson from finance will be 
    attending from Apple's side. The meeting is scheduled for December 15th at 
    Microsoft's headquarters in Redmond.
    """
    
    async with httpx.AsyncClient(timeout=30.0) as http_client:
        client = LangChainClient(
            http_client=http_client,
            tenant_id=settings.DEFAULT_TENANT
        )
        
        print("Testing entity extraction...")
        print(f"Input text length: {len(sample_text)} characters")
        print("-" * 80)
        
        try:
            # Extract entities
            entities = await client.extract_entities(sample_text)
            
            if entities:
                print(f"Found {len(entities)} entities:")
                print("-" * 80)
                
                # Group by type
                by_type = {}
                for entity in entities:
                    entity_type = entity.get('type', 'other')
                    if entity_type not in by_type:
                        by_type[entity_type] = []
                    by_type[entity_type].append(entity)
                
                # Display by type
                for entity_type, items in by_type.items():
                    print(f"\n{entity_type.upper()} ({len(items)}):")
                    for item in items:
                        print(f"  - {item.get('name')}")
                        if item.get('role'):
                            print(f"    Role: {item.get('role')}")
                        if item.get('context'):
                            print(f"    Context: {item.get('context')[:100]}...")
            else:
                print("No entities found.")
                
        except Exception as e:
            print(f"Error: {str(e)}")


if __name__ == "__main__":
    asyncio.run(test_entity_extraction())