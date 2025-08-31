"""
Herramientas personalizadas siguiendo el patrón oficial de CrewAI
"""
from crewai.tools import tool
from datetime import datetime
import requests
import os

@tool("web_search_tool")
def web_search_tool(query: str) -> str:
    """Search the web for current information using DuckDuckGo API"""
    try:
        print(f"🔍 Buscando: {query}")
        
        # Usar DuckDuckGo API (sin API key requerida)
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
            
            # Buscar información relevante
            abstract = data.get("Abstract", "")
            answer = data.get("Answer", "")
            definition = data.get("Definition", "")
            
            results = []
            if answer:
                results.append(f"Respuesta directa: {answer}")
            if abstract:
                results.append(f"Información: {abstract}")
            if definition:
                results.append(f"Definición: {definition}")
            
            # Buscar en related topics si no hay resultados principales
            if not results:
                related_topics = data.get("RelatedTopics", [])
                for topic in related_topics[:3]:
                    if isinstance(topic, dict) and "Text" in topic:
                        results.append(f"Información relacionada: {topic['Text']}")
            
            if results:
                return "\n".join(results)
            else:
                return f"No se encontró información específica para: {query}"
        else:
            return f"Error en búsqueda: código {response.status_code}"
            
    except Exception as e:
        return f"Error al buscar: {str(e)}"

@tool("time_tool")
def time_tool() -> str:
    """Get current time and date"""
    now = datetime.now()
    return f"Fecha y hora actual: {now.strftime('%Y-%m-%d %H:%M:%S')}"

@tool("calculator_tool")
def calculator_tool(expression: str) -> str:
    """Calculate mathematical expressions safely"""
    try:
        # Validar entrada por seguridad
        allowed_chars = "0123456789+-*/(). "
        if not all(c in allowed_chars for c in expression):
            return "Error: Solo números y operadores básicos permitidos (+, -, *, /, ())"
        
        result = eval(expression)
        return f"Resultado: {expression} = {result}"
    except Exception as e:
        return f"Error en cálculo: {str(e)}"

@tool("weather_search_tool")
def weather_search_tool(location: str) -> str:
    """Search for weather information for a specific location"""
    try:
        # Buscar información del clima usando web search
        query = f"weather forecast {location} today current temperature"
        return web_search_tool(query)
    except Exception as e:
        return f"Error al buscar información del clima: {str(e)}"