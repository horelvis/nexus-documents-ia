#!/bin/bash

echo "Installing LangGraph service dependencies..."

# Upgrade pip first
pip install --upgrade pip setuptools wheel

# Install core dependencies first
pip install fastapi==0.109.0 uvicorn[standard]==0.27.0 pydantic==2.5.3

# Install langchain-core to establish base
pip install langchain-core==0.2.23

# Install main packages
pip install langchain==0.2.11
pip install langgraph==0.1.19

# Install additional packages one by one to avoid conflicts
pip install langchain-community==0.2.10
pip install langchain-ollama==0.1.0
pip install qdrant-client==1.10.1
pip install langchain-qdrant==0.1.3

# Install checkpoint packages
pip install langgraph-checkpoint==1.0.2
pip install langgraph-checkpoint-sqlite==1.0.2

# Install remaining dependencies
pip install sqlalchemy==2.0.25
pip install psycopg2-binary==2.9.9
pip install asyncpg==0.29.0
pip install redis==5.0.1
pip install httpx==0.26.0
pip install aiohttp==3.9.5
pip install loguru==0.7.2
pip install python-multipart==0.0.6
pip install tenacity==8.2.3
pip install orjson==3.10.6
pip install pydantic-settings==2.1.0
pip install python-dotenv==1.0.0
pip install hiredis==2.3.2
pip install jsonpatch==1.33
pip install langsmith==0.1.93

echo "Installation complete!"