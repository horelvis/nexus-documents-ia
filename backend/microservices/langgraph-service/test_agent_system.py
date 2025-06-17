#!/usr/bin/env python3
"""
Test script for the dynamic agent system with LangGraph + CrewAI
Tests document analysis with the software service agreement
"""
import asyncio
import json
from pathlib import Path
import sys
from datetime import datetime
from typing import Dict, Any

# Add parent directory to path
sys.path.append(str(Path(__file__).parent.parent.parent.parent))

from loguru import logger
from langchain_ollama import ChatOllama
from langgraph.checkpoint.memory import MemorySaver

from app.graphs.document_analysis_crew import DocumentAnalysisCrew


async def load_test_document() -> str:
    """Load the test document"""
    doc_path = Path(__file__).parent / "test_documents" / "software_service_agreement.md"
    if not doc_path.exists():
        raise FileNotFoundError(f"Test document not found: {doc_path}")
    
    with open(doc_path, 'r', encoding='utf-8') as f:
        return f.read()


async def test_agent_system():
    """Test the dynamic agent system with a complex document"""
    logger.info("=== Starting Agent System Test ===")
    
    # Load test document
    logger.info("Loading test document...")
    document_content = await load_test_document()
    logger.info(f"Document loaded: {len(document_content)} characters")
    
    # Initialize components
    logger.info("Initializing LLM and components...")
    llm = ChatOllama(
        model="llama3.2",
        temperature=0.3,
        base_url="http://localhost:11434"  # Adjust if needed
    )
    
    checkpointer = MemorySaver()
    
    # Create document analysis crew
    logger.info("Creating DocumentAnalysisCrew with dynamic agents...")
    crew = DocumentAnalysisCrew(
        llm=llm,
        checkpointer=checkpointer
    )
    
    # Prepare input
    input_data = {
        "document_id": "test-saas-agreement-001",
        "document_content": document_content,
        "tenant_id": "test-tenant",
        "user_id": "test-user"
    }
    
    logger.info("Starting document analysis...")
    logger.info("This will:")
    logger.info("1. Classify the document type")
    logger.info("2. Select appropriate specialist agents")
    logger.info("3. Extract entities and data")
    logger.info("4. Run CrewAI with selected agents")
    logger.info("5. Perform specialized analysis (compliance, financial, risk)")
    logger.info("6. Synthesize findings and generate recommendations")
    
    start_time = datetime.now()
    
    try:
        # Execute the analysis
        result = await crew.ainvoke(input_data)
        
        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()
        
        # Display results
        logger.success(f"\n=== Analysis Complete in {duration:.2f} seconds ===")
        
        print("\n📄 DOCUMENT ANALYSIS RESULTS")
        print("=" * 80)
        
        print(f"\n📋 Document Type: {result['document_type']}")
        print(f"✍️  Requires Signature: {result['requires_signature']}")
        print(f"✅ Success: {result['success']}")
        
        if result.get('error'):
            print(f"❌ Error: {result['error']}")
        
        print(f"\n🤖 Agents Used ({len(result['agents_used'])}):")
        for agent_id in result['agents_used']:
            print(f"   - {agent_id}")
        
        print("\n📊 Analysis Summary:")
        analysis = result.get('analysis', {})
        if analysis:
            print(f"   - Summary: {analysis.get('summary', 'N/A')[:200]}...")
            print(f"   - Compliance Status: {analysis.get('compliance_status', 'N/A')}")
            print(f"   - Risk Level: {analysis.get('risk_level', 'N/A')}")
            print(f"   - Confidence Score: {analysis.get('confidence_score', 0):.2%}")
        
        print("\n💡 Key Recommendations:")
        recommendations = result.get('recommendations', [])
        for i, rec in enumerate(recommendations[:5], 1):
            print(f"   {i}. {rec}")
        
        print("\n📌 Action Items:")
        action_items = result.get('action_items', [])
        for item in action_items:
            print(f"   - [{item.get('priority', 'medium').upper()}] {item.get('type', 'N/A')}: {item.get('description', 'N/A')}")
        
        print("\n💰 Financial Metrics:")
        financial = result.get('financial_metrics', {})
        if financial:
            print(f"   - Monthly Base Fee: ${financial.get('monthly_base', 'N/A')}")
            print(f"   - Annual Commitment: ${financial.get('annual_minimum', 'N/A')}")
            print(f"   - Contract Length: {financial.get('contract_length', 'N/A')}")
        
        print("\n📊 Extracted Data (Sample):")
        extracted = result.get('extracted_data', {})
        if extracted:
            # Show first few extracted items
            for key, value in list(extracted.items())[:5]:
                print(f"   - {key}: {str(value)[:100]}...")
        
        print("\n⚖️ Compliance Check:")
        compliance = result.get('compliance_status', {})
        if compliance:
            print(f"   - Status: {compliance.get('status', 'N/A')}")
            if 'issues' in compliance:
                print(f"   - Issues Found: {len(compliance['issues'])}")
        
        print("\n⚠️ Risk Assessment:")
        risk = result.get('risk_assessment', {})
        if risk:
            print(f"   - Overall Risk: {risk.get('overall_risk', 'N/A')}")
            if 'risks' in risk:
                print(f"   - Identified Risks: {len(risk['risks'])}")
        
        print("\n🎯 Confidence Scores:")
        scores = result.get('confidence_scores', {})
        for metric, score in scores.items():
            print(f"   - {metric.replace('_', ' ').title()}: {score:.2%}")
        
        # Save detailed results
        output_file = Path(__file__).parent / f"test_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(result, f, indent=2, default=str)
        
        print(f"\n💾 Detailed results saved to: {output_file}")
        
    except Exception as e:
        logger.error(f"Test failed: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    return True


async def test_streaming():
    """Test streaming execution of the analysis"""
    logger.info("\n=== Testing Streaming Analysis ===")
    
    document_content = await load_test_document()
    
    llm = ChatOllama(
        model="llama3.2",
        temperature=0.3,
        base_url="http://localhost:11434"
    )
    
    checkpointer = MemorySaver()
    crew = DocumentAnalysisCrew(
        llm=llm,
        checkpointer=checkpointer
    )
    
    input_data = {
        "document_id": "test-streaming-001",
        "document_content": document_content[:2000],  # Use shorter content for streaming test
        "tenant_id": "test-tenant",
        "user_id": "test-user"
    }
    
    try:
        logger.info("Starting streaming analysis...")
        event_count = 0
        
        async for event in crew.astream_events(input_data, version="v1"):
            event_count += 1
            
            if event["event"] == "on_chain_start":
                logger.info(f"🔗 Chain started: {event.get('name', 'unknown')}")
            elif event["event"] == "on_chain_end":
                logger.info(f"✅ Chain completed: {event.get('name', 'unknown')}")
            elif event["event"] == "on_tool_start":
                logger.info(f"🔧 Tool started: {event.get('name', 'unknown')}")
            elif event["event"] == "on_tool_end":
                logger.info(f"✔️ Tool completed: {event.get('name', 'unknown')}")
            
            # Log every 10th event to avoid spam
            if event_count % 10 == 0:
                logger.info(f"... processed {event_count} events")
        
        logger.success(f"Streaming test complete. Total events: {event_count}")
        
    except Exception as e:
        logger.error(f"Streaming test failed: {e}")
        return False
    
    return True


def display_agent_info():
    """Display information about loaded agents"""
    from app.agents.agent_loader import agent_loader
    
    print("\n🤖 LOADED AGENTS")
    print("=" * 80)
    
    # Load agents
    agent_loader.load_all_agents()
    
    print(f"\nTotal agents loaded: {len(agent_loader.agents_collection.agents)}")
    
    for agent in agent_loader.agents_collection.agents:
        print(f"\n📌 {agent.name} ({agent.id})")
        print(f"   Role: {agent.role}")
        print(f"   Capabilities: {', '.join([c.value for c in agent.capabilities])}")
        print(f"   Document Types: {', '.join(agent.document_types)}")
        print(f"   Active: {'✅' if agent.active else '❌'}")
    
    # Show selection rules
    print("\n📋 DOCUMENT TYPE MAPPINGS")
    print("=" * 80)
    rules = agent_loader.get_agent_selection_rules()
    for doc_type, agent_ids in rules.items():
        print(f"\n{doc_type}:")
        for agent_id in agent_ids:
            agent = agent_loader.get_agent_definition(agent_id)
            if agent:
                print(f"   - {agent.name}")


async def main():
    """Run all tests"""
    print("\n" + "="*80)
    print("🧪 DYNAMIC AGENT SYSTEM TEST SUITE")
    print("="*80)
    
    # Display agent information
    display_agent_info()
    
    # Test 1: Full document analysis
    print("\n\n📝 TEST 1: Full Document Analysis")
    print("-" * 80)
    success1 = await test_agent_system()
    
    # Test 2: Streaming analysis
    print("\n\n📡 TEST 2: Streaming Analysis")
    print("-" * 80)
    success2 = await test_streaming()
    
    # Summary
    print("\n\n📊 TEST SUMMARY")
    print("=" * 80)
    print(f"Test 1 (Full Analysis): {'✅ PASSED' if success1 else '❌ FAILED'}")
    print(f"Test 2 (Streaming): {'✅ PASSED' if success2 else '❌ FAILED'}")
    
    if success1 and success2:
        logger.success("\n🎉 All tests passed! The agent system is working correctly.")
    else:
        logger.error("\n❌ Some tests failed. Please check the logs above.")


if __name__ == "__main__":
    # Configure logging
    logger.remove()
    logger.add(
        sys.stdout,
        format="<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
        level="INFO"
    )
    
    # Run tests
    asyncio.run(main())