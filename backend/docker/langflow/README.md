# Langflow Integration for Nexus

This directory contains Langflow flows and custom components for the Nexus document management system.

## Directory Structure

```
langflow/
├── flows/              # Exported Langflow flows (JSON)
├── components/         # Custom Langflow components
└── README.md          # This file
```

## Getting Started

1. **Start Langflow**:
   ```bash
   cd backend/docker
   ./start-dev-with-langflow.sh
   ```

2. **Access Langflow UI**: http://localhost:7860

3. **Create or Import Flows**:
   - Import example flows from `flows/` directory
   - Create new flows using the visual builder

## Available Components

### Built-in Components
- **Ollama LLM**: Connected to local Ollama service
- **Qdrant Vector Store**: For RAG capabilities
- **Prompt Templates**: For structured prompts
- **Memory**: Conversation history management

### Custom Components
- **Nexus Document Loader**: Load documents from Nexus API
- More components in `components/` directory

## Example Flows

### RAG Document Assistant
File: `flows/example-rag-agent.json`

This flow creates a RAG-based document assistant that:
- Retrieves relevant documents from Qdrant
- Uses Ollama LLM for generation
- Maintains conversation history
- Returns source documents

### Importing Flows to Nexus

1. **Export from Langflow**: Export → Download as JSON
2. **Import to Nexus**:
   ```bash
   curl -X POST http://localhost:8000/api/v1/agent-registry/import/langflow \
     -H "Content-Type: application/json" \
     -d @flows/your-flow.json
   ```

## Best Practices

1. **Naming**: Use descriptive names for flows and nodes
2. **Testing**: Test flows in Langflow before importing
3. **Documentation**: Add descriptions to nodes
4. **Version Control**: Commit flow JSON files
5. **Error Handling**: Include error handling nodes

## Troubleshooting

- **Connection Issues**: Ensure all services are running
- **Model Not Found**: Check Ollama has required models
- **Import Fails**: Validate JSON structure

## Resources

- [Langflow Documentation](https://docs.langflow.org/)
- [Nexus Agent Registry API](/api/v1/agent-registry)
- [Custom Component Guide](https://docs.langflow.org/components/custom)