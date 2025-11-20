import asyncio
import uuid
import sys
import os

# Ensure app modules can be imported
sys.path.append(os.getcwd())
sys.path.append(os.path.join(os.getcwd(), "backend"))

from backend.app.services.elasticsearch_client import elasticsearch_client

async def test_es_flow():
    tenant_id = str(uuid.uuid4())
    doc_id = str(uuid.uuid4())
    
    print(f"🚀 Starting ES Flow Test")
    print(f"📍 Tenant ID: {tenant_id}")
    print(f"📄 Doc ID: {doc_id}")
    
    # 1. Index Document
    print("\n[1] Indexing Document...")
    success = await elasticsearch_client.index_document(
        tenant_id=tenant_id,
        doc_id=doc_id,
        title="Test Document for Search",
        content="This is a test document content that should be searchable via elasticsearch hybrid search.",
        description="A description of the test document",
        metadata={"file_type": "txt", "category": "test"}
    )
    
    if not success:
        print("❌ Indexing Failed!")
        return
    print("✅ Indexing Success!")
    
    # 2. Wait a moment for ES refresh (default 1s)
    print("\n[2] Waiting 2s for index refresh...")
    await asyncio.sleep(2)
    
    # 3. Search Document
    print("\n[3] Searching 'test document'...")
    results = await elasticsearch_client.hybrid_search(
        tenant_id=tenant_id,
        query="test document"
    )
    
    print(f"🔍 Found {len(results)} results")
    for res in results:
        print(f"   - {res['document']['title']} (Score: {res['score']})")
        
    if len(results) > 0:
        print("\n✅ Search Success!")
    else:
        print("\n❌ Search Failed (No results found)")

if __name__ == "__main__":
    asyncio.run(test_es_flow())
