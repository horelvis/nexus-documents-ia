# CrewAI Official Pattern Test

Implementación de CrewAI siguiendo el patrón oficial con decoradores y configuración YAML.

## Estructura del Proyecto

```
crewai_official_test/
├── src/
│   └── crewai_official_test/
│       ├── __init__.py
│       ├── main.py           # Punto de entrada principal
│       ├── crew.py           # Clase principal con decoradores @CrewBase
│       ├── config/
│       │   ├── agents.yaml   # Configuración de agentes
│       │   └── tasks.yaml    # Configuración de tareas
│       └── tools/
│           ├── __init__.py
│           └── custom_tools.py  # Herramientas personalizadas
├── pyproject.toml
└── README.md
```

## Características

### ✅ Patrón Oficial CrewAI
- Uso de decoradores `@CrewBase`, `@agent`, `@task`, `@crew`
- Configuración YAML para agentes y tareas
- Herramientas oficiales (SerperDevTool) con fallback personalizado

### ✅ Herramientas Funcionales
- Búsqueda web (DuckDuckGo API / SerperDev)
- Calculadora matemática
- Información de fecha/hora
- Búsqueda específica de clima

### ✅ Agentes Especializados
- **Researcher**: Investigación con herramientas de búsqueda
- **Reporting Analyst**: Generación de reportes detallados
- **Virtual Assistant**: Asistente completo con múltiples herramientas

## Uso

### Ejecutar Tests
```bash
cd crewai_official_test/src
python -m crewai_official_test.main
```

### Uso Programático
```python
from crewai_official_test import OfficialCrewAITest, run_chat, run_research

# Chat simple
result = await run_chat("¿Qué hora es?")

# Investigación
report = await run_research("inteligencia artificial")

# Uso avanzado
crew_instance = OfficialCrewAITest()
chat_crew = crew_instance.chat_crew()
result = await asyncio.to_thread(chat_crew.kickoff, inputs={"user_message": "Busca información sobre Python"})
```

## Variables de Entorno

- `OPENAI_API_KEY`: Para LLM principal (puede ser fake para test)
- `SERPER_API_KEY`: Para búsqueda web oficial (opcional)

Si no se configuran, el sistema usará valores de prueba y herramientas personalizadas.

## Diferencias con Implementación Actual

### ❌ Implementación Actual (Problemática)
- Decorador `@tool` en funciones anidadas
- Mezcla configuración YAML con creación manual
- Complejidad innecesaria
- Herramientas que fallan

### ✅ Implementación Oficial (Correcta)
- Decoradores oficiales `@CrewBase`, `@agent`, `@task`
- Configuración YAML pura
- Herramientas funcionales
- Patrón simple y claro