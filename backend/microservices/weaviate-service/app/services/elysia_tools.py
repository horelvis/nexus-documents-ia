"""Advanced Elysia tools for NexusDocs360 specific operations
All LLM operations route through CAG/Elysia service."""
import logging
from typing import Dict, Any, List, Optional
from datetime import datetime

from app.core.config import settings
from app.services.weaviate_service import weaviate_service

logger = logging.getLogger(__name__)


class NexusElysiaTools:
    """NexusDocs360-specific tools for Elysia decision trees.
    All LLM operations use CAG service."""

    def __init__(self):
        self.tools_registry = {}
        self._cag_service = None
        self._register_all_tools()

    async def _get_cag_service(self):
        """Lazy load CAG service to avoid circular imports"""
        if self._cag_service is None:
            from app.cag.services.cag_service import cag_service
            self._cag_service = cag_service
        return self._cag_service

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
            },
            "public_knowledge_search": {
                "name": "Public Knowledge Search",
                "description": "Searches public legal knowledge base (legislation, regulations, jurisprudence, templates)",
                "function": self.search_public_knowledge,
                "category": "search"
            },
            "legal_reference_lookup": {
                "name": "Legal Reference Lookup",
                "description": "Looks up specific legal references (BOE, EUR-Lex, etc.) in the public knowledge base",
                "function": self.lookup_legal_reference,
                "category": "search"
            }
        }

        logger.info(f"✅ Registered {len(self.tools_registry)} NexusDocs360 tools (CAG-based)")

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
    # TOOL IMPLEMENTATIONS (CAG-based)
    # ================================

    async def analyze_document_structure(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """Analyze document structure using CAG/Elysia"""
        try:
            documents = context.get("search_results", [])
            tenant_id = context.get("tenant_id", "default")
            user_id = context.get("user_id", "system")

            if not documents:
                return {"analysis": "No documents provided for analysis"}

            cag = await self._get_cag_service()
            analysis = {
                "total_documents": len(documents),
                "ai_structure_analysis": [],
                "processing_method": "cag_elysia"
            }

            for doc in documents:
                content = doc.get("content", "")

                if len(content) > 50:
                    logger.info(f"🔍 Analyzing document {doc.get('id')} via CAG")

                    result = await cag.analyze_document(
                        document_content=content,
                        document_id=doc.get("id", "unknown"),
                        tenant_id=tenant_id,
                        user_id=user_id,
                        analysis_type="structure"
                    )

                    analysis["ai_structure_analysis"].append({
                        "document_id": doc.get("id"),
                        "title": doc.get("title"),
                        "ai_analysis": result.get("analysis", ""),
                        "confidence": result.get("confidence", 0)
                    })

            return analysis

        except Exception as e:
            logger.error(f"❌ Document structure analysis failed: {e}")
            return {"error": str(e), "processing_method": "failed"}

    async def extract_contract_data(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """Extract key contract information using CAG/Elysia"""
        try:
            documents = context.get("search_results", [])
            tenant_id = context.get("tenant_id", "default")
            user_id = context.get("user_id", "system")

            cag = await self._get_cag_service()
            contract_data = {
                "contracts_found": 0,
                "extracted_data": [],
                "processing_method": "cag_elysia"
            }

            for doc in documents:
                content = doc.get("content", "")

                if len(content) > 50:
                    logger.info(f"🔍 Extracting contract data from {doc.get('id')} via CAG")

                    result = await cag.analyze_document(
                        document_content=content,
                        document_id=doc.get("id", "unknown"),
                        tenant_id=tenant_id,
                        user_id=user_id,
                        analysis_type="contract"
                    )

                    if result.get("success"):
                        contract_data["contracts_found"] += 1
                        contract_data["extracted_data"].append({
                            "document_id": doc.get("id"),
                            "title": doc.get("title"),
                            "extraction": result.get("analysis", ""),
                            "confidence": result.get("confidence", 0)
                        })

            return contract_data

        except Exception as e:
            logger.error(f"❌ Contract data extraction failed: {e}")
            return {"error": str(e), "processing_method": "failed"}

    async def analyze_financial_document(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """Analyze financial documents using CAG/Elysia"""
        try:
            documents = context.get("search_results", [])
            tenant_id = context.get("tenant_id", "default")
            user_id = context.get("user_id", "system")

            cag = await self._get_cag_service()
            financial_analysis = {
                "financial_documents": 0,
                "detailed_analysis": [],
                "processing_method": "cag_elysia"
            }

            for doc in documents:
                content = doc.get("content", "")

                if len(content) > 50:
                    logger.info(f"💰 Analyzing financial doc {doc.get('id')} via CAG")

                    result = await cag.analyze_document(
                        document_content=content,
                        document_id=doc.get("id", "unknown"),
                        tenant_id=tenant_id,
                        user_id=user_id,
                        analysis_type="financial"
                    )

                    if result.get("success"):
                        financial_analysis["financial_documents"] += 1
                        financial_analysis["detailed_analysis"].append({
                            "document_id": doc.get("id"),
                            "title": doc.get("title"),
                            "financial_analysis": result.get("analysis", ""),
                            "confidence": result.get("confidence", 0)
                        })

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
                doc_score = 100

                risk_keywords = ["unauthorized", "violation", "breach", "illegal", "non-compliant"]
                issues_in_doc = [keyword for keyword in risk_keywords if keyword in content]

                if issues_in_doc:
                    doc_score -= len(issues_in_doc) * 20
                    compliance_check["issues_found"].extend([
                        f"Document {doc.get('id')}: Contains '{issue}'"
                        for issue in issues_in_doc
                    ])

                positive_keywords = ["compliant", "authorized", "approved", "certified"]
                if any(keyword in content for keyword in positive_keywords):
                    doc_score += 10

                total_score += max(0, doc_score)

            compliance_check["compliance_score"] = total_score / len(documents) if documents else 0

            if compliance_check["compliance_score"] < 80:
                compliance_check["recommendations"].append("Review flagged documents for compliance issues")
            if compliance_check["issues_found"]:
                compliance_check["recommendations"].append("Address identified compliance violations")

            return compliance_check

        except Exception as e:
            logger.error(f"❌ Compliance check failed: {e}")
            return {"error": str(e)}

    async def smart_summarize(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """Create intelligent summaries using CAG/Elysia"""
        try:
            documents = context.get("search_results", [])
            tenant_id = context.get("tenant_id", "default")
            user_id = context.get("user_id", "system")

            cag = await self._get_cag_service()
            summaries = {
                "document_summaries": [],
                "processing_method": "cag_elysia"
            }

            for doc in documents:
                content = doc.get("content", "")
                doc_type = doc.get("document_type", "general")

                if len(content) > 50:
                    logger.info(f"📝 Summarizing {doc.get('id')} via CAG")

                    result = await cag.analyze_document(
                        document_content=content,
                        document_id=doc.get("id", "unknown"),
                        tenant_id=tenant_id,
                        user_id=user_id,
                        analysis_type="summary"
                    )

                    summaries["document_summaries"].append({
                        "document_id": doc.get("id"),
                        "title": doc.get("title"),
                        "document_type": doc_type,
                        "ai_summary": result.get("analysis", ""),
                        "confidence": result.get("confidence", 0)
                    })

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

            for doc in documents:
                content = doc.get("content", "")
                entities = self._extract_entities_simple(content)

                doc_id = doc.get("id", "unknown")
                entity_links["entities_found"][doc_id] = entities

                for entity in entities:
                    if entity not in entity_links["entity_network"]:
                        entity_links["entity_network"][entity] = []
                    entity_links["entity_network"][entity].append(doc_id)

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
        import re
        words = re.findall(r'\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*\b', content)
        stop_words = {"The", "This", "That", "These", "Those", "And", "Or", "But"}
        entities = [word for word in words if word not in stop_words and len(word) > 2]
        return list(set(entities))

    async def assess_risks(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """Assess risks using CAG/Elysia"""
        try:
            documents = context.get("search_results", [])
            query = context.get("query", "")
            tenant_id = context.get("tenant_id", "default")
            user_id = context.get("user_id", "system")

            cag = await self._get_cag_service()

            # If no documents but query mentions risks, use CAG for general query
            if not documents and any(word in query.lower() for word in ["riesgos", "risk", "risks"]):
                logger.info("🧠 No documents - using CAG for risk query")

                result = await cag.process_query(
                    query=query,
                    tenant_id=tenant_id,
                    user_id=user_id
                )

                return {
                    "answer": result.get("answer", ""),
                    "confidence_score": result.get("quality_score", 0),
                    "processing_method": "cag_query"
                }

            risk_assessment = {
                "total_documents": len(documents),
                "overall_risk_level": "LOW",
                "detailed_assessments": [],
                "processing_method": "cag_elysia"
            }

            high_risk_count = 0
            medium_risk_count = 0

            for doc in documents:
                content = doc.get("content", "")
                doc_type = doc.get("document_type", "general")

                if len(content) > 50:
                    logger.info(f"⚠️ Assessing risks in {doc.get('id')} via CAG")

                    result = await cag.analyze_document(
                        document_content=content,
                        document_id=doc.get("id", "unknown"),
                        tenant_id=tenant_id,
                        user_id=user_id,
                        analysis_type="risk"
                    )

                    assessment = {
                        "document_id": doc.get("id"),
                        "title": doc.get("title"),
                        "document_type": doc_type,
                        "risk_assessment": result.get("analysis", ""),
                        "confidence": result.get("confidence", 0)
                    }

                    risk_assessment["detailed_assessments"].append(assessment)

            total_docs = len(risk_assessment["detailed_assessments"])
            if total_docs == 0:
                risk_assessment["overall_risk_level"] = "UNKNOWN"
            elif high_risk_count > 0:
                risk_assessment["overall_risk_level"] = "HIGH"
            elif medium_risk_count > total_docs * 0.3:
                risk_assessment["overall_risk_level"] = "MEDIUM"

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

            from app.schemas.weaviate import SearchRequest

            search_request = SearchRequest(
                query=query,
                tenant_id=tenant_id,
                search_type="vector",
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

            for doc in documents:
                doc_type = doc.get("document_type", "unknown")
                trend_analysis["type_distribution"][doc_type] = trend_analysis["type_distribution"].get(doc_type, 0) + 1

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

            logger.info(f"🔍 Performing web search for: {query}")

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


    async def search_public_knowledge(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """Search the public legal knowledge base"""
        try:
            from app.services.public_knowledge_service import public_knowledge_service
            from app.schemas.public_knowledge import PublicSearchRequest, PublicDocumentCategory, Jurisdiction

            query = context.get("query", "")
            if not query:
                return {"error": "Query is required for public knowledge search"}

            # Extract categories from context if provided
            categories = None
            if context.get("categories"):
                try:
                    categories = [PublicDocumentCategory(c) for c in context["categories"]]
                except:
                    pass

            # Extract jurisdictions from context if provided
            jurisdictions = None
            if context.get("jurisdictions"):
                try:
                    jurisdictions = [Jurisdiction(j) for j in context["jurisdictions"]]
                except:
                    pass

            # Detect if query is about Spanish law
            spanish_keywords = ["españa", "español", "boe", "ley orgánica", "real decreto"]
            eu_keywords = ["europea", "ue", "directiva", "reglamento europeo", "rgpd", "gdpr"]

            query_lower = query.lower()
            if not jurisdictions:
                if any(kw in query_lower for kw in spanish_keywords):
                    jurisdictions = [Jurisdiction.SPAIN]
                elif any(kw in query_lower for kw in eu_keywords):
                    jurisdictions = [Jurisdiction.EUROPEAN_UNION]

            search_request = PublicSearchRequest(
                query=query,
                limit=context.get("limit", 10),
                categories=categories,
                jurisdictions=jurisdictions,
                verified_only=context.get("verified_only", False),
                search_type=context.get("search_type", "hybrid")
            )

            logger.info(f"📚 Searching public knowledge base: {query}")
            response = await public_knowledge_service.search(search_request)

            result = {
                "query": query,
                "total_results": response.total_results,
                "search_time_ms": response.search_time_ms,
                "source": "public_knowledge_base",
                "results": []
            }

            for doc in response.results:
                result["results"].append({
                    "id": doc.id,
                    "title": doc.title,
                    "summary": doc.summary,
                    "category": doc.category,
                    "jurisdiction": doc.jurisdiction,
                    "legal_reference": doc.legal_reference,
                    "source_name": doc.source_name,
                    "verified": doc.verified,
                    "similarity_score": doc.similarity_score,
                    "content_preview": doc.content[:500] if doc.content else ""
                })

            logger.info(f"✅ Found {response.total_results} public documents for: {query}")
            return result

        except Exception as e:
            logger.error(f"❌ Public knowledge search failed: {e}")
            return {"error": str(e), "query": context.get("query", "")}

    async def lookup_legal_reference(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """Look up a specific legal reference in the public knowledge base"""
        try:
            from app.services.public_knowledge_service import public_knowledge_service
            from app.schemas.public_knowledge import PublicSearchRequest

            reference = context.get("reference", "") or context.get("query", "")
            if not reference:
                return {"error": "Legal reference is required"}

            # Search by legal reference
            search_request = PublicSearchRequest(
                query=reference,
                limit=5,
                search_type="keyword",
                verified_only=True
            )

            logger.info(f"📖 Looking up legal reference: {reference}")
            response = await public_knowledge_service.search(search_request)

            if response.results:
                # Return the most relevant document
                doc = response.results[0]
                return {
                    "reference": reference,
                    "found": True,
                    "document": {
                        "id": doc.id,
                        "title": doc.title,
                        "summary": doc.summary,
                        "category": doc.category,
                        "jurisdiction": doc.jurisdiction,
                        "legal_reference": doc.legal_reference,
                        "publication_date": doc.publication_date.isoformat() if doc.publication_date else None,
                        "effective_date": doc.effective_date.isoformat() if doc.effective_date else None,
                        "source_url": doc.source_url,
                        "source_name": doc.source_name,
                        "verified": doc.verified,
                        "content": doc.content
                    },
                    "related_documents": [
                        {"id": d.id, "title": d.title, "legal_reference": d.legal_reference}
                        for d in response.results[1:5]
                    ]
                }
            else:
                return {
                    "reference": reference,
                    "found": False,
                    "message": f"No document found for reference: {reference}",
                    "suggestion": "Try a broader search or verify the reference format"
                }

        except Exception as e:
            logger.error(f"❌ Legal reference lookup failed: {e}")
            return {"error": str(e), "reference": context.get("reference", "")}


# Global tools instance
nexus_elysia_tools = NexusElysiaTools()
