"""
Multi-Agent Workflow Examples using LangGraph + CrewAI
Demonstrates various patterns for agent collaboration and memory sharing
"""
from typing import Dict, Any, List, Optional
from langgraph.graph import StateGraph, END
from crewai import Agent, Task, Crew, Process
from langchain_core.messages import HumanMessage, SystemMessage
from loguru import logger
import asyncio
from datetime import datetime

from app.services.memory_manager import UnifiedMemoryManager
from app.services.agent_factory import NexusAgentFactory


class FinancialAuditWorkflow:
    """
    Multi-agent workflow for comprehensive financial document audit
    Demonstrates hierarchical crew organization with memory sharing
    """
    
    def __init__(self, llm, memory_manager: UnifiedMemoryManager):
        self.llm = llm
        self.memory = memory_manager
        self.agent_factory = NexusAgentFactory(llm)
    
    async def audit_financial_documents(
        self,
        documents: List[Dict[str, Any]],
        audit_requirements: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Execute comprehensive financial audit with multiple specialist agents"""
        
        # Phase 1: Document Analysis Crew
        analysis_crew = self._create_analysis_crew()
        
        # Analyze each document
        document_analyses = []
        for doc in documents:
            # Retrieve relevant memories for this document type
            memories = await self.memory.retrieve_relevant_memories(
                query=f"Analyze {doc['type']} document",
                context={'task_type': 'financial_analysis'},
                memory_types=['procedural', 'semantic']
            )
            
            # Execute analysis with memory context
            analysis = await self._execute_analysis_crew(
                analysis_crew,
                doc,
                memories
            )
            document_analyses.append(analysis)
            
            # Store successful patterns
            await self.memory.store_interaction(
                agent_id='analysis_crew',
                task=f"Analyze {doc['type']}",
                result=analysis,
                metadata={
                    'task_type': 'financial_analysis',
                    'document_type': doc['type'],
                    'success': True,
                    'effectiveness_score': 0.9
                }
            )
        
        # Phase 2: Compliance Review Crew
        compliance_crew = self._create_compliance_crew()
        
        compliance_results = await self._execute_compliance_crew(
            compliance_crew,
            document_analyses,
            audit_requirements
        )
        
        # Phase 3: Synthesis and Reporting
        report = await self._synthesize_audit_report(
            document_analyses,
            compliance_results,
            audit_requirements
        )
        
        return {
            'audit_report': report,
            'document_analyses': document_analyses,
            'compliance_results': compliance_results,
            'timestamp': datetime.utcnow().isoformat()
        }
    
    def _create_analysis_crew(self) -> Crew:
        """Create crew for document analysis phase"""
        
        # Create specialized agents
        invoice_analyst = self.agent_factory.create_agent('invoice_analyst')
        expense_tracker = self.agent_factory.create_agent('expense_tracker')
        
        # Define tasks
        invoice_task = Task(
            description="Extract and validate all invoice data including line items, taxes, and totals",
            agent=invoice_analyst,
            expected_output="Structured invoice data with validation flags"
        )
        
        expense_task = Task(
            description="Categorize all expenses and identify any unusual patterns",
            agent=expense_tracker,
            expected_output="Categorized expense report with anomaly flags"
        )
        
        # Create crew with sequential process
        return Crew(
            agents=[invoice_analyst, expense_tracker],
            tasks=[invoice_task, expense_task],
            process=Process.sequential,
            verbose=True
        )
    
    def _create_compliance_crew(self) -> Crew:
        """Create crew for compliance review phase"""
        
        compliance_officer = self.agent_factory.create_agent('compliance_officer')
        
        # Add memory-enhanced capabilities
        compliance_officer.backstory += """
        You have access to historical compliance issues and resolutions.
        Use this knowledge to identify potential problems early.
        """
        
        compliance_task = Task(
            description="Review all financial documents for compliance with regulations and company policies",
            agent=compliance_officer,
            expected_output="Compliance report with issues and recommendations"
        )
        
        return Crew(
            agents=[compliance_officer],
            tasks=[compliance_task],
            process=Process.sequential
        )
    
    async def _execute_analysis_crew(
        self,
        crew: Crew,
        document: Dict[str, Any],
        memories: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Execute analysis crew with memory context"""
        
        # Enhance crew context with memories
        context = {
            'document': document,
            'similar_analyses': memories.get('episodic', [])[:3],
            'known_patterns': memories.get('procedural', [])
        }
        
        # Execute crew (simulated for POC)
        result = {
            'document_id': document.get('id'),
            'extracted_data': {
                'total_amount': 1500.00,
                'tax_amount': 150.00,
                'line_items': 5
            },
            'validation_results': {
                'totals_valid': True,
                'tax_calculation_valid': True
            },
            'expense_categories': {
                'office_supplies': 500.00,
                'software': 1000.00
            },
            'anomalies': []
        }
        
        return result
    
    async def _execute_compliance_crew(
        self,
        crew: Crew,
        analyses: List[Dict[str, Any]],
        requirements: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Execute compliance review crew"""
        
        # Check against requirements
        compliance_results = {
            'compliant': True,
            'issues': [],
            'warnings': [
                "Invoice #123 missing required approval signature"
            ],
            'recommendations': [
                "Implement automated approval workflow"
            ]
        }
        
        return compliance_results
    
    async def _synthesize_audit_report(
        self,
        analyses: List[Dict[str, Any]],
        compliance: Dict[str, Any],
        requirements: Dict[str, Any]
    ) -> str:
        """Synthesize final audit report"""
        
        # Use LLM to create comprehensive report
        messages = [
            SystemMessage(content="You are an audit report specialist. Create a professional audit report."),
            HumanMessage(content=f"""
Create a comprehensive financial audit report based on:

Document Analyses:
{analyses}

Compliance Results:
{compliance}

Audit Requirements:
{requirements}

Include:
1. Executive Summary
2. Detailed Findings
3. Compliance Status
4. Recommendations
5. Action Items
""")
        ]
        
        response = await self.llm.ainvoke(messages)
        
        return response.content


class ResearchSynthesisWorkflow:
    """
    Multi-agent workflow for research and synthesis
    Demonstrates parallel crew execution with result fusion
    """
    
    def __init__(self, llm, memory_manager: UnifiedMemoryManager):
        self.llm = llm
        self.memory = memory_manager
        self.agent_factory = NexusAgentFactory(llm)
    
    async def research_and_synthesize(
        self,
        research_query: str,
        scope: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Execute parallel research with multiple specialist agents"""
        
        # Create parallel research crews
        crews = await self._create_parallel_research_crews(research_query, scope)
        
        # Execute crews in parallel
        research_results = await self._execute_parallel_research(crews, research_query)
        
        # Fuse results with memory context
        fused_insights = await self._fuse_research_results(research_results)
        
        # Generate synthesis
        synthesis = await self._generate_synthesis(
            research_query,
            fused_insights,
            scope
        )
        
        # Store successful research pattern
        await self.memory.store_interaction(
            agent_id='research_synthesis_workflow',
            task=research_query,
            result=synthesis,
            metadata={
                'task_type': 'research_synthesis',
                'scope': scope,
                'agents_used': len(crews),
                'success': True,
                'effectiveness_score': 0.85
            }
        )
        
        return {
            'synthesis': synthesis,
            'research_results': research_results,
            'insights': fused_insights,
            'confidence_score': 0.85
        }
    
    async def _create_parallel_research_crews(
        self,
        query: str,
        scope: Dict[str, Any]
    ) -> List[Crew]:
        """Create multiple specialized research crews"""
        
        crews = []
        
        # Technical Research Crew
        if scope.get('include_technical', True):
            tech_researcher = self.agent_factory.create_agent('research_specialist')
            tech_researcher.goal = "Find technical documentation and implementation details"
            
            tech_task = Task(
                description=f"Research technical aspects of: {query}",
                agent=tech_researcher,
                expected_output="Technical findings with sources"
            )
            
            crews.append(Crew(
                agents=[tech_researcher],
                tasks=[tech_task],
                process=Process.sequential
            ))
        
        # Business Research Crew
        if scope.get('include_business', True):
            business_researcher = self.agent_factory.create_agent('research_specialist')
            business_researcher.goal = "Find business implications and use cases"
            
            business_task = Task(
                description=f"Research business aspects of: {query}",
                agent=business_researcher,
                expected_output="Business findings with examples"
            )
            
            crews.append(Crew(
                agents=[business_researcher],
                tasks=[business_task],
                process=Process.sequential
            ))
        
        # Legal/Compliance Research Crew
        if scope.get('include_compliance', False):
            compliance_researcher = self.agent_factory.create_agent('research_specialist')
            compliance_researcher.goal = "Find regulatory and compliance information"
            
            compliance_task = Task(
                description=f"Research compliance aspects of: {query}",
                agent=compliance_researcher,
                expected_output="Compliance findings with regulations"
            )
            
            crews.append(Crew(
                agents=[compliance_researcher],
                tasks=[compliance_task],
                process=Process.sequential
            ))
        
        return crews
    
    async def _execute_parallel_research(
        self,
        crews: List[Crew],
        query: str
    ) -> List[Dict[str, Any]]:
        """Execute research crews in parallel"""
        
        # In real implementation, would use asyncio.gather
        # For POC, simulate results
        results = []
        
        for i, crew in enumerate(crews):
            result = {
                'crew_id': f'crew_{i}',
                'findings': f"Research findings from crew {i} for: {query}",
                'sources': [
                    {'title': f'Source {j}', 'relevance': 0.8 + j*0.05}
                    for j in range(3)
                ],
                'confidence': 0.75 + i*0.05
            }
            results.append(result)
        
        return results
    
    async def _fuse_research_results(
        self,
        results: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Fuse results from multiple research crews"""
        
        # Retrieve relevant semantic memories
        all_findings = ' '.join([r['findings'] for r in results])
        
        memories = await self.memory.retrieve_relevant_memories(
            query=all_findings,
            context={'task_type': 'research_synthesis'},
            memory_types=['semantic'],
            limit=10
        )
        
        # Fuse insights
        fused = {
            'key_findings': [
                "Finding 1 from multiple sources",
                "Finding 2 corroborated by memory",
                "Finding 3 unique insight"
            ],
            'consensus_points': [
                "All crews agree on point A",
                "Majority agree on point B"
            ],
            'contradictions': [],
            'memory_insights': len(memories.get('semantic', [])),
            'confidence': sum(r['confidence'] for r in results) / len(results)
        }
        
        return fused
    
    async def _generate_synthesis(
        self,
        query: str,
        insights: Dict[str, Any],
        scope: Dict[str, Any]
    ) -> str:
        """Generate final synthesis report"""
        
        messages = [
            SystemMessage(content="You are a master synthesizer. Create comprehensive reports from research."),
            HumanMessage(content=f"""
Research Query: {query}

Fused Insights:
{insights}

Scope: {scope}

Create a well-structured synthesis that:
1. Answers the research query comprehensively
2. Highlights consensus findings
3. Notes any contradictions
4. Provides actionable recommendations
5. Includes confidence levels
""")
        ]
        
        response = await self.llm.ainvoke(messages)
        
        return response.content


class DocumentProcessingPipeline:
    """
    Advanced document processing pipeline with specialized agent teams
    Demonstrates agent handoffs and progressive enhancement
    """
    
    def __init__(self, llm, memory_manager: UnifiedMemoryManager):
        self.llm = llm
        self.memory = memory_manager
        self.agent_factory = NexusAgentFactory(llm)
    
    async def process_document_with_agents(
        self,
        document: Dict[str, Any],
        processing_requirements: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Process document through multiple agent stages"""
        
        # Stage 1: Initial Analysis
        initial_analysis = await self._stage1_initial_analysis(document)
        
        # Stage 2: Deep Processing based on document type
        deep_processing = await self._stage2_deep_processing(
            document,
            initial_analysis,
            processing_requirements
        )
        
        # Stage 3: Quality Enhancement
        enhanced_result = await self._stage3_quality_enhancement(
            deep_processing,
            processing_requirements
        )
        
        # Stage 4: Final Review and Package
        final_package = await self._stage4_final_review(
            enhanced_result,
            processing_requirements
        )
        
        return final_package
    
    async def _stage1_initial_analysis(
        self,
        document: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Initial document analysis by generalist agent"""
        
        analyst = self.agent_factory.create_agent('analyst')
        
        initial_task = Task(
            description=f"Perform initial analysis of document: {document['filename']}",
            agent=analyst,
            expected_output="Document type, structure, and key elements identified"
        )
        
        crew = Crew(
            agents=[analyst],
            tasks=[initial_task],
            process=Process.sequential
        )
        
        # Execute analysis
        result = {
            'document_type': 'invoice',
            'structure': {
                'has_header': True,
                'has_line_items': True,
                'has_totals': True
            },
            'language': 'en',
            'quality_score': 0.8
        }
        
        return result
    
    async def _stage2_deep_processing(
        self,
        document: Dict[str, Any],
        initial_analysis: Dict[str, Any],
        requirements: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Deep processing by specialist agents based on document type"""
        
        # Select specialists based on document type
        if initial_analysis['document_type'] == 'invoice':
            specialists = [
                self.agent_factory.create_agent('invoice_analyst'),
                self.agent_factory.create_agent('expense_tracker')
            ]
        else:
            specialists = [
                self.agent_factory.create_agent('research_specialist'),
                self.agent_factory.create_agent('summarizer')
            ]
        
        # Create tasks for specialists
        tasks = []
        for specialist in specialists:
            task = Task(
                description=f"Process document according to your specialty",
                agent=specialist,
                expected_output="Specialized processing results"
            )
            tasks.append(task)
        
        # Create crew with parallel processing
        crew = Crew(
            agents=specialists,
            tasks=tasks,
            process=Process.parallel if len(specialists) > 1 else Process.sequential
        )
        
        # Execute deep processing
        result = {
            'extracted_data': {
                'invoice_number': 'INV-001',
                'amount': 1500.00,
                'vendor': 'Tech Supplies Co'
            },
            'categorizations': {
                'expense_type': 'office_supplies',
                'tax_category': 'deductible'
            },
            'processing_notes': []
        }
        
        return result
    
    async def _stage3_quality_enhancement(
        self,
        processing_result: Dict[str, Any],
        requirements: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Enhance quality with editor and fact-checker agents"""
        
        # Create quality enhancement crew
        fact_checker = self.agent_factory.create_agent('fact_checker')
        editor = self.agent_factory.create_agent('editor')
        
        # Fact checking task
        fact_task = Task(
            description="Verify all extracted data and cross-reference with known patterns",
            agent=fact_checker,
            expected_output="Verification report with confidence scores"
        )
        
        # Quality enhancement task
        edit_task = Task(
            description="Enhance data quality and ensure consistency",
            agent=editor,
            expected_output="Quality-enhanced data with improvements noted"
        )
        
        crew = Crew(
            agents=[fact_checker, editor],
            tasks=[fact_task, edit_task],
            process=Process.sequential
        )
        
        # Execute enhancement
        enhanced = processing_result.copy()
        enhanced['verification'] = {
            'data_verified': True,
            'confidence': 0.95,
            'issues_found': []
        }
        enhanced['quality_improvements'] = [
            "Standardized date formats",
            "Normalized vendor names"
        ]
        
        return enhanced
    
    async def _stage4_final_review(
        self,
        enhanced_result: Dict[str, Any],
        requirements: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Final review and packaging by senior analyst"""
        
        # Retrieve best practices from memory
        best_practices = await self.memory.retrieve_relevant_memories(
            query="document processing final review",
            context={'task_type': 'quality_assurance'},
            memory_types=['procedural']
        )
        
        # Create final review agent with memory context
        senior_analyst = self.agent_factory.create_agent(
            'analyst',
            memory_context={'procedural': best_practices.get('procedural', [])}
        )
        
        review_task = Task(
            description="Perform final review and create deliverable package",
            agent=senior_analyst,
            expected_output="Final approved package with all components"
        )
        
        crew = Crew(
            agents=[senior_analyst],
            tasks=[review_task],
            process=Process.sequential
        )
        
        # Create final package
        final_package = {
            'status': 'approved',
            'processed_data': enhanced_result,
            'metadata': {
                'processing_stages': 4,
                'agents_involved': 6,
                'total_confidence': 0.92,
                'processing_time': '45 seconds'
            },
            'deliverables': {
                'structured_data': enhanced_result['extracted_data'],
                'verification_report': enhanced_result['verification'],
                'quality_notes': enhanced_result['quality_improvements']
            }
        }
        
        # Store successful processing pattern
        await self.memory.store_interaction(
            agent_id='document_processing_pipeline',
            task=f"Process {enhanced_result.get('document_type', 'document')}",
            result=final_package,
            metadata={
                'task_type': 'document_processing',
                'stages_completed': 4,
                'success': True,
                'effectiveness_score': 0.92
            }
        )
        
        return final_package


# Example usage function
async def demonstrate_workflows(llm, memory_manager):
    """Demonstrate various multi-agent workflows"""
    
    # Example 1: Financial Audit
    audit_workflow = FinancialAuditWorkflow(llm, memory_manager)
    
    audit_result = await audit_workflow.audit_financial_documents(
        documents=[
            {'id': 'doc1', 'type': 'invoice', 'content': 'Invoice content...'},
            {'id': 'doc2', 'type': 'expense_report', 'content': 'Expense content...'}
        ],
        audit_requirements={
            'compliance_standards': ['SOX', 'GAAP'],
            'focus_areas': ['tax_compliance', 'expense_validation']
        }
    )
    
    logger.info(f"Audit completed with {len(audit_result['document_analyses'])} documents analyzed")
    
    # Example 2: Research and Synthesis
    research_workflow = ResearchSynthesisWorkflow(llm, memory_manager)
    
    research_result = await research_workflow.research_and_synthesize(
        research_query="Best practices for AI agent orchestration",
        scope={
            'include_technical': True,
            'include_business': True,
            'include_compliance': False
        }
    )
    
    logger.info(f"Research completed with confidence: {research_result['confidence_score']}")
    
    # Example 3: Document Processing Pipeline
    processing_pipeline = DocumentProcessingPipeline(llm, memory_manager)
    
    processing_result = await processing_pipeline.process_document_with_agents(
        document={
            'id': 'doc123',
            'filename': 'invoice_2024_001.pdf',
            'content': 'Document content...'
        },
        processing_requirements={
            'extract_structured_data': True,
            'verify_accuracy': True,
            'enhance_quality': True
        }
    )
    
    logger.info(f"Document processed through {processing_result['metadata']['processing_stages']} stages")
    
    return {
        'audit_result': audit_result,
        'research_result': research_result,
        'processing_result': processing_result
    }