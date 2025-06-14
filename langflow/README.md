# Langflow Agent Flows

This directory contains Langflow-compatible JSON files for the five specialized agents in the Nexus Document Backend system. Each agent is designed as a visual flow that can be imported and customized in Langflow.

## Available Agents

### 1. Financial Analysis Agent (`financial_analysis_agent.json`)
Specialized in analyzing financial documents, tracking due dates, and providing financial insights.

**Key Features:**
- Invoice and payment tracking
- Expense analysis and categorization
- Cash flow analysis
- Due date monitoring and alerts
- Financial summary generation

**Use Cases:**
- "¿Cuándo vencen estas facturas?"
- "Analiza los gastos del último trimestre"
- "¿Cuál es el flujo de caja actual?"

### 2. Document Analyzer Agent (`document_analyzer_agent.json`)
Intelligent document analysis with NLP capabilities for various document types.

**Key Features:**
- Multi-format document support (PDF, DOCX, TXT, XLSX, CSV)
- Summarization and key point extraction
- Keyword and entity extraction
- Sentiment analysis
- Document comparison

**Use Cases:**
- "Resume estos documentos"
- "Extrae las palabras clave principales"
- "Compara estos dos contratos"

### 3. RAG Assistant Agent (`rag_assistant_agent.json`)
Retrieval-Augmented Generation assistant for intelligent Q&A over document collections.

**Key Features:**
- Semantic document search
- Contextual question answering
- Source attribution
- Multi-turn conversations
- Follow-up question suggestions

**Use Cases:**
- "¿Qué dice el contrato sobre penalizaciones?"
- "Busca información sobre términos de pago"
- "Explica las cláusulas de confidencialidad"

### 4. Legal Compliance Agent (`legal_compliance_agent.json`)
Contract analysis specialist focusing on legal compliance and risk assessment.

**Key Features:**
- Contract clause extraction
- Risk analysis (financial, legal, operational)
- Compliance checking (GDPR, SOX, CCPA, etc.)
- Renewal date tracking
- Template comparison

**Use Cases:**
- "Analiza los riesgos de este contrato"
- "Verifica el cumplimiento GDPR"
- "¿Cuándo se renueva este acuerdo?"

### 5. Digital Signature Agent (`digital_signature_agent.json`)
Manages digital signature workflows and document signing processes.

**Key Features:**
- Signature request creation
- Multi-party signature orchestration
- Status tracking and notifications
- Audit trail management
- Workflow automation

**Use Cases:**
- "Crea una solicitud de firma para este documento"
- "¿Cuál es el estado de la firma?"
- "Envía recordatorios a los firmantes"

## How to Use

### Importing to Langflow

1. Open Langflow in your browser
2. Click on "Import Flow" or drag and drop the JSON file
3. The flow will be loaded with all nodes and connections
4. Customize the flow as needed for your use case

### Flow Structure

Each flow contains:
- **Input nodes**: Accept user queries and documents
- **Processing nodes**: LLMs, custom components, and tools
- **Output nodes**: Format and deliver responses

### Customization

You can customize each flow by:
- Adjusting LLM parameters (temperature, model, prompts)
- Adding or removing processing steps
- Modifying node connections
- Updating templates and output formats

## Integration with Backend

These flows are designed to work with the Nexus Document Backend microservices:
- **Main API**: Port 8000
- **LangChain Service**: Port 8001
- **Langroid Service**: Port 8002
- **Storage Service**: Port 8003
- **Ollama Service**: Port 8004

## Environment Variables

Ensure these are set for proper operation:
```
OPENAI_API_KEY=your_openai_key
QDRANT_HOST=localhost
QDRANT_PORT=6333
BACKEND_API_URL=http://localhost:8000
```

## Node Types Reference

### Input/Output Nodes
- `input`: Text or document input
- `output`: Final response output
- `document_loader`: Load documents for processing

### Processing Nodes
- `llm`: Language model for text generation
- `embeddings`: Convert text to vectors
- `vector_search`: Search in vector database
- `custom_component`: Custom processing logic

### Control Flow
- `conditional_router`: Route based on conditions
- `aggregator`: Combine multiple inputs
- `template`: Format output using templates

## Best Practices

1. **Test flows** with sample data before production use
2. **Monitor performance** and adjust parameters as needed
3. **Keep prompts updated** based on user feedback
4. **Version control** your flow configurations
5. **Document changes** to flows for team collaboration

## Support

For issues or questions:
- Check the main project documentation
- Review the agent service implementations in `/backend/microservices/`
- Contact the development team