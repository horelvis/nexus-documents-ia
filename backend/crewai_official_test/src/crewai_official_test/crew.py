"""
Implementación oficial de CrewAI usando el patrón @CrewBase con decoradores
Basado en: https://github.com/crewAIInc/crewAI-examples
"""
import os
from crewai import Agent, Crew, Process, Task
from crewai.project import CrewBase, agent, crew, task
from crewai_tools import SerperDevTool
from typing import List

# Importar herramientas personalizadas
from .tools.custom_tools import (
    web_search_tool, 
    time_tool, 
    calculator_tool, 
    weather_search_tool
)

@CrewBase
class OfficialCrewAITest():
    """
    Implementación oficial de CrewAI siguiendo el patrón con decoradores
    """
    
    def __init__(self):
        # Configurar variables de entorno
        self._setup_environment()
    
    def _setup_environment(self):
        """Configurar variables de entorno necesarias"""
        # OpenAI para LLM principal (puede ser fake para test)
        if not os.getenv("OPENAI_API_KEY"):
            os.environ["OPENAI_API_KEY"] = "fake-key-for-test"
        
        # Serper para búsqueda web oficial (opcional)
        serper_key = os.getenv("SERPER_API_KEY")
        if serper_key:
            print(f"✅ SERPER_API_KEY configurada: {serper_key[:10]}...")
        else:
            print("⚠️ SERPER_API_KEY no configurada - usando herramientas personalizadas")

    @agent
    def researcher(self) -> Agent:
        """Agente investigador con herramientas de búsqueda"""
        tools = []
        
        # Intentar usar SerperDevTool oficial si está disponible
        try:
            if os.getenv("SERPER_API_KEY"):
                serper_tool = SerperDevTool()
                tools.append(serper_tool)
                print("✅ Usando SerperDevTool oficial")
            else:
                raise Exception("No SERPER_API_KEY")
        except Exception:
            # Fallback a herramientas personalizadas
            tools = [web_search_tool, weather_search_tool]
            print("📄 Usando herramientas de búsqueda personalizadas")
        
        return Agent(
            config=self.agents_config['researcher'],
            tools=tools,
            verbose=True
        )

    @agent  
    def reporting_analyst(self) -> Agent:
        """Agente analista de reportes"""
        return Agent(
            config=self.agents_config['reporting_analyst'],
            verbose=True
        )

    @agent
    def virtual_assistant(self) -> Agent:
        """Agente asistente virtual con herramientas completas"""
        tools = []
        
        # Intentar usar herramientas oficiales primero
        try:
            if os.getenv("SERPER_API_KEY"):
                tools.append(SerperDevTool())
                print("✅ Virtual Assistant usando SerperDevTool oficial")
        except Exception:
            pass
        
        # Agregar herramientas personalizadas
        tools.extend([
            web_search_tool,
            time_tool, 
            calculator_tool,
            weather_search_tool
        ])
        
        print(f"🛠️ Virtual Assistant configurado con {len(tools)} herramientas")
        
        return Agent(
            config=self.agents_config['virtual_assistant'],
            tools=tools,
            verbose=True
        )

    @task
    def research_task(self) -> Task:
        """Tarea de investigación"""
        return Task(
            config=self.tasks_config['research_task'],
            agent=self.researcher
        )

    @task
    def reporting_task(self) -> Task:
        """Tarea de generación de reportes"""
        return Task(
            config=self.tasks_config['reporting_task'],
            agent=self.reporting_analyst
        )

    @task
    def chat_task(self) -> Task:
        """Tarea de chat/asistencia"""
        return Task(
            config=self.tasks_config['chat_task'],
            agent=self.virtual_assistant
        )

    @crew
    def crew(self) -> Crew:
        """Crew principal con todos los agentes y tareas"""
        return Crew(
            agents=self.agents,
            tasks=self.tasks,
            process=Process.sequential,
            verbose=True
        )

    # Métodos de conveniencia para diferentes tipos de operaciones
    
    def research_crew(self) -> Crew:
        """Crew específico para investigación y reportes"""
        return Crew(
            agents=[self.researcher, self.reporting_analyst],
            tasks=[self.research_task, self.reporting_task],
            process=Process.sequential,
            verbose=True
        )
    
    def chat_crew(self) -> Crew:
        """Crew específico para chat/asistencia"""
        return Crew(
            agents=[self.virtual_assistant],
            tasks=[self.chat_task],
            process=Process.sequential,
            verbose=True
        )

# Funciones de utilidad para uso directo

async def run_research(topic: str) -> str:
    """Ejecutar investigación sobre un tema"""
    import asyncio
    
    crew_instance = OfficialCrewAITest()
    research_crew = crew_instance.research_crew()
    
    inputs = {"topic": topic}
    result = await asyncio.to_thread(research_crew.kickoff, inputs=inputs)
    return str(result)

async def run_chat(user_message: str) -> str:
    """Ejecutar chat con asistente virtual"""
    import asyncio
    
    crew_instance = OfficialCrewAITest()
    chat_crew = crew_instance.chat_crew()
    
    inputs = {"user_message": user_message}
    result = await asyncio.to_thread(chat_crew.kickoff, inputs=inputs)
    return str(result)