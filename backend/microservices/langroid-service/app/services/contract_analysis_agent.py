"""
Contract Analysis Langroid Agent - Advanced contract processing and analysis
"""
import asyncio
import logging
import json
from datetime import datetime
from typing import Dict, Any, List, Optional, AsyncGenerator
from uuid import UUID
import httpx

import langroid as lr
from langroid.agent.chat_agent import ChatAgent, ChatAgentConfig
from langroid.agent.tools.orchestration import AgentDoneTool
from langroid.language_models.base import LLMMessage, Role
from langroid.pydantic_v1 import BaseModel, Field

from app.core.config import settings
from app.services.tools.contract_tools import (
    ExtractClausesTool,
    RiskAnalysisTool,
    ComplianceCheckTool,
    RenewalAlertTool,
    ContractCompareTool
)

logger = logging.getLogger(__name__)


class ContractAnalysisLangroidAgent(ChatAgent):
    """Advanced Contract Analysis Agent using Langroid framework"""
    
    def __init__(
        self,
        agent_id: str,
        tenant_id: str,
        user_id: str,
        llm_config: lr.language_models.openai_gpt.OpenAIGPTConfig,
        vector_config: lr.vector_store.qdrantdb.QdrantDBConfig = None,
        config: Dict[str, Any] = None
    ):
        self.agent_id = agent_id
        self.tenant_id = tenant_id
        self.user_id = user_id
        self.config = config or {}
        
        # Configure agent
        agent_config = ChatAgentConfig(
            name="ContractAnalysisAgent",
            llm=llm_config,
            vecdb=vector_config,
            system_message=self._build_system_message(),
            use_tools=True,
            use_functions_api=True
        )
        
        super().__init__(agent_config)
        
        # Register specialized tools
        self.enable_message(ExtractClausesTool)
        self.enable_message(RiskAnalysisTool)
        self.enable_message(ComplianceCheckTool)
        self.enable_message(RenewalAlertTool)
        self.enable_message(ContractCompareTool)
        self.enable_message(AgentDoneTool)
        
        # HTTP client for backend communication
        self.http_client = httpx.AsyncClient(timeout=60.0)
        
        logger.info(f"Created ContractAnalysisLangroidAgent {agent_id} for tenant {tenant_id}")
    
    def _build_system_message(self) -> str:
        """Build system message for the contract analysis agent"""
        return f"""You are an expert contract analysis assistant powered by Langroid, specializing in comprehensive contract review and risk assessment.

IDENTITY & ROLE:
- Agent ID: {self.agent_id}
- Tenant: {self.tenant_id}
- Expert in contract law, risk analysis, and compliance
- Specialized in business contract analysis and legal document processing

CORE CAPABILITIES:
1. **Contract Clause Extraction**: Identify and extract key contract provisions
2. **Risk Assessment**: Comprehensive analysis of financial, legal, and operational risks
3. **Compliance Checking**: Verify adherence to regulations (GDPR, SOX, CCPA, etc.)
4. **Renewal Management**: Track important dates and generate alerts
5. **Contract Comparison**: Compare against templates and other contracts
6. **Legal Recommendations**: Provide actionable advice for contract improvements

AVAILABLE SPECIALIZED TOOLS:
1. ExtractClausesTool: Extract specific clauses (payment, termination, liability, etc.)
2. RiskAnalysisTool: Analyze financial, legal, operational, and reputational risks
3. ComplianceCheckTool: Check compliance with various regulations
4. RenewalAlertTool: Extract dates and generate renewal alerts
5. ContractCompareTool: Compare contracts against templates or other agreements

ANALYSIS METHODOLOGY:
- Always start with a comprehensive overview
- Extract key clauses first to understand structure
- Perform detailed risk analysis with severity levels
- Check relevant compliance requirements
- Identify critical dates and deadlines
- Provide specific, actionable recommendations

RISK ASSESSMENT FRAMEWORK:
- CRITICAL: Immediate legal or financial threat requiring urgent action
- HIGH: Significant risks that should be addressed before signing
- MEDIUM: Important considerations for negotiation
- LOW: Minor issues to monitor

COMMUNICATION STYLE:
- Professional and precise legal language
- Clear explanations of complex legal concepts
- Structured analysis with bullet points and sections
- Specific recommendations with rationale
- Risk-based prioritization of issues

SECURITY & COMPLIANCE:
- Maintain strict confidentiality of contract contents
- Respect tenant data boundaries
- Follow audit trails for all analysis
- Ensure compliance with data protection regulations

When analyzing contracts, use the specialized tools proactively to provide comprehensive analysis. Always explain your findings clearly and provide actionable recommendations prioritized by risk level.

Respond in Spanish when appropriate and adapt communication style to the business context."""
    
    async def chat_stream(
        self,
        message: str,
        conversation_id: Optional[str] = None,
        context: Dict[str, Any] = None
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """Chat with the agent and stream responses"""
        
        try:
            yield {
                "type": "message",
                "content": "Analizando tu consulta sobre contratos...",
                "metadata": {"status": "processing", "agent_id": self.agent_id}
            }
            
            # Determine analysis type based on message
            analysis_plan = await self._plan_contract_analysis(message, context)
            
            yield {
                "type": "analysis_plan",
                "content": f"Plan de análisis: {', '.join(analysis_plan['steps'])}",
                "metadata": {"plan": analysis_plan}
            }
            
            # Execute analysis workflow
            async for response in self._execute_analysis_workflow(
                message, analysis_plan, context
            ):
                yield response
                    
        except Exception as e:
            logger.error(f"Error in contract chat_stream: {str(e)}")
            yield {
                "type": "error",
                "content": f"Error procesando análisis de contrato: {str(e)}",
                "metadata": {"error": str(e), "agent_id": self.agent_id}
            }
    
    async def execute_task_stream(
        self,
        task_type: str,
        parameters: Dict[str, Any],
        context: Dict[str, Any] = None
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """Execute specific contract analysis task with streaming"""
        
        try:
            yield {
                "type": "task_progress",
                "content": f"Ejecutando análisis: {task_type}",
                "metadata": {
                    "task_type": task_type,
                    "agent_id": self.agent_id,
                    "progress": 10
                }
            }
            
            # Execute based on task type
            if task_type == "extract_clauses":
                async for response in self._execute_clause_extraction(parameters):
                    yield response
                    
            elif task_type == "analyze_risks":
                async for response in self._execute_risk_analysis(parameters):
                    yield response
                    
            elif task_type == "check_compliance":
                async for response in self._execute_compliance_check(parameters):
                    yield response
                    
            elif task_type == "manage_renewals":
                async for response in self._execute_renewal_management(parameters):
                    yield response
                    
            elif task_type == "compare_contracts":
                async for response in self._execute_contract_comparison(parameters):
                    yield response
                    
            elif task_type == "full_analysis":
                async for response in self._execute_full_contract_analysis(parameters):
                    yield response
                    
            else:
                yield {
                    "type": "error",
                    "content": f"Tipo de análisis no soportado: {task_type}",
                    "metadata": {"task_type": task_type, "agent_id": self.agent_id}
                }
                
        except Exception as e:
            logger.error(f"Error executing contract task {task_type}: {str(e)}")
            yield {
                "type": "error",
                "content": f"Error ejecutando análisis: {str(e)}",
                "metadata": {"task_type": task_type, "error": str(e)}
            }
    
    # =====================================
    # ANALYSIS PLANNING
    # =====================================
    
    async def _plan_contract_analysis(
        self, 
        message: str, 
        context: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """Plan contract analysis based on user request"""
        
        message_lower = message.lower()
        
        # Determine analysis steps based on keywords
        steps = []
        tools_needed = []
        
        # Check for specific analysis requests
        if any(word in message_lower for word in ["cláusulas", "clauses", "extraer", "extract"]):
            steps.append("extracción de cláusulas")
            tools_needed.append("extract_clauses")
        
        if any(word in message_lower for word in ["riesgo", "risk", "riesgos", "risks"]):
            steps.append("análisis de riesgos")
            tools_needed.append("analyze_risks")
        
        if any(word in message_lower for word in ["cumplimiento", "compliance", "regulación"]):
            steps.append("verificación de cumplimiento")
            tools_needed.append("check_compliance")
        
        if any(word in message_lower for word in ["renovación", "renewal", "fechas", "dates"]):
            steps.append("gestión de renovaciones")
            tools_needed.append("manage_renewals")
        
        if any(word in message_lower for word in ["comparar", "compare", "template"]):
            steps.append("comparación de contratos")
            tools_needed.append("compare_contracts")
        
        # If no specific request, do full analysis
        if not steps:
            steps = [
                "extracción de cláusulas",
                "análisis de riesgos", 
                "verificación de cumplimiento",
                "gestión de renovaciones"
            ]
            tools_needed = ["extract_clauses", "analyze_risks", "check_compliance", "manage_renewals"]
        
        return {
            "type": "comprehensive" if len(steps) > 2 else "targeted",
            "steps": steps,
            "tools_needed": tools_needed,
            "estimated_duration": len(tools_needed) * 30,  # seconds
            "requires_document": True
        }
    
    async def _execute_analysis_workflow(
        self,
        message: str,
        analysis_plan: Dict[str, Any],
        context: Dict[str, Any] = None
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """Execute planned analysis workflow"""
        
        # Extract document content from context or message
        document_content = self._extract_document_content(message, context)
        
        if not document_content:
            yield {
                "type": "error",
                "content": "No se encontró contenido del contrato para analizar. Por favor, proporciona el texto del contrato.",
                "metadata": {"error_type": "missing_document"}
            }
            return
        
        total_steps = len(analysis_plan["tools_needed"])
        current_step = 0
        
        analysis_results = {
            "document_analysis": {},
            "summary": {},
            "recommendations": []
        }
        
        # Execute each planned step
        for tool_name in analysis_plan["tools_needed"]:
            current_step += 1
            progress = int((current_step / total_steps) * 90)
            
            yield {
                "type": "workflow_progress",
                "content": f"Ejecutando paso {current_step}/{total_steps}: {tool_name}",
                "metadata": {"progress": progress, "step": current_step, "total": total_steps}
            }
            
            # Execute specific analysis
            step_result = await self._execute_analysis_step(tool_name, document_content, context)
            analysis_results["document_analysis"][tool_name] = step_result
            
            # Stream intermediate result
            yield {
                "type": "step_result",
                "content": f"Completado: {tool_name}",
                "metadata": {
                    "step": tool_name,
                    "result_summary": step_result.get("summary", "Análisis completado"),
                    "progress": progress
                }
            }
        
        # Generate final summary and recommendations
        final_summary = await self._generate_final_summary(analysis_results)
        
        yield {
            "type": "analysis_complete",
            "content": "Análisis completo del contrato finalizado",
            "metadata": {
                "progress": 100,
                "analysis_results": analysis_results,
                "final_summary": final_summary
            }
        }
    
    def _extract_document_content(
        self, 
        message: str, 
        context: Dict[str, Any] = None
    ) -> Optional[str]:
        """Extract document content from message or context"""
        
        # Try to get from context first
        if context:
            if "document_content" in context:
                return context["document_content"]
            if "file_content" in context:
                return context["file_content"]
        
        # If message is long enough, treat it as document content
        if len(message) > 500:
            return message
        
        return None
    
    async def _execute_analysis_step(
        self,
        tool_name: str,
        document_content: str,
        context: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """Execute a single analysis step"""
        
        try:
            if tool_name == "extract_clauses":
                tool = ExtractClausesTool(
                    document_content=document_content,
                    clause_types=["payment", "termination", "liability", "confidentiality"]
                )
                result = tool.handle()
                return {"status": "success", "data": json.loads(result), "summary": "Cláusulas extraídas"}
            
            elif tool_name == "analyze_risks":
                tool = RiskAnalysisTool(
                    document_content=document_content,
                    risk_categories=["financial", "legal", "operational", "reputational"]
                )
                result = tool.handle()
                return {"status": "success", "data": json.loads(result), "summary": "Riesgos analizados"}
            
            elif tool_name == "check_compliance":
                tool = ComplianceCheckTool(
                    document_content=document_content,
                    regulations=["gdpr", "sox", "ccpa"]
                )
                result = tool.handle()
                return {"status": "success", "data": json.loads(result), "summary": "Cumplimiento verificado"}
            
            elif tool_name == "manage_renewals":
                tool = RenewalAlertTool(
                    document_content=document_content
                )
                result = tool.handle()
                return {"status": "success", "data": json.loads(result), "summary": "Fechas de renovación identificadas"}
            
            else:
                return {"status": "error", "error": f"Unknown tool: {tool_name}"}
                
        except Exception as e:
            logger.error(f"Error executing analysis step {tool_name}: {str(e)}")
            return {"status": "error", "error": str(e)}
    
    async def _generate_final_summary(
        self, 
        analysis_results: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Generate final analysis summary and recommendations"""
        
        summary = {
            "overall_risk_level": "medium",
            "critical_issues": [],
            "key_findings": [],
            "recommendations": [],
            "next_actions": []
        }
        
        # Analyze risk analysis results
        if "analyze_risks" in analysis_results["document_analysis"]:
            risk_data = analysis_results["document_analysis"]["analyze_risks"].get("data", {})
            if "critical_risks" in risk_data:
                summary["critical_issues"].extend([
                    f"CRÍTICO: {risk['description']}" 
                    for risk in risk_data["critical_risks"]
                ])
            
            if "overall_risk_score" in risk_data:
                score = risk_data["overall_risk_score"]
                if score >= 75:
                    summary["overall_risk_level"] = "high"
                elif score >= 50:
                    summary["overall_risk_level"] = "medium"
                else:
                    summary["overall_risk_level"] = "low"
        
        # Analyze compliance results
        if "check_compliance" in analysis_results["document_analysis"]:
            compliance_data = analysis_results["document_analysis"]["check_compliance"].get("data", {})
            if "non_compliant_items" in compliance_data:
                summary["critical_issues"].extend([
                    f"CUMPLIMIENTO: {item['requirement']}" 
                    for item in compliance_data["non_compliant_items"]
                ])
        
        # Generate recommendations based on findings
        if summary["overall_risk_level"] == "high":
            summary["recommendations"].append("Se recomienda revisión legal completa antes de la firma")
            summary["next_actions"].append("Agendar revisión con equipo legal")
        
        if summary["critical_issues"]:
            summary["recommendations"].append("Abordar problemas críticos identificados")
            summary["next_actions"].extend([
                "Negociar modificaciones a cláusulas de alto riesgo",
                "Solicitar aclaraciones sobre términos ambiguos"
            ])
        
        return summary
    
    # =====================================
    # SPECIFIC TASK IMPLEMENTATIONS
    # =====================================
    
    async def _execute_clause_extraction(
        self, 
        parameters: Dict[str, Any]
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """Execute clause extraction task"""
        
        try:
            document_content = parameters.get("document_content", "")
            clause_types = parameters.get("clause_types", ["payment", "termination", "liability"])
            
            yield {
                "type": "task_progress",
                "content": "Extrayendo cláusulas del contrato...",
                "metadata": {"progress": 30}
            }
            
            tool = ExtractClausesTool(
                document_content=document_content,
                clause_types=clause_types
            )
            
            result = tool.handle()
            parsed_result = json.loads(result)
            
            yield {
                "type": "task_result",
                "content": "✅ Cláusulas extraídas exitosamente",
                "metadata": {
                    "progress": 100,
                    "result": parsed_result,
                    "task_type": "extract_clauses",
                    "clauses_found": parsed_result.get("extracted_clauses", 0)
                }
            }
            
        except Exception as e:
            yield {
                "type": "error",
                "content": f"Error extrayendo cláusulas: {str(e)}",
                "metadata": {"error": str(e)}
            }
    
    async def _execute_risk_analysis(
        self, 
        parameters: Dict[str, Any]
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """Execute comprehensive risk analysis"""
        
        try:
            document_content = parameters.get("document_content", "")
            risk_categories = parameters.get("risk_categories", ["financial", "legal", "operational"])
            
            yield {
                "type": "task_progress",
                "content": "Analizando riesgos contractuales...",
                "metadata": {"progress": 40}
            }
            
            tool = RiskAnalysisTool(
                document_content=document_content,
                risk_categories=risk_categories
            )
            
            result = tool.handle()
            parsed_result = json.loads(result)
            
            # Determine risk level for progress indication
            risk_score = parsed_result.get("overall_risk_score", 0)
            risk_level = "alto" if risk_score >= 70 else "medio" if risk_score >= 40 else "bajo"
            
            yield {
                "type": "task_result",
                "content": f"📊 Análisis de riesgos completado - Nivel: {risk_level}",
                "metadata": {
                    "progress": 100,
                    "result": parsed_result,
                    "task_type": "analyze_risks",
                    "risk_score": risk_score,
                    "risk_level": risk_level
                }
            }
            
        except Exception as e:
            yield {
                "type": "error",
                "content": f"Error analizando riesgos: {str(e)}",
                "metadata": {"error": str(e)}
            }
    
    async def _execute_compliance_check(
        self, 
        parameters: Dict[str, Any]
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """Execute compliance verification"""
        
        try:
            document_content = parameters.get("document_content", "")
            regulations = parameters.get("regulations", ["gdpr", "sox"])
            jurisdiction = parameters.get("jurisdiction", "US")
            
            yield {
                "type": "task_progress",
                "content": f"Verificando cumplimiento normativo ({', '.join(regulations)})...",
                "metadata": {"progress": 50}
            }
            
            tool = ComplianceCheckTool(
                document_content=document_content,
                regulations=regulations,
                jurisdiction=jurisdiction
            )
            
            result = tool.handle()
            parsed_result = json.loads(result)
            
            compliance_score = parsed_result.get("overall_compliance_score", 0)
            compliance_status = "conforme" if compliance_score >= 80 else "parcialmente conforme" if compliance_score >= 60 else "no conforme"
            
            yield {
                "type": "task_result",
                "content": f"🔍 Verificación de cumplimiento: {compliance_status}",
                "metadata": {
                    "progress": 100,
                    "result": parsed_result,
                    "task_type": "check_compliance",
                    "compliance_score": compliance_score,
                    "compliance_status": compliance_status
                }
            }
            
        except Exception as e:
            yield {
                "type": "error",
                "content": f"Error verificando cumplimiento: {str(e)}",
                "metadata": {"error": str(e)}
            }
    
    async def _execute_renewal_management(
        self, 
        parameters: Dict[str, Any]
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """Execute renewal date management"""
        
        try:
            document_content = parameters.get("document_content", "")
            current_date = parameters.get("current_date", None)
            
            yield {
                "type": "task_progress",
                "content": "Identificando fechas críticas y renovaciones...",
                "metadata": {"progress": 45}
            }
            
            tool = RenewalAlertTool(
                document_content=document_content,
                current_date=current_date
            )
            
            result = tool.handle()
            parsed_result = json.loads(result)
            
            dates_found = parsed_result.get("total_dates_found", 0)
            upcoming_deadlines = len(parsed_result.get("upcoming_deadlines", []))
            
            yield {
                "type": "task_result",
                "content": f"📅 Gestión de renovaciones: {dates_found} fechas, {upcoming_deadlines} próximas",
                "metadata": {
                    "progress": 100,
                    "result": parsed_result,
                    "task_type": "manage_renewals",
                    "dates_found": dates_found,
                    "upcoming_deadlines": upcoming_deadlines
                }
            }
            
        except Exception as e:
            yield {
                "type": "error",
                "content": f"Error gestionando renovaciones: {str(e)}",
                "metadata": {"error": str(e)}
            }
    
    async def _execute_contract_comparison(
        self, 
        parameters: Dict[str, Any]
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """Execute contract comparison"""
        
        try:
            primary_document = parameters.get("primary_document", "")
            comparison_document = parameters.get("comparison_document", "")
            comparison_type = parameters.get("comparison_type", "template")
            
            yield {
                "type": "task_progress",
                "content": f"Comparando contrato con {comparison_type}...",
                "metadata": {"progress": 60}
            }
            
            tool = ContractCompareTool(
                primary_document=primary_document,
                comparison_document=comparison_document,
                comparison_type=comparison_type
            )
            
            result = tool.handle()
            parsed_result = json.loads(result)
            
            similarity_score = parsed_result.get("similarity_score", 0)
            missing_clauses = len(parsed_result.get("missing_clauses", []))
            
            yield {
                "type": "task_result", 
                "content": f"🔄 Comparación completada - Similitud: {similarity_score}%",
                "metadata": {
                    "progress": 100,
                    "result": parsed_result,
                    "task_type": "compare_contracts",
                    "similarity_score": similarity_score,
                    "missing_clauses": missing_clauses
                }
            }
            
        except Exception as e:
            yield {
                "type": "error",
                "content": f"Error comparando contratos: {str(e)}",
                "metadata": {"error": str(e)}
            }
    
    async def _execute_full_contract_analysis(
        self, 
        parameters: Dict[str, Any]
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """Execute comprehensive contract analysis"""
        
        try:
            document_content = parameters.get("document_content", "")
            
            if not document_content:
                yield {
                    "type": "error",
                    "content": "Contenido del contrato requerido para análisis completo",
                    "metadata": {"error_type": "missing_content"}
                }
                return
            
            # Multi-step analysis
            analysis_steps = [
                ("extract_clauses", "Extrayendo cláusulas clave"),
                ("analyze_risks", "Analizando riesgos"), 
                ("check_compliance", "Verificando cumplimiento"),
                ("manage_renewals", "Identificando fechas críticas")
            ]
            
            full_results = {}
            
            for i, (step_name, step_description) in enumerate(analysis_steps):
                progress = int(((i + 1) / len(analysis_steps)) * 90)
                
                yield {
                    "type": "analysis_progress",
                    "content": f"Paso {i+1}/{len(analysis_steps)}: {step_description}",
                    "metadata": {"progress": progress, "step": step_name}
                }
                
                # Execute step
                step_result = await self._execute_analysis_step(step_name, document_content)
                full_results[step_name] = step_result
                
                # Brief delay to simulate processing
                await asyncio.sleep(0.5)
            
            # Generate comprehensive summary
            comprehensive_summary = await self._generate_comprehensive_summary(full_results)
            
            yield {
                "type": "analysis_complete",
                "content": "🎯 Análisis integral del contrato completado",
                "metadata": {
                    "progress": 100,
                    "task_type": "full_analysis",
                    "full_results": full_results,
                    "comprehensive_summary": comprehensive_summary,
                    "analysis_timestamp": datetime.now().isoformat()
                }
            }
            
        except Exception as e:
            yield {
                "type": "error",
                "content": f"Error en análisis completo: {str(e)}",
                "metadata": {"error": str(e)}
            }
    
    async def _generate_comprehensive_summary(
        self, 
        analysis_results: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Generate comprehensive analysis summary"""
        
        summary = {
            "executive_summary": "",
            "overall_risk_assessment": "medium",
            "key_findings": [],
            "critical_action_items": [],
            "recommendations": [],
            "compliance_status": "unknown",
            "financial_implications": [],
            "legal_considerations": [],
            "next_steps": []
        }
        
        # Process clause extraction results
        if "extract_clauses" in analysis_results:
            clause_data = analysis_results["extract_clauses"].get("data", {})
            high_risk_clauses = clause_data.get("high_risk_clauses", [])
            if high_risk_clauses:
                summary["key_findings"].append(f"Identificadas {len(high_risk_clauses)} cláusulas de alto riesgo")
                summary["critical_action_items"].extend([
                    f"Revisar cláusula de {clause}" for clause in high_risk_clauses[:3]
                ])
        
        # Process risk analysis results
        if "analyze_risks" in analysis_results:
            risk_data = analysis_results["analyze_risks"].get("data", {})
            overall_score = risk_data.get("overall_risk_score", 0)
            
            if overall_score >= 70:
                summary["overall_risk_assessment"] = "high"
                summary["executive_summary"] = "CONTRATO DE ALTO RIESGO - Requiere revisión legal inmediata"
                summary["critical_action_items"].append("Obtener revisión legal antes de firmar")
            elif overall_score >= 40:
                summary["overall_risk_assessment"] = "medium"
                summary["executive_summary"] = "Contrato con riesgos moderados - Revisar términos clave"
            else:
                summary["overall_risk_assessment"] = "low"
                summary["executive_summary"] = "Contrato con riesgos bajos - Aceptable con revisión mínima"
            
            # Extract critical risks
            critical_risks = risk_data.get("critical_risks", [])
            for risk in critical_risks:
                summary["critical_action_items"].append(f"CRÍTICO: {risk.get('description', '')}")
        
        # Process compliance results
        if "check_compliance" in analysis_results:
            compliance_data = analysis_results["check_compliance"].get("data", {})
            compliance_score = compliance_data.get("overall_compliance_score", 0)
            
            if compliance_score >= 80:
                summary["compliance_status"] = "compliant"
            elif compliance_score >= 60:
                summary["compliance_status"] = "partially_compliant"
                summary["legal_considerations"].append("Abordar elementos de cumplimiento parcial")
            else:
                summary["compliance_status"] = "non_compliant"
                summary["critical_action_items"].append("URGENTE: Corregir problemas de cumplimiento")
        
        # Process renewal management results
        if "manage_renewals" in analysis_results:
            renewal_data = analysis_results["manage_renewals"].get("data", {})
            upcoming_deadlines = renewal_data.get("upcoming_deadlines", [])
            
            for deadline in upcoming_deadlines[:3]:  # Top 3 upcoming
                days_until = deadline.get("days_until", 0)
                if days_until <= 30:
                    summary["critical_action_items"].append(
                        f"URGENTE: {deadline.get('description', '')} en {days_until} días"
                    )
        
        # Generate final recommendations
        if summary["overall_risk_assessment"] == "high":
            summary["recommendations"].extend([
                "Obtener revisión legal especializada",
                "Negociar modificaciones a cláusulas de alto riesgo",
                "Considerar seguros adicionales si es necesario"
            ])
        
        if summary["compliance_status"] in ["non_compliant", "partially_compliant"]:
            summary["recommendations"].append("Actualizar contrato para cumplimiento normativo completo")
        
        # Next steps
        summary["next_steps"] = [
            "Revisar elementos críticos identificados",
            "Consultar con equipo legal si es necesario",
            "Documentar decisiones y justificaciones",
            "Establecer calendario para seguimiento de fechas clave"
        ]
        
        return summary
    
    async def cleanup(self):
        """Clean up resources"""
        try:
            if hasattr(self, 'http_client'):
                await self.http_client.aclose()
            logger.info(f"Cleaned up ContractAnalysisLangroidAgent {self.agent_id}")
        except Exception as e:
            logger.error(f"Error cleaning up contract agent: {str(e)}")