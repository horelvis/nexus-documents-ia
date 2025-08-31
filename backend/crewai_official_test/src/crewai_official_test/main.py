#!/usr/bin/env python3
"""
Main entry point para CrewAI Official Test
Demuestra el uso del patrón oficial con decoradores @CrewBase
"""
import asyncio
import os
import sys

# Agregar el directorio padre al path para imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from crewai_official_test.crew import OfficialCrewAITest

async def test_chat():
    """Test de funcionalidad de chat"""
    print("🧪 Testing Chat Functionality")
    print("="*50)
    
    # Queries de prueba
    test_queries = [
        "¿Qué hora es?",
        "Calcula 25 * 8 + 15", 
        "Busca información sobre inteligencia artificial",
        "¿Cuál es el clima en Madrid?"
    ]
    
    crew_instance = OfficialCrewAITest()
    
    for i, query in enumerate(test_queries, 1):
        print(f"\n🔍 Test {i}: {query}")
        try:
            chat_crew = crew_instance.chat_crew()
            inputs = {"user_message": query}
            result = await asyncio.to_thread(chat_crew.kickoff, inputs=inputs)
            print(f"✅ Resultado: {result}")
        except Exception as e:
            print(f"❌ Error: {e}")
            import traceback
            traceback.print_exc()

async def test_research():
    """Test de funcionalidad de investigación"""
    print("\n🔬 Testing Research Functionality")
    print("="*50)
    
    topics = [
        "machine learning",
        "blockchain technology"
    ]
    
    crew_instance = OfficialCrewAITest()
    
    for topic in topics:
        print(f"\n📚 Investigando: {topic}")
        try:
            research_crew = crew_instance.research_crew()
            inputs = {"topic": topic}
            result = await asyncio.to_thread(research_crew.kickoff, inputs=inputs)
            print(f"✅ Reporte generado: {str(result)[:200]}...")
        except Exception as e:
            print(f"❌ Error: {e}")
            import traceback
            traceback.print_exc()

async def main():
    """Función principal"""
    print("🚀 CrewAI Official Pattern Test")
    print("Implementación con decoradores @CrewBase, @agent, @task, @crew")
    print("="*70)
    
    # Configurar variables de entorno para test
    if not os.getenv("OPENAI_API_KEY"):
        os.environ["OPENAI_API_KEY"] = "fake-key-for-test"
        print("⚙️ Usando OPENAI_API_KEY de prueba")
    
    serper_key = os.getenv("SERPER_API_KEY")
    if serper_key:
        print(f"✅ SERPER_API_KEY configurada: {serper_key[:10]}...")
    else:
        print("⚠️ SERPER_API_KEY no configurada - usando herramientas personalizadas")
    
    try:
        # Test chat básico
        await test_chat()
        
        # Test investigación (opcional, más lento)
        choice = input("\n¿Ejecutar tests de investigación? (más lento) [y/N]: ")
        if choice.lower() in ['y', 'yes', 'sí', 'si']:
            await test_research()
        
        print("\n🎉 Todos los tests completados")
        
    except KeyboardInterrupt:
        print("\n⏹️ Tests interrumpidos por el usuario")
    except Exception as e:
        print(f"\n❌ Error general: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(main())