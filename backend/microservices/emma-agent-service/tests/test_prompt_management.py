#!/usr/bin/env python3
"""
Test suite for Prompt Management Architecture
Execute from container: docker exec docker-emma-agent-service-1 python /app/tests/test_prompt_management.py

Tests the full flow:
1. Emma Service (8009) receives request
2. Emma calls Main API (8000) for database operations
3. Verifies CRUD operations work correctly
"""
import httpx
import json
import sys
import os
from datetime import datetime

# Configuration
EMMA_SERVICE = "http://localhost:8009"  # Inside emma container
MAIN_API = os.getenv("API_URL", "http://api:8000")  # Inside docker network
RESULTS_FILE = "/tmp/test_prompt_results.json"
TEST_TENANT_ID = "00000000-0000-0000-0000-000000000001"  # Valid UUID
API_KEY = os.getenv("MICROSERVICES_API_KEY", "dev-api-key-change-in-production")

results = {
    "timestamp": datetime.now().isoformat(),
    "tests": [],
    "summary": {"passed": 0, "failed": 0}
}


def log_result(test_name: str, passed: bool, response: dict = None, error: str = None):
    """Log test result with full details"""
    result = {
        "name": test_name,
        "passed": passed,
        "response": response,
        "error": error
    }
    results["tests"].append(result)
    if passed:
        results["summary"]["passed"] += 1
        print(f"✅ {test_name}")
    else:
        results["summary"]["failed"] += 1
        print(f"❌ {test_name}: {error}")

    if response and not passed:
        print(f"   Response: {json.dumps(response, indent=2, default=str)[:500]}")

    with open(RESULTS_FILE, "w") as f:
        json.dump(results, f, indent=2, default=str)


def test_main_api_health():
    """Test 0: Verify Main API is reachable and has prompts endpoints"""
    print("\n" + "="*50)
    print("TEST 0: Main API Health (database access)")
    print("="*50)
    try:
        with httpx.Client(timeout=30) as client:
            headers = {"X-API-Key": API_KEY}

            # Check main API health
            resp = client.get(f"{MAIN_API}/api/v1/prompts/health", headers=headers)

            if resp.status_code == 404:
                log_result("main_api_prompts_endpoint", False, error="Endpoint not found - router may not be registered")
                return False

            if resp.status_code != 200:
                log_result("main_api_prompts_endpoint", False, resp.json() if resp.content else {}, f"Status {resp.status_code}")
                return False

            data = resp.json()
            log_result("main_api_prompts_endpoint", True, data)

            db_ok = data.get("database", {}).get("connected", False)
            log_result("main_api_db_connection", db_ok, data.get("database"))

            return db_ok
    except httpx.ConnectError as e:
        log_result("main_api_connection", False, error=f"Cannot connect to Main API: {e}")
        return False
    except Exception as e:
        log_result("main_api_health", False, error=str(e))
        return False


def test_emma_health():
    """Test 1: Verify Emma service health (calls Main API internally)"""
    print("\n" + "="*50)
    print("TEST 1: Emma Service Health")
    print("="*50)
    try:
        with httpx.Client(timeout=30) as client:
            headers = {"X-API-Key": API_KEY}
            resp = client.get(f"{EMMA_SERVICE}/prompts/health", headers=headers)

            if resp.status_code != 200:
                log_result("emma_health_endpoint", False, resp.json() if resp.content else {}, f"Status {resp.status_code}")
                return False

            data = resp.json()
            log_result("emma_health_endpoint", True, data)

            langfuse_ok = data.get("langfuse_connected", False)
            db_ok = data.get("database_connected", False)

            log_result("emma_langfuse_connection", langfuse_ok, {"host": data.get("langfuse_host")})
            log_result("emma_database_connection", db_ok, {"via": "Main API"})

            return True
    except Exception as e:
        log_result("emma_health", False, error=str(e))
        return False


