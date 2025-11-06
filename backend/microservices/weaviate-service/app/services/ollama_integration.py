"""
Direct Ollama integration for Elysia decision trees
Optimized for NexusDocs360 use cases
"""
import logging
import httpx
import json
from typing import Dict, Any, List, Optional
from datetime import datetime

from app.core.config import settings

logger = logging.getLogger(__name__)


class ElysiaOllamaIntegration:
    """Direct integration between Elysia decision trees and Ollama LLM"""
    
    def __init__(self):
        self.ollama_url = settings.ollama_base_url
        self.model_name = settings.elysia_model_name
        self.timeout = httpx.Timeout(60.0)  # Longer timeout for complex analysis
        
        logger.info(f"🦙 ElysiaOllamaIntegration initialized")
        logger.info(f"   Ollama URL: {self.ollama_url}")
        logger.info(f"   Model: {self.model_name}")
    
    async def generate_with_context(
        self, 
        prompt: str, 
        context: Optional[Dict[str, Any]] = None,
        max_tokens: int = 2000,
        temperature: float = 0.7
    ) -> Dict[str, Any]:
        """Generate response using Ollama with context awareness"""
        try:
            # Enhance prompt with context if available
            enhanced_prompt = self._enhance_prompt_with_context(prompt, context)
            
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                url = f"{self.ollama_url}/api/generate"
                
                payload = {
                    "model": self.model_name,
                    "prompt": enhanced_prompt,
                    "stream": False,
                    "options": {
                        "num_predict": max_tokens,
                        "temperature": temperature,
                        "top_k": 40,
                        "top_p": 0.9,
                        "repeat_penalty": 1.1
                    }
                }
                
                response = await client.post(url, json=payload)
                response.raise_for_status()
                
                result = response.json()
                
                return {
                    "response": result.get("response", ""),
                    "model": self.model_name,
                    "tokens_generated": result.get("eval_count", 0),
                    "generation_time": result.get("total_duration", 0) / 1_000_000_000,  # Convert to seconds
                    "context_used": context is not None,
                    "enhanced_prompt_length": len(enhanced_prompt)
                }
                
        except Exception as e:
            logger.error(f"❌ Ollama generation failed: {e}")
            raise
    
    def _enhance_prompt_with_context(self, prompt: str, context: Optional[Dict[str, Any]]) -> str:
        """Enhance prompt with relevant context"""
        if not context:
            return prompt
        
        enhanced_parts = []
        
        # Add document context if available
        if "search_results" in context and context["search_results"]:
            enhanced_parts.append("=== DOCUMENT CONTEXT ===")
            for i, doc in enumerate(context["search_results"][:3]):  # Top 3 docs
                title = doc.get("title", "Untitled")
                content = doc.get("content", "")[:500]  # First 500 chars
                enhanced_parts.append(f"Document {i+1}: {title}\n{content}...\n")
        
        # Add query context
        if "query" in context:
            enhanced_parts.append(f"=== ORIGINAL QUERY ===\n{context['query']}\n")
        
        # Add tenant context for personalization
        if "tenant_id" in context:
            enhanced_parts.append(f"=== CONTEXT ===\nTenant: {context['tenant_id']}\n")
        
        enhanced_parts.append("=== INSTRUCTION ===")
        enhanced_parts.append(prompt)
        
        return "\n".join(enhanced_parts)
    
    async def analyze_document_structure(self, document_content: str) -> Dict[str, Any]:
        """Use Ollama to analyze document structure intelligently"""
        prompt = f"""Analyze the structure and type of this document. Return a JSON object with:
- document_type (contract, financial, legal, technical, etc.)
- key_sections (list of main sections found)
- metadata_quality (score 0-100)
- complexity_level (simple, medium, complex)
- language (detected language)
- key_entities (important entities found)
- summary (brief summary)

Document content:
{document_content[:2000]}

JSON:"""

        try:
            result = await self.generate_with_context(
                prompt, 
                max_tokens=800,
                temperature=0.1  # Low temperature for structured output
            )
            
            # Try to parse JSON response
            response_text = result["response"].strip()
            try:
                analysis = json.loads(response_text)
                return {
                    "status": "success",
                    "analysis": analysis,
                    "model_info": {
                        "model": result["model"],
                        "tokens": result["tokens_generated"],
                        "time": result["generation_time"]
                    }
                }
            except json.JSONDecodeError:
                # If JSON parsing fails, return raw analysis
                return {
                    "status": "partial",
                    "raw_analysis": response_text,
                    "model_info": {
                        "model": result["model"],
                        "tokens": result["tokens_generated"],
                        "time": result["generation_time"]
                    }
                }
                
        except Exception as e:
            logger.error(f"❌ Document analysis failed: {e}")
            return {"status": "error", "error": str(e)}
    
    async def extract_contract_terms(self, contract_content: str) -> Dict[str, Any]:
        """Use Ollama to extract contract terms intelligently"""
        prompt = f"""Extract key contract information from this document. Return JSON with:
- parties (list of contracting parties)
- effective_date (contract start date if found)
- expiration_date (contract end date if found) 
- key_terms (list of important terms and obligations)
- monetary_amounts (any dollar amounts mentioned)
- governing_law (jurisdiction if mentioned)
- contract_type (service agreement, employment, lease, etc.)
- risk_clauses (any liability or risk-related clauses)

Contract content:
{contract_content[:2500]}

JSON:"""

        try:
            result = await self.generate_with_context(
                prompt,
                max_tokens=1000,
                temperature=0.1
            )
            
            response_text = result["response"].strip()
            try:
                contract_data = json.loads(response_text)
                return {
                    "status": "success",
                    "contract_data": contract_data,
                    "extraction_confidence": self._calculate_confidence(contract_data),
                    "model_info": {
                        "model": result["model"],
                        "tokens": result["tokens_generated"],
                        "time": result["generation_time"]
                    }
                }
            except json.JSONDecodeError:
                return {
                    "status": "partial",
                    "raw_extraction": response_text,
                    "model_info": {
                        "model": result["model"],
                        "tokens": result["tokens_generated"],
                        "time": result["generation_time"]
                    }
                }
                
        except Exception as e:
            logger.error(f"❌ Contract extraction failed: {e}")
            return {"status": "error", "error": str(e)}
    
    async def analyze_financial_metrics(self, financial_content: str) -> Dict[str, Any]:
        """Use Ollama to analyze financial documents"""
        prompt = f"""Analyze this financial document and extract key metrics. Return JSON with:
- revenue_figures (any revenue numbers found)
- profit_loss (profit/loss indicators and amounts)
- key_metrics (important financial ratios or metrics)
- time_period (reporting period if identified)
- currency (currency used)
- financial_health (assessment: excellent, good, concerning, poor)
- trends (any growth/decline trends mentioned)
- risk_factors (financial risks identified)

Financial content:
{financial_content[:2500]}

JSON:"""

        try:
            result = await self.generate_with_context(
                prompt,
                max_tokens=800,
                temperature=0.2
            )
            
            response_text = result["response"].strip()
            try:
                financial_data = json.loads(response_text)
                return {
                    "status": "success",
                    "financial_analysis": financial_data,
                    "analysis_confidence": self._calculate_confidence(financial_data),
                    "model_info": {
                        "model": result["model"],
                        "tokens": result["tokens_generated"],
                        "time": result["generation_time"]
                    }
                }
            except json.JSONDecodeError:
                return {
                    "status": "partial",
                    "raw_analysis": response_text,
                    "model_info": {
                        "model": result["model"],
                        "tokens": result["tokens_generated"],
                        "time": result["generation_time"]
                    }
                }
                
        except Exception as e:
            logger.error(f"❌ Financial analysis failed: {e}")
            return {"status": "error", "error": str(e)}
    
    async def assess_document_risks(self, document_content: str, document_type: str = "general") -> Dict[str, Any]:
        """Use Ollama to assess risks in documents"""
        prompt = f"""Analyze this {document_type} document for potential risks. Return JSON with:
- risk_level (low, medium, high, critical)
- identified_risks (list of specific risks found)
- risk_categories (legal, financial, operational, reputational, etc.)
- mitigation_suggestions (recommendations to address risks)
- compliance_concerns (any regulatory issues)
- urgency_level (immediate, near-term, long-term)
- confidence_score (0-100 confidence in risk assessment)

Document content:
{document_content[:2500]}

JSON:"""

        try:
            result = await self.generate_with_context(
                prompt,
                max_tokens=1000,
                temperature=0.3
            )
            
            response_text = result["response"].strip()
            try:
                risk_data = json.loads(response_text)
                return {
                    "status": "success",
                    "risk_assessment": risk_data,
                    "assessment_timestamp": datetime.now().isoformat(),
                    "model_info": {
                        "model": result["model"],
                        "tokens": result["tokens_generated"],
                        "time": result["generation_time"]
                    }
                }
            except json.JSONDecodeError:
                return {
                    "status": "partial",
                    "raw_assessment": response_text,
                    "model_info": {
                        "model": result["model"],
                        "tokens": result["tokens_generated"],
                        "time": result["generation_time"]
                    }
                }
                
        except Exception as e:
            logger.error(f"❌ Risk assessment failed: {e}")
            return {"status": "error", "error": str(e)}
    
    async def generate_smart_summary(self, document_content: str, document_type: str = "general", summary_length: str = "medium") -> Dict[str, Any]:
        """Generate intelligent summaries based on document type"""
        
        length_instructions = {
            "short": "1-2 sentences",
            "medium": "1 paragraph (3-5 sentences)", 
            "long": "2-3 paragraphs with key details"
        }
        
        length_instruction = length_instructions.get(summary_length, "1 paragraph")
        
        if document_type == "contract":
            prompt = f"""Summarize this contract document focusing on: parties involved, key obligations, important dates, and critical terms. Length: {length_instruction}

Contract content:
{document_content[:3000]}

Summary:"""
        elif document_type == "financial":
            prompt = f"""Summarize this financial document focusing on: key financial metrics, performance indicators, trends, and important findings. Length: {length_instruction}

Financial content:
{document_content[:3000]}

Summary:"""
        else:
            prompt = f"""Provide an intelligent summary of this {document_type} document, highlighting the most important information and key takeaways. Length: {length_instruction}

Document content:
{document_content[:3000]}

Summary:"""
        
        try:
            result = await self.generate_with_context(
                prompt,
                max_tokens=400 if summary_length == "short" else 800 if summary_length == "medium" else 1200,
                temperature=0.4
            )
            
            return {
                "status": "success",
                "summary": result["response"].strip(),
                "summary_type": document_type,
                "summary_length": summary_length,
                "original_length": len(document_content),
                "compression_ratio": len(document_content) / len(result["response"]),
                "model_info": {
                    "model": result["model"],
                    "tokens": result["tokens_generated"],
                    "time": result["generation_time"]
                }
            }
            
        except Exception as e:
            logger.error(f"❌ Summary generation failed: {e}")
            return {"status": "error", "error": str(e)}
    
    def _calculate_confidence(self, extracted_data: Dict[str, Any]) -> float:
        """Calculate confidence score based on extracted data completeness"""
        if not extracted_data:
            return 0.0
        
        # Count non-empty fields
        non_empty_fields = sum(1 for v in extracted_data.values() if v and v != "N/A" and v != [])
        total_fields = len(extracted_data)
        
        if total_fields == 0:
            return 0.0
        
        confidence = (non_empty_fields / total_fields) * 100
        return round(confidence, 1)
    
    async def health_check(self) -> Dict[str, Any]:
        """Check health of Ollama integration"""
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(10.0)) as client:
                # Test basic connectivity
                response = await client.get(f"{self.ollama_url}/api/tags")
                
                if response.status_code == 200:
                    models = response.json().get("models", [])
                    model_available = any(model["name"] == self.model_name for model in models)
                    
                    return {
                        "status": "healthy",
                        "ollama_url": self.ollama_url,
                        "model_name": self.model_name,
                        "model_available": model_available,
                        "total_models": len(models),
                        "available_models": [m["name"] for m in models[:5]]  # First 5 models
                    }
                else:
                    return {
                        "status": "unhealthy",
                        "error": f"Ollama responded with status {response.status_code}"
                    }
                    
        except Exception as e:
            return {
                "status": "unhealthy",
                "error": str(e),
                "ollama_url": self.ollama_url,
                "model_name": self.model_name
            }
    
    async def generate_general_risk_knowledge(self, query: str) -> Dict[str, Any]:
        """Generate general risk knowledge using Ollama"""
        prompt = f"""You are an expert risk management consultant. Answer this query about risks with actionable insights:

Query: {query}

Provide a comprehensive response that includes:
1. Key risk categories relevant to the query
2. Specific examples of each risk type
3. Practical recommendations for mitigation
4. Industry best practices

Focus on being informative and practical. Answer in the same language as the query."""

        try:
            result = await self.generate_with_context(
                prompt,
                max_tokens=1500,
                temperature=0.7
            )
            
            if result.get("response"):
                return {
                    "status": "success",
                    "response": result["response"],
                    "risk_categories": ["Operational", "Financial", "Legal", "Compliance"],
                    "recommendations": ["Regular review", "Risk assessment", "Monitoring"],
                    "model_info": {
                        "model": result["model"],
                        "tokens": result.get("tokens_generated", 0),
                        "time": result.get("generation_time", 0)
                    }
                }
            else:
                return {"status": "error", "error": "Failed to generate response"}
                
        except Exception as e:
            logger.error(f"❌ General risk knowledge generation failed: {e}")
            return {"status": "error", "error": str(e)}


# Global instance
elysia_ollama = ElysiaOllamaIntegration()