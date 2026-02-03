#!/usr/bin/env python3
"""
Test Suite: Emma Social Channel Responses

Prueba las respuestas de Emma en canales sociales (Slack, Telegram).
Verifica:
1. Filtrado de mensajes (qué ignorar vs responder)
2. Calidad de respuestas (tono, longitud, contenido)
3. Manejo de diferentes tipos de consultas

Ejecutar:
    python -m pytest tests/test_social_channel_responses.py -v

O directamente:
    python tests/test_social_channel_responses.py
"""

import asyncio
import json
import sys
from dataclasses import dataclass
from enum import Enum
from typing import Optional

# Add parent to path for imports
sys.path.insert(0, "/home/nexus/git/nexus-documents-ia/backend/microservices/emma-agent-service")


class ExpectedBehavior(Enum):
    SHOULD_RESPOND = "respond"
    SHOULD_IGNORE = "ignore"


@dataclass
class TestCase:
    """Test case for social channel response."""
    id: str
    message: str
    expected: ExpectedBehavior
    category: str
    description: str
    is_mentioned: bool = False
    is_group: bool = True


# =============================================================================
# TEST CASES
# =============================================================================

TEST_CASES = [
    # --- DEBE IGNORAR: Chat casual ---
    TestCase(
        id="casual_01",
        message="uff que mal tiempo",
        expected=ExpectedBehavior.SHOULD_IGNORE,
        category="casual",
        description="Comentario casual sobre el tiempo",
    ),
    TestCase(
        id="casual_02",
        message="jajaja buenísimo",
        expected=ExpectedBehavior.SHOULD_IGNORE,
        category="casual",
        description="Risa/reacción",
    ),
    TestCase(
        id="casual_03",
        message="ok",
        expected=ExpectedBehavior.SHOULD_IGNORE,
        category="casual",
        description="Acknowledgment corto",
    ),
    TestCase(
        id="casual_04",
        message="gracias!",
        expected=ExpectedBehavior.SHOULD_IGNORE,
        category="casual",
        description="Agradecimiento simple",
    ),
    TestCase(
        id="casual_05",
        message="👍",
        expected=ExpectedBehavior.SHOULD_IGNORE,
        category="casual",
        description="Emoji de confirmación",
    ),
    TestCase(
        id="casual_06",
        message="buenas tardes a todos",
        expected=ExpectedBehavior.SHOULD_IGNORE,
        category="casual",
        description="Saludo grupal",
    ),
    TestCase(
        id="casual_07",
        message="qué calor hace hoy",
        expected=ExpectedBehavior.SHOULD_IGNORE,
        category="casual",
        description="Comentario clima",
    ),
    TestCase(
        id="casual_08",
        message="buen finde a todos!",
        expected=ExpectedBehavior.SHOULD_IGNORE,
        category="casual",
        description="Despedida de fin de semana",
    ),

    # --- DEBE RESPONDER: Menciones directas ---
    TestCase(
        id="mention_01",
        message="hola",
        expected=ExpectedBehavior.SHOULD_RESPOND,
        category="mention",
        description="Saludo con mención",
        is_mentioned=True,
    ),
    TestCase(
        id="mention_02",
        message="qué tiempo hace?",
        expected=ExpectedBehavior.SHOULD_RESPOND,
        category="mention",
        description="Pregunta casual CON mención (debe responder aunque no sepa)",
        is_mentioned=True,
    ),
    TestCase(
        id="mention_03",
        message="ayuda",
        expected=ExpectedBehavior.SHOULD_RESPOND,
        category="mention",
        description="Solicitud de ayuda con mención",
        is_mentioned=True,
    ),

    # --- DEBE RESPONDER: Preguntas sobre documentos ---
    TestCase(
        id="docs_01",
        message="¿qué contratos tenemos con ACME?",
        expected=ExpectedBehavior.SHOULD_RESPOND,
        category="documents",
        description="Pregunta sobre contratos",
    ),
    TestCase(
        id="docs_02",
        message="busca las facturas de enero",
        expected=ExpectedBehavior.SHOULD_RESPOND,
        category="documents",
        description="Búsqueda de facturas",
    ),
    TestCase(
        id="docs_03",
        message="¿hay algún documento sobre RGPD?",
        expected=ExpectedBehavior.SHOULD_RESPOND,
        category="documents",
        description="Pregunta sobre documentos RGPD",
    ),
    TestCase(
        id="docs_04",
        message="necesito revisar el contrato de arrendamiento",
        expected=ExpectedBehavior.SHOULD_RESPOND,
        category="documents",
        description="Solicitud de revisión",
    ),
    TestCase(
        id="docs_05",
        message="¿cuántos documentos tengo indexados?",
        expected=ExpectedBehavior.SHOULD_RESPOND,
        category="documents",
        description="Pregunta de conteo",
    ),

    # --- DEBE RESPONDER: Preguntas legales/fiscales ---
    TestCase(
        id="legal_01",
        message="¿cuál es la jornada máxima laboral?",
        expected=ExpectedBehavior.SHOULD_RESPOND,
        category="legal",
        description="Pregunta laboral",
    ),
    TestCase(
        id="legal_02",
        message="¿qué dice el artículo 34 del Estatuto de los Trabajadores?",
        expected=ExpectedBehavior.SHOULD_RESPOND,
        category="legal",
        description="Pregunta sobre legislación específica",
    ),
    TestCase(
        id="legal_03",
        message="¿cuáles son los plazos de prescripción de deudas?",
        expected=ExpectedBehavior.SHOULD_RESPOND,
        category="legal",
        description="Pregunta legal general",
    ),
    TestCase(
        id="legal_04",
        message="explícame las obligaciones del RGPD",
        expected=ExpectedBehavior.SHOULD_RESPOND,
        category="legal",
        description="Explicación normativa",
    ),

    # --- DEBE RESPONDER: Solicitudes de ayuda ---
    TestCase(
        id="help_01",
        message="¿puedes ayudarme a encontrar un documento?",
        expected=ExpectedBehavior.SHOULD_RESPOND,
        category="help",
        description="Solicitud de ayuda genérica",
    ),
    TestCase(
        id="help_02",
        message="necesito analizar un contrato",
        expected=ExpectedBehavior.SHOULD_RESPOND,
        category="help",
        description="Necesidad de análisis",
    ),
    TestCase(
        id="help_03",
        message="¿podrías revisar este documento?",
        expected=ExpectedBehavior.SHOULD_RESPOND,
        category="help",
        description="Solicitud de revisión",
    ),

    # --- CHAT PRIVADO: Siempre responde ---
    TestCase(
        id="private_01",
        message="hola",
        expected=ExpectedBehavior.SHOULD_RESPOND,
        category="private",
        description="Saludo en chat privado",
        is_group=False,
    ),
    TestCase(
        id="private_02",
        message="qué tiempo hace?",
        expected=ExpectedBehavior.SHOULD_RESPOND,
        category="private",
        description="Pregunta casual en privado (responde aunque no sepa)",
        is_group=False,
    ),

    # --- CASOS AMBIGUOS (para ajustar) ---
    TestCase(
        id="ambig_01",
        message="¿alguien sabe dónde está el contrato de ACME?",
        expected=ExpectedBehavior.SHOULD_RESPOND,
        category="ambiguous",
        description="Pregunta a todos pero sobre documento",
    ),
    TestCase(
        id="ambig_02",
        message="¿hay novedades?",
        expected=ExpectedBehavior.SHOULD_IGNORE,
        category="ambiguous",
        description="Pregunta vaga sin contexto documental",
    ),

    # --- BÚSQUEDA WEB: Con mención, Emma usa web_search ---
    TestCase(
        id="web_01",
        message="¿qué tiempo hace hoy?",
        expected=ExpectedBehavior.SHOULD_RESPOND,
        category="web_search",
        description="Pregunta de clima CON mención (usa web_search)",
        is_mentioned=True,
    ),
    TestCase(
        id="web_02",
        message="¿cuáles son las últimas noticias?",
        expected=ExpectedBehavior.SHOULD_RESPOND,
        category="web_search",
        description="Pregunta de noticias CON mención",
        is_mentioned=True,
    ),
    TestCase(
        id="web_03",
        message="¿qué hora es en Nueva York?",
        expected=ExpectedBehavior.SHOULD_RESPOND,
        category="web_search",
        description="Pregunta de hora en otra ciudad CON mención",
        is_mentioned=True,
    ),
]


