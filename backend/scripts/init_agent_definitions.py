#!/usr/bin/env python3
"""
Initialize Agent Definitions in the database
"""
import asyncio
import logging
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.async_database import get_async_db
from app.db.agent_models import AgentDefinition, AgentType, AgentExecutionMode

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Agent definitions to be created
AGENT_DEFINITIONS = [
    {
        "agent_type": AgentType.DOCUMENT_ANALYZER,
        "name": "Document Analyzer",
        "description": "Analyzes documents to extract key information, classify content, and provide insights",
        "category": "document",
        "capabilities": {
            "extraction": ["entities", "dates", "amounts", "references"],
            "classification": ["type", "language", "domain"],
            "analysis": ["summary", "key_points", "sentiment"]
        },
        "required_permissions": ["document:read"],
        "execution_mode": AgentExecutionMode.AUTOMATIC,
        "requires_context": True,
        "supports_streaming": True,
        "max_tokens": 2000,
        "timeout_seconds": 300
    },
    {
        "agent_type": AgentType.CONTRACT_INTELLIGENCE,
        "name": "Contract Intelligence",
        "description": "Specialized agent for analyzing contracts, identifying clauses, risks, and obligations",
        "category": "legal",
        "capabilities": {
            "clause_detection": ["terms", "conditions", "obligations", "penalties"],
            "risk_analysis": ["high_risk_clauses", "missing_clauses", "ambiguities"],
            "comparison": ["standard_templates", "market_standards"]
        },
        "required_permissions": ["document:read", "legal:analyze"],
        "execution_mode": AgentExecutionMode.CONFIRMATION_REQUIRED,
        "requires_context": True,
        "supports_streaming": True,
        "max_tokens": 4000,
        "timeout_seconds": 600
    },
    {
        "agent_type": AgentType.COMPLIANCE_CHECKER,
        "name": "Compliance Checker",
        "description": "Verifies documents against regulatory requirements and compliance standards",
        "category": "compliance",
        "capabilities": {
            "regulations": ["GDPR", "HIPAA", "SOX", "local_regulations"],
            "validation": ["required_fields", "format_compliance", "data_protection"],
            "reporting": ["compliance_score", "violations", "recommendations"]
        },
        "required_permissions": ["document:read", "compliance:check"],
        "execution_mode": AgentExecutionMode.AUTOMATIC,
        "requires_context": True,
        "supports_streaming": False,
        "max_tokens": 3000,
        "timeout_seconds": 450
    },
    {
        "agent_type": AgentType.SIGNATURE_AGENT,
        "name": "Digital Signature Agent",
        "description": "Manages digital signature workflows, tracks signing progress, and ensures completion",
        "category": "workflow",
        "capabilities": {
            "signature_management": ["placement", "tracking", "reminders"],
            "workflow": ["sequential", "parallel", "conditional"],
            "integration": ["docusign", "adobe_sign", "internal"]
        },
        "required_permissions": ["document:read", "signature:manage"],
        "execution_mode": AgentExecutionMode.AUTOMATIC,
        "requires_context": True,
        "supports_streaming": False,
        "max_tokens": 1000,
        "timeout_seconds": 180
    },
    {
        "agent_type": AgentType.FINANCIAL_ANALYZER,
        "name": "Financial Analyzer",
        "description": "Analyzes financial documents, extracts metrics, and provides financial insights",
        "category": "financial",
        "capabilities": {
            "extraction": ["revenue", "expenses", "ratios", "trends"],
            "analysis": ["profitability", "liquidity", "solvency", "efficiency"],
            "forecasting": ["projections", "scenarios", "risks"]
        },
        "required_permissions": ["document:read", "financial:analyze"],
        "execution_mode": AgentExecutionMode.CONFIRMATION_REQUIRED,
        "requires_context": True,
        "supports_streaming": True,
        "max_tokens": 3000,
        "timeout_seconds": 500
    },
    {
        "agent_type": AgentType.LEGAL_ADVISOR,
        "name": "Legal Advisor",
        "description": "Provides legal insights, identifies potential issues, and suggests legal considerations",
        "category": "legal",
        "capabilities": {
            "review": ["legal_issues", "liability", "compliance"],
            "advice": ["recommendations", "alternatives", "best_practices"],
            "research": ["precedents", "regulations", "case_law"]
        },
        "required_permissions": ["document:read", "legal:advise"],
        "execution_mode": AgentExecutionMode.CONFIRMATION_REQUIRED,
        "requires_context": True,
        "supports_streaming": True,
        "max_tokens": 4000,
        "timeout_seconds": 600
    },
    {
        "agent_type": AgentType.RAG_ASSISTANT,
        "name": "RAG Assistant",
        "description": "Retrieval-augmented generation assistant for Q&A across document collections",
        "category": "assistant",
        "capabilities": {
            "search": ["semantic", "keyword", "hybrid"],
            "qa": ["factual", "analytical", "comparative"],
            "synthesis": ["multi_document", "summarization", "insights"]
        },
        "required_permissions": ["document:read"],
        "execution_mode": AgentExecutionMode.AUTOMATIC,
        "requires_context": False,
        "supports_streaming": True,
        "max_tokens": 2000,
        "timeout_seconds": 300
    }
]


async def init_agent_definitions():
    """Initialize agent definitions in the database"""
    async for db in get_async_db():
        created_count = 0
        updated_count = 0
        
        for agent_def in AGENT_DEFINITIONS:
            # Check if agent type already exists
            query = select(AgentDefinition).where(
                AgentDefinition.agent_type == agent_def["agent_type"]
            )
            result = await db.execute(query)
            existing = result.scalar_one_or_none()
            
            if existing:
                # Update existing definition
                for key, value in agent_def.items():
                    setattr(existing, key, value)
                updated_count += 1
                logger.info(f"Updated agent definition: {agent_def['name']}")
            else:
                # Create new definition
                new_definition = AgentDefinition(**agent_def)
                db.add(new_definition)
                created_count += 1
                logger.info(f"Created agent definition: {agent_def['name']}")
        
        await db.commit()
        
        logger.info(f"✅ Agent definitions initialized: {created_count} created, {updated_count} updated")
        
        # List all agent definitions
        all_query = select(AgentDefinition).order_by(AgentDefinition.category, AgentDefinition.name)
        all_result = await db.execute(all_query)
        all_definitions = all_result.scalars().all()
        
        logger.info("\n📋 All Agent Definitions:")
        for definition in all_definitions:
            logger.info(f"  - {definition.name} ({definition.agent_type.value}) - {definition.category}")
        
        break  # Exit after first iteration since we only need one session


if __name__ == "__main__":
    asyncio.run(init_agent_definitions())