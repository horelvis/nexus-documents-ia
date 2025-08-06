"""
Virtual Assistant implementado con CrewAI
TODO lo que necesitas YA está hecho en el framework
"""
from typing import Dict, Any, List, Optional
from datetime import datetime
from crewai import Agent, Task, Crew, Process
from crewai_tools import (
    DirectoryReadTool,
    FileReadTool, 
    SerperDevTool,
    WebsiteSearchTool,
    PDFSearchTool,
    DOCXSearchTool,
    CSVSearchTool
)
from crewai.memory import ShortTermMemory, LongTermMemory
from loguru import logger


class CrewAIVirtualAssistant:
    """
    Asistente Virtual usando CrewAI - Framework completo
    """
    
    def __init__(self, tenant_id: str):
        self.tenant_id = tenant_id
        self.workspace = f"/workspace/{tenant_id}"
        
        # Configurar herramientas
        self.tools = self._setup_tools()
        
        # Crear agentes especializados
        self.agents = self._create_agents()
        
        # Configurar crew (equipo de agentes)
        self.crew = self._setup_crew()
    
    def _setup_tools(self) -> List:
        """Configurar herramientas disponibles"""
        return [
            # Búsqueda de documentos
            DirectoryReadTool(directory=self.workspace),
            PDFSearchTool(directory=self.workspace),
            DOCXSearchTool(directory=self.workspace),
            CSVSearchTool(directory=self.workspace),
            
            # Lectura de archivos
            FileReadTool(),
            
            # Búsqueda web (si necesario)
            # SerperDevTool(),
            # WebsiteSearchTool(),
        ]
    
    def _create_agents(self) -> List[Agent]:
        """Crear agentes especializados"""
        
        # Agente de búsqueda de documentos
        search_agent = Agent(
            role='Document Searcher',
            goal='Find relevant documents based on user queries',
            backstory="""You are an expert at searching through documents 
                        and finding the most relevant information.""",
            tools=self.tools,
            llm='ollama/llama3.2',  # Usar Ollama local
            verbose=True,
            allow_delegation=False,
            max_iter=3
        )
        
        # Agente de análisis
        analyst_agent = Agent(
            role='Document Analyst',
            goal='Analyze documents and extract key information',
            backstory="""You are a senior analyst specialized in 
                        understanding complex documents and extracting insights.""",
            tools=self.tools,
            llm='ollama/gemma3:12b',  # Modelo más potente para análisis
            verbose=True,
            allow_delegation=True,  # Puede delegar a search_agent
            max_iter=5
        )
        
        # Agente de síntesis/respuesta
        response_agent = Agent(
            role='Response Synthesizer',
            goal='Provide clear, accurate answers to user questions',
            backstory="""You are an expert communicator who can synthesize 
                        complex information into clear, actionable responses.""",
            llm='ollama/llama3.2',
            verbose=True,
            allow_delegation=False
        )
        
        # Agente de cumplimiento (opcional)
        compliance_agent = Agent(
            role='Compliance Officer',
            goal='Ensure documents meet regulatory requirements',
            backstory="""You are a compliance expert who ensures all 
                        documents meet legal and regulatory standards.""",
            tools=self.tools,
            llm='ollama/llama3.2',
            verbose=True
        )
        
        return [search_agent, analyst_agent, response_agent, compliance_agent]
    
    def _setup_crew(self) -> Crew:
        """Configurar el equipo de agentes"""
        return Crew(
            agents=self.agents[:3],  # Usar los 3 primeros por defecto
            process=Process.sequential,  # Proceso secuencial
            memory=True,  # Activar memoria
            cache=True,   # Activar cache
            max_rpm=100,  # Límite de requests
            share_crew=False,  # No compartir entre tenants
            verbose=True,
            embedder={
                "provider": "ollama",
                "config": {
                    "model": "nomic-embed-text",
                    "base_url": "http://ollama-service:11434"
                }
            },
            # Configuración de LLM manager
            manager_llm="ollama/llama3.2",
            function_calling_llm="ollama/gemma3:12b"
        )
    
    async def process_query(
        self,
        query: str,
        user_id: str,
        context: Optional[Dict] = None
    ) -> Dict[str, Any]:
        """Procesar consulta del usuario"""
        
        try:
            # Crear tareas basadas en la consulta
            tasks = self._create_tasks(query, context)
            
            # Ejecutar crew
            logger.info(f"Processing query for tenant {self.tenant_id}: {query}")
            
            # Kickoff asíncrono con streaming
            result = await self.crew.kickoff_async(
                inputs={
                    "query": query,
                    "tenant_id": self.tenant_id,
                    "user_id": user_id,
                    "context": context or {}
                }
            )
            
            return {
                "success": True,
                "query": query,
                "answer": result.raw_output,
                "tasks_output": [
                    {
                        "task": task.description[:100],
                        "output": task.output.raw_output if task.output else None
                    }
                    for task in result.tasks_output
                ],
                "token_usage": result.token_usage,
                "engine": "crewai"
            }
            
        except Exception as e:
            logger.error(f"CrewAI error: {e}")
            return {
                "success": False,
                "error": str(e),
                "query": query
            }
    
    def _create_tasks(self, query: str, context: Optional[Dict]) -> List[Task]:
        """Crear tareas dinámicamente basadas en la consulta"""
        
        tasks = []
        
        # Tarea 1: Búsqueda de documentos
        search_task = Task(
            description=f"""Search for documents related to: {query}
                          Find the most relevant documents in the workspace.""",
            agent=self.agents[0],  # search_agent
            expected_output="List of relevant documents with summaries"
        )
        tasks.append(search_task)
        
        # Tarea 2: Análisis de documentos
        analysis_task = Task(
            description=f"""Analyze the found documents and extract:
                          1. Key information related to the query
                          2. Important entities (people, dates, amounts)
                          3. Relevant insights and patterns
                          Query: {query}""",
            agent=self.agents[1],  # analyst_agent
            expected_output="Detailed analysis with extracted information",
            context=[search_task]  # Depende de search_task
        )
        tasks.append(analysis_task)
        
        # Tarea 3: Generar respuesta
        response_task = Task(
            description=f"""Based on the analysis, provide a comprehensive answer to:
                          {query}
                          
                          The answer should be:
                          - Clear and concise
                          - Include relevant document references
                          - Provide actionable insights
                          - In Spanish if the query is in Spanish""",
            agent=self.agents[2],  # response_agent
            expected_output="Clear, comprehensive answer to the user query",
            context=[search_task, analysis_task]  # Depende de ambas
        )
        tasks.append(response_task)
        
        return tasks
    
    async def analyze_document(
        self,
        document_path: str,
        analysis_type: str = "comprehensive"
    ) -> Dict[str, Any]:
        """Analizar un documento específico"""
        
        # Crear agente especializado para el tipo de análisis
        if analysis_type == "contract":
            agents = [self.agents[3]]  # compliance_agent
        else:
            agents = self.agents[:3]
        
        # Crear crew específico para análisis
        analysis_crew = Crew(
            agents=agents,
            process=Process.sequential,
            memory=True,
            verbose=True
        )
        
        # Crear tareas de análisis
        tasks = [
            Task(
                description=f"""Analyze the document at {document_path}:
                              1. Extract key information
                              2. Identify important clauses
                              3. Find risks and opportunities
                              4. Provide recommendations""",
                agent=agents[0],
                expected_output="Comprehensive document analysis"
            )
        ]
        
        # Ejecutar análisis
        result = await analysis_crew.kickoff_async(
            inputs={"document_path": document_path}
        )
        
        return {
            "success": True,
            "analysis": result.raw_output,
            "document_path": document_path,
            "analysis_type": analysis_type
        }
    
    async def chat(
        self,
        message: str,
        chat_history: List[Dict] = None
    ) -> Dict[str, Any]:
        """Chat conversacional con memoria"""
        
        # CrewAI mantiene automáticamente el contexto con memory=True
        
        # Crear tarea de chat
        chat_task = Task(
            description=f"""Respond to the user message: {message}
                          Consider the conversation history if available.
                          Be helpful, accurate, and friendly.""",
            agent=self.agents[2],  # response_agent
            expected_output="Natural, helpful response"
        )
        
        # Ejecutar con contexto de chat
        result = await self.crew.kickoff_async(
            inputs={
                "message": message,
                "history": chat_history or []
            }
        )
        
        return {
            "success": True,
            "response": result.raw_output,
            "engine": "crewai-chat"
        }


# Ejemplo de uso
async def test_crewai():
    """Test CrewAI Virtual Assistant"""
    
    assistant = CrewAIVirtualAssistant(tenant_id="test-tenant")
    
    # Test query
    result = await assistant.process_query(
        query="¿Qué documentos tenemos sobre contratos?",
        user_id="test-user"
    )
    
    print(f"Success: {result.get('success')}")
    print(f"Answer: {result.get('answer')}")
    print(f"Engine: {result.get('engine')}")
    
    return result