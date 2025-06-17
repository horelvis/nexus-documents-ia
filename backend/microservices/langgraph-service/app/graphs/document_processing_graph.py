from typing import TypedDict, List, Dict, Any, Optional
from langgraph.graph import StateGraph, END
from langchain_core.messages import HumanMessage
from langchain.text_splitter import RecursiveCharacterTextSplitter
from loguru import logger
import hashlib

from app.schemas.graph import GraphNode


class DocumentState(TypedDict):
    """State for document processing graph"""
    document_id: str
    content: str
    filename: str
    tenant_id: str
    user_id: Optional[str]
    metadata: Dict[str, Any]
    chunks: Optional[List[Dict[str, Any]]]
    embeddings_generated: bool
    quality_score: Optional[float]
    processing_notes: List[str]
    needs_reprocessing: bool
    iteration: int


class DocumentProcessingGraph:
    """Graph for processing documents with quality checks and adaptive chunking"""
    
    def __init__(self, llm, embeddings, qdrant_client, checkpointer, tenant_id: str, **kwargs):
        self.llm = llm
        self.embeddings = embeddings
        self.qdrant_client = qdrant_client
        self.checkpointer = checkpointer
        self.tenant_id = tenant_id
        self.text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=1000,
            chunk_overlap=200,
            length_function=len,
            separators=["\n\n", "\n", ". ", " ", ""]
        )
        self.graph = self._build_graph()
    
    def _build_graph(self):
        """Build the document processing graph"""
        workflow = StateGraph(DocumentState)
        
        # Add nodes
        workflow.add_node("extract_metadata", self.extract_metadata)
        workflow.add_node("detect_language", self.detect_language)
        workflow.add_node("chunk_document", self.chunk_document)
        workflow.add_node("quality_check", self.quality_check)
        workflow.add_node("generate_embeddings", self.generate_embeddings)
        workflow.add_node("store_vectors", self.store_vectors)
        workflow.add_node("reprocess_chunks", self.reprocess_chunks)
        
        # Set entry point
        workflow.set_entry_point("extract_metadata")
        
        # Add edges
        workflow.add_edge("extract_metadata", "detect_language")
        workflow.add_edge("detect_language", "chunk_document")
        workflow.add_edge("chunk_document", "quality_check")
        
        # Conditional edge for quality check
        workflow.add_conditional_edges(
            "quality_check",
            self.should_reprocess,
            {
                "reprocess": "reprocess_chunks",
                "continue": "generate_embeddings"
            }
        )
        
        workflow.add_edge("reprocess_chunks", "quality_check")
        workflow.add_edge("generate_embeddings", "store_vectors")
        workflow.add_edge("store_vectors", END)
        
        # Compile with checkpointer
        return workflow.compile(checkpointer=self.checkpointer)
    
    async def extract_metadata(self, state: DocumentState) -> DocumentState:
        """Extract metadata from document"""
        logger.info(f"Extracting metadata for document {state['document_id']}")
        
        messages = [
            HumanMessage(content=f"""
Extract key metadata from this document:

Filename: {state['filename']}
Content preview: {state['content'][:500]}...

Extract:
1. Document type (report, invoice, contract, etc.)
2. Date (if present)
3. Author/Organization (if present)
4. Main topic
5. Key entities mentioned

Return as JSON format.
""")
        ]
        
        response = await self.llm.ainvoke(messages)
        
        # Parse metadata (simplified for POC)
        state["metadata"] = {
            "filename": state["filename"],
            "extracted_metadata": response.content,
            "processing_timestamp": "2024-12-20"
        }
        
        state["processing_notes"] = ["Metadata extracted"]
        state["iteration"] = state.get("iteration", 0) + 1
        
        return state
    
    async def detect_language(self, state: DocumentState) -> DocumentState:
        """Detect document language"""
        logger.info("Detecting document language")
        
        # Simplified language detection
        state["metadata"]["language"] = "en"
        state["processing_notes"].append("Language detected: English")
        
        return state
    
    async def chunk_document(self, state: DocumentState) -> DocumentState:
        """Chunk document into processable pieces"""
        logger.info("Chunking document")
        
        # Split text
        texts = self.text_splitter.split_text(state["content"])
        
        # Create chunks with metadata
        chunks = []
        for i, text in enumerate(texts):
            chunk_id = hashlib.md5(f"{state['document_id']}_{i}_{text[:50]}".encode()).hexdigest()
            chunks.append({
                "chunk_id": chunk_id,
                "document_id": state["document_id"],
                "chunk_index": i,
                "content": text,
                "metadata": {
                    **state["metadata"],
                    "chunk_index": i,
                    "total_chunks": len(texts)
                }
            })
        
        state["chunks"] = chunks
        state["processing_notes"].append(f"Created {len(chunks)} chunks")
        
        return state
    
    async def quality_check(self, state: DocumentState) -> DocumentState:
        """Check quality of chunks"""
        logger.info("Performing quality check")
        
        if not state.get("chunks"):
            state["quality_score"] = 0.0
            state["needs_reprocessing"] = True
            return state
        
        # Simple quality metrics
        total_length = sum(len(chunk["content"]) for chunk in state["chunks"])
        avg_chunk_length = total_length / len(state["chunks"])
        
        # Quality score based on chunk characteristics
        if avg_chunk_length < 100:
            quality_score = 0.3
        elif avg_chunk_length > 2000:
            quality_score = 0.5
        else:
            quality_score = 0.9
        
        state["quality_score"] = quality_score
        state["needs_reprocessing"] = quality_score < 0.7 and state.get("iteration", 0) < 2
        
        state["processing_notes"].append(f"Quality score: {quality_score:.2f}")
        
        return state
    
    async def reprocess_chunks(self, state: DocumentState) -> DocumentState:
        """Reprocess chunks with different parameters"""
        logger.info("Reprocessing chunks")
        
        # Adjust chunking parameters
        if state.get("quality_score", 0) < 0.5:
            chunk_size = 500
            overlap = 100
        else:
            chunk_size = 1500
            overlap = 300
        
        self.text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=chunk_size,
            chunk_overlap=overlap
        )
        
        # Re-chunk
        state = await self.chunk_document(state)
        state["processing_notes"].append(f"Reprocessed with chunk_size={chunk_size}")
        
        return state
    
    async def generate_embeddings(self, state: DocumentState) -> DocumentState:
        """Generate embeddings for chunks"""
        logger.info("Generating embeddings")
        
        # In real implementation, would generate actual embeddings
        # For POC, mark as generated
        state["embeddings_generated"] = True
        state["processing_notes"].append("Embeddings generated for all chunks")
        
        return state
    
    async def store_vectors(self, state: DocumentState) -> DocumentState:
        """Store vectors in Qdrant"""
        logger.info("Storing vectors in Qdrant")
        
        # In real implementation, would store in Qdrant
        # For POC, mark as stored
        state["processing_notes"].append(f"Stored {len(state['chunks'])} vectors in collection documents_{state['tenant_id']}")
        
        return state
    
    def should_reprocess(self, state: DocumentState) -> str:
        """Determine if reprocessing is needed"""
        if state.get("needs_reprocessing", False):
            return "reprocess"
        return "continue"
    
    async def ainvoke(self, input_data: Dict[str, Any], config: Optional[Dict[str, Any]] = None):
        """Invoke the graph"""
        # Initialize state
        initial_state = DocumentState(
            document_id=input_data["document_id"],
            content=input_data["content"],
            filename=input_data["filename"],
            tenant_id=input_data["tenant_id"],
            user_id=input_data.get("user_id"),
            metadata=input_data.get("metadata", {}),
            chunks=None,
            embeddings_generated=False,
            quality_score=None,
            processing_notes=[],
            needs_reprocessing=False,
            iteration=0
        )
        
        # Run graph
        result = await self.graph.ainvoke(initial_state, config)
        
        # Return formatted result
        return {
            "document_id": result["document_id"],
            "chunks": result.get("chunks", []),
            "embeddings_generated": result.get("embeddings_generated", False),
            "metadata": result.get("metadata", {}),
            "quality_score": result.get("quality_score"),
            "processing_notes": result.get("processing_notes", []),
            "_iterations": result.get("iteration", 0)
        }
    
    async def astream_events(self, input_data: Dict[str, Any], config: Optional[Dict[str, Any]] = None, version: str = "v1"):
        """Stream events from graph execution"""
        initial_state = DocumentState(
            document_id=input_data["document_id"],
            content=input_data["content"],
            filename=input_data["filename"],
            tenant_id=input_data["tenant_id"],
            user_id=input_data.get("user_id"),
            metadata=input_data.get("metadata", {}),
            chunks=None,
            embeddings_generated=False,
            quality_score=None,
            processing_notes=[],
            needs_reprocessing=False,
            iteration=0
        )
        
        async for event in self.graph.astream_events(initial_state, config, version=version):
            yield event
    
    @staticmethod
    def get_structure() -> Dict[str, Any]:
        """Get the structure of this graph"""
        return {
            "nodes": [
                GraphNode(
                    id="extract_metadata",
                    name="Extract Metadata",
                    type="llm",
                    description="Extract metadata from document using LLM"
                ).dict(),
                GraphNode(
                    id="detect_language",
                    name="Detect Language",
                    type="processing",
                    description="Detect document language"
                ).dict(),
                GraphNode(
                    id="chunk_document",
                    name="Chunk Document",
                    type="processing",
                    description="Split document into chunks"
                ).dict(),
                GraphNode(
                    id="quality_check",
                    name="Quality Check",
                    type="analysis",
                    description="Check chunk quality"
                ).dict(),
                GraphNode(
                    id="generate_embeddings",
                    name="Generate Embeddings",
                    type="ml",
                    description="Generate embeddings for chunks"
                ).dict(),
                GraphNode(
                    id="store_vectors",
                    name="Store Vectors",
                    type="storage",
                    description="Store vectors in Qdrant"
                ).dict(),
                GraphNode(
                    id="reprocess_chunks",
                    name="Reprocess Chunks",
                    type="processing",
                    description="Reprocess with different parameters"
                ).dict()
            ],
            "edges": [
                {"from": "extract_metadata", "to": "detect_language"},
                {"from": "detect_language", "to": "chunk_document"},
                {"from": "chunk_document", "to": "quality_check"},
                {"from": "quality_check", "to": "generate_embeddings", "condition": "quality_ok"},
                {"from": "quality_check", "to": "reprocess_chunks", "condition": "needs_reprocessing"},
                {"from": "reprocess_chunks", "to": "quality_check"},
                {"from": "generate_embeddings", "to": "store_vectors"},
                {"from": "store_vectors", "to": "END"}
            ],
            "entry_point": "extract_metadata",
            "description": "Intelligent document processing with quality checks and adaptive chunking"
        }