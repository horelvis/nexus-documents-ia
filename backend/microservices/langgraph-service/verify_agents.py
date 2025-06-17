#!/usr/bin/env python3
"""
Simple verification script for agent definitions
"""
import json
from pathlib import Path

def verify_agent_definitions():
    """Verify all agent definition JSON files"""
    definitions_dir = Path(__file__).parent / "app" / "agents" / "definitions"
    
    if not definitions_dir.exists():
        print(f"❌ Definitions directory not found: {definitions_dir}")
        return False
    
    print(f"\n📁 Agent Definitions Directory: {definitions_dir}")
    print("=" * 80)
    
    json_files = list(definitions_dir.glob("*.json"))
    print(f"\nFound {len(json_files)} agent definition files")
    
    all_valid = True
    agents = []
    
    for json_file in sorted(json_files):
        print(f"\n📄 Checking {json_file.name}...")
        
        try:
            with open(json_file, 'r', encoding='utf-8') as f:
                agent_def = json.load(f)
            
            # Check required fields
            required_fields = ['id', 'name', 'role', 'goal', 'backstory']
            missing_fields = [field for field in required_fields if field not in agent_def]
            
            if missing_fields:
                print(f"   ❌ Missing required fields: {missing_fields}")
                all_valid = False
                continue
            
            # Display agent info
            print(f"   ✅ Valid agent definition")
            print(f"   - ID: {agent_def['id']}")
            print(f"   - Name: {agent_def['name']}")
            print(f"   - Role: {agent_def['role']}")
            print(f"   - Capabilities: {', '.join(agent_def.get('capabilities', []))}")
            print(f"   - Document Types: {', '.join(agent_def.get('document_types', []))}")
            print(f"   - Active: {'Yes' if agent_def.get('active', True) else 'No'}")
            
            agents.append(agent_def)
            
        except json.JSONDecodeError as e:
            print(f"   ❌ Invalid JSON: {e}")
            all_valid = False
        except Exception as e:
            print(f"   ❌ Error reading file: {e}")
            all_valid = False
    
    # Summary
    print("\n" + "=" * 80)
    print("📊 SUMMARY")
    print("=" * 80)
    print(f"Total agents: {len(agents)}")
    print(f"Status: {'✅ All valid' if all_valid else '❌ Some errors found'}")
    
    # Group by capabilities
    print("\n🎯 Agents by Capability:")
    capability_map = {}
    for agent in agents:
        for cap in agent.get('capabilities', []):
            if cap not in capability_map:
                capability_map[cap] = []
            capability_map[cap].append(agent['name'])
    
    for cap, agent_names in sorted(capability_map.items()):
        print(f"   {cap}: {', '.join(agent_names)}")
    
    # Group by document types
    print("\n📄 Agents by Document Type:")
    doc_type_map = {}
    for agent in agents:
        for doc_type in agent.get('document_types', []):
            if doc_type not in doc_type_map:
                doc_type_map[doc_type] = []
            doc_type_map[doc_type].append(agent['name'])
    
    for doc_type, agent_names in sorted(doc_type_map.items()):
        print(f"   {doc_type}: {', '.join(agent_names)}")
    
    # Test document analysis flow
    print("\n🔄 Sample Document Analysis Flow:")
    print("1. Document uploaded: 'software_service_agreement.md'")
    print("2. Document classified as: 'agreement'")
    print("3. Agents selected for analysis:")
    
    # Simulate agent selection for agreement
    agreement_agents = []
    for agent in agents:
        if 'agreement' in agent.get('document_types', []) or 'all' in agent.get('document_types', []):
            if agent.get('active', True):
                agreement_agents.append(agent)
                print(f"   - {agent['name']} ({agent['role']})")
    
    print(f"\n4. Total agents assigned: {len(agreement_agents)}")
    print("5. Analysis workflow:")
    print("   - Entity extraction by Data Extraction Specialist")
    print("   - Contract review by Contract Review Expert")
    print("   - Financial analysis by Financial Document Analyst")
    print("   - Compliance check by Compliance Officer")
    print("   - Risk assessment by Risk Assessment Specialist")
    print("   - Summary generation by Executive Summary Writer")
    
    return all_valid


def main():
    """Run verification"""
    print("🤖 NEXUS DOCUMENT AGENT SYSTEM VERIFICATION")
    print("=" * 80)
    
    success = verify_agent_definitions()
    
    print("\n" + "=" * 80)
    if success:
        print("✅ Agent system ready for deployment!")
        print("\nNext steps:")
        print("1. Start the Langraph service: cd backend/docker && ./start-dev.sh")
        print("2. Access API documentation: http://localhost:8000/docs")
        print("3. Test document analysis endpoint: POST /api/v1/agents/document/analyze")
    else:
        print("❌ Please fix the errors above before proceeding")
    
    return 0 if success else 1


if __name__ == "__main__":
    exit(main())