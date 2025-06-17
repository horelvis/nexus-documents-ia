"""
Unified Memory Manager for CrewAI agents with LangGraph state management
"""
from typing import Dict, List, Any, Optional
from datetime import datetime, timedelta
import json
import hashlib
from loguru import logger
import redis.asyncio as redis
from langchain_core.embeddings import Embeddings
from qdrant_client import QdrantClient
from qdrant_client.models import PointStruct, Filter, FieldCondition, MatchValue

from app.core.config import settings


class MemoryType:
    """Memory type definitions"""
    EPISODIC = "episodic"      # Specific interactions and events
    SEMANTIC = "semantic"       # General knowledge and facts
    PROCEDURAL = "procedural"   # How-to knowledge and successful patterns
    WORKING = "working"         # Short-term, current context


class UnifiedMemoryManager:
    """Manages memory across LangGraph state and CrewAI agents"""
    
    def __init__(self, tenant_id: str, vector_store: QdrantClient, embeddings: Embeddings):
        self.tenant_id = tenant_id
        self.vector_store = vector_store
        self.embeddings = embeddings
        self.collection_prefix = f"memory_{tenant_id}"
        
        # Initialize Redis for fast access
        self.redis_client = None
        self._init_redis()
        
        # Memory configurations
        self.ttl_config = {
            MemoryType.WORKING: 3600,      # 1 hour
            MemoryType.EPISODIC: 86400 * 7,  # 7 days
            MemoryType.SEMANTIC: None,      # No expiry
            MemoryType.PROCEDURAL: None     # No expiry
        }
    
    def _init_redis(self):
        """Initialize Redis connection"""
        try:
            self.redis_client = redis.from_url(settings.redis_url)
        except Exception as e:
            logger.error(f"Failed to initialize Redis: {e}")
    
    def _get_collection_name(self, memory_type: str) -> str:
        """Get collection name for memory type"""
        return f"{self.collection_prefix}_{memory_type}"
    
    async def store_interaction(
        self,
        agent_id: str,
        task: str,
        result: Any,
        metadata: Dict[str, Any]
    ) -> str:
        """Store agent interaction in multiple memory types"""
        
        interaction_id = hashlib.md5(
            f"{agent_id}_{task}_{datetime.utcnow().isoformat()}".encode()
        ).hexdigest()
        
        # Store in episodic memory
        episode = {
            "id": interaction_id,
            "agent_id": agent_id,
            "task": task,
            "result": result if isinstance(result, str) else json.dumps(result),
            "timestamp": datetime.utcnow().isoformat(),
            "metadata": metadata
        }
        
        await self._store_episodic(episode)
        
        # Extract and store semantic knowledge if successful
        if metadata.get("success", False):
            await self._extract_and_store_semantic(task, result, metadata)
        
        # Store procedural knowledge for successful patterns
        if metadata.get("effectiveness_score", 0) > 0.7:
            await self._store_procedural_pattern(agent_id, task, metadata)
        
        # Update working memory
        await self._update_working_memory(agent_id, task, result)
        
        logger.info(f"Stored interaction {interaction_id} for agent {agent_id}")
        
        return interaction_id
    
    async def _store_episodic(self, episode: Dict[str, Any]):
        """Store episodic memory in vector store"""
        try:
            # Generate embedding for the episode
            text = f"{episode['task']} {episode['result']}"
            embedding = await self._generate_embedding(text)
            
            # Store in Qdrant
            collection = self._get_collection_name(MemoryType.EPISODIC)
            
            point = PointStruct(
                id=episode["id"],
                vector=embedding,
                payload=episode
            )
            
            # Ensure collection exists
            await self._ensure_collection(collection, len(embedding))
            
            # Store point
            self.vector_store.upsert(
                collection_name=collection,
                points=[point]
            )
            
        except Exception as e:
            logger.error(f"Failed to store episodic memory: {e}")
    
    async def _extract_and_store_semantic(
        self,
        task: str,
        result: Any,
        metadata: Dict[str, Any]
    ):
        """Extract semantic knowledge from successful interactions"""
        try:
            # Extract key facts (simplified for POC)
            facts = self._extract_facts(result)
            
            for fact in facts:
                fact_id = hashlib.md5(fact.encode()).hexdigest()
                
                # Generate embedding
                embedding = await self._generate_embedding(fact)
                
                # Store in semantic memory
                collection = self._get_collection_name(MemoryType.SEMANTIC)
                
                point = PointStruct(
                    id=fact_id,
                    vector=embedding,
                    payload={
                        "fact": fact,
                        "source_task": task,
                        "confidence": metadata.get("effectiveness_score", 0.8),
                        "timestamp": datetime.utcnow().isoformat(),
                        "metadata": metadata
                    }
                )
                
                await self._ensure_collection(collection, len(embedding))
                
                self.vector_store.upsert(
                    collection_name=collection,
                    points=[point]
                )
                
        except Exception as e:
            logger.error(f"Failed to store semantic memory: {e}")
    
    async def _store_procedural_pattern(
        self,
        agent_id: str,
        task: str,
        metadata: Dict[str, Any]
    ):
        """Store successful procedural patterns"""
        try:
            pattern = {
                "agent_type": metadata.get("agent_role", agent_id),
                "task_type": metadata.get("task_type"),
                "approach": metadata.get("approach", "standard"),
                "effectiveness": metadata.get("effectiveness_score", 0.8),
                "conditions": {
                    "task_keywords": self._extract_keywords(task),
                    "context": metadata.get("context_type")
                }
            }
            
            pattern_id = hashlib.md5(
                f"{pattern['agent_type']}_{pattern['task_type']}_{pattern['approach']}".encode()
            ).hexdigest()
            
            # Generate embedding for pattern matching
            pattern_text = f"{pattern['task_type']} {pattern['approach']} {' '.join(pattern['conditions']['task_keywords'])}"
            embedding = await self._generate_embedding(pattern_text)
            
            # Store in procedural memory
            collection = self._get_collection_name(MemoryType.PROCEDURAL)
            
            point = PointStruct(
                id=pattern_id,
                vector=embedding,
                payload={
                    "pattern": pattern,
                    "success_count": 1,  # Would increment on updates
                    "last_used": datetime.utcnow().isoformat()
                }
            )
            
            await self._ensure_collection(collection, len(embedding))
            
            self.vector_store.upsert(
                collection_name=collection,
                points=[point]
            )
            
        except Exception as e:
            logger.error(f"Failed to store procedural memory: {e}")
    
    async def _update_working_memory(
        self,
        agent_id: str,
        task: str,
        result: Any
    ):
        """Update short-term working memory in Redis"""
        if not self.redis_client:
            return
        
        try:
            key = f"working_memory:{self.tenant_id}:{agent_id}"
            
            memory_entry = {
                "task": task,
                "result": result if isinstance(result, str) else json.dumps(result),
                "timestamp": datetime.utcnow().isoformat()
            }
            
            # Store with TTL
            await self.redis_client.setex(
                key,
                self.ttl_config[MemoryType.WORKING],
                json.dumps(memory_entry)
            )
            
        except Exception as e:
            logger.error(f"Failed to update working memory: {e}")
    
    async def retrieve_relevant_memories(
        self,
        query: str,
        context: Dict[str, Any],
        memory_types: List[str] = None,
        limit: int = 5
    ) -> Dict[str, List[Any]]:
        """Retrieve relevant memories for current task"""
        
        memories = {}
        types_to_search = memory_types or [
            MemoryType.EPISODIC,
            MemoryType.SEMANTIC,
            MemoryType.PROCEDURAL
        ]
        
        # Generate query embedding
        query_embedding = await self._generate_embedding(query)
        
        for mem_type in types_to_search:
            try:
                if mem_type == MemoryType.WORKING:
                    # Retrieve from Redis
                    memories[mem_type] = await self._retrieve_working_memory(context)
                else:
                    # Retrieve from vector store
                    collection = self._get_collection_name(mem_type)
                    
                    # Search with filters if provided
                    filters = None
                    if context.get("task_type"):
                        filters = Filter(
                            must=[
                                FieldCondition(
                                    key="metadata.task_type",
                                    match=MatchValue(value=context["task_type"])
                                )
                            ]
                        )
                    
                    results = self.vector_store.search(
                        collection_name=collection,
                        query_vector=query_embedding,
                        limit=limit,
                        query_filter=filters
                    )
                    
                    memories[mem_type] = [
                        {
                            "content": hit.payload,
                            "score": hit.score
                        }
                        for hit in results
                    ]
                    
            except Exception as e:
                logger.error(f"Failed to retrieve {mem_type} memories: {e}")
                memories[mem_type] = []
        
        return memories
    
    async def _retrieve_working_memory(self, context: Dict[str, Any]) -> List[Any]:
        """Retrieve working memory from Redis"""
        if not self.redis_client:
            return []
        
        try:
            # Get all working memory keys for tenant
            pattern = f"working_memory:{self.tenant_id}:*"
            keys = await self.redis_client.keys(pattern)
            
            memories = []
            for key in keys[:5]:  # Limit to recent 5
                value = await self.redis_client.get(key)
                if value:
                    memories.append(json.loads(value))
            
            return memories
            
        except Exception as e:
            logger.error(f"Failed to retrieve working memory: {e}")
            return []
    
    async def store_agent_contribution(
        self,
        agent_type: str,
        contribution: Any,
        task_context: str
    ):
        """Store individual agent contributions"""
        
        contribution_id = hashlib.md5(
            f"{agent_type}_{task_context}_{datetime.utcnow().isoformat()}".encode()
        ).hexdigest()
        
        # Store as episodic memory with agent attribution
        episode = {
            "id": contribution_id,
            "agent_type": agent_type,
            "contribution": contribution,
            "task_context": task_context,
            "timestamp": datetime.utcnow().isoformat(),
            "metadata": {
                "contribution_type": "agent_output"
            }
        }
        
        await self._store_episodic(episode)
    
    async def get_agent_performance_history(
        self,
        agent_type: str,
        task_type: Optional[str] = None,
        days: int = 7
    ) -> List[Dict[str, Any]]:
        """Get historical performance data for an agent type"""
        
        # Calculate date filter
        since_date = (datetime.utcnow() - timedelta(days=days)).isoformat()
        
        # Build filter
        must_conditions = [
            FieldCondition(
                key="pattern.agent_type",
                match=MatchValue(value=agent_type)
            ),
            FieldCondition(
                key="last_used",
                range={
                    "gte": since_date
                }
            )
        ]
        
        if task_type:
            must_conditions.append(
                FieldCondition(
                    key="pattern.task_type",
                    match=MatchValue(value=task_type)
                )
            )
        
        filters = Filter(must=must_conditions)
        
        # Search procedural memory
        collection = self._get_collection_name(MemoryType.PROCEDURAL)
        
        try:
            results = self.vector_store.scroll(
                collection_name=collection,
                scroll_filter=filters,
                limit=100
            )
            
            return [point.payload for point in results[0]]
            
        except Exception as e:
            logger.error(f"Failed to get agent performance history: {e}")
            return []
    
    async def _generate_embedding(self, text: str) -> List[float]:
        """Generate embedding for text"""
        try:
            # Use the provided embeddings model
            embedding = await self.embeddings.aembed_query(text)
            return embedding
        except Exception as e:
            logger.error(f"Failed to generate embedding: {e}")
            # Return zero vector as fallback
            return [0.0] * 384  # Assuming 384-dim embeddings
    
    async def _ensure_collection(self, collection_name: str, vector_size: int):
        """Ensure collection exists in vector store"""
        try:
            # Check if collection exists
            collections = self.vector_store.get_collections()
            if not any(c.name == collection_name for c in collections.collections):
                # Create collection
                self.vector_store.create_collection(
                    collection_name=collection_name,
                    vectors_config={
                        "size": vector_size,
                        "distance": "Cosine"
                    }
                )
                logger.info(f"Created collection: {collection_name}")
        except Exception as e:
            logger.error(f"Failed to ensure collection: {e}")
    
    def _extract_facts(self, result: Any) -> List[str]:
        """Extract facts from result (simplified)"""
        # In real implementation, would use NLP to extract facts
        if isinstance(result, str):
            # Simple sentence splitting
            sentences = result.split(". ")
            return [s.strip() for s in sentences if len(s.strip()) > 20][:5]
        return []
    
    def _extract_keywords(self, text: str) -> List[str]:
        """Extract keywords from text (simplified)"""
        # In real implementation, would use proper keyword extraction
        words = text.lower().split()
        # Filter common words
        stopwords = {"the", "a", "an", "and", "or", "but", "in", "on", "at", "to", "for"}
        keywords = [w for w in words if w not in stopwords and len(w) > 3]
        return keywords[:10]