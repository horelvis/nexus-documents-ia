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


class TestPlanNodeReasoning:
    """Tests para el razonamiento en el nodo de planificación."""

    @pytest.mark.asyncio
    async def test_structural_query_detection(self):
        """Test que detecta consultas estructurales y emite pasos."""
        from app.agents.langgraph.nodes.plan import _is_structural_query

        # Consultas estructurales
        structural_queries = [
            "¿Cuántos expedientes tengo del año 2006?",
            "Lista todos los contratos de ACME",
            "¿Tengo facturas de más de 10.000€?",
            "Documentos del último mes",
            "¿Cuántas nóminas hay del 2023?",
        ]

        for query in structural_queries:
            is_structural, pattern = _is_structural_query(query)
            print(f"✓ '{query[:40]}...' → structural={is_structural}, pattern='{pattern}'")
            assert is_structural, f"Debería ser estructural: {query}"

        # Consultas semánticas (no estructurales)
        semantic_queries = [
            "¿Qué dice el contrato sobre penalizaciones?",
            "Explícame la cláusula de confidencialidad",
            "Resume el documento de privacidad",
        ]

        for query in semantic_queries:
            is_structural, pattern = _is_structural_query(query)
            print(f"✗ '{query[:40]}...' → structural={is_structural}")
            assert not is_structural, f"No debería ser estructural: {query}"

    @pytest.mark.asyncio
    async def test_plan_node_emits_reasoning_steps(self):
        """Test que plan_node emite pasos de razonamiento."""
        from app.agents.langgraph.nodes.plan import plan_node
        from app.agents.langgraph.reasoning_tracker import ReasoningTracker

        # Mock state para consulta estructural
        state = {
            "query": "¿Cuántos expedientes tengo del año 2006?",
            "tenant_id": "test-tenant",
            "retrieved_docs": [],
            "metadata": {},
        }

        # Ejecutar con tracker
        with ReasoningTracker.create() as tracker:
            result = await plan_node(state)

        # Verificar resultado
        assert result["detected_domains"] == ["structural"]
        assert result["execution_plan"] == ["general_agent"]
        assert "reasoning_steps" in result

        steps = result["reasoning_steps"]
        print(f"\n📋 Pasos de razonamiento ({len(steps)}):")
        for i, step in enumerate(steps, 1):
            print(f"  {i}. [{step['type']}] {step['content']}")

        assert len(steps) >= 3  # Al menos: análisis, detección, decisión


class TestStructuralQueryReasoning:
    """Tests para el razonamiento en consultas estructurales."""

    @pytest.mark.asyncio
    async def test_structural_query_with_mock_client(self):
        """Test de structural_query con cliente mockeado."""
        from app.agents.langgraph.nodes.specialists.general import structural_query
        from app.agents.langgraph.reasoning_tracker import ReasoningTracker
        from unittest.mock import AsyncMock, patch, MagicMock

        # Mock del resultado
        mock_result = MagicMock()
        mock_result.route = "GRAPH_ONLY"
        mock_result.confidence = 0.95
        mock_result.context = "Encontrados 15 expedientes del año 2006"
        mock_result.data = {
            "count": 15,
            "documents": [{"title": f"Expediente {i}"} for i in range(15)]
        }

        # Mock del cliente
        mock_client = AsyncMock()
        mock_client.structural_query = AsyncMock(return_value=mock_result)

        with patch("app.agents.langgraph.nodes.specialists.general.get_weaviate_client", return_value=mock_client):
            with ReasoningTracker.create() as tracker:
                result = await structural_query(
                    query="¿Cuántos expedientes tengo del año 2006?",
                    tenant_id="test-tenant",
                )

                steps = tracker.get_steps()

        # Verificar resultado
        assert "response" in result
        assert "reasoning_steps" in result
        assert "15" in result["response"]

        print(f"\n📋 Pasos de razonamiento de structural_query ({len(steps)}):")
        for i, step in enumerate(steps, 1):
            conf = step.get('confidence', 1.0)
            print(f"  {i}. [{step['type']}] {step['content']} (conf: {conf:.0%})")

        # Debe tener pasos de: análisis, conexión, routing, extracción, respuesta
        step_types = [s["type"] for s in steps]
        assert "query_analysis" in step_types
        assert "connector" in step_types or "routing" in step_types


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

    # Test de detección
    asyncio.run(TestPlanNodeReasoning().test_structural_query_detection())
    print("✅ test_structural_query_detection passed")

    # Tests end-to-end
    asyncio.run(TestEndToEndReasoning().test_full_flow_structural())
    print("✅ test_full_flow_structural passed")

    asyncio.run(TestEndToEndReasoning().test_full_flow_semantic())
    print("✅ test_full_flow_semantic passed")

    print("\n✅ Todos los tests pasaron!")