# =============================================================================
# TEST RUNNER
# =============================================================================

def test_should_respond_filter():
    """Test the _should_respond_in_group function directly."""
    from app.services.channel_router import _should_respond_in_group

    results = []
    passed = 0
    failed = 0

    print("\n" + "=" * 70)
    print("TEST: Filtro de mensajes en grupos")
    print("=" * 70 + "\n")

    for tc in TEST_CASES:
        actual = _should_respond_in_group(
            content=tc.message,
            is_mentioned=tc.is_mentioned,
            is_group=tc.is_group,
        )

        expected_bool = tc.expected == ExpectedBehavior.SHOULD_RESPOND
        success = actual == expected_bool

        if success:
            passed += 1
            status = "✅ PASS"
        else:
            failed += 1
            status = "❌ FAIL"

        results.append({
            "id": tc.id,
            "message": tc.message[:40],
            "expected": tc.expected.value,
            "actual": "respond" if actual else "ignore",
            "success": success,
        })

        print(f"{status} [{tc.id}] {tc.category}")
        print(f"      Mensaje: \"{tc.message[:50]}{'...' if len(tc.message) > 50 else ''}\"")
        print(f"      Esperado: {tc.expected.value} | Actual: {'respond' if actual else 'ignore'}")
        if tc.is_mentioned:
            print(f"      (con mención)")
        if not tc.is_group:
            print(f"      (chat privado)")
        print()

    print("=" * 70)
    print(f"RESULTADOS: {passed}/{len(TEST_CASES)} pasaron ({failed} fallaron)")
    print("=" * 70)

    return failed == 0


