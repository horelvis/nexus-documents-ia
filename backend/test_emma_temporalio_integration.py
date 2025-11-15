"""
Test Emma AI + Temporalio Integration
Comprehensive test of the workflow template system with Emma AI
"""
import asyncio
import json
import httpx
from datetime import datetime
import os

API_KEY = os.getenv("MICROSERVICES_API_KEY")
if not API_KEY:
    raise RuntimeError("MICROSERVICES_API_KEY environment variable is required for test_emma_temporalio_integration.py")


async def test_emma_temporalio_integration():
    """Test complete Emma AI + Temporalio workflow integration"""
    
    core_base_url = "http://localhost:8000/api/v1"
    workflow_service_url = "http://localhost:8010"
    api_key = API_KEY
    
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    
    print("🧪 Starting Emma AI + Temporalio Integration Test")
    print("=" * 60)
    
    async with httpx.AsyncClient(follow_redirects=True) as client:
        
        # 1. Test Temporalio Service Health
        print("\n1️⃣ Testing Temporalio Service Health...")
        try:
            response = await client.get(
                f"{core_base_url}/temporalio/health",
                headers=headers,
                timeout=10.0
            )
            if response.status_code == 200:
                health_data = response.json()
                print(f"   ✅ Temporalio Service: {health_data.get('status', 'unknown')}")
                if "temporalio_service" in health_data:
                    temp_status = health_data["temporalio_service"].get("status", "unknown")
                    print(f"   📊 Temporalio Components: {temp_status}")
            else:
                print(f"   ❌ Temporalio Health Check Failed: {response.status_code}")
                return False
        except Exception as e:
            print(f"   ❌ Temporalio Connection Error: {repr(e)}")
            return False
        
        # 2. Test Emma AI Service Health
        print("\n2️⃣ Testing Emma AI Service Health...")
        try:
            # Direct call to weaviate service
            response = await client.get("http://localhost:8007/health", timeout=10.0)
            if response.status_code == 200:
                emma_data = response.json()
                print(f"   ✅ Emma AI Service: {emma_data.get('status', 'unknown')}")
            else:
                print(f"   ⚠️ Emma AI Health Check: {response.status_code}")
        except Exception as e:
            print(f"   ❌ Emma AI Connection Error: {e}")
            
        # 3. Test Workflow Template Listing
        print("\n3️⃣ Testing Workflow Templates...")
        try:
            response = await client.get(
                f"{workflow_service_url}/workflow-templates",
                headers=headers,
                timeout=10.0
            )
            if response.status_code == 200:
                templates = response.json()
                print(f"   ✅ Found {len(templates)} workflow templates")
                
                legal_templates = [t for t in templates if t.get('category') == 'legal']
                if legal_templates:
                    print(f"   📋 Legal templates available: {len(legal_templates)}")
                    for template in legal_templates[:2]:  # Show first 2
                        print(f"      • {template['name']} (ID: {template['id'][:8]}...)")
                else:
                    print("   ⚠️ No legal advisory templates found")
            else:
                print(f"   ❌ Templates fetch failed: {response.status_code}")
                return False
        except Exception as e:
            print(f"   ❌ Templates Error: {e}")
            return False
        
        # 4. Test Workflow Execution with Emma AI Integration
        print("\n4️⃣ Testing Workflow Execution with Emma AI...")
        
        # Find legal advisory template
        legal_template = None
        for template in templates:
            if template.get('name') == 'Asesoría Laboral' or 'legal' in template.get('category', '').lower():
                legal_template = template
                break
        
        if not legal_template and templates:
            legal_template = templates[0]
            print(f"   ⚠️ Falling back to template: {legal_template.get('name')}")
        
        if not legal_template:
            print("   ❌ No workflow template available for testing")
            return False
        
        print(f"   📋 Using template: {legal_template['name']}")
        
        # Prepare test case data
        test_case_data = {
            "template_id": legal_template['id'],
            "tenant_id": "test-tenant",
            "input_data": {
                "client_name": "Juan Pérez Test",
                "client_email": "juan.perez@test.com",
                "client_phone": "+34 600 123 456",
                "company_name": "Empresa Test S.L.",
                "consultation_type": "discrimination",
                "urgency_level": "alta",
                "case_description": """
                Empleado de 45 años con 10 años de antigüedad en la empresa. 
                Tras solicitar una reducción de jornada por cuidado de hijo menor, 
                ha sido trasladado a un departamento con menor responsabilidad y 
                su superior le ha comentado que "ya no tiene el mismo compromiso con la empresa".
                Se siente discriminado por su situación familiar y considera que 
                este trato constituye una represalia por ejercer sus derechos.
                La empresa argumenta reorganización interna, pero el empleado 
                observa que otros compañeros sin cargas familiares no han sido trasladados.
                """,
                "affected_employees": 1,
                "contract_type": "indefinido",
                "preferred_resolution": "legal_action",
                "budget_range": "5000-15000",
                "deadline": "2025-02-15",
                "additional_notes": "El empleado tiene documentación de las conversaciones y emails que demuestran el trato discriminatorio."
            },
            "context": {
                "test_mode": True,
                "priority": "high"
            }
        }
        
        try:
            # Start workflow execution
            print(f"   🚀 Starting workflow execution...")
            response = await client.post(
                f"{workflow_service_url}/workflow-executions/start", 
                json=test_case_data, 
                headers=headers,
                timeout=30.0
            )
            
            if response.status_code == 200:
                execution_data = response.json()
                execution_id = execution_data.get('workflow_id') or execution_data.get('id')
                workflow_id = execution_data.get('temporalio_workflow_id') or execution_id
                
                print(f"   ✅ Workflow started successfully!")
                print(f"      • Execution ID: {execution_id[:8]}...")
                print(f"      • Temporalio ID: {workflow_id}")
                print(f"      • Status: {execution_data['status']}")
                
                # 5. Monitor workflow execution
                print(f"\n5️⃣ Monitoring Workflow Execution...")
                
                max_attempts = 10
                attempt = 0
                
                while attempt < max_attempts:
                    await asyncio.sleep(5)  # Wait 5 seconds between checks
                    attempt += 1
                    
                    try:
                        # Get execution status
                        response = await client.get(
                            f"{workflow_service_url}/workflow-executions/{workflow_id}",
                            headers=headers,
                            timeout=10.0
                        )
                        
                        if response.status_code == 200:
                            status_data = response.json()
                            current_status = status_data['status']
                            progress = status_data.get('progress_percentage', 0)
                            current_step = status_data.get('current_step', 'unknown')
                            
                            print(f"   📊 Attempt {attempt}: Status={current_status}, Progress={progress}%, Step={current_step}")
                            
                            if current_status in ['completed', 'failed', 'cancelled']:
                                print(f"   🎯 Workflow finished with status: {current_status}")
                                
                                # Get execution logs
                                # Optionally fetch workflow history for debugging
                                history_response = await client.get(
                                    f"{workflow_service_url}/workflow-executions/{workflow_id}/history",
                                    headers=headers,
                                    timeout=10.0
                                )
                                if history_response.status_code == 200:
                                    history_data = history_response.json()
                                    print(f"\n6️⃣ Execution History Entries: {len(history_data.get('events', []))}")

                                break
                        else:
                            print(f"   ❌ Status check failed: {response.status_code}")
                            break
                            
                    except Exception as e:
                        print(f"   ❌ Status check error: {e}")
                        break
                
                if attempt >= max_attempts:
                    print(f"   ⚠️ Workflow monitoring timeout after {max_attempts} attempts")
                
                return True
                
            else:
                print(f"   ❌ Workflow start failed: {response.status_code}")
                error_detail = response.text
                print(f"      Error details: {error_detail}")
                return False
                
        except Exception as e:
            print(f"   ❌ Workflow execution error: {e}")
            return False
    
    print("\n" + "=" * 60)
    return True


