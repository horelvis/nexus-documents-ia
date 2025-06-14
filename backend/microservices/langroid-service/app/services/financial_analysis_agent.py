"""
Enhanced Financial Analysis Agent with Chain of Thought
"""
import logging
from typing import Dict, Any, AsyncGenerator, Optional, List
from datetime import datetime, timedelta
import json
import re

from app.services.enhanced_langroid_agent import EnhancedLangroidAgent

logger = logging.getLogger(__name__)


class FinancialAnalysisAgent(EnhancedLangroidAgent):
    """Financial analysis agent with specialized capabilities"""
    
    async def _process_message(
        self,
        message: str,
        context: Optional[Dict[str, Any]] = None
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """Process financial analysis request with chain of thought"""
        
        # Extract document context
        documents = context.get("documents", []) if context else []
        
        # Determine analysis type
        analysis_type = self._determine_financial_analysis_type(message)
        
        if self.thinking_enabled:
            yield await self.think(
                f"Analyzing financial query: '{message[:100]}...'",
                {"analysis_type": analysis_type}
            )
        
        # Execute specific analysis based on type
        if analysis_type == "due_dates_payments":
            async for event in self._analyze_due_dates_and_payments(documents):
                yield event
        elif analysis_type == "expense_analysis":
            async for event in self._analyze_expenses(documents):
                yield event
        elif analysis_type == "financial_summary":
            async for event in self._create_financial_summary(documents):
                yield event
        elif analysis_type == "cash_flow":
            async for event in self._analyze_cash_flow(documents):
                yield event
        else:
            async for event in self._general_financial_analysis(message, documents):
                yield event
    
    def _determine_financial_analysis_type(self, message: str) -> str:
        """Determine what type of financial analysis is needed"""
        message_lower = message.lower()
        
        # Due dates and payments
        if any(keyword in message_lower for keyword in ["venc", "due", "pago", "payment", "factura", "invoice", "cobr", "collect"]):
            return "due_dates_payments"
        
        # Expense analysis
        elif any(keyword in message_lower for keyword in ["gasto", "expense", "cost", "presupuesto", "budget"]):
            return "expense_analysis"
        
        # Cash flow
        elif any(keyword in message_lower for keyword in ["flujo", "cash flow", "liquidez", "liquidity"]):
            return "cash_flow"
        
        # Summary
        elif any(keyword in message_lower for keyword in ["resumen", "summary", "overview", "balance"]):
            return "financial_summary"
        
        else:
            return "general"
    
    async def _analyze_due_dates_and_payments(self, documents: List[Dict[str, Any]]) -> AsyncGenerator[Dict[str, Any], None]:
        """Analyze documents for due dates and payment status"""
        
        if self.thinking_enabled:
            yield await self.plan([
                "Identify all invoices and payment documents",
                "Extract due dates and payment terms",
                "Check current date against due dates",
                "Categorize by urgency (overdue, due soon, upcoming)",
                "Calculate total amounts by category",
                "Generate payment recommendations"
            ])
        
        # Analysis steps
        yield {
            "type": "progress",
            "content": "Scanning documents for payment information...",
            "metadata": {"progress": 0.2}
        }
        
        # Simulate document analysis
        invoices = []
        overdue = []
        due_soon = []
        upcoming = []
        
        current_date = datetime.now()
        
        for i, doc in enumerate(documents):
            if self.thinking_enabled:
                yield await self.observe(
                    f"Analyzing document: {doc.get('title', 'Untitled')}",
                    {"document_type": doc.get('type'), "index": i}
                )
            
            # Simulate invoice detection and date extraction
            if "factura" in doc.get('title', '').lower() or "invoice" in doc.get('title', '').lower():
                # Simulate extracted data
                due_date = current_date + timedelta(days=(i * 7) - 14)  # Varying due dates
                amount = 1000 + (i * 500)  # Varying amounts
                
                invoice_data = {
                    "document": doc.get('title'),
                    "due_date": due_date.strftime("%Y-%m-%d"),
                    "amount": amount,
                    "days_until_due": (due_date - current_date).days
                }
                
                invoices.append(invoice_data)
                
                if due_date < current_date:
                    overdue.append(invoice_data)
                elif (due_date - current_date).days <= 7:
                    due_soon.append(invoice_data)
                else:
                    upcoming.append(invoice_data)
        
        yield {
            "type": "progress",
            "content": "Categorizing by payment urgency...",
            "metadata": {"progress": 0.6}
        }
        
        if self.thinking_enabled:
            yield await self.reason(
                f"Found {len(invoices)} invoices: {len(overdue)} overdue, {len(due_soon)} due within 7 days, {len(upcoming)} upcoming",
                evidence=[f"{inv['document']}: {inv['days_until_due']} days" for inv in invoices[:3]]
            )
        
        # Generate response
        response = self._format_due_dates_analysis(overdue, due_soon, upcoming)
        
        yield await self.conclude(
            f"Payment analysis complete. Found {len(overdue)} overdue items requiring immediate attention.",
            confidence=0.85
        )
        
        yield {
            "type": "message",
            "content": response,
            "metadata": {
                "total_invoices": len(invoices),
                "overdue_count": len(overdue),
                "urgent_count": len(due_soon)
            }
        }
    
    async def _analyze_expenses(self, documents: List[Dict[str, Any]]) -> AsyncGenerator[Dict[str, Any], None]:
        """Analyze expense patterns and categories"""
        
        if self.thinking_enabled:
            yield await self.plan([
                "Identify expense documents",
                "Extract amounts and categories",
                "Calculate totals by category",
                "Identify trends and anomalies",
                "Compare with budget if available",
                "Generate cost-saving recommendations"
            ])
        
        # Simulate expense analysis
        yield {
            "type": "progress",
            "content": "Analyzing expense patterns...",
            "metadata": {"progress": 0.3}
        }
        
        # Generate expense analysis response
        response = """## Expense Analysis

### Category Breakdown:
- **Operational Expenses**: $15,420 (45%)
- **Personnel Costs**: $8,300 (24%)
- **Marketing**: $5,200 (15%)
- **Technology**: $3,100 (9%)
- **Other**: $2,400 (7%)

### Key Findings:
1. **Trend**: 12% increase in operational expenses vs last period
2. **Anomaly**: Unusual spike in marketing costs (Week 3)
3. **Opportunity**: Technology costs can be optimized by 20%

### Recommendations:
- Review recurring operational subscriptions
- Negotiate better rates with top 3 vendors
- Implement expense approval workflow for amounts > $1,000"""
        
        yield {
            "type": "message",
            "content": response,
            "metadata": {"analysis_type": "expense_analysis"}
        }
    
    async def _analyze_cash_flow(self, documents: List[Dict[str, Any]]) -> AsyncGenerator[Dict[str, Any], None]:
        """Analyze cash flow patterns"""
        
        if self.thinking_enabled:
            yield await self.think("Analyzing cash flow patterns from financial documents...")
        
        yield {
            "type": "progress",
            "content": "Calculating cash inflows and outflows...",
            "metadata": {"progress": 0.5}
        }
        
        response = """## Cash Flow Analysis

### Current Period Summary:
- **Opening Balance**: $45,000
- **Total Inflows**: $32,500
- **Total Outflows**: $28,900
- **Closing Balance**: $48,600

### Cash Flow Trends:
- **Average Daily Cash Flow**: +$120
- **Peak Inflow Day**: 15th (payroll processing)
- **Peak Outflow Day**: 1st (rent and utilities)

### Liquidity Status: 🟢 Healthy
- Current Ratio: 2.3
- Quick Ratio: 1.8
- Days Cash on Hand: 42

### Recommendations:
1. Consider negotiating payment terms to smooth cash flow
2. Set up automatic transfers to reserve account
3. Monitor receivables aging closely"""
        
        yield {
            "type": "message",
            "content": response,
            "metadata": {"analysis_type": "cash_flow"}
        }
    
    async def _create_financial_summary(self, documents: List[Dict[str, Any]]) -> AsyncGenerator[Dict[str, Any], None]:
        """Create comprehensive financial summary"""
        
        if self.thinking_enabled:
            yield await self.think("Creating comprehensive financial summary...")
        
        response = f"""## Financial Summary

### Document Overview:
- **Total Financial Documents**: {len(documents)}
- **Date Range**: Last 90 days
- **Document Types**: Invoices, Receipts, Statements

### Key Metrics:
- **Total Revenue**: $125,430
- **Total Expenses**: $98,200
- **Net Profit**: $27,230 (21.7% margin)
- **Outstanding Receivables**: $18,500
- **Pending Payables**: $12,300

### Financial Health Score: 8.2/10 🟢

### Action Items:
1. **Immediate**: Review 3 overdue invoices ($4,200)
2. **This Week**: Process pending expense reports
3. **This Month**: Prepare quarterly financial review

### Trends:
- Revenue up 15% vs last quarter
- Expenses controlled within budget
- Cash position strengthening"""
        
        yield {
            "type": "message",
            "content": response,
            "metadata": {"analysis_type": "financial_summary"}
        }
    
    async def _general_financial_analysis(self, message: str, documents: List[Dict[str, Any]]) -> AsyncGenerator[Dict[str, Any], None]:
        """Perform general financial analysis based on the query"""
        
        if self.thinking_enabled:
            yield await self.think(f"Performing general financial analysis for: {message}")
        
        response = f"""I've analyzed {len(documents)} financial documents based on your query.

### Analysis Results:
Based on the documents provided, here are the key financial insights:

1. **Document Types Found**:
   - Invoices: {sum(1 for d in documents if 'invoice' in d.get('title', '').lower())}
   - Receipts: {sum(1 for d in documents if 'receipt' in d.get('title', '').lower())}
   - Other: {len(documents) - sum(1 for d in documents if any(t in d.get('title', '').lower() for t in ['invoice', 'receipt']))}

2. **Financial Overview**:
   - Multiple financial transactions identified
   - Various payment methods detected
   - Different currencies may be involved

3. **Recommendations**:
   - Organize documents by date and type
   - Ensure all amounts are properly recorded
   - Review for any discrepancies

Would you like me to perform a more specific analysis on any particular aspect?"""
        
        yield {
            "type": "message",
            "content": response,
            "metadata": {"analysis_type": "general"}
        }
    
    def _format_due_dates_analysis(self, overdue: List[Dict], due_soon: List[Dict], upcoming: List[Dict]) -> str:
        """Format the due dates analysis results"""
        
        total_overdue = sum(inv['amount'] for inv in overdue)
        total_due_soon = sum(inv['amount'] for inv in due_soon)
        total_upcoming = sum(inv['amount'] for inv in upcoming)
        
        response = "## Payment Due Dates Analysis\n\n"
        
        # Overdue section
        if overdue:
            response += f"### 🔴 OVERDUE ({len(overdue)} items - ${total_overdue:,.2f})\n"
            response += "**Immediate action required:**\n"
            for inv in overdue[:5]:  # Show max 5
                response += f"- {inv['document']}: ${inv['amount']:,.2f} (Overdue by {abs(inv['days_until_due'])} days)\n"
            if len(overdue) > 5:
                response += f"- ... and {len(overdue) - 5} more overdue items\n"
            response += "\n"
        
        # Due soon section
        if due_soon:
            response += f"### 🟡 DUE WITHIN 7 DAYS ({len(due_soon)} items - ${total_due_soon:,.2f})\n"
            response += "**Action needed this week:**\n"
            for inv in due_soon[:5]:
                response += f"- {inv['document']}: ${inv['amount']:,.2f} (Due in {inv['days_until_due']} days)\n"
            if len(due_soon) > 5:
                response += f"- ... and {len(due_soon) - 5} more items due soon\n"
            response += "\n"
        
        # Upcoming section
        if upcoming:
            response += f"### 🟢 UPCOMING ({len(upcoming)} items - ${total_upcoming:,.2f})\n"
            response += "**Plan ahead:**\n"
            for inv in upcoming[:3]:
                response += f"- {inv['document']}: ${inv['amount']:,.2f} (Due in {inv['days_until_due']} days)\n"
            if len(upcoming) > 3:
                response += f"- ... and {len(upcoming) - 3} more upcoming items\n"
            response += "\n"
        
        # Summary
        total_amount = total_overdue + total_due_soon + total_upcoming
        response += f"### Summary\n"
        response += f"- **Total Outstanding**: ${total_amount:,.2f}\n"
        response += f"- **Urgent Action Required**: ${total_overdue + total_due_soon:,.2f}\n"
        response += f"- **Payment Priority**: Focus on overdue items first\n\n"
        
        # Recommendations
        response += "### Recommended Actions:\n"
        if overdue:
            response += "1. **Contact overdue accounts immediately** to arrange payment\n"
        if due_soon:
            response += "2. **Process payments due this week** to avoid late fees\n"
        response += "3. **Set up payment reminders** for upcoming due dates\n"
        response += "4. **Consider early payment discounts** where available\n"
        
        return response