#!/usr/bin/env python3
"""
Test de CrewAI con YAML simplificado que realmente funciona
Sin usar decoradores complejos, pero con configuración YAML
"""
import os
import asyncio
import yaml
from pathlib import Path
from crewai import Agent, Task, Crew, Process
from crewai.tools import tool
from crewai_tools import SerperDevTool

# Configurar variables de entorno
os.environ["OPENAI_API_KEY"] = os.getenv("OPENAI_API_KEY", "fake-key-for-test")

@tool("time_tool")
def time_tool() -> str:
    """Get current time and date"""
    from datetime import datetime
    now = datetime.now()
    return f"Fecha y hora actual: {now.strftime('%Y-%m-%d %H:%M:%S')}"

@tool("calculator_tool")
def calculator_tool(expression: str) -> str:
    """Calculate mathematical expressions safely"""
    try:
        allowed_chars = "0123456789+-*/(). "
        if not all(c in allowed_chars for c in expression):
            return "Error: Solo números y operadores básicos permitidos"
        result = eval(expression)
        return f"Resultado: {expression} = {result}"
    except Exception as e:
        return f"Error en cálculo: {str(e)}"

@tool("simple_search_tool")
def simple_search_tool(query: str) -> str:
    """Simple search tool using DuckDuckGo API"""
    try:
        import requests
        print(f"🔍 Buscando: {query}")
        
        search_url = "https://api.duckduckgo.com/"
        params = {
            "q": query,
            "format": "json",
            "no_html": "1",
            "skip_disambig": "1"
        }
        
        response = requests.get(search_url, params=params, timeout=10)
        if response.status_code == 200:
            data = response.json()
            abstract = data.get("Abstract", "")
            answer = data.get("Answer", "")
            
            if abstract:
                return f"Información encontrada: {abstract}"
            elif answer:
                return f"Respuesta encontrada: {answer}"
            else:
                return f"Búsqueda realizada para: {query}, pero sin resultados específicos en DuckDuckGo API"
        else:
            return f"Error en búsqueda: código {response.status_code}"
    except Exception as e:
        return f"Error al buscar: {str(e)}"

class CrewAIYAMLTest:
    """Test de CrewAI con configuración YAML simplificada"""
    
    def __init__(self):
        self.agents_config = None
        self.tasks_config = None
        self._load_configs()
    
    def _load_configs(self):
        """Cargar configuraciones YAML"""
        # Crear configuraciones en memoria (simulando archivos YAML)
        self.agents_config = {
            "virtual_assistant": {
                "role": "Intelligent Virtual Assistant",
                "goal": "Provide helpful, accurate, and contextual responses to user queries",
                "backstory": """You are a knowledgeable virtual assistant with access to tools.
                When users ask for current information, time, calculations, or searches,
                you MUST use the appropriate tools. Always provide specific, helpful responses.""",
                "verbose": True,
                "memory": True,
                "allow_delegation": False
            }
        }
        
        self.tasks_config = {
            "chat_task": {
                "description": """Respond to the user query: {user_message}
                
                IMPORTANT INSTRUCTIONS:
                - For time questions: USE the time_tool
                - For calculations: USE the calculator_tool  
                - For searches/information: USE the simple_search_tool or serper_tool
                - Always use appropriate tools when the query requires it
                - Provide clear, specific responses based on tool results""",
                "expected_output": "A helpful, accurate response that uses tools when appropriate and provides specific information"
            }
        }
    
    def create_virtual_assistant(self) -> Agent:
        """Crear agente asistente virtual desde configuración YAML"""
        config = self.agents_config['virtual_assistant']
        
        # Configurar herramientas
        tools = [time_tool, calculator_tool, simple_search_tool]
        
        # Intentar agregar SerperDevTool si está disponible
        serper_key = os.getenv("SERPER_API_KEY")
        if serper_key:
            try:
                serper_tool = SerperDevTool()
                tools.append(serper_tool)
                print(f"✅ SerperDevTool agregado (key: {serper_key[:10]}...)")
            except Exception as e:
                print(f"⚠️ SerperDevTool falló: {e}")
        else:
            print("⚠️ SERPER_API_KEY no configurada")
        
        print(f"🛠️ Agente configurado con {len(tools)} herramientas")
        
        return Agent(
            role=config['role'],
            goal=config['goal'],
            backstory=config['backstory'],
            tools=tools,
            verbose=config['verbose'],
            memory=config['memory'],
            allow_delegation=config['allow_delegation']
        )
    
    def create_chat_task(self, agent: Agent, user_message: str) -> Task:
        """Crear tarea de chat desde configuración YAML"""
        config = self.tasks_config['chat_task']
        
        return Task(
            description=config['description'].format(user_message=user_message),
            expected_output=config['expected_output'],
            agent=agent
        )
    
    async def chat(self, user_message: str) -> str:
        """Ejecutar chat usando configuración YAML"""
        try:
            print(f"💬 Procesando: {user_message}")
            
            # Crear agente desde YAML
            agent = self.create_virtual_assistant()
            
            # Crear tarea desde YAML
            task = self.create_chat_task(agent, user_message)
            
            # Crear crew
            crew = Crew(
                agents=[agent],
                tasks=[task],
                process=Process.sequential,
                verbose=True
            )
            
            # Ejecutar
            result = await asyncio.to_thread(crew.kickoff)
            return str(result)
            
        except Exception as e:
            return f"Error: {str(e)}"

async def test_yaml_crewai():
    """Test principal de CrewAI con YAML"""
    print("🚀 Test CrewAI con Configuración YAML Simplificada")
    print("="*60)
    
    serper_key = os.getenv("SERPER_API_KEY")
    if serper_key:
        print(f"✅ SERPER_API_KEY: {serper_key[:10]}...")
    else:
        print("⚠️ SERPER_API_KEY no configurada - usando herramientas personalizadas")
    
    crew_test = CrewAIYAMLTest()
    
    # Tests
    test_queries = [
        "¿Qué hora es?",
        "Calcula 20 * 6 + 50", 
        "Busca información sobre Python programming",
        "¿Cuál es la capital de Francia?"
    ]
    
    for i, query in enumerate(test_queries, 1):
        print(f"\n{'='*50}")
        print(f"🧪 TEST {i}/{len(test_queries)}: {query}")
        print(f"{'='*50}")
        
        result = await crew_test.chat(query)
        print(f"\n✅ RESULTADO:")
        print(f"📝 {result}")
        print(f"\n✅ Test {i} completado")
    
    print(f"\n🎉 Todos los tests con YAML completados")

if __name__ == "__main__":
    asyncio.run(test_yaml_crewai())