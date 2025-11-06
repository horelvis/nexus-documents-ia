#!/usr/bin/env python3
"""
Test simple de LangGraph basado en ejemplos oficiales
Documentación: https://python.langchain.com/docs/langgraph
"""
import asyncio
from typing import TypedDict, Annotated, Sequence
import operator

from langgraph.graph import StateGraph, END
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage
from langchain_ollama import ChatOllama


# 1. Definir el estado del grafo (ejemplo oficial)
class AgentState(TypedDict):
    messages: Annotated[Sequence[BaseMessage], operator.add]
    

# 2. Crear nodos simples
async def chatbot_node(state: AgentState):
    """Nodo simple que responde usando LLM"""
    print(f"Chatbot procesando {len(state['messages'])} mensajes")
    
    # Simular respuesta de LLM
    response = AIMessage(content="Soy una respuesta del chatbot")
    return {"messages": [response]}


async def should_continue(state: AgentState) -> str:
    """Decidir si continuar o terminar"""
    messages = state.get("messages", [])
    if len(messages) > 3:
        return "end"
    return "continue"


# 3. Construir el grafo
def build_simple_graph():
    workflow = StateGraph(AgentState)
    
    # Agregar nodos
    workflow.add_node("chatbot", chatbot_node)
    
    # Establecer punto de entrada
    workflow.set_entry_point("chatbot")
    
    # Agregar edge condicional
    workflow.add_conditional_edges(
        "chatbot",
        should_continue,
        {
            "continue": "chatbot",  # Loop back
            "end": END
        }
    )
    
    # Compilar
    return workflow.compile()


async def test_simple():
    """Test simple del grafo"""
    print("=== Test Simple de LangGraph ===")
    
    # Crear grafo
    app = build_simple_graph()
    
    # Estado inicial
    initial_state = {
        "messages": [HumanMessage(content="Hola")]
    }
    
    # Ejecutar
    print("\nEjecutando grafo...")
    async for event in app.astream(initial_state):
        print(f"Evento: {list(event.keys())}")
    
    print("\n✅ LangGraph funciona correctamente!")


async def test_with_ollama():
    """Test con Ollama real"""
    print("\n=== Test con Ollama ===")
    
    try:
        # Intentar conectar con Ollama
        llm = ChatOllama(
            model="llama3.2",
            base_url="http://ollama-service:11434"
        )
        
        # Test básico
        response = await llm.ainvoke("Di 'hola' en una palabra")
        print(f"Respuesta de Ollama: {response.content}")
        print("✅ Ollama conectado y funcionando!")
        
    except Exception as e:
        print(f"❌ Error con Ollama: {e}")


if __name__ == "__main__":
    # Ejecutar tests
    asyncio.run(test_simple())
    asyncio.run(test_with_ollama())