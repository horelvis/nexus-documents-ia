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
        self.provider = (settings.default_provider or "ollama").lower()
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
            
            "nomina": {
                "prompt": """Extrae información estructurada de esta nómina laboral:
                - Trabajador (nombre completo, NIF, número seguridad social)
                - Empresa (nombre, CIF)
                - Período de liquidación (mes/año)
                - Devengos (salario base, complementos, pagas extra, horas extra)
                - Deducciones (IRPF, Seguridad Social, anticipos)
                - Líquido total a percibir
                - Datos bancarios (IBAN)

                Extrae cantidades numéricas exactas y fechas tal como aparecen.""",

                "examples": [
                    lx.data.ExampleData(
                        text="Nómina - Período: Enero 2025\nTrabajador: Juan Pérez López, NIF: 12345678A\nSalario Base: 1.800,00 €\nIRPF: -270,00 €\nLíquido a Percibir: 1.530,00 €",
                        extractions=[
                            lx.data.Extraction(
                                extraction_class="trabajador",
                                extraction_text="Juan Pérez López",
                                attributes={"nif": "12345678A", "tipo": "empleado"}
                            ),
                            lx.data.Extraction(
                                extraction_class="periodo",
                                extraction_text="Enero 2025",
                                attributes={"tipo": "mensual"}
                            ),
                            lx.data.Extraction(
                                extraction_class="devengo",
                                extraction_text="1.800,00 €",
                                attributes={"concepto": "salario_base"}
                            ),
                            lx.data.Extraction(
                                extraction_class="deduccion",
                                extraction_text="-270,00 €",
                                attributes={"concepto": "irpf", "tipo": "retencion"}
                            ),
                            lx.data.Extraction(
                                extraction_class="liquido",
                                extraction_text="1.530,00 €",
                                attributes={"tipo": "total_percibir"}
                            )
                        ]
                    )
                ]
            },

            "modelo_111": {
                "prompt": """Extrae información del Modelo 111 (Retenciones IRPF trimestral):
                - NIF y nombre del declarante
                - Período de declaración (trimestre y año)
                - Número de perceptores
                - Retenciones practicadas
                - Ingresos a cuenta
                - Resultado a ingresar o devolver
                - Fecha de presentación

                Mantén formato numérico exacto y estructura fiscal.""",

                "examples": [
                    lx.data.ExampleData(
                        text="Modelo 111 - 1T 2025\nDeclarante: TechCorp SL, CIF: B12345678\nPerceptores: 15\nRetenciones: 4.500,00 €\nResultado: 4.500,00 € a ingresar",
                        extractions=[
                            lx.data.Extraction(
                                extraction_class="declarante",
                                extraction_text="TechCorp SL",
                                attributes={"cif": "B12345678", "tipo": "empresa"}
                            ),
                            lx.data.Extraction(
                                extraction_class="periodo",
                                extraction_text="1T 2025",
                                attributes={"tipo": "trimestral", "trimestre": "1"}
                            ),
                            lx.data.Extraction(
                                extraction_class="perceptores",
                                extraction_text="15",
                                attributes={"tipo": "numero"}
                            ),
                            lx.data.Extraction(
                                extraction_class="retencion",
                                extraction_text="4.500,00 €",
                                attributes={"concepto": "irpf_practicado"}
                            ),
                            lx.data.Extraction(
                                extraction_class="resultado",
                                extraction_text="4.500,00 €",
                                attributes={"tipo": "a_ingresar"}
                            )
                        ]
                    )
                ]
            },

            "modelo_190": {
                "prompt": """Extrae información del Modelo 190 (Resumen anual IRPF):
                - NIF y nombre del declarante
                - Ejercicio fiscal (año)
                - Percepciones totales por empleado
                - Retenciones totales practicadas
                - Número total de perceptores
                - Resumen por conceptos

                Preserva estructura de datos anuales y totalizaciones.""",

                "examples": [
                    lx.data.ExampleData(
                        text="Modelo 190 - Ejercicio 2024\nDeclarante: GlobalCorp SA, CIF: A87654321\nTotal Perceptores: 120\nTotal Percepciones: 2.400.000,00 €\nTotal Retenciones: 360.000,00 €",
                        extractions=[
                            lx.data.Extraction(
                                extraction_class="declarante",
                                extraction_text="GlobalCorp SA",
                                attributes={"cif": "A87654321"}
                            ),
                            lx.data.Extraction(
                                extraction_class="ejercicio",
                                extraction_text="2024",
                                attributes={"tipo": "anual"}
                            ),
                            lx.data.Extraction(
                                extraction_class="perceptores",
                                extraction_text="120",
                                attributes={"tipo": "total"}
                            ),
                            lx.data.Extraction(
                                extraction_class="percepciones",
                                extraction_text="2.400.000,00 €",
                                attributes={"tipo": "total_anual"}
                            ),
                            lx.data.Extraction(
                                extraction_class="retenciones",
                                extraction_text="360.000,00 €",
                                attributes={"tipo": "total_anual"}
                            )
                        ]
                    )
                ]
            },

            "modelo_303": {
                "prompt": """Extrae información del Modelo 303 (IVA trimestral):
                - NIF y nombre del declarante
                - Período (trimestre y año)
                - IVA devengado (base imponible y cuota)
                - IVA deducible (base imponible y cuota)
                - Resultado (a ingresar o compensar)

                Mantén separación entre bases imponibles y cuotas.""",

                "examples": [
                    lx.data.ExampleData(
                        text="Modelo 303 - 4T 2024\nDeclarante: Services Ltd, CIF: B99887766\nIVA Devengado: Base 50.000,00 € - Cuota 10.500,00 €\nIVA Deducible: Base 30.000,00 € - Cuota 6.300,00 €\nResultado: 4.200,00 € a ingresar",
                        extractions=[
                            lx.data.Extraction(
                                extraction_class="declarante",
                                extraction_text="Services Ltd",
                                attributes={"cif": "B99887766"}
                            ),
                            lx.data.Extraction(
                                extraction_class="periodo",
                                extraction_text="4T 2024",
                                attributes={"trimestre": "4", "año": "2024"}
                            ),
                            lx.data.Extraction(
                                extraction_class="iva_devengado",
                                extraction_text="10.500,00 €",
                                attributes={"base": "50.000,00 €", "tipo": "cuota"}
                            ),
                            lx.data.Extraction(
                                extraction_class="iva_deducible",
                                extraction_text="6.300,00 €",
                                attributes={"base": "30.000,00 €", "tipo": "cuota"}
                            ),
                            lx.data.Extraction(
                                extraction_class="resultado",
                                extraction_text="4.200,00 €",
                                attributes={"tipo": "a_ingresar"}
                            )
                        ]
                    )
                ]
            },

            "certificado": {
                "prompt": """Extrae información de este certificado laboral:
                - Emisor (empresa/organización)
                - Trabajador o beneficiario
                - Tipo de certificado
                - Fecha de emisión
                - Período al que refiere
                - Datos certificados (antigüedad, salarios, etc.)
                - Firma y sello

                Preserva datos oficiales y declaraciones exactas.""",

                "examples": [
                    lx.data.ExampleData(
                        text="CERTIFICADO DE EMPRESA\nCertificamos que D. Carlos Martínez ha prestado servicios desde 01/01/2020 hasta 31/12/2024.\nPuesto: Ingeniero Senior\nMadrid, 15 de enero de 2025",
                        extractions=[
                            lx.data.Extraction(
                                extraction_class="trabajador",
                                extraction_text="Carlos Martínez",
                                attributes={"tratamiento": "D."}
                            ),
                            lx.data.Extraction(
                                extraction_class="periodo",
                                extraction_text="01/01/2020 hasta 31/12/2024",
                                attributes={"tipo": "antigüedad"}
                            ),
                            lx.data.Extraction(
                                extraction_class="puesto",
                                extraction_text="Ingeniero Senior",
                                attributes={"tipo": "cargo"}
                            ),
                            lx.data.Extraction(
                                extraction_class="fecha_emision",
                                extraction_text="15 de enero de 2025",
                                attributes={"lugar": "Madrid"}
                            )
                        ]
                    )
                ]
            },

            "comunicacion_itss": {
                "prompt": """Extrae información de comunicación de Inspección de Trabajo:
                - Órgano emisor (Inspección Provincial, etc.)
                - Empresa destinataria
                - Número de expediente
                - Tipo de comunicación (requerimiento, acta, sanción)
                - Fecha de comunicación
                - Plazo de respuesta
                - Objeto o motivo

                Identifica datos administrativos y plazos legales.""",

                "examples": [
                    lx.data.ExampleData(
                        text="INSPECCIÓN DE TRABAJO Y SEGURIDAD SOCIAL\nExpediente: ITSS-2025-00123\nEmpresa: Industrial Corp SL\nRequerimiento de documentación laboral\nPlazo: 10 días hábiles desde notificación",
                        extractions=[
                            lx.data.Extraction(
                                extraction_class="expediente",
                                extraction_text="ITSS-2025-00123",
                                attributes={"tipo": "numero_expediente"}
                            ),
                            lx.data.Extraction(
                                extraction_class="empresa",
                                extraction_text="Industrial Corp SL",
                                attributes={"tipo": "destinatario"}
                            ),
                            lx.data.Extraction(
                                extraction_class="tipo_comunicacion",
                                extraction_text="Requerimiento de documentación laboral",
                                attributes={"categoria": "requerimiento"}
                            ),
                            lx.data.Extraction(
                                extraction_class="plazo",
                                extraction_text="10 días hábiles",
                                attributes={"tipo": "respuesta"}
                            )
                        ]
                    )
                ]
            },

            "general": {
                "prompt": """Extrae SOLO las siguientes entidades clave del documento:

PERSONAS:
- Nombres de personas (trabajadores, clientes, firmantes, representantes)
- Cargos o roles de las personas

EMPRESAS/ORGANIZACIONES:
- Nombres de empresas, sociedades, organizaciones
- CIF/NIF de empresas
- Direcciones de empresas

INFORMACIÓN FINANCIERA:
- Importes monetarios (salarios, totales, deducciones, cuotas)
- Números de cuenta bancaria (IBAN)

FECHAS Y PERÍODOS:
- Fechas relevantes (emisión, vencimiento, período)
- Períodos (trimestres, meses, ejercicios)

IDENTIFICADORES:
- Números de factura, expediente, contrato
- NIF/CIF de personas

NO extraigas: descripciones genéricas, temas, conceptos abstractos, ubicaciones genéricas.
Usa el texto EXACTO del documento.""",

                "examples": [
                    lx.data.ExampleData(
                        text="Contrato entre TechCorp SL (CIF: B12345678) representada por Juan García López y el trabajador María Pérez Ruiz (NIF: 12345678A). Salario: 30.000 € anuales. Fecha inicio: 01/02/2025.",
                        extractions=[
                            lx.data.Extraction(
                                extraction_class="empresa",
                                extraction_text="TechCorp SL",
                                attributes={"cif": "B12345678", "rol": "empleador"}
                            ),
                            lx.data.Extraction(
                                extraction_class="person",
                                extraction_text="Juan García López",
                                attributes={"rol": "representante legal"}
                            ),
                            lx.data.Extraction(
                                extraction_class="trabajador",
                                extraction_text="María Pérez Ruiz",
                                attributes={"nif": "12345678A", "rol": "empleado"}
                            ),
                            lx.data.Extraction(
                                extraction_class="amount",
                                extraction_text="30.000 €",
                                attributes={"tipo": "salario", "periodicidad": "anual"}
                            ),
                            lx.data.Extraction(
                                extraction_class="fecha",
                                extraction_text="01/02/2025",
                                attributes={"tipo": "fecha_inicio"}
                            )
                        ]
                    ),
                    lx.data.ExampleData(
                        text="Factura Nº 2025-0042. Cliente: Servicios Digitales SA. Total: 1.210,00 € (IVA incluido). Vencimiento: 15/03/2025. IBAN: ES91 2100 0418 4502 0005 1332",
                        extractions=[
                            lx.data.Extraction(
                                extraction_class="invoice_number",
                                extraction_text="2025-0042",
                                attributes={"tipo": "numero_factura"}
                            ),
                            lx.data.Extraction(
                                extraction_class="cliente",
                                extraction_text="Servicios Digitales SA",
                                attributes={"rol": "comprador"}
                            ),
                            lx.data.Extraction(
                                extraction_class="amount",
                                extraction_text="1.210,00 €",
                                attributes={"tipo": "total", "iva_incluido": "true"}
                            ),
                            lx.data.Extraction(
                                extraction_class="fecha",
                                extraction_text="15/03/2025",
                                attributes={"tipo": "vencimiento"}
                            ),
                            lx.data.Extraction(
                                extraction_class="iban",
                                extraction_text="ES91 2100 0418 4502 0005 1332",
                                attributes={"tipo": "cuenta_bancaria"}
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
        provider: Optional[str] = None,
        _retry_count: int = 0
    ) -> Dict[str, Any]:
        """
        Extract structured information from document text using LangExtract's native API.

        Args:
            text: Document text to analyze
            document_type: Type of document (determined dynamically by LLM)
            filename: Optional filename for context
            provider: Optional provider override (ollama, gemini, openai, anthropic)
            _retry_count: Internal retry counter

        Returns:
            Dictionary with extractions, entities, and metadata
        """
        MAX_RETRIES = 2
        selected_provider = None
        model_name = None

        try:
            # Get configuration for document type (uses "general" if type not found)
            config = self.extraction_configs.get(
                document_type,
                self.extraction_configs["general"]
            )

            # Select and normalize provider
            requested_provider = provider or self.provider
            selected_provider = self._normalize_provider(requested_provider)

            # Build extraction params using LangExtract's native API
            # See: https://github.com/google/langextract
            extract_params = {
                "text_or_documents": text,
                "prompt_description": config["prompt"],
                "examples": config["examples"],
                "extraction_passes": settings.extraction_passes,
                "max_char_buffer": settings.max_char_buffer,
            }

            # Configure provider-specific parameters using LangExtract native API
            if selected_provider == "ollama":
                model_name = settings.llm_model
                extract_params["model_id"] = model_name
                extract_params["model_url"] = self._resolve_api_base("ollama")
                extract_params["fence_output"] = False
                extract_params["use_schema_constraints"] = False
                logger.info(f"Using Ollama: model={model_name}, url={extract_params['model_url']}")

            elif selected_provider == "gemini":
                api_key = self._resolve_api_key("gemini")
                if not api_key:
                    raise ValueError("Gemini requires GEMINI_API_KEY or LLM_API_KEY")
                model_name = getattr(settings, 'gemini_model', None) or "gemini-2.0-flash"
                extract_params["model_id"] = model_name
                extract_params["api_key"] = api_key
                logger.info(f"Using Gemini: model={model_name}")

            elif selected_provider == "openai":
                api_key = self._resolve_api_key("openai")
                if not api_key:
                    raise ValueError("OpenAI requires OPENAI_API_KEY or LLM_API_KEY")
                # LangExtract requires model pattern ^gpt-4* for OpenAI provider detection
                model_name = getattr(settings, 'openai_model', None) or "gpt-4o-mini"
                extract_params["model_id"] = model_name
                extract_params["api_key"] = api_key
                # OpenAI requires these specific settings per LangExtract docs
                extract_params["fence_output"] = True
                extract_params["use_schema_constraints"] = False
                logger.info(f"Using OpenAI: model={model_name}, fence_output=True")

            elif selected_provider in ("anthropic", "claude"):
                api_key = self._resolve_api_key("anthropic")
                if not api_key:
                    raise ValueError("Anthropic requires LLM_API_KEY")
                model_name = getattr(settings, 'anthropic_model', None) or "claude-3-5-haiku-latest"
                extract_params["model_id"] = model_name
                extract_params["api_key"] = api_key
                logger.info(f"Using Anthropic: model={model_name}")

            else:
                raise ValueError(f"Provider '{selected_provider}' not supported")

            # Perform extraction using LangExtract native API
            logger.info(f"Starting extraction for '{document_type}' document")
            result = lx.extract(**extract_params)

            # Process and structure results
            structured_data = self._structure_results(result, document_type)

            # Add metadata
            structured_data["metadata"] = {
                "document_type": document_type,
                "filename": filename,
                "provider": selected_provider,
                "provider_requested": requested_provider,
                "model": model_name,
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

        except json.JSONDecodeError as e:
            # JSON parsing error from LLM output - retry with smaller buffer
            logger.warning(f"JSON parse error (attempt {_retry_count + 1}): {e}")
            if _retry_count < MAX_RETRIES:
                logger.info(f"Retrying extraction with reduced buffer...")
                return await self.extract(
                    text=text[:min(len(text), 3000)],  # Reduce text size
                    document_type=document_type,
                    filename=filename,
                    provider=provider,
                    _retry_count=_retry_count + 1
                )
            return {
                "success": False,
                "error": f"Failed to parse JSON content: {str(e)}",
                "document_type": document_type,
                "provider": selected_provider or "unknown"
            }

        except Exception as e:
            error_msg = str(e)
            # Detect JSON errors from LangExtract
            if "json" in error_msg.lower() or "parse" in error_msg.lower() or "delimiter" in error_msg.lower():
                logger.warning(f"LangExtract JSON error (attempt {_retry_count + 1}): {e}")
                if _retry_count < MAX_RETRIES:
                    logger.info(f"Retrying extraction with reduced text...")
                    return await self.extract(
                        text=text[:min(len(text), 3000)],
                        document_type=document_type,
                        filename=filename,
                        provider=provider,
                        _retry_count=_retry_count + 1
                    )

            logger.error(f"Extraction failed: {e}")
            return {
                "success": False,
                "error": str(e),
                "document_type": document_type,
                "provider": selected_provider or "unknown"
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

        if settings.gemini_api_key or (settings.llm_api_key and settings.default_provider == "gemini"):
            providers.append("gemini")

        if settings.openai_api_key or (settings.llm_api_key and settings.default_provider == "openai"):
            providers.append("openai")

        if settings.llm_api_key and settings.default_provider in ("anthropic", "claude"):
            providers.append("anthropic")

        return providers

    def _normalize_provider(self, provider_value: Optional[str]) -> str:
        """Normalize provider name - error if invalid, no fallback"""
        normalized = (provider_value or self.provider or "ollama").lower()
        # Map claude -> anthropic
        if normalized == "claude":
            normalized = "anthropic"
        valid_providers = {"ollama", "gemini", "openai", "anthropic"}
        if normalized not in valid_providers:
            raise ValueError(
                f"Invalid provider '{provider_value}'. "
                f"Valid providers: {', '.join(sorted(valid_providers))}"
            )
        return normalized

    def _resolve_model(self, provider: str) -> str:
        """Resolve model name based on provider - each provider has its own default"""
        # Provider-specific model resolution
        if provider == "ollama":
            model = settings.llm_model  # Use configured LLM_MODEL for Ollama
        elif provider == "openai":
            # Use OPENAI_MODEL env var or sensible default
            model = getattr(settings, 'openai_model', None) or "gpt-3.5-turbo"
        elif provider == "gemini":
            model = getattr(settings, 'gemini_model', None) or "gemini-1.5-flash"
        elif provider in ("anthropic", "claude"):
            model = getattr(settings, 'anthropic_model', None) or "claude-3-5-haiku-latest"
        else:
            model = settings.llm_model

        # Sanitize model name: replace special hyphens (U+2011) with standard hyphens (U+002D)
        return model.replace('‑', '-')

    def _resolve_api_key(self, provider: str) -> Optional[str]:
        """Resolve API key for provider, allowing generic LLM_API_KEY override"""
        if provider == "openai":
            return settings.openai_api_key or settings.llm_api_key
        if provider == "gemini":
            return settings.gemini_api_key or settings.llm_api_key
        if provider in ("anthropic", "claude"):
            return settings.llm_api_key  # Anthropic uses generic LLM_API_KEY
        return None
    
    def _resolve_api_base(self, provider: str) -> str:
        """Resolve API base endpoint per provider"""
        if provider == "ollama":
            return (settings.ollama_host or "http://ollama:11434").rstrip("/")
        if settings.llm_api_base:
            return settings.llm_api_base.rstrip("/")
        if provider == "openai":
            return "https://api.openai.com/v1"
        if provider == "gemini":
            # Public Gemini endpoint prefix
            return "https://generativelanguage.googleapis.com"
        return ""

    async def detect_document_type(
        self,
        text: str,
        filename: Optional[str] = None,
        context: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Detecta el tipo de documento usando LangExtract.
        Extrae el tipo como una entidad estructurada con source grounding.

        Args:
            text: Contenido del documento
            filename: Nombre del archivo (opcional, ayuda a la detección)
            context: Contexto adicional (opcional)

        Returns:
            {
                "detected_type": str,
                "confidence": float,
                "reasoning": str,
                "alternative_types": List[Dict],
                "extractions": List[Dict],
                "summary": Dict,
                "visualization_html": str
            }
        """
        try:
            logger.info("🔍 Clasificando documento usando LangExtract")

            # Usar primeros 2000 caracteres para clasificación
            text_sample = text[:2000]
            if filename:
                text_sample = f"Filename: {filename}\n\n{text_sample}"

            # Configuración de extracción para clasificación de documentos
            classification_prompt = """Analiza este documento y extrae:
1. El TIPO de documento (document_type): nomina, modelo_111, modelo_190, modelo_303,
   certificado, comunicacion_itss, invoice, contract, report, o general
2. El MOTIVO de la clasificación (classification_reason): explicación breve
3. Entidades clave que justifican la clasificación

Tipos de documentos:
- nomina: Nóminas laborales con salarios, deducciones, líquido
- modelo_111: Modelo tributario 111 (retenciones IRPF trimestrales)
- modelo_190: Modelo tributario 190 (resumen anual IRPF)
- modelo_303: Modelo tributario 303 (IVA trimestral)
- certificado: Certificados laborales
- comunicacion_itss: Comunicaciones de Inspección de Trabajo
- invoice: Facturas, recibos
- contract: Contratos legales
- report: Informes, documentación técnica
- general: Otros documentos"""

            classification_examples = [
                lx.data.ExampleData(
                    text="NÓMINA - Período: Enero 2025\nTrabajador: Juan García\nSalario Base: 2.500 €\nIRPF: -375 €\nLíquido: 2.125 €",
                    extractions=[
                        lx.data.Extraction(
                            extraction_class="document_type",
                            extraction_text="nomina",
                            attributes={"confidence": 0.95}
                        ),
                        lx.data.Extraction(
                            extraction_class="classification_reason",
                            extraction_text="Contiene salario base, IRPF, líquido a percibir y período de nómina",
                            attributes={}
                        ),
                    ]
                ),
                lx.data.ExampleData(
                    text="FACTURA Nº: 2025-001\nCliente: ABC Corp\nConcepto: Servicios\nBase Imponible: 1.000 €\nIVA 21%: 210 €\nTotal: 1.210 €",
                    extractions=[
                        lx.data.Extraction(
                            extraction_class="document_type",
                            extraction_text="invoice",
                            attributes={"confidence": 0.95}
                        ),
                        lx.data.Extraction(
                            extraction_class="classification_reason",
                            extraction_text="Contiene número de factura, cliente, base imponible e IVA",
                            attributes={}
                        ),
                    ]
                ),
                lx.data.ExampleData(
                    text="MODELO 111 - Declaración trimestral\nEjercicio: 2025 Período: 1T\nRendimientos del trabajo: 50.000 €\nRetenciones practicadas: 7.500 €",
                    extractions=[
                        lx.data.Extraction(
                            extraction_class="document_type",
                            extraction_text="modelo_111",
                            attributes={"confidence": 0.98}
                        ),
                        lx.data.Extraction(
                            extraction_class="classification_reason",
                            extraction_text="Formulario tributario 111 con retenciones IRPF trimestrales",
                            attributes={}
                        ),
                    ]
                ),
            ]

            # Configurar parámetros de extracción según provider
            provider = self._normalize_provider(settings.default_provider)
            extract_params = {
                "text_or_documents": text_sample,
                "prompt_description": classification_prompt,
                "examples": classification_examples,
                "extraction_passes": 1,  # Solo una pasada para clasificación
                "max_char_buffer": 3000,
            }

            # Configurar provider
            if provider == "ollama":
                extract_params["model_id"] = settings.llm_model
                extract_params["model_url"] = self._resolve_api_base("ollama")
                extract_params["fence_output"] = False
                extract_params["use_schema_constraints"] = False
            elif provider == "gemini":
                extract_params["model_id"] = getattr(settings, 'gemini_model', None) or "gemini-2.0-flash"
                extract_params["api_key"] = self._resolve_api_key("gemini")
            elif provider == "openai":
                extract_params["model_id"] = getattr(settings, 'openai_model', None) or "gpt-4o-mini"
                extract_params["api_key"] = self._resolve_api_key("openai")
                extract_params["fence_output"] = True
                extract_params["use_schema_constraints"] = False

            logger.info(f"🤖 Clasificando con {provider} ({extract_params.get('model_id', 'default')})")

            # Ejecutar extracción con LangExtract
            result = lx.extract(**extract_params)

            # Procesar resultados
            detected_type = "general"
            confidence = 0.5
            reasoning = "No se pudo determinar el tipo con certeza"

            if result.extractions:
                for ext in result.extractions:
                    if ext.extraction_class == "document_type":
                        detected_type = ext.extraction_text.lower().strip()
                        # Asegurar que confidence sea float (el LLM puede devolver string)
                        raw_confidence = ext.attributes.get("confidence", 0.8) if ext.attributes else 0.8
                        try:
                            confidence = float(raw_confidence)
                        except (ValueError, TypeError):
                            confidence = 0.8
                    elif ext.extraction_class == "classification_reason":
                        reasoning = ext.extraction_text

            # Validar tipo detectado
            valid_types = [
                "nomina", "modelo_111", "modelo_190", "modelo_303",
                "certificado", "comunicacion_itss",
                "invoice", "factura", "contract", "contrato", "report", "informe", "general"
            ]

            # Normalizar tipo detectado
            for valid_type in valid_types:
                if valid_type in detected_type:
                    detected_type = valid_type
                    break
            else:
                if detected_type not in valid_types:
                    logger.warning(f"⚠️ Tipo '{detected_type}' no válido, usando 'general'")
                    detected_type = "general"

            logger.info(f"✅ LangExtract detectó: '{detected_type}' (confianza: {confidence:.2f})")

            # Generar visualización HTML si hay extracciones
            visualization_html = None
            if result.extractions:
                try:
                    visualization_html = lx.visualize(result)
                except Exception as e:
                    logger.warning(f"No se pudo generar visualización: {e}")

            return {
                "detected_type": detected_type,
                "confidence": round(float(confidence), 2),
                "reasoning": reasoning,
                "alternative_types": [],
                "extractions": [
                    {
                        "class": ext.extraction_class,
                        "text": ext.extraction_text,
                        "attributes": ext.attributes or {}
                    }
                    for ext in (result.extractions or [])
                ],
                "summary": {},
                "visualization_html": visualization_html
            }

        except Exception as e:
            logger.error(f"❌ Error en clasificación LangExtract: {e}", exc_info=True)
            return {
                "detected_type": "general",
                "confidence": 0.0,
                "reasoning": f"Error durante clasificación: {str(e)}",
                "alternative_types": [],
                "extractions": [],
                "summary": {},
                "visualization_html": None
            }



# Singleton instance
_extractor_instance = None


def get_extractor() -> DocumentExtractor:
    """Get or create singleton extractor instance"""
    global _extractor_instance
    if _extractor_instance is None:
        _extractor_instance = DocumentExtractor()
    return _extractor_instance
