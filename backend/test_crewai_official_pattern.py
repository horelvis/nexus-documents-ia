#!/usr/bin/env python3
"""
Test oficial de CrewAI siguiendo patrones correctos de la documentación
Prueba básica sin dependencias externas complejas
"""
import os
import asyncio
from datetime import datetime
from crewai import Agent, Task, Crew, Process
from crewai.tools import tool

# Configurar variables de entorno básicas
os.environ["OPENAI_API_KEY"] = os.getenv("OPENAI_API_KEY", "fake-key-for-test")

@tool("current_time")
def current_time() -> str:
    """Get the current time and date"""
    now = datetime.now()
    return f"Fecha y hora actual: {now.strftime('%Y-%m-%d %H:%M:%S')}"

@tool("simple_calculator")
def simple_calculator(expression: str) -> str:
    """Calculate simple mathematical expressions like '2+2' or '10*5'"""
    try:
        # Validar entrada por seguridad
        allowed_chars = "0123456789+-*/(). "
        if not all(c in allowed_chars for c in expression):
            return "Error: Solo números y operadores básicos permitidos"
        
        result = eval(expression)
        return f"Resultado: {expression} = {result}"
    except Exception as e:
        return f"Error en cálculo: {str(e)}"

@tool("simple_search")
def simple_search(query: str) -> str:
    """Simulate a simple search without external APIs"""
    # Simular búsqueda básica sin APIs externas
    responses = {
        "inteligencia artificial": "La inteligencia artificial (IA) es una rama de la informática que se centra en crear sistemas capaces de realizar tareas que normalmente requieren inteligencia humana.",
        "python": "Python es un lenguaje de programación de alto nivel, interpretado y de propósito general conocido por su sintaxis clara y legible.",
        "crewai": "CrewAI es un framework para orquestar agentes de IA autónomos que colaboran en tareas complejas mediante roles específicos."
    }
    
    query_lower = query.lower()
    for key, response in responses.items():
        if key in query_lower:
            return f"Información encontrada sobre '{query}': {response}"
    
    return f"No tengo información específica sobre '{query}' en mi base de conocimiento limitada."

def create_simple_agent():
    """Crear un agente simple con herramientas básicas"""
    return Agent(
        role="Asistente de Información",
        goal="Ayudar a los usuarios con información, cálculos y consultas básicas",
        backstory="""Eres un asistente virtual útil que puede:
        - Proporcionar la hora actual
        - Realizar cálculos matemáticos simples  
        - Buscar información básica
        
        IMPORTANTE: Siempre usa las herramientas disponibles cuando el usuario lo requiera.
        No inventes información, usa solo lo que las herramientas te proporcionan.""",
        tools=[current_time, simple_calculator, simple_search],
        verbose=True,
        allow_delegation=False,
        memory=False
    )

def create_simple_task(agent, query):
    """Crear una tarea simple"""
    return Task(
        description=f"""
        Responde a la siguiente consulta del usuario: "{query}"
        
        INSTRUCCIONES:
        - Si el usuario pregunta por la hora, usa la herramienta current_time
        - Si el usuario pide un cálculo, usa la herramienta simple_calculator
        - Si el usuario busca información, usa la herramienta simple_search
        - Proporciona una respuesta clara y útil basada en los resultados de las herramientas
        """,
        expected_output="Una respuesta clara y útil que incluya los resultados de las herramientas cuando sea apropiado",
        agent=agent
    )

async def test_official_crewai():
    """Test principal siguiendo el patrón oficial"""
    
    print("🚀 Iniciando test oficial de CrewAI...")
    
    # Queries de prueba
    test_queries = [
        "¿Qué hora es ahora?",
        "Calcula 15 * 8 + 25",
        "Busca información sobre inteligencia artificial",
        "Dime sobre CrewAI"
    ]
    
    for i, query in enumerate(test_queries, 1):
        print(f"\n{'='*60}")
        print(f"🧪 TEST {i}/4: {query}")
        print(f"{'='*60}")
        
        try:
            # Crear agente con herramientas
            agent = create_simple_agent()
            
            # Crear tarea
            task = create_simple_task(agent, query)
            
            # Crear crew (equipo)
            crew = Crew(
                agents=[agent],
                tasks=[task],
                process=Process.sequential,
                verbose=True
            )
            
            # Ejecutar
            print(f"⚡ Ejecutando crew para: {query}")
            result = await asyncio.to_thread(crew.kickoff)
            
            print(f"\n✅ RESULTADO #{i}:")
            print(f"📝 {result}")
            print(f"✅ Test exitoso")
            
        except Exception as e:
            print(f"❌ Error en test #{i}: {e}")
            import traceback
            traceback.print_exc()
    
    print(f"\n🎉 Test oficial CrewAI completado")

if __name__ == "__main__":
    asyncio.run(test_official_crewai())