async def test_emma_responses():
    """Test actual Emma responses via the background service."""
    from app.services.emma_background_service import emma_background_service

    # Select a few key test cases for actual response testing
    test_queries = [
        ("¿cuál es la jornada máxima laboral en España?", "legal"),
        ("busca contratos de 2024", "documents"),
        ("¿qué obligaciones tiene el RGPD?", "legal"),
        ("hola, ¿en qué puedes ayudarme?", "greeting"),
        ("¿qué tiempo hace hoy?", "web_search"),  # NEW: Web search test
        ("¿cuáles son las últimas noticias de España?", "web_search"),  # NEW
    ]

    print("\n" + "=" * 70)
    print("TEST: Respuestas reales de Emma")
    print("=" * 70 + "\n")

    tenant_id = "test-tenant"

    # Channel config with location (like a real Slack channel would have)
    channel_config = {
        "location": {
            "city": "Molina de Segura",
            "region": "Murcia",
            "country": "España",
            "timezone": "Europe/Madrid",
        }
    }

    for query, category in test_queries:
        print(f"📤 Query [{category}]: {query}")
        print("-" * 50)

        try:
            result = await emma_background_service.channel_query(
                tenant_id=tenant_id,
                query=query,
                channel_type="slack",
                user_id="test-user",
                is_group=True,
                group_name="test-channel",
                channel_config=channel_config,  # Pass location config
            )

            answer = result.get("answer", "")
            success = result.get("success", False)

            print(f"✅ Success: {success}")
            print(f"📥 Respuesta ({len(answer)} chars):")
            print(f"   {answer[:200]}{'...' if len(answer) > 200 else ''}")

            # Quality checks
            issues = []
            if len(answer) > 1500:
                issues.append("⚠️ Respuesta muy larga para chat")
            if "##" in answer:
                issues.append("⚠️ Contiene headers markdown")
            if answer.count("\n") > 10:
                issues.append("⚠️ Demasiados saltos de línea")
            if "EDMS" in answer and category != "greeting":
                issues.append("⚠️ Incluye presentación corporativa innecesaria")

            if issues:
                print("   Issues:")
                for issue in issues:
                    print(f"     {issue}")

        except Exception as e:
            print(f"❌ Error: {e}")

        print("\n")


def run_filter_tests():
    """Run only the filter tests (no async, no Emma calls)."""
    return test_should_respond_filter()


async def run_all_tests():
    """Run all tests including Emma response tests."""
    filter_ok = test_should_respond_filter()

    print("\n" + "⏳ Ejecutando tests de respuesta real (requiere servicios activos)...")
    try:
        await test_emma_responses()
    except Exception as e:
        print(f"❌ Tests de respuesta fallaron: {e}")
        print("   (Asegúrate de que emma-agent-service esté corriendo)")

    return filter_ok


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Test Emma social channel responses")
    parser.add_argument("--filter-only", action="store_true",
                        help="Only run filter tests (no Emma calls)")
    args = parser.parse_args()

    if args.filter_only:
        success = run_filter_tests()
    else:
        success = asyncio.run(run_all_tests())

    sys.exit(0 if success else 1)
