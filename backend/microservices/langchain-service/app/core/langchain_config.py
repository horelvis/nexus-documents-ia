"""
LangChain configuration and initialization
"""
import logging
from typing import Optional
from langchain_ollama import OllamaEmbeddings, OllamaLLM
from langchain_qdrant import Qdrant
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain.chains import RetrievalQA
from langchain_core.prompts import PromptTemplate
from qdrant_client import QdrantClient

from app.core.config import settings

logger = logging.getLogger(__name__)


class LangChainManager:
    """Central manager for LangChain components"""
    
    _embeddings_instance: Optional[OllamaEmbeddings] = None
    _llm_instance: Optional[OllamaLLM] = None
    _text_splitter_instance: Optional[RecursiveCharacterTextSplitter] = None
    
    @classmethod
    def get_embeddings(cls) -> OllamaEmbeddings:
        """Get singleton embeddings instance"""
        if cls._embeddings_instance is None:
            cls._embeddings_instance = OllamaEmbeddings(
                base_url=settings.OLLAMA_BASE_URL,
                model=settings.EMBEDDING_MODEL
            )
            logger.info(f"Initialized embeddings with model: {settings.EMBEDDING_MODEL}")
        return cls._embeddings_instance
    
    @classmethod
    def get_llm(cls) -> OllamaLLM:
        """Get singleton LLM instance"""
        if cls._llm_instance is None:
            cls._llm_instance = OllamaLLM(
                base_url=settings.OLLAMA_BASE_URL,
                model=settings.OLLAMA_MODEL,
                temperature=0.7
            )
            logger.info(f"Initialized LLM with model: {settings.OLLAMA_MODEL}")
        return cls._llm_instance
    
    @classmethod
    def get_text_splitter(cls) -> RecursiveCharacterTextSplitter:
        """Get singleton text splitter instance"""
        if cls._text_splitter_instance is None:
            cls._text_splitter_instance = RecursiveCharacterTextSplitter(
                chunk_size=settings.CHUNK_SIZE,
                chunk_overlap=settings.CHUNK_OVERLAP,
                length_function=len,
                separators=["\n\n", "\n", " ", ""]
            )
            logger.info(f"Initialized text splitter with chunk_size: {settings.CHUNK_SIZE}")
        return cls._text_splitter_instance
    
    @classmethod
    def get_qdrant_client(cls) -> QdrantClient:
        """Get Qdrant client"""
        return QdrantClient(
            host=settings.QDRANT_HOST,
            port=settings.QDRANT_PORT
        )
    
    @classmethod
    def create_vectorstore(cls, collection_name: str) -> Qdrant:
        """Create Qdrant vectorstore for a collection"""
        client = cls.get_qdrant_client()
        embeddings = cls.get_embeddings()
        
        return Qdrant(
            client=client,
            collection_name=collection_name,
            embeddings=embeddings
        )
    
    @classmethod
    def create_rag_prompt(cls) -> PromptTemplate:
        """Create RAG prompt template"""
        template = """Usa el siguiente contexto para responder la pregunta de manera precisa y detallada.
        Si no puedes responder con la información proporcionada, menciona que no tienes suficiente información.

        Contexto: {context}

        Pregunta: {question}

        Respuesta detallada:"""
        
        return PromptTemplate(
            template=template,
            input_variables=["context", "question"]
        )
    
    @classmethod
    def create_rag_chain(cls, vectorstore: Qdrant) -> RetrievalQA:
        """Create RAG chain with vectorstore"""
        llm = cls.get_llm()
        prompt = cls.create_rag_prompt()
        
        return RetrievalQA.from_chain_type(
            llm=llm,
            chain_type="stuff",
            retriever=vectorstore.as_retriever(search_kwargs={"k": 5}),
            chain_type_kwargs={"prompt": prompt},
            return_source_documents=True
        )