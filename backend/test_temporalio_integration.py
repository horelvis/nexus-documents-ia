#!/usr/bin/env python3
"""
Test de Integración para Temporalio Microservice
Prueba la conectividad, endpoints y ejecución de workflows
"""
import os
import requests
import time
import json
from typing import Dict, Any

API_KEY = os.getenv("MICROSERVICES_API_KEY")
if not API_KEY:
    raise RuntimeError("MICROSERVICES_API_KEY environment variable is required for test_temporalio_integration.py")


class TemporalioIntegrationTest:
    def __init__(self, base_url: str = "http://localhost:8010"):
        self.base_url = base_url
        self.headers = {
            "Authorization": f"Bearer {API_KEY}",
            "Content-Type": "application/json"
        }
        self.test_results = []

    def log_test(self, test_name: str, success: bool, message: str = "", data: Any = None):
        """Log test result"""
        result = {
            "test": test_name,
            "success": success,
            "message": message,
            "data": data,
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
        }
        self.test_results.append(result)
        
        status = "✅ PASS" if success else "❌ FAIL"
        print(f"{status} {test_name}: {message}")
        if data and not success:
            print(f"   Data: {data}")

    def test_health_check(self):
        """Test 1: Health Check"""
        try:
            response = requests.get(f"{self.base_url}/health", timeout=10)
            
            if response.status_code == 200:
                health_data = response.json()
                
                # Verificar estructura de respuesta
                required_fields = ["status", "service", "temporalio_service", "workers"]
                missing_fields = [field for field in required_fields if field not in health_data]
                
                if missing_fields:
                    self.log_test("Health Check", False, f"Missing fields: {missing_fields}", health_data)
                    return False
                
                # Verificar estado de los servicios
                if health_data["status"] == "healthy":
                    self.log_test("Health Check", True, "Service is healthy", health_data)
                    return True
                else:
                    self.log_test("Health Check", False, f"Service unhealthy: {health_data['status']}", health_data)
                    return False
            else:
                self.log_test("Health Check", False, f"HTTP {response.status_code}", response.text)
                return False
                
        except requests.exceptions.RequestException as e:
            self.log_test("Health Check", False, f"Connection error: {str(e)}")
            return False

    def test_workflow_templates_endpoint(self):
        """Test 2: Workflow Templates Endpoint"""
        try:
            response = requests.get(
                f"{self.base_url}/workflow-templates",
                headers=self.headers,
                timeout=10
            )
            
            if response.status_code == 200:
                templates = response.json()
                
                if isinstance(templates, list):
                    self.log_test("Templates Endpoint", True, f"Retrieved {len(templates)} templates", templates)
                    return templates
                else:
                    self.log_test("Templates Endpoint", False, "Response is not a list", templates)
                    return None
            else:
                self.log_test("Templates Endpoint", False, f"HTTP {response.status_code}", response.text)
                return None
                
        except requests.exceptions.RequestException as e:
            self.log_test("Templates Endpoint", False, f"Request error: {str(e)}")
            return None

    def test_get_specific_template(self, template_id: str = "legal-advisory-template"):
        """Test 3: Get Specific Template"""
        try:
            response = requests.get(
                f"{self.base_url}/workflow-templates/{template_id}",
                headers=self.headers,
                timeout=10
            )
            
            if response.status_code == 200:
                template = response.json()
                
                # Verificar campos requeridos del template
                required_fields = ["id", "name", "workflow_definition", "tenant_id"]
                missing_fields = [field for field in required_fields if field not in template]
                
                if missing_fields:
                    self.log_test("Get Template", False, f"Missing fields: {missing_fields}", template)
                    return None
                
                self.log_test("Get Template", True, f"Template retrieved: {template['name']}", template)
                return template
            else:
                self.log_test("Get Template", False, f"HTTP {response.status_code}", response.text)
                return None
                
        except requests.exceptions.RequestException as e:
            self.log_test("Get Template", False, f"Request error: {str(e)}")
            return None

    def test_workflow_execution(self, template_id: str = "legal-advisory-template"):
        """Test 4: Workflow Execution"""
        try:
            # Datos de prueba para el workflow
            execution_request = {
                "template_id": template_id,
                "tenant_id": "test-tenant",
                "input_data": {
                    "client_name": "Juan Pérez",
                    "case_type": "Laboral",
                    "description": "Consulta sobre despido improcedente"
                }
            }
            
            response = requests.post(
                f"{self.base_url}/workflow-executions/start",
                headers=self.headers,
                json=execution_request,
                timeout=15
            )
            
            if response.status_code == 200:
                execution_result = response.json()
                
                # Verificar campos de respuesta
                required_fields = ["success", "workflow_id", "template_id", "status"]
                missing_fields = [field for field in required_fields if field not in execution_result]
                
                if missing_fields:
                    self.log_test("Workflow Execution", False, f"Missing fields: {missing_fields}", execution_result)
                    return None
                
                if execution_result["success"]:
                    self.log_test("Workflow Execution", True, f"Workflow started: {execution_result['workflow_id']}", execution_result)
                    return execution_result["workflow_id"]
                else:
                    self.log_test("Workflow Execution", False, "Workflow failed to start", execution_result)
                    return None
            else:
                self.log_test("Workflow Execution", False, f"HTTP {response.status_code}", response.text)
                return None
                
        except requests.exceptions.RequestException as e:
            self.log_test("Workflow Execution", False, f"Request error: {str(e)}")
            return None

    def test_workflow_status(self, workflow_id: str):
        """Test 5: Workflow Status Check"""
        try:
            response = requests.get(
                f"{self.base_url}/workflow-executions/{workflow_id}",
                headers=self.headers,
                timeout=10
            )
            
            if response.status_code == 200:
                status_data = response.json()
                
                # Verificar campos de estado
                required_fields = ["workflow_id", "status"]
                missing_fields = [field for field in required_fields if field not in status_data]
                
                if missing_fields:
                    self.log_test("Workflow Status", False, f"Missing fields: {missing_fields}", status_data)
                    return None
                
                self.log_test("Workflow Status", True, f"Status: {status_data['status']}", status_data)
                return status_data
            else:
                self.log_test("Workflow Status", False, f"HTTP {response.status_code}", response.text)
                return None
                
        except requests.exceptions.RequestException as e:
            self.log_test("Workflow Status", False, f"Request error: {str(e)}")
            return None

    def test_authentication(self):
        """Test 6: Authentication"""
        try:
            # Test sin autenticación
            response = requests.get(f"{self.base_url}/workflow-templates", timeout=10)
            
            if response.status_code == 401:
                self.log_test("Authentication", True, "Correctly requires authentication")
                return True
            else:
                self.log_test("Authentication", False, f"Expected 401, got {response.status_code}", response.text)
                return False
                
        except requests.exceptions.RequestException as e:
            self.log_test("Authentication", False, f"Request error: {str(e)}")
            return False

    def test_temporalio_server_connectivity(self):
        """Test 7: Temporalio Server Connectivity"""
        try:
            # Test del WebUI de Temporalio
            response = requests.get("http://localhost:8233/", timeout=10)
            
            if response.status_code == 200:
                self.log_test("Temporalio Server", True, "Temporalio WebUI is accessible")
                return True
            else:
                self.log_test("Temporalio Server", False, f"WebUI HTTP {response.status_code}")
                return False
                
        except requests.exceptions.RequestException as e:
            self.log_test("Temporalio Server", False, f"WebUI not accessible: {str(e)}")
            return False

    def run_all_tests(self):
        """Execute all integration tests"""
        print("🚀 Starting Temporalio Microservice Integration Tests\n")
        print(f"Testing service at: {self.base_url}")
        print("=" * 60)
        
        # Test 1: Health Check
        health_ok = self.test_health_check()
        
        # Test 2: Authentication
        auth_ok = self.test_authentication()
        
        # Test 3: Templates Endpoint
        templates = self.test_workflow_templates_endpoint()
        
        # Test 4: Specific Template
        template = self.test_get_specific_template()
        
        # Test 5: Workflow Execution (solo si los anteriores funcionan)
        workflow_id = None
        if health_ok and templates is not None:
            workflow_id = self.test_workflow_execution()
        
        # Test 6: Workflow Status (solo si se ejecutó un workflow)
        if workflow_id:
            time.sleep(2)  # Esperar un poco para el estado
            self.test_workflow_status(workflow_id)
        
        # Test 7: Temporalio Server
        self.test_temporalio_server_connectivity()
        
        # Resumen de resultados
        self.print_summary()
        
        return self.test_results

    def print_summary(self):
        """Print test summary"""
        print("\n" + "=" * 60)
        print("🔍 RESUMEN DE TESTS")
        print("=" * 60)
        
        total_tests = len(self.test_results)
        passed_tests = sum(1 for result in self.test_results if result["success"])
        failed_tests = total_tests - passed_tests
        
        print(f"Total Tests: {total_tests}")
        print(f"✅ Passed: {passed_tests}")
        print(f"❌ Failed: {failed_tests}")
        print(f"Success Rate: {(passed_tests/total_tests)*100:.1f}%")
        
        if failed_tests > 0:
            print("\n❌ FAILED TESTS:")
            for result in self.test_results:
                if not result["success"]:
                    print(f"   - {result['test']}: {result['message']}")
        
        print("\n" + "=" * 60)


def main():
    """Main test execution"""
    tester = TemporalioIntegrationTest()
    results = tester.run_all_tests()
    
    # Guardar resultados en archivo
    with open("/tmp/temporalio_test_results.json", "w") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    
    print(f"\n📁 Resultados guardados en: /tmp/temporalio_test_results.json")
    
    # Exit code basado en resultados
    failed_tests = sum(1 for result in results if not result["success"])
    return 0 if failed_tests == 0 else 1


if __name__ == "__main__":
    exit(main())
