"""Advanced Elysia tools for NexusDocs360 specific operations"""
import logging
import asyncio
import json
from typing import Dict, Any, List, Optional
from datetime import datetime

from app.core.config import settings
from app.services.weaviate_service import weaviate_service
from app.services.ollama_integration import elysia_ollama

logger = logging.getLogger(__name__)


class NexusElysiaTools:
    """NexusDocs360-specific tools for Elysia decision trees"""
    
    def __init__(self):
        self.tools_registry = {}
        self._register_all_tools()
    
    def _register_all_tools(self):
        """Register all available NexusDocs360 tools"""
        self.tools_registry = {
            "document_analyzer": {
                "name": "Document Analyzer",
                "description": "Analyzes document structure, content type, and key metadata",
                "function": self.analyze_document_structure,
                "category": "analysis"
            },
            "contract_extractor": {
                "name": "Contract Data Extractor", 
                "description": "Extracts key contract information: parties, dates, amounts, terms",
                "function": self.extract_contract_data,
                "category": "extraction"
            },
            "financial_analyzer": {
                "name": "Financial Document Analyzer",
                "description": "Analyzes financial documents for key metrics and insights",
                "function": self.analyze_financial_document,
                "category": "analysis"
            },
            "compliance_checker": {
                "name": "Compliance Rule Checker",
                "description": "Checks documents against compliance rules and regulations",
                "function": self.check_compliance,
                "category": "compliance"
            },
            "smart_summarizer": {
                "name": "Intelligent Document Summarizer",
                "description": "Creates context-aware summaries based on document type",
                "function": self.smart_summarize,
                "category": "summarization"
            },
            "entity_linker": {
                "name": "Entity Relationship Linker",
                "description": "Links entities across documents to find relationships",
                "function": self.link_entities,
                "category": "analysis"
            },
            "risk_assessor": {
                "name": "Document Risk Assessor",
                "description": "Assesses potential risks mentioned in documents",
                "function": self.assess_risks,
                "category": "analysis"
            },
            "similarity_finder": {
                "name": "Document Similarity Finder",
                "description": "Finds similar documents using advanced vector matching",
                "function": self.find_similar_documents,
                "category": "search"
            },
            "trend_analyzer": {
                "name": "Document Trend Analyzer",
                "description": "Analyzes trends across document collections over time",
                "function": self.analyze_trends,
                "category": "analytics"
            },
            "multi_lang_processor": {
                "name": "Multi-Language Processor",
                "description": "Processes and translates multi-language documents",
                "function": self.process_multilingual,
                "category": "processing"
            },
            "web_search": {
                "name": "Web Search",
                "description": "Searches the web for current information, news, weather, and real-time data",
                "function": self.search_web,
                "category": "search"
            },
            "weather_info": {
                "name": "Weather Information",
                "description": "Gets current weather information for any location worldwide",
                "function": self.get_weather_info,
                "category": "information"
            }
        }
        
        logger.info(f"✅ Registered {len(self.tools_registry)} NexusDocs360 tools")
    
    async def get_tool_by_name(self, tool_name: str) -> Optional[Dict[str, Any]]:
        """Get tool information by name"""
        return self.tools_registry.get(tool_name)
    
    async def list_all_tools(self) -> List[Dict[str, Any]]:
        """List all available tools"""
        return [
            {
                "name": tool_name,
                "display_name": tool_info["name"],
                "description": tool_info["description"],
                "category": tool_info["category"]
            }
            for tool_name, tool_info in self.tools_registry.items()
        ]
    
    async def execute_tool(self, tool_name: str, context: Dict[str, Any]) -> Dict[str, Any]:
        """Execute a specific tool with given context"""
        if tool_name not in self.tools_registry:
            raise ValueError(f"Tool {tool_name} not found")
        
        tool_func = self.tools_registry[tool_name]["function"]
        
        try:
            result = await tool_func(context)
            return {
                "tool": tool_name,
                "status": "success",
                "result": result,
                "timestamp": datetime.now().isoformat()
            }
        except Exception as e:
            logger.error(f"❌ Tool {tool_name} execution failed: {e}")
            return {
                "tool": tool_name,
                "status": "error",
                "error": str(e),
                "timestamp": datetime.now().isoformat()
            }
    
    # ================================
    # TOOL IMPLEMENTATIONS
    # ================================
    
    async def analyze_document_structure(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """Analyze document structure using Ollama AI"""
        try:
            documents = context.get("search_results", [])
            
            if not documents:
                return {"analysis": "No documents provided for analysis"}
            
            analysis = {
                "total_documents": len(documents),
                "ai_structure_analysis": [],
                "processing_method": "ollama_ai"
            }
            
            for doc in documents:
                content = doc.get("content", "")
                
                # Use AI for intelligent document structure analysis
                if len(content) > 50:  # Only process substantial content
                    logger.info(f"🔍 Processing document {doc.get('id')} with Ollama for structure analysis")
                    
                    structure_result = await elysia_ollama.analyze_document_structure(content)
                    
                    if structure_result["status"] == "success":
                        structure_data = {
                            "document_id": doc.get("id"),
                            "title": doc.get("title"),
                            "ai_analysis": structure_result["analysis"],
                            "model_info": structure_result["model_info"]
                        }
                        
                        analysis["ai_structure_analysis"].append(structure_data)
                        logger.info(f"✅ Document structure analysis completed")
                    
                    elif structure_result["status"] == "partial":
                        # Handle partial analysis
                        structure_data = {
                            "document_id": doc.get("id"),
                            "title": doc.get("title"),
                            "raw_analysis": structure_result["raw_analysis"],
                            "status": "partial_analysis",
                            "model_info": structure_result["model_info"]
                        }
                        
                        analysis["ai_structure_analysis"].append(structure_data)
                        logger.warning(f"⚠️ Partial structure analysis for document {doc.get('id')}")
            
            return analysis
            
        except Exception as e:
            logger.error(f"❌ Document structure analysis failed: {e}")
            return {"error": str(e), "processing_method": "failed"}
    
    async def extract_contract_data(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """Extract key contract information using Ollama AI"""
        try:
            documents = context.get("search_results", [])
            
            contract_data = {
                "contracts_found": 0,
                "extracted_data": [],
                "processing_method": "ollama_ai"
            }
            
            for doc in documents:
                content = doc.get("content", "")
                
                # Use AI to detect if this is a contract and extract data
                if len(content) > 50:  # Only process substantial content
                    logger.info(f"🔍 Processing document {doc.get('id')} with Ollama for contract extraction")
                    
                    extraction_result = await elysia_ollama.extract_contract_terms(content)
                    
                    if extraction_result["status"] == "success":
                        contract_data["contracts_found"] += 1
                        
                        extracted = {
                            "document_id": doc.get("id"),
                            "title": doc.get("title"),
                            "ollama_extraction": extraction_result["contract_data"],
                            "confidence": extraction_result.get("extraction_confidence", 0.0),
                            "model_info": extraction_result["model_info"]
                        }
                        
                        contract_data["extracted_data"].append(extracted)
                        logger.info(f"✅ Contract data extracted with {extraction_result.get('extraction_confidence', 0)}% confidence")
                    
                    elif extraction_result["status"] == "partial":
                        # Handle partial extraction
                        extracted = {
                            "document_id": doc.get("id"),
                            "title": doc.get("title"),
                            "raw_analysis": extraction_result["raw_extraction"],
                            "status": "partial_extraction",
                            "model_info": extraction_result["model_info"]
                        }
                        
                        contract_data["extracted_data"].append(extracted)
                        logger.warning(f"⚠️ Partial contract extraction for document {doc.get('id')}")
            
            return contract_data
            
        except Exception as e:
            logger.error(f"❌ Contract data extraction failed: {e}")
            return {"error": str(e), "processing_method": "failed"}
    
    async def analyze_financial_document(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """Analyze financial documents using Ollama AI"""
        try:
            documents = context.get("search_results", [])
            
            financial_analysis = {
                "financial_documents": 0,
                "detailed_analysis": [],
                "processing_method": "ollama_ai"
            }
            
            for doc in documents:
                content = doc.get("content", "")
                
                # Use AI to analyze financial content
                if len(content) > 50:  # Only process substantial content
                    logger.info(f"💰 Processing document {doc.get('id')} with Ollama for financial analysis")
                    
                    analysis_result = await elysia_ollama.analyze_financial_metrics(content)
                    
                    if analysis_result["status"] == "success":
                        financial_analysis["financial_documents"] += 1
                        
                        analyzed = {
                            "document_id": doc.get("id"),
                            "title": doc.get("title"),
                            "financial_analysis": analysis_result["financial_analysis"],
                            "confidence": analysis_result.get("analysis_confidence", 0.0),
                            "model_info": analysis_result["model_info"]
                        }
                        
                        financial_analysis["detailed_analysis"].append(analyzed)
                        logger.info(f"✅ Financial analysis completed with {analysis_result.get('analysis_confidence', 0)}% confidence")
                    
                    elif analysis_result["status"] == "partial":
                        # Handle partial analysis
                        analyzed = {
                            "document_id": doc.get("id"),
                            "title": doc.get("title"),
                            "raw_analysis": analysis_result["raw_analysis"],
                            "status": "partial_analysis",
                            "model_info": analysis_result["model_info"]
                        }
                        
                        financial_analysis["detailed_analysis"].append(analyzed)
                        logger.warning(f"⚠️ Partial financial analysis for document {doc.get('id')}")
            
            return financial_analysis
            
        except Exception as e:
            logger.error(f"❌ Financial analysis failed: {e}")
            return {"error": str(e), "processing_method": "failed"}
    
    async def check_compliance(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """Check documents for compliance issues"""
        try:
            documents = context.get("search_results", [])
            
            compliance_check = {
                "total_documents": len(documents),
                "compliance_score": 0.0,
                "issues_found": [],
                "recommendations": []
            }
            
            total_score = 0
            
            for doc in documents:
                content = doc.get("content", "").lower()
                doc_score = 100  # Start with perfect score
                
                # Check for potential compliance issues
                risk_keywords = ["unauthorized", "violation", "breach", "illegal", "non-compliant"]
                issues_in_doc = [keyword for keyword in risk_keywords if keyword in content]
                
                if issues_in_doc:
                    doc_score -= len(issues_in_doc) * 20
                    compliance_check["issues_found"].extend([
                        f"Document {doc.get('id')}: Contains '{issue}'"
                        for issue in issues_in_doc
                    ])
                
                # Check for positive compliance indicators
                positive_keywords = ["compliant", "authorized", "approved", "certified"]
                if any(keyword in content for keyword in positive_keywords):
                    doc_score += 10
                
                total_score += max(0, doc_score)
            
            compliance_check["compliance_score"] = total_score / len(documents) if documents else 0
            
            # Generate recommendations
            if compliance_check["compliance_score"] < 80:
                compliance_check["recommendations"].append("Review flagged documents for compliance issues")
            if compliance_check["issues_found"]:
                compliance_check["recommendations"].append("Address identified compliance violations")
            
            return compliance_check
            
        except Exception as e:
            logger.error(f"❌ Compliance check failed: {e}")
            return {"error": str(e)}
    
    async def smart_summarize(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """Create intelligent summaries using Ollama AI"""
        try:
            documents = context.get("search_results", [])
            
            summaries = {
                "document_summaries": [],
                "processing_method": "ollama_ai"
            }
            
            for doc in documents:
                content = doc.get("content", "")
                doc_type = doc.get("document_type", "general")
                
                # Use AI for intelligent, type-aware summarization
                if len(content) > 50:  # Only process substantial content
                    logger.info(f"📝 Processing document {doc.get('id')} with Ollama for smart summarization")
                    
                    summary_result = await elysia_ollama.generate_smart_summary(
                        content, 
                        doc_type, 
                        summary_length="medium"
                    )
                    
                    if summary_result["status"] == "success":
                        summary_data = {
                            "document_id": doc.get("id"),
                            "title": doc.get("title"),
                            "document_type": doc_type,
                            "ai_summary": summary_result["summary"],
                            "summary_type": summary_result["summary_type"],
                            "summary_length": summary_result["summary_length"],
                            "original_length": summary_result["original_length"],
                            "compression_ratio": summary_result["compression_ratio"],
                            "model_info": summary_result["model_info"]
                        }
                        
                        summaries["document_summaries"].append(summary_data)
                        logger.info(f"✅ Smart summary generated (compression: {summary_result['compression_ratio']:.1f}x)")
                    
                    else:
                        # Handle failed summarization
                        summary_data = {
                            "document_id": doc.get("id"),
                            "title": doc.get("title"),
                            "document_type": doc_type,
                            "error": summary_result.get("error", "Unknown error"),
                            "status": "failed"
                        }
                        
                        summaries["document_summaries"].append(summary_data)
                        logger.warning(f"⚠️ Summarization failed for document {doc.get('id')}")
            
            return summaries
            
        except Exception as e:
            logger.error(f"❌ Smart summarization failed: {e}")
            return {"error": str(e), "processing_method": "failed"}
    
    
    async def link_entities(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """Link entities across documents"""
        try:
            documents = context.get("search_results", [])
            
            entity_links = {
                "entities_found": {},
                "cross_document_links": [],
                "entity_network": {}
            }
            
            # Extract entities from each document
            for doc in documents:
                content = doc.get("content", "")
                entities = self._extract_entities_simple(content)
                
                doc_id = doc.get("id", "unknown")
                entity_links["entities_found"][doc_id] = entities
                
                # Build entity network
                for entity in entities:
                    if entity not in entity_links["entity_network"]:
                        entity_links["entity_network"][entity] = []
                    entity_links["entity_network"][entity].append(doc_id)
            
            # Find cross-document links
            for entity, docs in entity_links["entity_network"].items():
                if len(docs) > 1:
                    entity_links["cross_document_links"].append({
                        "entity": entity,
                        "documents": docs,
                        "link_strength": len(docs)
                    })
            
            return entity_links
            
        except Exception as e:
            logger.error(f"❌ Entity linking failed: {e}")
            return {"error": str(e)}
    
    def _extract_entities_simple(self, content: str) -> List[str]:
        """Simple entity extraction"""
        # Look for capitalized words that might be entities
        import re
        words = re.findall(r'\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*\b', content)
        
        # Filter out common words
        stop_words = {"The", "This", "That", "These", "Those", "And", "Or", "But"}
        entities = [word for word in words if word not in stop_words and len(word) > 2]
        
        # Return unique entities
        return list(set(entities))
    
    async def assess_risks(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """Assess risks using Ollama AI analysis"""
        try:
            documents = context.get("search_results", [])
            query = context.get("query", "")
            
            # If no documents but query mentions risks, provide general risk analysis
            if not documents and any(word in query.lower() for word in ["riesgos", "risk", "risks"]):
                logger.info("🧠 No documents found - generating general risk knowledge response")
                
                # Use Ollama to generate general risk knowledge
                risk_result = await elysia_ollama.generate_general_risk_knowledge(query)
                
                if risk_result and risk_result.get("status") == "success":
                    response_data = {
                        "answer": risk_result["response"],
                        "confidence_score": 0.8,
                        "data": {
                            "risk_categories": risk_result.get("risk_categories", []),
                            "recommendations": risk_result.get("recommendations", [])
                        },
                        "processing_method": "general_knowledge_ai"
                    }
                    logger.info(f"🔥 RISK_ASSESSOR RESPONSE: answer={response_data['answer'][:100]}..., confidence={response_data['confidence_score']}")
                    return response_data
            
            risk_assessment = {
                "total_documents": len(documents),
                "overall_risk_level": "LOW",
                "detailed_assessments": [],
                "processing_method": "document_analysis_ai"
            }
            
            high_risk_count = 0
            medium_risk_count = 0
            
            for doc in documents:
                content = doc.get("content", "")
                doc_type = doc.get("document_type", "general")
                
                # Use AI for intelligent risk assessment
                if len(content) > 50:  # Only process substantial content
                    logger.info(f"⚠️ Processing document {doc.get('id')} with Ollama for risk assessment")
                    
                    risk_result = await elysia_ollama.assess_document_risks(content, doc_type)
                    
                    if risk_result["status"] == "success":
                        assessment = {
                            "document_id": doc.get("id"),
                            "title": doc.get("title"),
                            "document_type": doc_type,
                            "risk_assessment": risk_result["risk_assessment"],
                            "assessment_timestamp": risk_result["assessment_timestamp"],
                            "model_info": risk_result["model_info"]
                        }
                        
                        risk_assessment["detailed_assessments"].append(assessment)
                        
                        # Count risk levels for overall assessment
                        doc_risk_level = risk_result["risk_assessment"].get("risk_level", "low").upper()
                        if doc_risk_level == "HIGH" or doc_risk_level == "CRITICAL":
                            high_risk_count += 1
                        elif doc_risk_level == "MEDIUM":
                            medium_risk_count += 1
                        
                        logger.info(f"✅ Risk assessment completed - Level: {doc_risk_level}")
                    
                    elif risk_result["status"] == "partial":
                        # Handle partial assessment
                        assessment = {
                            "document_id": doc.get("id"),
                            "title": doc.get("title"),
                            "document_type": doc_type,
                            "raw_assessment": risk_result["raw_assessment"],
                            "status": "partial_assessment",
                            "model_info": risk_result["model_info"]
                        }
                        
                        risk_assessment["detailed_assessments"].append(assessment)
                        logger.warning(f"⚠️ Partial risk assessment for document {doc.get('id')}")
            
            # Determine overall risk level
            total_docs = len(risk_assessment["detailed_assessments"])
            if total_docs == 0:
                risk_assessment["overall_risk_level"] = "UNKNOWN"
            elif high_risk_count > 0:
                risk_assessment["overall_risk_level"] = "HIGH"
            elif medium_risk_count > total_docs * 0.3:  # More than 30% medium risk
                risk_assessment["overall_risk_level"] = "MEDIUM"
            else:
                risk_assessment["overall_risk_level"] = "LOW"
            
            return risk_assessment
            
        except Exception as e:
            logger.error(f"❌ Risk assessment failed: {e}")
            return {"error": str(e), "processing_method": "failed"}
    
    async def find_similar_documents(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """Find similar documents using advanced vector matching"""
        try:
            query = context.get("query", "")
            tenant_id = context.get("tenant_id", "")
            
            if not query or not tenant_id:
                return {"error": "Query and tenant_id required for similarity search"}
            
            # Use Weaviate service for advanced similarity search
            from app.schemas.weaviate import SearchRequest
            
            search_request = SearchRequest(
                query=query,
                tenant_id=tenant_id,
                search_type="vector",  # Pure vector similarity
                limit=20,
                min_similarity=0.7
            )
            
            collection_name = f"nexus_{tenant_id}_documents".lower().replace("-", "_")
            results = await weaviate_service.search_documents(collection_name, search_request)
            
            similarity_analysis = {
                "query": query,
                "similar_documents": len(results.results),
                "search_time_ms": results.search_time_ms,
                "documents": [
                    {
                        "id": doc.id,
                        "title": doc.title,
                        "similarity_score": doc.similarity_score,
                        "document_type": doc.document_type
                    }
                    for doc in results.results
                ]
            }
            
            return similarity_analysis
            
        except Exception as e:
            logger.error(f"❌ Similarity search failed: {e}")
            return {"error": str(e)}
    
    async def analyze_trends(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """Analyze trends across document collections"""
        try:
            documents = context.get("search_results", [])
            
            trend_analysis = {
                "total_documents": len(documents),
                "temporal_trends": {},
                "content_trends": {},
                "type_distribution": {}
            }
            
            # Analyze document types
            for doc in documents:
                doc_type = doc.get("document_type", "unknown")
                trend_analysis["type_distribution"][doc_type] = trend_analysis["type_distribution"].get(doc_type, 0) + 1
            
            # Analyze content trends (simplified)
            all_content = " ".join([doc.get("content", "") for doc in documents])
            trend_keywords = ["increase", "decrease", "growth", "decline", "trend", "change"]
            
            for keyword in trend_keywords:
                count = all_content.lower().count(keyword)
                if count > 0:
                    trend_analysis["content_trends"][keyword] = count
            
            return trend_analysis
            
        except Exception as e:
            logger.error(f"❌ Trend analysis failed: {e}")
            return {"error": str(e)}
    
    async def process_multilingual(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """Process multi-language documents"""
        try:
            documents = context.get("search_results", [])
            
            multilingual_analysis = {
                "total_documents": len(documents),
                "languages_detected": {},
                "translation_needed": [],
                "language_distribution": {}
            }
            
            for doc in documents:
                content = doc.get("content", "")
                
                # Simple language detection (placeholder)
                detected_lang = self._detect_language_simple(content)
                
                multilingual_analysis["languages_detected"][doc.get("id", "unknown")] = detected_lang
                
                if detected_lang != "english":
                    multilingual_analysis["translation_needed"].append({
                        "document_id": doc.get("id"),
                        "detected_language": detected_lang,
                        "title": doc.get("title")
                    })
                
                multilingual_analysis["language_distribution"][detected_lang] = multilingual_analysis["language_distribution"].get(detected_lang, 0) + 1
            
            return multilingual_analysis
            
        except Exception as e:
            logger.error(f"❌ Multilingual processing failed: {e}")
            return {"error": str(e)}
    
    def _detect_language_simple(self, content: str) -> str:
        """Simple language detection"""
        # Simplified detection based on common words
        spanish_indicators = ["el", "la", "de", "que", "y", "es", "en", "un", "se", "no"]
        french_indicators = ["le", "de", "et", "à", "un", "il", "être", "et", "en", "avoir"]
        german_indicators = ["der", "die", "und", "in", "den", "von", "zu", "das", "mit", "sich"]
        
        content_lower = content.lower()
        
        spanish_count = sum(1 for word in spanish_indicators if word in content_lower)
        french_count = sum(1 for word in french_indicators if word in content_lower)
        german_count = sum(1 for word in german_indicators if word in content_lower)
        
        if spanish_count > 5:
            return "spanish"
        elif french_count > 5:
            return "french"
        elif german_count > 5:
            return "german"
        else:
            return "english"
    
    async def search_web(self, query: str, max_results: int = 5) -> Dict[str, Any]:
        """Search the web for current information"""
        try:
            import httpx
            from bs4 import BeautifulSoup
            import re
            
            logger.info(f"🔍 Performing web search for: {query}")
            
            # Use DuckDuckGo instant answer API (no API key required)
            search_url = "https://api.duckduckgo.com/"
            params = {
                "q": query,
                "format": "json",
                "no_redirect": "1",
                "no_html": "1",
                "skip_disambig": "1"
            }
            
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(search_url, params=params)
                
                if response.status_code == 200:
                    data = response.json()
                    
                    result = {
                        "query": query,
                        "timestamp": datetime.now().isoformat(),
                        "source": "DuckDuckGo",
                        "instant_answer": data.get("Answer", ""),
                        "abstract": data.get("Abstract", ""),
                        "definition": data.get("Definition", ""),
                        "related_topics": [topic.get("Text", "") for topic in data.get("RelatedTopics", [])[:3]]
                    }
                    
                    # If we got useful information, return it
                    if result["instant_answer"] or result["abstract"] or result["definition"]:
                        logger.info(f"✅ Web search successful for: {query}")
                        return result
                    else:
                        return {
                            "query": query,
                            "error": "No instant results found",
                            "suggestion": "Try a more specific search query"
                        }
                else:
                    return {
                        "query": query,
                        "error": f"Search service unavailable (HTTP {response.status_code})"
                    }
                    
        except Exception as e:
            logger.error(f"❌ Web search failed: {e}")
            return {
                "query": query,
                "error": f"Search failed: {str(e)}"
            }
    
    async def get_weather_info(self, location: str) -> Dict[str, Any]:
        """Get current weather information for a location"""
        try:
            import httpx
            
            logger.info(f"🌤️ Getting weather info for: {location}")
            
            # Use OpenWeatherMap-like free service (wttr.in)
            weather_url = f"https://wttr.in/{location}?format=j1"
            
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(weather_url)
                
                if response.status_code == 200:
                    data = response.json()
                    current = data.get("current_condition", [{}])[0]
                    
                    weather_info = {
                        "location": location,
                        "timestamp": datetime.now().isoformat(),
                        "temperature": f"{current.get('temp_C', 'N/A')}°C",
                        "feels_like": f"{current.get('FeelsLikeC', 'N/A')}°C",
                        "condition": current.get('weatherDesc', [{}])[0].get('value', 'Unknown'),
                        "humidity": f"{current.get('humidity', 'N/A')}%",
                        "wind": f"{current.get('windspeedKmph', 'N/A')} km/h {current.get('winddir16Point', '')}",
                        "visibility": f"{current.get('visibility', 'N/A')} km",
                        "uv_index": current.get('uvIndex', 'N/A'),
                        "source": "wttr.in"
                    }
                    
                    logger.info(f"✅ Weather info retrieved for: {location}")
                    return weather_info
                else:
                    return {
                        "location": location,
                        "error": f"Weather service unavailable (HTTP {response.status_code})",
                        "suggestion": "Try with a more specific location (city, country)"
                    }
                    
        except Exception as e:
            logger.error(f"❌ Weather info failed: {e}")
            return {
                "location": location,
                "error": f"Weather request failed: {str(e)}"
            }


# Global tools instance
nexus_elysia_tools = NexusElysiaTools()