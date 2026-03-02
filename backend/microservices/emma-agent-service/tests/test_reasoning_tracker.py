"""
Test del sistema de razonamiento dinámico de Emma.

Ejecutar:
    cd /home/nexus/git/nexus-documents-ia/backend/microservices/emma-agent-service
    python -m pytest tests/test_reasoning_tracker.py -v -s
"""

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

# Test del ReasoningTracker básico
class TestReasoningTracker:
    """Tests para el sistema de tracking de razonamiento."""

    def test_tracker_creation(self):
        """Test que el tracker se crea correctamente."""
        from app.agents.langgraph.reasoning_tracker import ReasoningTracker, StepType

        tracker = ReasoningTracker.create()

        assert tracker is not None
        assert tracker.get_step_count() == 0

        # Añadir pasos
        tracker.add_step(StepType.QUERY_ANALYSIS, "Analizando consulta...")
        tracker.add_step(StepType.ROUTING, "Detectado: consulta estructural")

        assert tracker.get_step_count() == 2

        steps = tracker.get_steps()
        assert len(steps) == 2
        assert steps[0]["type"] == "query_analysis"
        assert steps[1]["type"] == "routing"

        # Limpiar
        ReasoningTracker.clear()

    def test_tracker_context_manager(self):
        """Test del context manager."""
        from app.agents.langgraph.reasoning_tracker import ReasoningTracker, StepType

        with ReasoningTracker.create() as tracker:
            tracker.add_step(StepType.SEARCH, "Buscando...")
            assert tracker.get_step_count() == 1

        # Fuera del contexto, get_current devuelve uno nuevo
        new_tracker = ReasoningTracker.get_current()
        assert new_tracker.get_step_count() == 0

    def test_connector_step(self):
        """Test de pasos de conector."""
        from app.agents.langgraph.reasoning_tracker import ReasoningTracker

        with ReasoningTracker.create() as tracker:
            tracker.add_connector_step("Apache AGE", "conectando", "localhost:5432")
            tracker.add_connector_step("Weaviate", "buscando", "query='test'")

            steps = tracker.get_steps()
            assert len(steps) == 2
            assert "Apache AGE" in steps[0]["content"]
            assert "Weaviate" in steps[1]["content"]

    def test_search_step(self):
        """Test de pasos de búsqueda."""
        from app.agents.langgraph.reasoning_tracker import ReasoningTracker

        with ReasoningTracker.create() as tracker:
            tracker.add_search_step("Weaviate", "contratos laborales", result_count=5)

            steps = tracker.get_steps()
            assert len(steps) == 1
            assert "5 resultados" in steps[0]["content"]
            assert steps[0]["metadata"]["result_count"] == 5


class TestEndToEndReasoning:
    """Test end-to-end del flujo de razonamiento."""

    @pytest.mark.asyncio
    async def test_full_flow_structural(self):
        """Test del flujo completo para consulta estructural."""
        from app.agents.langgraph.reasoning_tracker import ReasoningTracker, StepType

        print("\n" + "="*60)
        print("SIMULACIÓN: ¿Cuántos expedientes tengo del año 2006?")
        print("="*60)

        with ReasoningTracker.create() as tracker:
            # Simular plan_node
            tracker.set_source("plan_node")
            tracker.add_step(StepType.QUERY_ANALYSIS, "Analizando consulta: '¿Cuántos expedientes tengo del año 2006?'")
            tracker.add_step(StepType.ROUTING, "Detectado: consulta estructural (patrón: 'cuántos expedientes')", confidence=0.95)
            tracker.add_step(StepType.ROUTING, "Decisión: usar Apache AGE (base de datos de grafos)", confidence=0.95)

            # Simular structural_query
            tracker.set_source("structural_query")
            tracker.add_connector_step("Apache AGE", "conectando", "weaviate-service/structural")
            tracker.add_step(StepType.SEARCH, "Ejecutando consulta estructural...")
            tracker.add_step(StepType.ROUTING, "Ruta: GRAPH_ONLY - Solo grafo (rápido)", confidence=0.95)
            tracker.add_step(StepType.DATA_EXTRACTION, "Extraído: 15 elementos, 15 expedientes", entities=["15 expedientes"])
            tracker.add_step(StepType.RESPONSE, "Respuesta generada (45ms)")

            steps = tracker.get_steps()

        print("\n📋 Pasos que vería el usuario en Emma Chat:")
        print("-"*60)
        for i, step in enumerate(steps, 1):
            conf = step.get('confidence', 1.0)
            source = step.get('source', '')
            print(f"  {i}. {step['content']}")
            if conf < 1.0:
                print(f"     └─ confianza: {conf:.0%}")

        print("-"*60)
        print(f"Total: {len(steps)} pasos de razonamiento")

        assert len(steps) == 8

    @pytest.mark.asyncio
    async def test_full_flow_semantic(self):
        """Test del flujo completo para consulta semántica."""
        from app.agents.langgraph.reasoning_tracker import ReasoningTracker, StepType

        print("\n" + "="*60)
        print("SIMULACIÓN: ¿Qué dice el contrato sobre penalizaciones?")
        print("="*60)

        with ReasoningTracker.create() as tracker:
            # Simular plan_node
            tracker.set_source("plan_node")
            tracker.add_step(StepType.QUERY_ANALYSIS, "Analizando consulta: '¿Qué dice el contrato sobre penalizaciones?'")
            tracker.add_step(StepType.ROUTING, "No es consulta estructural, analizando dominio semántico...", confidence=0.5)
            tracker.add_step(StepType.ROUTING, "Detectado: dominio contract", confidence=0.85)
            tracker.add_step(StepType.ROUTING, "Decisión: búsqueda semántica en Weaviate (vectores)", confidence=0.85)
            tracker.add_step(StepType.RESPONSE, "Plan listo: contract_agent (120ms)")

            # Simular búsqueda vectorial
            tracker.set_source("document_search")
            tracker.add_search_step("Weaviate", "penalizaciones contrato", result_count=3)
            tracker.add_step(StepType.DATA_EXTRACTION, "Analizando 3 chunks relevantes...")
            tracker.add_step(StepType.RESPONSE, "Respuesta sintetizada (850ms)")

            steps = tracker.get_steps()

        print("\n📋 Pasos que vería el usuario en Emma Chat:")
        print("-"*60)
        for i, step in enumerate(steps, 1):
            print(f"  {i}. {step['content']}")

        print("-"*60)
        print(f"Total: {len(steps)} pasos de razonamiento")

        assert len(steps) == 8


if __name__ == "__main__":
    # Ejecutar tests manualmente
    print("\n🧪 Ejecutando tests de ReasoningTracker...\n")

    # Test básico
    test = TestReasoningTracker()
    test.test_tracker_creation()
    print("✅ test_tracker_creation passed")

    test.test_tracker_context_manager()
    print("✅ test_tracker_context_manager passed")

    test.test_connector_step()
    print("✅ test_connector_step passed")

    # Tests end-to-end
    asyncio.run(TestEndToEndReasoning().test_full_flow_structural())
    print("✅ test_full_flow_structural passed")

    asyncio.run(TestEndToEndReasoning().test_full_flow_semantic())
    print("✅ test_full_flow_semantic passed")

    print("\n✅ Todos los tests pasaron!")
