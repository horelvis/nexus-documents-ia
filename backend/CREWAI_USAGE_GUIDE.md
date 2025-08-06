# CrewAI Usage Guide - NexusDocs360

## 🚀 Principio Fundamental
**"No reinventar la rueda en las implementaciones, siempre buscar alternativas opensource y evitar los desarrollo custom"**

## Overview
NexusDocs360 uses CrewAI as the primary agent framework for all AI-powered features. CrewAI provides a complete solution for agent orchestration, eliminating the need for custom implementations.

## Architecture

### 6 Specialized Agents
```python
1. Document Search Specialist - Finds relevant documents
2. Senior Document Analyst - Analyzes and extracts insights  
3. Compliance and Legal Expert - Ensures regulatory compliance
4. Communication Specialist - Provides clear responses
5. Digital Signature Specialist - Manages signature workflows
6. Financial Analyst - Analyzes financial documents
```

### Process Flow
```
User Query → CrewAI Manager → Delegate to Agents → Collect Results → Response
```

## Basic Usage

### 1. Process a Query
```python
from app.services.crewai_cag_service import crewai_cag_service

# Initialize (only once)
await crewai_cag_service.initialize()

# Process query
result = await crewai_cag_service.process_query(
    query="Find all contracts requiring signature",
    tenant_id="tenant-123",
    user_id="user-456"
)

# Check result
if result["success"]:
    print(f"Answer: {result['answer']}")
    print(f"Agents used: {result['agents_used']}")
```

### 2. Analyze a Document
```python
result = await crewai_cag_service.analyze_document(
    document_content="Contract text here...",
    document_id="doc-789",
    tenant_id="tenant-123",
    user_id="user-456",
    analysis_type="contract"  # or "financial", "compliance", "comprehensive"
)

if result["success"]:
    print(f"Analysis: {result['analysis']}")
    print(f"Document type: {result['document_type']}")
```

### 3. Chat Conversation
```python
# CrewAI maintains memory automatically
result = await crewai_cag_service.chat(
    message="What were the main points from the previous document?",
    tenant_id="tenant-123",
    user_id="user-456",
    chat_history=previous_messages  # Optional
)
```

### 4. Streaming Responses
```python
async for event in crewai_cag_service.process_query_stream(
    query="Analyze all financial documents",
    tenant_id="tenant-123",
    user_id="user-456"
):
    if event["type"] == "progress":
        print(f"Progress: {event['content']}")
    elif event["type"] == "result":
        print(f"Final: {event['content']}")
```

## Configuration

### Environment Variables
```bash
# Set in docker-compose.yml or .env
OLLAMA_HOST=http://genai-ollama:11434
OPENAI_API_KEY=not-needed  # Required by CrewAI even for Ollama
OPENAI_API_BASE=http://genai-ollama:11434/v1
```

### Models Configuration
```python
# In crewai_cag_service.py
manager_llm="ollama/gemma3:12b-it-qat"  # Manager model
function_calling_llm="ollama/llama3.2"   # Tool calling model
```

## Multi-Tenant Support

Each tenant gets isolated:
- **Separate workspace**: `/workspace/{tenant_id}/`
- **Isolated vector store**: `tenant_{tenant_id}_documents`
- **Independent crew instance**: One crew per tenant
- **Separate memory/cache**: No data sharing between tenants

## Tools Available

CrewAI provides built-in tools:
- `DirectoryReadTool` - Read directories
- `FileReadTool` - Read files
- `TXTSearchTool` - Search text files
- `PDFSearchTool` - Search PDFs
- `DOCXSearchTool` - Search Word docs
- `CSVSearchTool` - Search CSV files
- `JSONSearchTool` - Search JSON files
- `XMLSearchTool` - Search XML files

Custom tools:
- `QdrantSearchTool` - Vector similarity search
- `StatisticsTool` - Get tenant statistics

## Best Practices

### 1. Use Framework Features
❌ **DON'T**: Write custom agent orchestration
✅ **DO**: Use CrewAI's hierarchical process

❌ **DON'T**: Implement custom memory management
✅ **DO**: Enable CrewAI's built-in memory

❌ **DON'T**: Build custom tool systems
✅ **DO**: Use CrewAI's tool framework

### 2. Agent Design
- Keep agents focused on single responsibilities
- Use delegation between agents
- Let the manager coordinate complex tasks
- Configure appropriate models for each agent

### 3. Error Handling
```python
result = await crewai_cag_service.process_query(...)
if result["success"]:
    # Handle success
    answer = result["answer"]
else:
    # Handle error
    error = result["error"]
    # Fallback to simpler processing if needed
```

## Integration with Virtual Assistant

The Virtual Assistant automatically uses CrewAI:
```python
# In virtual_assistant_agent.py
cag_response = await self.cag_client.process_with_agent(
    message=message,
    context=cag_context,
    agent_type="virtual_assistant"  # CrewAI orchestrates
)
```

## Monitoring & Debugging

### Health Check
```python
health = await crewai_cag_service.health_check()
print(f"Status: {health['status']}")
print(f"Checks: {health['checks']}")
```

### Verbose Mode
CrewAI crews are configured with `verbose=True` for detailed logging:
- Agent decisions
- Tool usage
- Task delegation
- Results

## Common Patterns

### 1. Document Search Pattern
```python
# Query triggers multiple agents:
# 1. Search Agent finds documents
# 2. Analyst Agent extracts information
# 3. Response Agent formats answer
```

### 2. Compliance Check Pattern
```python
# Specialized flow:
# 1. Search Agent finds relevant docs
# 2. Compliance Agent checks regulations
# 3. Legal Expert validates
# 4. Response Agent summarizes findings
```

### 3. Financial Analysis Pattern
```python
# Financial flow:
# 1. Search Agent finds financial docs
# 2. Financial Agent analyzes
# 3. Analyst Agent provides insights
# 4. Response Agent creates report
```

## Troubleshooting

### Connection Issues
- Verify Ollama is running: `docker ps | grep ollama`
- Check connection: `curl http://genai-ollama:11434/api/tags`
- Restart CAG service: `docker restart docker-cag-service-1`

### Memory Issues
- Disable memory temporarily: `memory=False` in Crew config
- Clear cache if needed
- Check disk space for persistent storage

### Performance
- Use lighter models for simple tasks
- Limit max_iterations for agents
- Enable caching for repeated queries

## Future Enhancements

Following the "no reinventar" principle, future enhancements will use:
- **LangSmith** for observability (when needed)
- **LlamaIndex** for advanced RAG (if CrewAI RAG insufficient)
- **Agents frameworks** updates as CrewAI evolves

## Remember
🎯 **"Nunca más reinventar la rueda"**
- Always check if CrewAI has the feature
- Look for existing tools before creating new ones
- Use framework patterns instead of custom code
- Contribute back to open source when possible

## Resources
- [CrewAI Documentation](https://docs.crewai.com)
- [CrewAI GitHub](https://github.com/joaomdmoura/crewai)
- [CrewAI Tools](https://docs.crewai.com/core-concepts/tools/)
- [LiteLLM Models](https://docs.litellm.ai/docs/providers/ollama)