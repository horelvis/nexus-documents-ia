# DEPRECATED - Custom CAG Implementations

## ⚠️ NO USAR - Usar CrewAI en su lugar

Following the principle "No reinventar la rueda", all custom CAG implementations have been deprecated in favor of CrewAI framework.

### Deprecated Files:
1. **app/core/cag_engine.py** - Custom CAG engine (DEPRECATED - Use CrewAI)
2. **app/services/cag_langgraph_service.py** - LangGraph implementation (DEPRECATED - Use CrewAI) 
3. **app/core/simple_langgraph_cag.py** - Simple LangGraph (DEPRECATED - Use CrewAI)
4. **app/services/llamaindex_cag_service.py** - LlamaIndex implementation (DEPRECATED - Use CrewAI)

### Active Implementation:
✅ **app/services/crewai_cag_service.py** - CrewAI implementation (USE THIS)

### Why CrewAI?
- **Complete framework** - Agents, tools, memory, RAG, all included
- **Production ready** - Battle-tested in real applications
- **No reinventing** - Everything you need is already built
- **Easy to use** - Simple API, great documentation
- **Active development** - Regular updates and improvements

### Migration Guide:
```python
# OLD - Custom implementation
from app.core.cag_engine import CAGEngine
engine = CAGEngine()
result = await engine.process(query)

# NEW - CrewAI implementation  
from app.services.crewai_cag_service import crewai_cag_service
result = await crewai_cag_service.process_query(
    query=query,
    tenant_id=tenant_id,
    user_id=user_id
)
```

### Benefits of CrewAI:
1. **6 Specialized Agents** working together
2. **Hierarchical Process** with manager coordination
3. **Built-in Tools** for document operations
4. **Memory & Caching** for better performance
5. **Multi-tenant Support** out of the box

## Remember: "Nunca más reinventar la rueda" 🎯