"""
LLM Service - Handles LLM operations including RAG
"""
from typing import Dict, Any, List, Optional
from langchain_core.messages import HumanMessage, SystemMessage
from loguru import logger
import json

from app.services.vector_service import VectorService


class LLMService:
    """Service for LLM operations"""
    
    def __init__(self, llm, embeddings=None, qdrant_client=None):
        self.llm = llm
        self.embeddings = embeddings
        self.qdrant_client = qdrant_client
    
    async def generate_response(
        self,
        query: str,
        tenant_id: Optional[str] = None,
        doc_ids: Optional[List[str]] = None,
        max_tokens: int = 500,
        temperature: float = 0.7
    ) -> Dict[str, Any]:
        """Generate LLM response with optional RAG context"""
        
        context = ""
        sources = []
        context_used = 0
        
        # If tenant_id is provided, use RAG
        if tenant_id and self.embeddings and self.qdrant_client:
            vector_service = VectorService(
                tenant_id=tenant_id,
                qdrant_client=self.qdrant_client,
                embeddings=self.embeddings
            )
            
            # Search for relevant context
            if doc_ids:
                search_results = await vector_service.search_by_document_ids(
                    doc_ids=doc_ids,
                    query=query,
                    limit=5
                )
            else:
                search_results = await vector_service.search_similar(
                    query=query,
                    limit=5
                )
            
            # Build context from search results
            if search_results:
                context_parts = []
                for result in search_results:
                    context_parts.append(result["text"])
                    sources.append({
                        "doc_id": result["doc_id"],
                        "score": result["score"],
                        "metadata": result["metadata"]
                    })
                
                context = "\n\n".join(context_parts)
                context_used = len(context_parts)
        
        # Prepare messages
        messages = [
            SystemMessage(content="You are a helpful assistant. Answer questions based on the provided context if available.")
        ]
        
        if context:
            messages.append(HumanMessage(content=f"""
Based on the following context, answer the user's question.

Context:
{context}

Question: {query}

Provide a comprehensive answer. If the context doesn't contain enough information, say so.
"""))
        else:
            messages.append(HumanMessage(content=query))
        
        # Generate response
        response = await self.llm.ainvoke(messages, config={
            "max_tokens": max_tokens,
            "temperature": temperature
        })
        
        return {
            "answer": response.content,
            "sources": sources,
            "context_used": context_used
        }
    
    async def suggest_tags(self, text: str, num_tags: int = 5) -> List[str]:
        """Suggest tags for the given text"""
        
        messages = [
            SystemMessage(content="You are a tag suggestion expert. Generate relevant tags for documents."),
            HumanMessage(content=f"""
Analyze the following text and suggest {num_tags} relevant tags.
Return ONLY a JSON array of tag strings, no explanation.

Text:
{text[:1000]}  # Limit text length

Example output: ["finance", "invoice", "2024", "technology", "report"]
""")
        ]
        
        try:
            response = await self.llm.ainvoke(messages)
            
            # Parse JSON response
            tags = json.loads(response.content)
            
            # Ensure we have a list of strings
            if isinstance(tags, list):
                return tags[:num_tags]
            else:
                logger.warning(f"Invalid tag response format: {response.content}")
                return []
                
        except json.JSONDecodeError:
            logger.error(f"Failed to parse tags from response: {response.content}")
            return []
        except Exception as e:
            logger.error(f"Error suggesting tags: {e}")
            return []
    
    async def extract_metadata(self, text: str) -> Dict[str, Any]:
        """Extract metadata from text"""
        
        messages = [
            SystemMessage(content="You are a metadata extraction expert. Extract key information from documents."),
            HumanMessage(content=f"""
Extract metadata from the following text.
Return ONLY a JSON object with extracted information.

Text:
{text[:2000]}  # Limit text length

Expected fields (include only if found):
- title: Document title
- date: Date mentioned (ISO format)
- author: Author name
- type: Document type (invoice, report, email, etc.)
- company: Company name
- amount: Monetary amount (if applicable)
- summary: One-line summary

Example output: {{"title": "Invoice #123", "date": "2024-01-15", "type": "invoice", "amount": 1500.00}}
""")
        ]
        
        try:
            response = await self.llm.ainvoke(messages)
            
            # Parse JSON response
            metadata = json.loads(response.content)
            
            return metadata if isinstance(metadata, dict) else {}
                
        except json.JSONDecodeError:
            logger.error(f"Failed to parse metadata from response: {response.content}")
            return {}
        except Exception as e:
            logger.error(f"Error extracting metadata: {e}")
            return {}
    
    async def summarize_text(self, text: str, max_length: int = 200) -> str:
        """Summarize text to specified length"""
        
        messages = [
            SystemMessage(content="You are a text summarization expert. Create concise, informative summaries."),
            HumanMessage(content=f"""
Summarize the following text in approximately {max_length} characters.
Be concise but include all key points.

Text:
{text[:5000]}  # Limit text length

Provide ONLY the summary, no introduction or explanation.
""")
        ]
        
        try:
            response = await self.llm.ainvoke(messages)
            
            summary = response.content.strip()
            
            # Truncate if too long
            if len(summary) > max_length * 1.2:  # Allow 20% overflow
                summary = summary[:max_length] + "..."
            
            return summary
            
        except Exception as e:
            logger.error(f"Error summarizing text: {e}")
            return "Error generating summary"
    
    async def extract_entities(self, text: str) -> List[Dict[str, str]]:
        """Extract named entities from text"""
        
        messages = [
            SystemMessage(content="You are a named entity recognition expert. Extract entities from text."),
            HumanMessage(content=f"""
Extract named entities from the following text.
Return ONLY a JSON array of objects with 'entity' and 'type' fields.

Text:
{text[:3000]}  # Limit text length

Entity types: PERSON, ORGANIZATION, LOCATION, DATE, MONEY, PRODUCT, EVENT

Example output: [
    {{"entity": "John Smith", "type": "PERSON"}},
    {{"entity": "Apple Inc.", "type": "ORGANIZATION"}},
    {{"entity": "$1,500", "type": "MONEY"}}
]
""")
        ]
        
        try:
            response = await self.llm.ainvoke(messages)
            
            # Parse JSON response
            entities = json.loads(response.content)
            
            # Validate format
            if isinstance(entities, list):
                return [
                    e for e in entities
                    if isinstance(e, dict) and "entity" in e and "type" in e
                ]
            else:
                return []
                
        except json.JSONDecodeError:
            logger.error(f"Failed to parse entities from response: {response.content}")
            return []
        except Exception as e:
            logger.error(f"Error extracting entities: {e}")
            return []