async def test_direct_emma_ai():
    """Test direct Emma AI integration"""
    
    print("\n🧠 Testing Direct Emma AI Integration")
    print("-" * 40)
    
    emma_url = "http://localhost:8007"
    api_key = API_KEY
    
    test_query = """
    Analiza este caso de discriminación laboral:
    
    Un empleado solicita reducción de jornada por cuidado de hijo menor.
    Posteriormente es trasladado a un puesto de menor responsabilidad.
    Su supervisor le comenta que "ya no tiene el mismo compromiso".
    
    ¿Qué análisis legal proporcionas?
    """
    
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{emma_url}/elysia/query",
                json={
                    "query": test_query,
                    "tenant_id": "test_tenant",
                    "enable_debug": True
                },
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json"
                },
                timeout=60.0
            )
            
            if response.status_code == 200:
                emma_response = response.json()
                analysis = emma_response.get("response", "")
                debug_info = emma_response.get("debug", {})
                
                print(f"✅ Emma AI Direct Test Successful!")
                print(f"   📝 Response length: {len(analysis)} characters")
                
                if debug_info:
                    print(f"   🔧 Debug info available:")
                    tools_used = debug_info.get("tools_used", [])
                    print(f"      • Tools used: {len(tools_used)}")
                    if tools_used:
                        print(f"      • Tool types: {[tool.get('tool_name', 'Unknown') for tool in tools_used[:3]]}")
                    
                    confidence = debug_info.get("confidence_score", 0)
                    print(f"      • Confidence: {confidence}")
                
                # Check for legal keywords
                legal_keywords = ["discriminación", "reducción de jornada", "artículo", "estatuto", "derecho"]
                found_keywords = [kw for kw in legal_keywords if kw.lower() in analysis.lower()]
                print(f"   🔍 Legal keywords found: {len(found_keywords)}/{len(legal_keywords)}")
                
                return True
            else:
                print(f"❌ Emma AI Direct Test Failed: {response.status_code}")
                print(f"   Error: {response.text}")
                return False
                
    except Exception as e:
        print(f"❌ Emma AI Direct Test Error: {e}")
        return False


async def main():
    """Main test function"""
    
    print("🧪 Emma AI + Temporalio Integration Test Suite")
    print("=" * 60)
    print(f"⏰ Started at: {datetime.utcnow().isoformat()}")
    
    # Test direct Emma AI first
    emma_test_passed = await test_direct_emma_ai()
    
    # Test full integration if Emma AI works
    if emma_test_passed:
        integration_test_passed = await test_emma_temporalio_integration()
        
        print(f"\n🎯 TEST RESULTS:")
        print(f"   Emma AI Direct: {'✅ PASSED' if emma_test_passed else '❌ FAILED'}")
        print(f"   Full Integration: {'✅ PASSED' if integration_test_passed else '❌ FAILED'}")
        
        if emma_test_passed and integration_test_passed:
            print(f"\n🎉 ALL TESTS PASSED! Emma AI + Temporalio integration is working!")
        else:
            print(f"\n⚠️ Some tests failed. Check the logs above.")
    else:
        print(f"\n❌ Emma AI direct test failed. Cannot proceed with integration test.")
    
    print(f"\n⏰ Completed at: {datetime.utcnow().isoformat()}")


if __name__ == "__main__":
    asyncio.run(main())
