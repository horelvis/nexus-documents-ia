"""
Tests for LangChain-based services
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.embedding_service import EmbeddingService
from app.services.vector_service import VectorService
from app.services.llm_service import LLMService
from app.services.search_service import SearchService


class TestEmbeddingService:
    """Tests for LangChain EmbeddingService"""
    
    @patch('app.services.embedding_service.LangChainManager')
    def test_embedding_service_init(self, mock_manager, test_tenant):
        """Test EmbeddingService initialization"""
        mock_embeddings = MagicMock()
        mock_text_splitter = MagicMock()
        mock_manager.get_embeddings.return_value = mock_embeddings
        mock_manager.get_text_splitter.return_value = mock_text_splitter
        
        service = EmbeddingService(test_tenant.id)
        
        assert service.tenant_id == test_tenant.id
        assert service.embeddings == mock_embeddings
        assert service.text_splitter == mock_text_splitter
    
    @patch('app.services.embedding_service.LangChainManager')
    def test_get_embeddings(self, mock_manager, test_tenant):
        """Test embeddings generation"""
        mock_embeddings = MagicMock()
        mock_embeddings.embed_documents.return_value = [[0.1, 0.2, 0.3], [0.4, 0.5, 0.6]]
        mock_manager.get_embeddings.return_value = mock_embeddings
        mock_manager.get_text_splitter.return_value = MagicMock()
        
        service = EmbeddingService(test_tenant.id)
        texts = ["texto 1", "texto 2"]
        
        result = service.get_embeddings(texts)
        
        assert len(result) == 2
        assert result[0] == [0.1, 0.2, 0.3]
        mock_embeddings.embed_documents.assert_called_once_with(texts)
    
    @patch('app.services.embedding_service.LangChainManager')
    def test_chunk_text(self, mock_manager, test_tenant):
        """Test text chunking"""
        mock_text_splitter = MagicMock()
        mock_text_splitter.split_text.return_value = ["chunk 1", "chunk 2"]
        mock_manager.get_text_splitter.return_value = mock_text_splitter
        mock_manager.get_embeddings.return_value = MagicMock()
        
        service = EmbeddingService(test_tenant.id)
        text = "Este es un texto largo para dividir en chunks"
        
        result = service.chunk_text(text)
        
        assert len(result) == 2
        assert result[0]["text"] == "chunk 1"
        assert result[0]["chunk_index"] == 0
        assert result[1]["text"] == "chunk 2"
        assert result[1]["chunk_index"] == 1


class TestVectorService:
    """Tests for LangChain VectorService"""
    
    @patch('app.services.vector_service.LangChainManager')
    def test_vector_service_init(self, mock_manager, test_tenant):
        """Test VectorService initialization"""
        mock_client = MagicMock()
        mock_embeddings = MagicMock()
        mock_manager.get_qdrant_client.return_value = mock_client
        mock_manager.get_embeddings.return_value = mock_embeddings
        
        # Mock collection check
        mock_client.get_collections.return_value = MagicMock(collections=[])
        
        service = VectorService(test_tenant.id)
        
        assert service.tenant_id == test_tenant.id
        assert service.collection_name == f"documents_{test_tenant.id}"
        assert service.client == mock_client
    
    @patch('app.services.vector_service.LangChainManager')
    def test_add_documents(self, mock_manager, test_tenant):
        """Test adding documents to vector store"""
        mock_vectorstore = MagicMock()
        mock_manager.create_vectorstore.return_value = mock_vectorstore
        mock_manager.get_qdrant_client.return_value = MagicMock()
        mock_manager.get_embeddings.return_value = MagicMock()
        
        # Mock collection check
        mock_client = MagicMock()
        mock_client.get_collections.return_value = MagicMock(collections=[])
        mock_manager.get_qdrant_client.return_value = mock_client
        
        service = VectorService(test_tenant.id)
        texts = ["texto 1", "texto 2"]
        metadatas = [{"meta": "data1"}, {"meta": "data2"}]
        
        result = service.add_documents(texts, metadatas)
        
        assert result is True
        mock_vectorstore.add_texts.assert_called_once()
    
    @patch('app.services.vector_service.LangChainManager')
    def test_search_similar(self, mock_manager, test_tenant):
        """Test similarity search"""
        mock_vectorstore = MagicMock()
        mock_doc1 = MagicMock(page_content="content 1", metadata={"id": "1"})
        mock_doc2 = MagicMock(page_content="content 2", metadata={"id": "2"})
        mock_vectorstore.similarity_search_with_score.return_value = [
            (mock_doc1, 0.9),
            (mock_doc2, 0.8)
        ]
        mock_manager.create_vectorstore.return_value = mock_vectorstore
        mock_manager.get_qdrant_client.return_value = MagicMock()
        mock_manager.get_embeddings.return_value = MagicMock()
        
        # Mock collection check
        mock_client = MagicMock()
        mock_client.get_collections.return_value = MagicMock(collections=[])
        mock_manager.get_qdrant_client.return_value = mock_client
        
        service = VectorService(test_tenant.id)
        
        results = service.search_similar("query test", limit=2)
        
        assert len(results) == 2
        assert results[0]["content"] == "content 1"
        assert results[0]["score"] == 0.9
        assert results[1]["content"] == "content 2"
        assert results[1]["score"] == 0.8


class TestLLMService:
    """Tests for LangChain LLMService"""
    
    @patch('app.services.llm_service.LangChainManager')
    def test_llm_service_init(self, mock_manager):
        """Test LLMService initialization"""
        mock_llm = MagicMock()
        mock_manager.get_llm.return_value = mock_llm
        
        service = LLMService()
        
        assert service.llm == mock_llm
    
    @patch('app.services.llm_service.LangChainManager')
    @patch('app.services.llm_service.VectorService')
    @pytest.mark.asyncio
    async def test_generate_response_with_rag(self, mock_vector_service_class, mock_manager):
        """Test RAG response generation"""
        # Setup mocks
        mock_llm = MagicMock()
        mock_llm.invoke.return_value = "Direct LLM response"
        mock_manager.get_llm.return_value = mock_llm
        
        mock_chain = MagicMock()
        mock_chain.return_value = {
            "result": "RAG response",
            "source_documents": [
                MagicMock(page_content="source content", metadata={"doc_id": "1"})
            ]
        }
        mock_manager.create_rag_chain.return_value = mock_chain
        
        mock_vector_service = MagicMock()
        mock_vector_service.get_vectorstore.return_value = MagicMock()
        mock_vector_service.search_by_document_ids.return_value = [
            {"content": "context", "metadata": {"doc_id": "1"}}
        ]
        mock_vector_service_class.return_value = mock_vector_service
        
        service = LLMService()
        
        # Test RAG response
        result = await service.generate_response(
            query="test query",
            doc_ids=["doc1"],
            tenant_id="tenant1"
        )
        
        assert "answer" in result
        assert "sources" in result
        assert result["answer"] == "RAG response"
    
    @patch('app.services.llm_service.LangChainManager')
    @pytest.mark.asyncio
    async def test_generate_direct_response(self, mock_manager):
        """Test direct LLM response"""
        mock_llm = MagicMock()
        mock_llm.invoke.return_value = "Direct response"
        mock_manager.get_llm.return_value = mock_llm
        
        service = LLMService()
        
        result = await service.generate_response(query="test query")
        
        assert result["answer"] == "Direct response"
        assert result["sources"] == []
        assert result["type"] == "direct_llm"
    
    @patch('app.services.llm_service.LangChainManager')
    @pytest.mark.asyncio
    async def test_suggest_tags(self, mock_manager):
        """Test tag suggestion"""
        mock_llm = MagicMock()
        mock_llm.invoke.return_value = "tag1, tag2, tag3, tag4, tag5"
        mock_manager.get_llm.return_value = mock_llm
        
        service = LLMService()
        
        tags = await service.suggest_tags("sample text", num_tags=3)
        
        assert len(tags) == 3
        assert "tag1" in tags
        assert "tag2" in tags
        assert "tag3" in tags


class TestSearchService:
    """Tests for SearchService"""
    
    @patch('app.services.search_service.LLMService')
    @patch('app.services.search_service.VectorService')
    def test_search_service_init(self, mock_vector_service, mock_llm_service):
        """Test SearchService initialization"""
        tenant_id = "test_tenant"
        
        service = SearchService(tenant_id)
        
        assert service.tenant_id == tenant_id
        mock_llm_service.assert_called_once()
        mock_vector_service.assert_called_once_with(tenant_id)
    
    @patch('app.services.search_service.LLMService')
    @patch('app.services.search_service.VectorService')
    @pytest.mark.asyncio
    async def test_chat_with_documents(self, mock_vector_service, mock_llm_service):
        """Test chat with documents"""
        # Setup mocks
        mock_llm_instance = MagicMock()
        mock_llm_instance.generate_response = AsyncMock(return_value={
            "answer": "Test response",
            "sources": [{"content": "source1"}]
        })
        mock_llm_service.return_value = mock_llm_instance
        
        service = SearchService("test_tenant")
        
        result = await service.chat_with_documents("test query", ["doc1"])
        
        assert result["answer"] == "Test response"
        assert len(result["sources"]) == 1
        mock_llm_instance.generate_response.assert_called_once_with(
            query="test query",
            doc_ids=["doc1"],
            tenant_id="test_tenant"
        )
    
    @patch('app.services.search_service.VectorService')
    @pytest.mark.asyncio
    async def test_search_documents(self, mock_vector_service):
        """Test document search"""
        mock_vector_instance = MagicMock()
        mock_vector_instance.search_similar.return_value = [
            {"content": "result1", "score": 0.9}
        ]
        mock_vector_service.return_value = mock_vector_instance
        
        service = SearchService("test_tenant")
        
        results = await service.search_documents("test query", limit=5)
        
        assert len(results) == 1
        assert results[0]["content"] == "result1"
        mock_vector_instance.search_similar.assert_called_once_with(
            query="test query",
            limit=5
        )