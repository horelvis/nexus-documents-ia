"""
Specialist Agent Nodes

Domain-specific agents with specialized tools and prompts.
Currently implemented:

- Privacy: GDPR, data protection, consent (LOPD, RGPD)
- Legal: Spanish legislation, BOE search, jurisprudence
- General: Fallback for non-specialized queries

Future agents (to be implemented as needed):
- Labor: Employment law, contracts, dismissals, payroll
- Fiscal: Tax law, VAT, invoices, declarations
- Contract: General contract analysis

Each agent:
1. Has domain-specific system prompt
2. Has access to domain-specific tools
3. Operates on the retrieved documents
4. Returns results to shared state
"""

from .privacy import privacy_node
from .legal import legal_node
from .general import general_node
from .base import create_specialist_node

__all__ = [
    "privacy_node",
    "legal_node",
    "general_node",
    "create_specialist_node",
]
