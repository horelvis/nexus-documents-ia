#!/usr/bin/env python3
"""
Script to seed the database with default agent definitions
"""
import asyncio
import sys
import os

# Add the backend directory to the Python path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.db.database import SessionLocal
from app.db.agent_models import AgentDefinition, AgentType, AgentExecutionMode
from sqlalchemy.exc import IntegrityError

def seed_agent_definitions():
    """Seed the database with default agent definitions"""
    
    agent_definitions = [
        {
            "agent_type": AgentType.DOCUMENT_ANALYZER,
            "name": "Document Analyzer",
            "description": "Analyzes and categorizes documents using advanced AI",
            "category": "document",
            "capabilities": {
                "capabilities": ["classification", "extraction", "analysis", "summarization"],
                "supported_formats": ["pdf", "docx", "txt", "md"],
                "languages": ["en", "es", "fr", "de"]
            },
            "required_permissions": ["document.read", "ai.analyze"],
            "execution_mode": AgentExecutionMode.CONFIRMATION_REQUIRED,
            "requires_context": True,
            "supports_streaming": True,
            "max_tokens": 4000,
            "timeout_seconds": 300
        },
        {
            "agent_type": AgentType.RAG_ASSISTANT,
            "name": "RAG Assistant",
            "description": "Retrieval-Augmented Generation for intelligent Q&A",
            "category": "assistant",
            "capabilities": {
                "capabilities": ["search", "qa", "context_retrieval", "multi_turn_conversation"],
                "search_types": ["semantic", "keyword", "hybrid"],
                "languages": ["en", "es"]
            },
            "required_permissions": ["document.read", "search.execute"],
            "execution_mode": AgentExecutionMode.AUTOMATIC,
            "requires_context": False,
            "supports_streaming": True,
            "max_tokens": 2000,
            "timeout_seconds": 60
        },
        {
            "agent_type": AgentType.SIGNATURE_AGENT,
            "name": "Digital Signature Agent",
            "description": "Manages digital signature workflows and processes",
            "category": "workflow",
            "capabilities": {
                "capabilities": ["signature_management", "tracking", "validation", "notifications"],
                "signature_types": ["electronic", "digital", "wet_signature"],
                "providers": ["docusign", "adobe_sign", "internal"]
            },
            "required_permissions": ["document.read", "document.sign", "workflow.execute"],
            "execution_mode": AgentExecutionMode.CONFIRMATION_REQUIRED,
            "requires_context": True,
            "supports_streaming": False,
            "max_tokens": 1000,
            "timeout_seconds": 600
        },
        {
            "agent_type": AgentType.LEGAL_ADVISOR,
            "name": "Legal Compliance Agent",
            "description": "Validates legal requirements and ensures compliance",
            "category": "legal",
            "capabilities": {
                "capabilities": ["compliance_check", "risk_assessment", "regulatory_validation"],
                "jurisdictions": ["us", "eu", "uk", "international"],
                "legal_areas": ["contract", "privacy", "employment", "corporate"]
            },
            "required_permissions": ["document.read", "legal.analyze"],
            "execution_mode": AgentExecutionMode.CONFIRMATION_REQUIRED,
            "requires_context": True,
            "supports_streaming": True,
            "max_tokens": 3000,
            "timeout_seconds": 600
        },
        {
            "agent_type": AgentType.FINANCIAL_ANALYZER,
            "name": "Financial Analysis Agent",
            "description": "Analyzes financial documents and generates insights",
            "category": "financial",
            "capabilities": {
                "capabilities": ["financial_metrics", "trend_analysis", "reporting", "forecasting"],
                "document_types": ["invoices", "statements", "reports", "contracts"],
                "currencies": ["USD", "EUR", "GBP", "JPY"]
            },
            "required_permissions": ["document.read", "financial.analyze"],
            "execution_mode": AgentExecutionMode.CONFIRMATION_REQUIRED,
            "requires_context": True,
            "supports_streaming": True,
            "max_tokens": 3000,
            "timeout_seconds": 300
        },
        {
            "agent_type": AgentType.CONTRACT_INTELLIGENCE,
            "name": "Contract Analyzer",
            "description": "Analyzes contracts and legal agreements",
            "category": "legal",
            "capabilities": {
                "capabilities": ["clause_extraction", "risk_identification", "comparison", "negotiation_support"],
                "contract_types": ["employment", "vendor", "lease", "service", "nda"],
                "analysis_types": ["terms", "obligations", "risks", "compliance"]
            },
            "required_permissions": ["document.read", "legal.analyze", "contract.analyze"],
            "execution_mode": AgentExecutionMode.CONFIRMATION_REQUIRED,
            "requires_context": True,
            "supports_streaming": True,
            "max_tokens": 4000,
            "timeout_seconds": 600
        },
        {
            "agent_type": AgentType.COMPLIANCE_CHECKER,
            "name": "Compliance Checker",
            "description": "Automated compliance validation and reporting",
            "category": "compliance",
            "capabilities": {
                "capabilities": ["policy_check", "regulatory_scan", "violation_detection", "reporting"],
                "standards": ["gdpr", "hipaa", "sox", "iso27001", "pci_dss"],
                "check_types": ["automatic", "scheduled", "on_demand"]
            },
            "required_permissions": ["document.read", "compliance.check"],
            "execution_mode": AgentExecutionMode.AUTOMATIC,
            "requires_context": True,
            "supports_streaming": False,
            "max_tokens": 2000,
            "timeout_seconds": 300
        }
    ]
    
    with SessionLocal() as db:
        created_count = 0
        updated_count = 0
        
        for agent_data in agent_definitions:
            try:
                # Check if agent definition already exists
                existing_agent = db.query(AgentDefinition).filter(
                    AgentDefinition.agent_type == agent_data["agent_type"]
                ).first()
                
                if existing_agent:
                    # Update existing agent
                    for key, value in agent_data.items():
                        if key != "agent_type":  # Don't update the type
                            setattr(existing_agent, key, value)
                    updated_count += 1
                    print(f"Updated agent definition: {agent_data['name']}")
                else:
                    # Create new agent definition
                    agent_def = AgentDefinition(**agent_data)
                    db.add(agent_def)
                    created_count += 1
                    print(f"Created agent definition: {agent_data['name']}")
                    
            except IntegrityError as e:
                print(f"Error with agent {agent_data['name']}: {str(e)}")
                db.rollback()
                continue
            except Exception as e:
                print(f"Unexpected error with agent {agent_data['name']}: {str(e)}")
                db.rollback()
                continue
        
        try:
            db.commit()
            print(f"\n✅ Agent seeding completed!")
            print(f"   Created: {created_count} new agent definitions")
            print(f"   Updated: {updated_count} existing agent definitions")
            print(f"   Total: {created_count + updated_count} agent definitions processed")
        except Exception as e:
            print(f"❌ Failed to commit changes: {str(e)}")
            db.rollback()

if __name__ == "__main__":
    print("🚀 Seeding agent definitions...")
    seed_agent_definitions()