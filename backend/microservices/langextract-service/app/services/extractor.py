"""
LangExtract Document Extraction Service
"""
import langextract as lx
from typing import Dict, Any, List, Optional
from loguru import logger
import json
from ..core.config import settings


class DocumentExtractor:
    """Service for extracting structured information from documents using LangExtract"""
    
    def __init__(self):
        self.provider = settings.default_provider
        self.extraction_configs = self._load_extraction_configs()
        
    def _load_extraction_configs(self) -> Dict[str, Dict]:
        """Load extraction configurations for different document types"""
        return {
            "contract": {
                "prompt": """Extract the following information from this contract:
                - Parties involved (names and roles)
                - Contract type and purpose
                - Key dates (effective date, expiration, deadlines)
                - Payment terms and amounts
                - Obligations and deliverables
                - Termination clauses
                - Governing law and jurisdiction
                - Signatures and execution details
                
                Use exact text from the document. Map each extraction to its source.""",
                
                "examples": [
                    lx.data.ExampleData(
                        text="This Service Agreement ('Agreement') is entered into as of January 1, 2025, between TechCorp Inc. ('Service Provider') and ClientCo Ltd. ('Client').",
                        extractions=[
                            lx.data.Extraction(
                                extraction_class="party",
                                extraction_text="TechCorp Inc.",
                                attributes={"role": "Service Provider", "type": "company"}
                            ),
                            lx.data.Extraction(
                                extraction_class="party",
                                extraction_text="ClientCo Ltd.",
                                attributes={"role": "Client", "type": "company"}
                            ),
                            lx.data.Extraction(
                                extraction_class="contract_type",
                                extraction_text="Service Agreement",
                                attributes={"category": "services"}
                            ),
                            lx.data.Extraction(
                                extraction_class="date",
                                extraction_text="January 1, 2025",
                                attributes={"type": "effective_date"}
                            )
                        ]
                    )
                ]
            },
            
            "invoice": {
                "prompt": """Extract the following information from this invoice:
                - Invoice number and date
                - Vendor/seller information
                - Customer/buyer information
                - Line items with descriptions and amounts
                - Subtotal, tax, and total amounts
                - Payment terms and due date
                - Bank/payment details
                
                Extract exact amounts and details as they appear.""",
                
                "examples": [
                    lx.data.ExampleData(
                        text="Invoice #2025-001\nDate: March 15, 2025\nBill To: ABC Company\nTotal: $5,000.00\nDue: April 15, 2025",
                        extractions=[
                            lx.data.Extraction(
                                extraction_class="invoice_number",
                                extraction_text="2025-001",
                                attributes={"format": "year-sequential"}
                            ),
                            lx.data.Extraction(
                                extraction_class="date",
                                extraction_text="March 15, 2025",
                                attributes={"type": "invoice_date"}
                            ),
                            lx.data.Extraction(
                                extraction_class="customer",
                                extraction_text="ABC Company",
                                attributes={"role": "buyer"}
                            ),
                            lx.data.Extraction(
                                extraction_class="amount",
                                extraction_text="$5,000.00",
                                attributes={"type": "total", "currency": "USD"}
                            ),
                            lx.data.Extraction(
                                extraction_class="date",
                                extraction_text="April 15, 2025",
                                attributes={"type": "due_date"}
                            )
                        ]
                    )
                ]
            },
            
            "report": {
                "prompt": """Extract the following information from this report:
                - Report title and type
                - Author(s) and organization
                - Date of publication
                - Executive summary or abstract
                - Key findings and conclusions
                - Recommendations
                - Data points and statistics
                - References to other documents
                
                Maintain the context and relationships between extracted elements.""",
                
                "examples": [
                    lx.data.ExampleData(
                        text="Annual Financial Report 2025\nPrepared by: Finance Department\nKey Finding: Revenue increased by 25% year-over-year",
                        extractions=[
                            lx.data.Extraction(
                                extraction_class="title",
                                extraction_text="Annual Financial Report 2025",
                                attributes={"type": "financial", "period": "annual"}
                            ),
                            lx.data.Extraction(
                                extraction_class="author",
                                extraction_text="Finance Department",
                                attributes={"type": "department"}
                            ),
                            lx.data.Extraction(
                                extraction_class="finding",
                                extraction_text="Revenue increased by 25% year-over-year",
                                attributes={"category": "financial", "metric": "revenue", "change": "+25%"}
                            )
                        ]
                    )
                ]
            },
            
            "general": {
                "prompt": """Extract key information from this document:
                - Main topics and themes
                - Important entities (people, organizations, places)
                - Dates and time references
                - Numerical values and amounts
                - Key facts and statements
                - Actions and obligations
                
                Preserve the original text and context.""",
                
                "examples": [
                    lx.data.ExampleData(
                        text="The meeting will be held on July 10, 2025 at the headquarters of Global Corp.",
                        extractions=[
                            lx.data.Extraction(
                                extraction_class="event",
                                extraction_text="meeting",
                                attributes={"type": "business"}
                            ),
                            lx.data.Extraction(
                                extraction_class="date",
                                extraction_text="July 10, 2025",
                                attributes={"type": "event_date"}
                            ),
                            lx.data.Extraction(
                                extraction_class="organization",
                                extraction_text="Global Corp",
                                attributes={"role": "host"}
                            ),
                            lx.data.Extraction(
                                extraction_class="location",
                                extraction_text="headquarters",
                                attributes={"type": "business_location"}
                            )
                        ]
                    )
                ]
            }
        }
    
    async def extract(
        self, 
        text: str, 
        document_type: str = "general",
        filename: Optional[str] = None,
        provider: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Extract structured information from document text
        
        Args:
            text: Document text to analyze
            document_type: Type of document (contract, invoice, report, general)
            filename: Optional filename for context
            provider: Optional provider override (ollama, gemini, openai)
            
        Returns:
            Dictionary with extractions, entities, and metadata
        """
        try:
            # Get configuration for document type
            config = self.extraction_configs.get(
                document_type, 
                self.extraction_configs["general"]
            )
            
            # Select provider
            selected_provider = provider or self.provider
            
            # Select provider and configure extraction
            if selected_provider == "ollama":
                # Use Ollama language model class (not instance)
                language_model_type = lx.inference.OllamaLanguageModel
                model_kwargs = {
                    "model_id": settings.ollama_model,
                    "base_url": settings.ollama_host
                }
                logger.info(f"Using Ollama provider with model {settings.ollama_model}")
                
            elif selected_provider == "gemini" and settings.gemini_api_key:
                # Use Gemini language model class
                language_model_type = lx.inference.GeminiLanguageModel
                model_kwargs = {
                    "model": settings.gemini_model,
                    "api_key": settings.gemini_api_key
                }
                logger.info(f"Using Gemini provider with model {settings.gemini_model}")
                
            elif selected_provider == "openai" and settings.openai_api_key:
                # Use OpenAI language model class
                language_model_type = lx.inference.OpenAILanguageModel
                model_kwargs = {
                    "model": settings.openai_model,
                    "api_key": settings.openai_api_key
                }
                logger.info(f"Using OpenAI provider with model {settings.openai_model}")
                
            else:
                # Fallback to Ollama if no valid provider
                language_model_type = lx.inference.OllamaLanguageModel
                model_kwargs = {
                    "model_id": settings.ollama_model,
                    "base_url": settings.ollama_host
                }
                logger.warning(f"Provider {selected_provider} not available, using Ollama")
            
            # Perform extraction
            logger.info(f"Starting extraction for {document_type} document")
            result = lx.extract(
                text_or_documents=text,
                prompt_description=config["prompt"],
                examples=config["examples"],
                extraction_passes=settings.extraction_passes,
                max_char_buffer=settings.max_char_buffer,
                language_model_type=language_model_type,
                **model_kwargs
            )
            
            # Process and structure results
            structured_data = self._structure_results(result, document_type)
            
            # Add metadata
            structured_data["metadata"] = {
                "document_type": document_type,
                "filename": filename,
                "provider": selected_provider,
                "model": settings.ollama_model if selected_provider == "ollama" else settings.gemini_model if selected_provider == "gemini" else settings.openai_model,
                "extraction_passes": settings.extraction_passes,
                "total_extractions": len(result.extractions) if result.extractions else 0
            }
            
            # Generate visualization HTML if extractions exist
            if result.extractions:
                try:
                    structured_data["visualization_html"] = lx.visualize(result)
                    logger.info(f"Generated visualization for {len(result.extractions)} extractions")
                except Exception as e:
                    logger.warning(f"Could not generate visualization: {e}")
                    structured_data["visualization_html"] = None
            
            return structured_data
            
        except Exception as e:
            logger.error(f"Extraction failed: {e}")
            return {
                "success": False,
                "error": str(e),
                "document_type": document_type,
                "provider": selected_provider
            }
    
    def _structure_results(self, result: Any, document_type: str) -> Dict[str, Any]:
        """
        Structure extraction results into organized format
        
        Args:
            result: LangExtract result object
            document_type: Type of document
            
        Returns:
            Structured dictionary with categorized extractions
        """
        structured = {
            "success": True,
            "extractions": [],
            "entities": {},
            "summary": {}
        }
        
        if not result or not result.extractions:
            return structured
        
        # Convert extractions to dictionaries
        for extraction in result.extractions:
            ext_dict = {
                "class": extraction.extraction_class,
                "text": extraction.extraction_text,
                "attributes": extraction.attributes if hasattr(extraction, 'attributes') else {},
                "source_indices": extraction.source_indices if hasattr(extraction, 'source_indices') else None
            }
            structured["extractions"].append(ext_dict)
            
            # Group by class
            if extraction.extraction_class not in structured["entities"]:
                structured["entities"][extraction.extraction_class] = []
            structured["entities"][extraction.extraction_class].append(ext_dict)
        
        # Create summary based on document type
        if document_type == "contract":
            structured["summary"] = self._summarize_contract(structured["entities"])
        elif document_type == "invoice":
            structured["summary"] = self._summarize_invoice(structured["entities"])
        elif document_type == "report":
            structured["summary"] = self._summarize_report(structured["entities"])
        else:
            structured["summary"] = self._summarize_general(structured["entities"])
        
        return structured
    
    def _summarize_contract(self, entities: Dict) -> Dict:
        """Create contract summary from entities"""
        summary = {
            "parties": [],
            "dates": {},
            "amounts": [],
            "obligations": []
        }
        
        if "party" in entities:
            summary["parties"] = [e["text"] for e in entities["party"]]
        
        if "date" in entities:
            for date_ent in entities["date"]:
                date_type = date_ent.get("attributes", {}).get("type", "unknown")
                summary["dates"][date_type] = date_ent["text"]
        
        if "amount" in entities:
            summary["amounts"] = [e["text"] for e in entities["amount"]]
        
        if "obligation" in entities:
            summary["obligations"] = [e["text"] for e in entities["obligation"]]
        
        return summary
    
    def _summarize_invoice(self, entities: Dict) -> Dict:
        """Create invoice summary from entities"""
        summary = {
            "invoice_number": None,
            "dates": {},
            "customer": None,
            "total_amount": None,
            "line_items": []
        }
        
        if "invoice_number" in entities:
            summary["invoice_number"] = entities["invoice_number"][0]["text"]
        
        if "customer" in entities:
            summary["customer"] = entities["customer"][0]["text"]
        
        if "amount" in entities:
            for amount in entities["amount"]:
                if amount.get("attributes", {}).get("type") == "total":
                    summary["total_amount"] = amount["text"]
        
        if "date" in entities:
            for date_ent in entities["date"]:
                date_type = date_ent.get("attributes", {}).get("type", "unknown")
                summary["dates"][date_type] = date_ent["text"]
        
        return summary
    
    def _summarize_report(self, entities: Dict) -> Dict:
        """Create report summary from entities"""
        summary = {
            "title": None,
            "authors": [],
            "findings": [],
            "recommendations": []
        }
        
        if "title" in entities:
            summary["title"] = entities["title"][0]["text"]
        
        if "author" in entities:
            summary["authors"] = [e["text"] for e in entities["author"]]
        
        if "finding" in entities:
            summary["findings"] = [e["text"] for e in entities["finding"]]
        
        if "recommendation" in entities:
            summary["recommendations"] = [e["text"] for e in entities["recommendation"]]
        
        return summary
    
    def _summarize_general(self, entities: Dict) -> Dict:
        """Create general summary from entities"""
        summary = {
            "key_entities": [],
            "dates": [],
            "locations": [],
            "amounts": []
        }
        
        for class_name, items in entities.items():
            if class_name in ["organization", "person", "company"]:
                summary["key_entities"].extend([e["text"] for e in items])
            elif class_name == "date":
                summary["dates"].extend([e["text"] for e in items])
            elif class_name == "location":
                summary["locations"].extend([e["text"] for e in items])
            elif class_name == "amount":
                summary["amounts"].extend([e["text"] for e in items])
        
        return summary
    
    def get_extraction_stats(self) -> Dict[str, Any]:
        """Get statistics about extraction capabilities"""
        return {
            "supported_document_types": list(self.extraction_configs.keys()),
            "default_provider": settings.default_provider,
            "available_providers": self._get_available_providers(),
            "extraction_passes": settings.extraction_passes,
            "max_char_buffer": settings.max_char_buffer,
            "confidence_threshold": settings.confidence_threshold
        }
    
    def _get_available_providers(self) -> List[str]:
        """Get list of available providers based on configuration"""
        providers = ["ollama"]  # Always available
        
        if settings.gemini_api_key:
            providers.append("gemini")
        
        if settings.openai_api_key:
            providers.append("openai")
        
        return providers


# Singleton instance
_extractor_instance = None


def get_extractor() -> DocumentExtractor:
    """Get or create singleton extractor instance"""
    global _extractor_instance
    if _extractor_instance is None:
        _extractor_instance = DocumentExtractor()
    return _extractor_instance