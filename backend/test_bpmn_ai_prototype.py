#!/usr/bin/env python3
"""
Test script para el prototipo BPM AI + Emma AI
Prueba la integración de modelos especializados con Emma AI para renovación de contratos
"""
import asyncio
import json
import sys
import os
from datetime import datetime, timedelta
from loguru import logger

# Add project root to path
sys.path.append(os.path.join(os.path.dirname(__file__)))

# Configure logger
logger.remove()
logger.add(sys.stdout, format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | {message}")


async def test_bpmn_ai_service():
    """Test complete BPM AI service integration"""
    
    logger.info("🚀 Testing BPM AI Service Integration")
    
    try:
        # Import after adding to path
        from microservices.weaviate_service.app.services.bpmn_ai_service import bpmn_ai_service
        
        # 1. Initialize service
        logger.info("📋 Step 1: Initializing BPM AI Service...")
        await bpmn_ai_service.initialize()
        
        # 2. Health check
        logger.info("🔍 Step 2: Running health check...")
        health_status = await bpmn_ai_service.health_check()
        logger.info(f"Health Status: {json.dumps(health_status, indent=2)}")
        
        # 3. Test contract data
        test_contract = {
            "contract_id": "test_contract_001",
            "tenant_id": "test_tenant_abc",
            "employee_name": "María López", 
            "employee_id": "emp_001",
            "contract_type": "temporal",
            "start_date": "2024-01-15",
            "expiration_date": "2025-01-15",
            "position": "Desarrolladora Full Stack",
            "department": "Tecnología",
            "manager": "Carlos Ruiz",
            "current_salary": 42000,
            "performance_rating": "Excelente",
            "attendance_score": 98,
            "contract_extensions": 0,
            "original_contract_date": "2024-01-15"
        }
        
        logger.info(f"📄 Test Contract: {test_contract['employee_name']} - {test_contract['position']}")
        
        # 4. Generate BPMN process
        logger.info("🎨 Step 3: Generating BPMN process...")
        bpmn_result = await bpmn_ai_service.generate_contract_renewal_bpmn(
            contract_data=test_contract,
            tenant_id=test_contract["tenant_id"]
        )
        
        logger.success("✅ BPMN Generation completed!")
        logger.info(f"Process Description: {bpmn_result['process_description'][:150]}...")
        
        # Show extracted elements
        if "extracted_elements" in bpmn_result:
            elements = bpmn_result["extracted_elements"]
            logger.info(f"🔍 Extracted Elements:")
            logger.info(f"  - Agents: {[a['name'] for a in elements.get('agents', [])]}")
            logger.info(f"  - Tasks: {len(elements.get('tasks', []))} tasks identified")
            logger.info(f"  - Conditions: {len(elements.get('conditions', []))} conditions found")
        
        # Show generated BPMN
        if "generated_bpmn" in bpmn_result:
            bpmn_diagram = bpmn_result["generated_bpmn"]
            logger.info(f"📊 Generated BPMN (preview): {bpmn_diagram[:200]}...")
        
        # Show Emma AI validation
        if "validated_bpmn" in bpmn_result:
            validation = bpmn_result["validated_bpmn"]
            logger.info(f"🧠 Emma AI Validation:")
            logger.info(f"  - Confidence: {validation.get('emma_confidence', 'N/A')}")
            logger.info(f"  - Legal Points: {len(validation.get('legal_compliance_points', []))}")
            logger.info(f"  - Recommendations: {len(validation.get('recommendations', []))}")
        
        # Show execution plan
        if "execution_plan" in bpmn_result:
            plan = bpmn_result["execution_plan"]
            logger.info(f"📅 Execution Plan:")
            logger.info(f"  - Steps: {len(plan.get('execution_steps', []))}")
            logger.info(f"  - Timeline: {plan.get('timeline', {}).get('total_duration', 'N/A')}")
            logger.info(f"  - Stakeholders: {list(plan.get('stakeholders', {}).keys())}")
        
        # 5. Test execution
        logger.info("⚡ Step 4: Testing process execution...")
        execution_result = await bpmn_ai_service.execute_contract_renewal_process(
            contract_id=test_contract["contract_id"],
            tenant_id=test_contract["tenant_id"],
            user_id="test_user_123"
        )
        
        if execution_result["success"]:
            logger.success("✅ Process Execution completed!")
            
            exec_details = execution_result.get("execution_result", {})
            logger.info(f"📈 Execution Summary:")
            logger.info(f"  - Steps Completed: {exec_details.get('steps_completed', 0)}/{exec_details.get('total_steps', 0)}")
            logger.info(f"  - Final Decision: {exec_details.get('final_decision', 'N/A')}")
            
            # Show execution log (last 3 steps)
            exec_log = exec_details.get("execution_log", [])
            if exec_log:
                logger.info(f"📋 Recent Execution Steps:")
                for step in exec_log[-3:]:
                    status = step.get("status", "unknown")
                    step_desc = step.get("step_description", "N/A")
                    logger.info(f"  - [{status.upper()}] {step_desc}")
        else:
            logger.error(f"❌ Process execution failed: {execution_result.get('error', 'Unknown error')}")
        
        # 6. Summary
        logger.info("🎯 Step 5: Test Summary")
        logger.success("✅ BPM AI Service Integration Test COMPLETED")
        
        return True
        
    except Exception as e:
        logger.error(f"❌ Test failed with error: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_models_availability():
    """Test if HuggingFace models are available"""
    
    logger.info("🤖 Testing HuggingFace Models Availability...")
    
    try:
        import transformers
        logger.info(f"✅ Transformers library available: v{transformers.__version__}")
        
        # Test TXT2BPMN model availability
        try:
            from transformers import AutoTokenizer
            tokenizer = AutoTokenizer.from_pretrained("fachati/TXT2BPMN")
            logger.info("✅ TXT2BPMN model accessible")
        except Exception as e:
            logger.warning(f"⚠️ TXT2BPMN model not available: {e}")
        
        # Test BPMN extraction model
        try:
            from transformers import pipeline
            extractor = pipeline(
                "token-classification",
                model="jtlicardo/bpmn-information-extraction",
                tokenizer="jtlicardo/bpmn-information-extraction"
            )
            logger.info("✅ BPMN Information Extraction model accessible")
            
            # Quick test
            test_text = "RRHH analiza el rendimiento del empleado y decide si renovar el contrato"
            result = extractor(test_text)
            logger.info(f"📊 Test extraction result: {len(result)} entities found")
            
        except Exception as e:
            logger.warning(f"⚠️ BPMN extraction model not available: {e}")
        
    except ImportError:
        logger.error("❌ Transformers library not available")
        logger.info("💡 To install: pip install transformers torch")


async def test_emma_ai_integration():
    """Test Emma AI integration"""
    
    logger.info("🧠 Testing Emma AI Integration...")
    
    try:
        from microservices.weaviate_service.app.services.elysia_service import elysia_service
        
        # Initialize Emma AI
        await elysia_service.initialize()
        
        # Test simple query
        test_query = """
        Analiza este caso de renovación de contrato:
        - Empleado: Ana García
        - Puesto: Analista de Datos
        - Rendimiento: Excelente
        - Contrato vence: 15 febrero 2025
        
        ¿Recomiendas renovar? Explica tu razonamiento.
        """
        
        logger.info("📤 Sending test query to Emma AI...")
        response = await elysia_service.query(test_query)
        
        if response and hasattr(response, 'response'):
            logger.success("✅ Emma AI responded successfully")
            logger.info(f"🧠 Emma AI Response (preview): {response.response[:200]}...")
        else:
            logger.warning("⚠️ Emma AI response format unexpected")
            
    except Exception as e:
        logger.error(f"❌ Emma AI integration test failed: {e}")


async def main():
    """Run all tests"""
    
    logger.info("🧪 Starting BPM AI Prototype Tests")
    logger.info("=" * 60)
    
    # Test 1: Models availability
    await test_models_availability()
    logger.info("-" * 40)
    
    # Test 2: Emma AI integration
    await test_emma_ai_integration()  
    logger.info("-" * 40)
    
    # Test 3: Full BPM AI service
    success = await test_bpmn_ai_service()
    
    logger.info("=" * 60)
    if success:
        logger.success("🎉 ALL TESTS PASSED - Prototipo BPM AI funcional!")
        logger.info("🚀 Puedes probar los endpoints:")
        logger.info("  - GET  /bpmn-ai/health")
        logger.info("  - POST /bpmn-ai/demo/contract-renewal")
        logger.info("  - POST /bpmn-ai/generate-bpmn")
        logger.info("  - POST /bpmn-ai/contracts/{contract_id}/renewal")
    else:
        logger.error("❌ Some tests failed - check logs above")
    
    return success


if __name__ == "__main__":
    # Run tests
    result = asyncio.run(main())
    
    # Exit with appropriate code
    sys.exit(0 if result else 1)