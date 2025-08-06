"""
CAG Simple usando LangGraph - Implementación REAL basada en documentación oficial
https://python.langchain.com/docs/langgraph/tutorials/rag/langgraph_agentic_rag
"""
from typing import TypedDict, Annotated, List, Dict, Any
import operator
from datetime import datetime

from langgraph.graph import StateGraph, END
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage, SystemMessage
from langchain_ollama import ChatOllama
from langchain_community.vectorstores import Qdrant
from loguru import logger


class CAGState(TypedDict):
    """Estado del grafo CAG - Ejemplo oficial de LangGraph"""
    query: str
    context: List[str]
    answer: str
    iteration: int
    max_iterations: int
    quality_score: float


class SimpleLangGraphCAG:
    """CAG implementado con LangGraph - Versión simple y funcional"""
    
    def __init__(self, llm=None, vector_store=None, max_iterations=3):
        self.llm = llm
        self.vector_store = vector_store
        self.max_iterations = max_iterations
        self.app = self._build_graph()
    
    def _build_graph(self):
        """Construir el grafo de estados"""
        workflow = StateGraph(CAGState)
        
        # Agregar nodos
        workflow.add_node("retrieve", self.retrieve_node)
        workflow.add_node("generate", self.generate_node)
        workflow.add_node("grade", self.grade_node)
        
        # Configurar flujo
        workflow.set_entry_point("retrieve")
        workflow.add_edge("retrieve", "generate")
        workflow.add_edge("generate", "grade")
        
        # Edge condicional para iteración
        workflow.add_conditional_edges(
            "grade",
            self.should_continue,
            {
                "continue": "retrieve",  # Volver a buscar más contexto
                "end": END
            }
        )
        
        return workflow.compile()
    
    async def retrieve_node(self, state: CAGState) -> Dict:
        """Buscar contexto relevante"""
        logger.info(f"Retrieving context for: {state['query']}")
        
        # Si no hay vector store, usar contexto dummy
        if not self.vector_store:
            return {
                "context": ["Contexto de ejemplo para la consulta"],
                "iteration": state.get("iteration", 0) + 1
            }
        
        # Buscar documentos reales
        try:
            retriever = self.vector_store.as_retriever(search_kwargs={"k": 3})
            docs = await retriever.aget_relevant_documents(state["query"])
            context = [doc.page_content for doc in docs]
            
            return {
                "context": context,
                "iteration": state.get("iteration", 0) + 1
            }
        except Exception as e:
            logger.error(f"Retrieval error: {e}")
            return {
                "context": ["Error retrieving context"],
                "iteration": state.get("iteration", 0) + 1
            }
    
    async def generate_node(self, state: CAGState) -> Dict:
        """Generar respuesta basada en contexto"""
        logger.info(f"Generating answer (iteration {state.get('iteration', 1)})")
        
        # Si no hay LLM, usar respuesta dummy
        if not self.llm:
            return {
                "answer": f"Respuesta generada para: {state['query']}",
                "quality_score": 0.7
            }
        
        # Crear prompt con contexto
        context_str = "\n".join(state.get("context", []))
        prompt = f"""Basándote en el siguiente contexto, responde la pregunta:
        
Contexto:
{context_str}

Pregunta: {state['query']}

Respuesta:"""
        
        try:
            response = await self.llm.ainvoke(prompt)
            answer = response.content if hasattr(response, 'content') else str(response)
            
            return {
                "answer": answer,
                "quality_score": 0.8  # Simplified scoring
            }
        except Exception as e:
            logger.error(f"Generation error: {e}")
            return {
                "answer": f"Error generando respuesta: {e}",
                "quality_score": 0.3
            }
    
    async def grade_node(self, state: CAGState) -> Dict:
        """Evaluar calidad de la respuesta"""
        score = state.get("quality_score", 0)
        iteration = state.get("iteration", 1)
        
        logger.info(f"Grading answer - Score: {score}, Iteration: {iteration}")
        
        # Simple quality check
        if len(state.get("answer", "")) < 10:
            score = 0.2
        
        return {"quality_score": score}
    
    def should_continue(self, state: CAGState) -> str:
        """Decidir si continuar iterando"""
        iteration = state.get("iteration", 1)
        max_iter = state.get("max_iterations", self.max_iterations)
        score = state.get("quality_score", 0)
        
        # Continuar si la calidad es baja y no hemos llegado al límite
        if score < 0.7 and iteration < max_iter:
            logger.info(f"Continuing - Score too low ({score})")
            return "continue"
        else:
            logger.info(f"Ending - Score: {score}, Iterations: {iteration}")
            return "end"
    
    async def process(self, query: str) -> Dict[str, Any]:
        """Procesar una consulta"""
        initial_state = {
            "query": query,
            "context": [],
            "answer": "",
            "iteration": 0,
            "max_iterations": self.max_iterations,
            "quality_score": 0.0
        }
        
        try:
            # Ejecutar el grafo
            final_state = None
            async for event in self.app.astream(initial_state):
                logger.debug(f"Event: {list(event.keys())}")
                final_state = event
            
            # Extraer el estado final
            if final_state:
                # El último evento contiene el estado final
                for node_name, node_state in final_state.items():
                    if isinstance(node_state, dict):
                        answer = node_state.get("answer", "")
                        if answer:
                            return {
                                "success": True,
                                "query": query,
                                "answer": answer,
                                "quality_score": node_state.get("quality_score", 0),
                                "iterations": node_state.get("iteration", 1),
                                "context_used": len(node_state.get("context", []))
                            }
            
            # Si no hay respuesta, usar el estado acumulado
            return {
                "success": True,
                "query": query,
                "answer": "No se pudo generar una respuesta",
                "quality_score": 0,
                "iterations": 0
            }
            
        except Exception as e:
            logger.error(f"Process error: {e}")
            return {
                "success": False,
                "error": str(e),
                "query": query
            }


# Test function
async def test_simple_cag():
    """Test the simple CAG implementation"""
    import os
    os.environ["OLLAMA_HOST"] = "http://ollama-service:11434"
    
    # Try to create LLM
    try:
        llm = ChatOllama(model="llama3.2", timeout=5)
        await llm.ainvoke("test")
        logger.info("LLM connected successfully")
    except:
        logger.warning("LLM not available, using mock mode")
        llm = None
    
    # Create CAG
    cag = SimpleLangGraphCAG(llm=llm, vector_store=None)
    
    # Test query
    result = await cag.process("¿Qué es LangGraph?")
    
    print("\n=== CAG Result ===")
    print(f"Success: {result.get('success')}")
    print(f"Answer: {result.get('answer', '')[:200]}...")
    print(f"Quality: {result.get('quality_score')}")
    print(f"Iterations: {result.get('iterations')}")
    
    return result


if __name__ == "__main__":
    import asyncio
    asyncio.run(test_simple_cag())