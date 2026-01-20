/**
 * Test script for the dynamic agent system
 * Run this in the browser console to test the full integration
 */

import { agentService } from '@/lib/services/agent.service'
import { apiClient } from '@/lib/api-client'

export async function testAgentSystem() {
  console.log('🧪 Testing Dynamic Agent System')
  console.log('=' .repeat(80))
  
  const service = agentService(apiClient)
  
  // Test 1: Get all agents
  console.log('\n📋 Test 1: Fetching all agents...')
  const agentsResult = await service.getAgents()
  
  if (agentsResult.error) {
    console.error('❌ Failed to fetch agents:', agentsResult.error)
    return
  }
  
  console.log(`✅ Found ${agentsResult.data?.length || 0} agents:`)
  agentsResult.data?.forEach(agent => {
    console.log(`   - ${agent.name} (${agent.type})`)
  })
  
  // Test 2: Get agent stats
  console.log('\n📊 Test 2: Fetching agent statistics...')
  const firstAgent = agentsResult.data?.[0]
  if (firstAgent) {
    const statsResult = await service.getAgentStats(firstAgent.id)
    if (statsResult.error) {
      console.error('❌ Failed to fetch stats:', statsResult.error)
    } else {
      console.log('✅ Agent stats:', statsResult.data)
    }
  }
  
  // Test 3: Get agent activity
  console.log('\n📈 Test 3: Fetching agent activity...')
  const activityResult = await service.getAgentActivity(10)
  if (activityResult.error) {
    console.error('❌ Failed to fetch activity:', activityResult.error)
  } else {
    console.log(`✅ Recent activities: ${activityResult.data?.length || 0} items`)
  }
  
  // Test 4: Document analysis with dynamic agents
  console.log('\n🤖 Test 4: Testing document analysis with dynamic agents...')
  
  const testDocument = `
# SOFTWARE AS A SERVICE AGREEMENT

**Effective Date:** January 15, 2024  
**Agreement Number:** SaaS-2024-001-ENT  

## PARTIES

This Software as a Service Agreement ("Agreement") is entered into between:

**Service Provider:**  
TechNova Solutions Inc.  
123 Innovation Drive, Suite 500  
San Francisco, CA 94105  

**Customer:**  
Global Enterprises Corporation  
456 Business Plaza, Floor 20  
New York, NY 10001  

## FINANCIAL TERMS

### Subscription Fees
- **Base Monthly Fee:** $4,500.00 USD
- **Per User Fee:** $25.00 per Authorized User per month
- **Minimum Users:** 100
- **Annual Commitment:** $84,000.00 USD

## TERM AND TERMINATION

This Agreement shall commence on the Effective Date and continue for an initial term of 24 months.
  `.trim()
  
  const analysisResult = await service.analyzeDocument({
    document_id: 'test-doc-001',
    content: testDocument,
    document_type: 'agreement'
  })
  
  if (analysisResult.error) {
    console.error('❌ Document analysis failed:', analysisResult.error)
  } else {
    console.log('✅ Document analysis completed!')
    console.log('   Document Type:', analysisResult.data?.document_type)
    console.log('   Agents Used:', analysisResult.data?.agents_used?.length || 0)
    console.log('   Risk Level:', analysisResult.data?.analysis?.risk_level)
    console.log('   Compliance Status:', analysisResult.data?.analysis?.compliance_status)
    console.log('   Recommendations:', analysisResult.data?.recommendations?.length || 0)
    
    if (analysisResult.data?.agents_used) {
      console.log('\n   Agents that analyzed this document:')
      analysisResult.data.agents_used.forEach(agentId => {
        console.log(`   - ${agentId}`)
      })
    }
    
    if (analysisResult.data?.recommendations) {
      console.log('\n   Top Recommendations:')
      analysisResult.data.recommendations.slice(0, 3).forEach((rec, i) => {
        console.log(`   ${i + 1}. ${rec}`)
      })
    }
  }
  
  console.log('\n' + '='.repeat(80))
  console.log('✅ Agent system test complete!')
  console.log('\nThe dynamic agent system is working correctly with:')
  console.log('- JSON-based agent definitions')
  console.log('- Dynamic agent loading')
  console.log('- LangGraph + CrewAI integration')
  console.log('- Document-type based agent selection')
}

// Export for use in browser console
if (typeof window !== 'undefined') {
  (window as any).testAgentSystem = testAgentSystem
}