def test_rules_crud():
    """Test 2: Rules Engine CRUD operations via Emma -> Main API"""
    print("\n" + "="*50)
    print("TEST 2: Rules Engine CRUD")
    print("="*50)
    try:
        with httpx.Client(timeout=30) as client:
            headers = {
                "X-Tenant-ID": TEST_TENANT_ID,
                "Content-Type": "application/json",
                "X-API-Key": API_KEY
            }

            # CREATE rule
            rule_data = {
                "rule_name": "test_labor_contract_rule",
                "description": "Test rule for labor contracts",
                "conditions": {
                    "document_type": "contrato_laboral",
                    "action": "analyze"
                },
                "action_type": "inject_block",
                "action_config": {
                    "block_name": "labor_analysis_instructions",
                    "content": "Analiza especialmente: salario, jornada, vacaciones"
                },
                "priority": 100,
                "is_active": True
            }

            resp = client.post(f"{EMMA_SERVICE}/prompts/rules", json=rule_data, headers=headers)
            if resp.status_code not in [200, 201]:
                log_result("rules_create", False, resp.json() if resp.content else {}, f"Status {resp.status_code}")
                return False

            created = resp.json()
            rule_id = created.get("id")
            log_result("rules_create", True, {"id": rule_id, "rule_name": created.get("rule_name")})

            # READ rules
            resp = client.get(f"{EMMA_SERVICE}/prompts/rules", headers=headers)
            if resp.status_code == 200:
                rules_data = resp.json()
                rules_list = rules_data.get("rules", []) if isinstance(rules_data, dict) else rules_data
                found = any(str(r.get("id")) == str(rule_id) for r in rules_list)
                log_result("rules_list", found, {"count": len(rules_list), "found_created": found})
            else:
                log_result("rules_list", False, resp.json() if resp.content else {}, f"Status {resp.status_code}")

            # EVALUATE rule
            eval_data = {
                "document_type": "contrato_laboral",
                "action": "analyze"
            }
            resp = client.post(f"{EMMA_SERVICE}/prompts/rules/evaluate", json=eval_data, headers=headers)
            if resp.status_code == 200:
                eval_result = resp.json()
                matched = len(eval_result.get("matched_rules", [])) > 0
                log_result("rules_evaluate", True, {"matched": matched})
            else:
                log_result("rules_evaluate", False, resp.json() if resp.content else {}, f"Status {resp.status_code}")

            # DELETE rule (cleanup)
            if rule_id:
                resp = client.delete(f"{EMMA_SERVICE}/prompts/rules/{rule_id}", headers=headers)
                log_result("rules_delete", resp.status_code in [200, 204], {"rule_id": rule_id})

            return True
    except Exception as e:
        log_result("rules_crud", False, error=str(e))
        return False


def test_few_shot():
    """Test 3: Few-Shot Examples (embedding generated by Emma, stored via Main API)"""
    print("\n" + "="*50)
    print("TEST 3: Few-Shot Examples")
    print("="*50)
    try:
        with httpx.Client(timeout=60) as client:
            headers = {
                "X-Tenant-ID": TEST_TENANT_ID,
                "Content-Type": "application/json",
                "X-API-Key": API_KEY
            }

            # CREATE example
            example_data = {
                "question": "¿Cuántos días de preaviso necesito para un despido disciplinario?",
                "answer": "En un despido disciplinario no se requiere preaviso según el artículo 55 del ET.",
                "category": "despido",
                "domain": "legal"  # Valid: legal, medical, documental, general
            }

            resp = client.post(f"{EMMA_SERVICE}/prompts/few-shot", json=example_data, headers=headers)
            if resp.status_code not in [200, 201]:
                log_result("few_shot_create", False, resp.json() if resp.content else {}, f"Status {resp.status_code}")
                return False

            created = resp.json()
            example_id = created.get("id")
            log_result("few_shot_create", True, {"id": example_id})

            # SEARCH similar examples
            search_data = {
                "query": "¿Cuánto preaviso para despedir a un empleado?",
                "limit": 3
            }
            resp = client.post(f"{EMMA_SERVICE}/prompts/few-shot/search", json=search_data, headers=headers)
            if resp.status_code == 200:
                search_result = resp.json()
                examples = search_result.get("examples", [])
                log_result("few_shot_search", True, {"found": len(examples), "query": search_data["query"][:30]})
            else:
                log_result("few_shot_search", False, resp.json() if resp.content else {}, f"Status {resp.status_code}")

            # LIST examples
            resp = client.get(f"{EMMA_SERVICE}/prompts/few-shot", headers=headers)
            if resp.status_code == 200:
                list_result = resp.json()
                examples = list_result.get("examples", []) if isinstance(list_result, dict) else list_result
                log_result("few_shot_list", True, {"count": len(examples)})
            else:
                log_result("few_shot_list", False, error=f"Status {resp.status_code}")

            # DELETE example (cleanup)
            if example_id:
                resp = client.delete(f"{EMMA_SERVICE}/prompts/few-shot/{example_id}", headers=headers)
                log_result("few_shot_delete", resp.status_code in [200, 204], {"example_id": example_id})

            return True
    except Exception as e:
        log_result("few_shot", False, error=str(e))
        return False


def test_guardrails():
    """Test 4: Guardrails CRUD"""
    print("\n" + "="*50)
    print("TEST 4: Guardrails")
    print("="*50)
    try:
        with httpx.Client(timeout=30) as client:
            headers = {
                "X-Tenant-ID": TEST_TENANT_ID,
                "Content-Type": "application/json",
                "X-API-Key": API_KEY
            }

            # CREATE guardrail
            guardrail_data = {
                "guardrail_name": "test_pii_blocker",
                "description": "Block PII in responses",
                "guardrail_type": "keyword",
                "config": {
                    "blocked_words": ["DNI", "NIF", "número de cuenta"]
                },
                "action_on_match": "redact",
                "applies_to": ["*"]
            }

            resp = client.post(f"{EMMA_SERVICE}/prompts/guardrails", json=guardrail_data, headers=headers)
            if resp.status_code not in [200, 201]:
                log_result("guardrails_create", False, resp.json() if resp.content else {}, f"Status {resp.status_code}")
                return False

            created = resp.json()
            guardrail_id = created.get("id")
            log_result("guardrails_create", True, {"id": guardrail_id})

            # TEST guardrail
            test_data = {
                "content": "El DNI del cliente es 12345678A",
                "agent_name": "test_agent"
            }
            resp = client.post(f"{EMMA_SERVICE}/prompts/guardrails/test", json=test_data, headers=headers)
            if resp.status_code == 200:
                test_result = resp.json()
                would_block = test_result.get("would_block", False)
                log_result("guardrails_test", True, {"would_block": would_block})
            else:
                log_result("guardrails_test", False, error=f"Status {resp.status_code}")

            # LIST guardrails
            resp = client.get(f"{EMMA_SERVICE}/prompts/guardrails", headers=headers)
            if resp.status_code == 200:
                list_result = resp.json()
                guardrails = list_result.get("guardrails", []) if isinstance(list_result, dict) else list_result
                log_result("guardrails_list", True, {"count": len(guardrails)})
            else:
                log_result("guardrails_list", False, error=f"Status {resp.status_code}")

            # DELETE guardrail (cleanup)
            if guardrail_id:
                resp = client.delete(f"{EMMA_SERVICE}/prompts/guardrails/{guardrail_id}", headers=headers)
                log_result("guardrails_delete", resp.status_code in [200, 204], {"guardrail_id": guardrail_id})

            return True
    except Exception as e:
        log_result("guardrails", False, error=str(e))
        return False


def test_utilities():
    """Test 5: Utility endpoints (cache, sync, reload)"""
    print("\n" + "="*50)
    print("TEST 5: Utility Endpoints")
    print("="*50)
    try:
        with httpx.Client(timeout=30) as client:
            headers = {"X-API-Key": API_KEY, "Content-Type": "application/json"}

            # Cache invalidate
            resp = client.post(f"{EMMA_SERVICE}/prompts/cache/invalidate", json={}, headers=headers)
            log_result("cache_invalidate", resp.status_code in [200, 204])

            # YAML reload
            resp = client.post(f"{EMMA_SERVICE}/prompts/reload", headers=headers)
            log_result("yaml_reload", resp.status_code in [200, 204])

            # List available prompts
            resp = client.get(f"{EMMA_SERVICE}/prompts/available", headers=headers)
            if resp.status_code == 200:
                prompts = resp.json()
                log_result("list_available_prompts", True, {"count": len(prompts) if isinstance(prompts, list) else "dict"})
            else:
                log_result("list_available_prompts", resp.status_code == 200)

            return True
    except Exception as e:
        log_result("utilities", False, error=str(e))
        return False


def main():
    print("=" * 60)
    print("🧪 PROMPT MANAGEMENT TEST SUITE")
    print("=" * 60)
    print(f"Emma Service: {EMMA_SERVICE}")
    print(f"Main API: {MAIN_API}")
    print(f"Results: {RESULTS_FILE}")
    print("=" * 60)

    # Run tests in order
    main_api_ok = test_main_api_health()

    if not main_api_ok:
        print("\n⚠️  Main API not healthy - some tests may fail")

    test_emma_health()
    test_rules_crud()
    test_few_shot()
    test_guardrails()
    test_utilities()

    # Final summary
    print("\n" + "=" * 60)
    print("📊 FINAL SUMMARY")
    print("=" * 60)
    print(f"✅ Passed: {results['summary']['passed']}")
    print(f"❌ Failed: {results['summary']['failed']}")
    print(f"\n📄 Full results saved to: {RESULTS_FILE}")

    # Print failed tests
    failed = [t for t in results["tests"] if not t["passed"]]
    if failed:
        print("\n🔴 FAILED TESTS:")
        for t in failed:
            print(f"   - {t['name']}: {t['error']}")

    sys.exit(0 if results["summary"]["failed"] == 0 else 1)


if __name__ == "__main__":
    main()
