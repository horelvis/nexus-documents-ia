import pytest
import json
from unittest.mock import patch, MagicMock

from app.services.llm_service import LLMService


def test_summarize_text(monkeypatch):
    """Prueba para resumir texto"""
    # Mock para _call_ollama_api
    def mock_call_ollama_api(*args, **kwargs):
        return "This is a summary of the text."
    
    # Aplicar mock
    llm_service = LLMService()
    monkeypatch.setattr(llm_service, "_call_ollama_api", mock_call_ollama_api)
    
    # Ejecutar prueba
    result = llm_service.summarize_text(
        "This is a long text that should be summarized. " * 20,
        max_length=100
    )
    
    assert result == "This is a summary of the text."
    
    # Prueba con texto corto (no necesita resumen)
    short_text = "This is a short text."
    result = llm_service.summarize_text(short_text, max_length=100)
    
    assert result == short_text

def test_suggest_tags(monkeypatch):
    """Prueba para sugerir etiquetas"""
    # Mock para _call_ollama_api
    def mock_call_ollama_api(*args, **kwargs):
        return "tag1, tag2, tag3, tag4, tag5"
    
    # Aplicar mock
    llm_service = LLMService()
    monkeypatch.setattr(llm_service, "_call_ollama_api", mock_call_ollama_api)
    
    # Ejecutar prueba
    result = llm_service.suggest_tags(
        "This is a text about programming, Python, and machine learning.",
        num_tags=3
    )
    
    assert isinstance(result, list)
    assert len(result) == 3
    assert "tag1" in result
    assert "tag2" in result
    assert "tag3" in result

def test_extract_metadata(monkeypatch):
    """Prueba para extraer metadatos"""
    # Mock para _call_ollama_api
    def mock_call_ollama_api(*args, **kwargs):
        return json.dumps({
            "título": "Test Document",
            "autor": "Test Author",
            "fecha": "2023-01-01",
            "categoría": "Test",
            "entidades": ["Entity1", "Entity2"]
        })
    
    # Aplicar mock
    llm_service = LLMService()
    monkeypatch.setattr(llm_service, "_call_ollama_api", mock_call_ollama_api)
    
    # Ejecutar prueba
    result = llm_service.extract_metadata(
        "This is a document by Test Author dated 2023-01-01."
    )
    
    assert isinstance(result, dict)
    assert result["título"] == "Test Document"
    assert result["autor"] == "Test Author"
    assert result["fecha"] == "2023-01-01"
    assert len(result["entidades"]) == 2

def test_answer_question(monkeypatch):
    """Prueba para responder preguntas"""
    # Mock para _call_ollama_api
    def mock_call_ollama_api(*args, **kwargs):
        return "This is the answer to the question."
    
    # Aplicar mock
    llm_service = LLMService()
    monkeypatch.setattr(llm_service, "_call_ollama_api", mock_call_ollama_api)
    
    # Ejecutar prueba
    result = llm_service.answer_question(
        "What is the main topic?",
        "This document discusses various topics including programming."
    )
    
    assert result == "This is the answer to the question."

def test_classify_document(monkeypatch):
    """Prueba para clasificar documentos"""
    # Mock para _call_ollama_api
    def mock_call_ollama_api(*args, **kwargs):
        return "Category1"
    
    # Aplicar mock
    llm_service = LLMService()
    monkeypatch.setattr(llm_service, "_call_ollama_api", mock_call_ollama_api)
    
    # Ejecutar prueba
    result = llm_service.classify_document(
        "This is a document about programming.",
        categories=["Category1", "Category2", "Category3"]
    )
    
    assert result == "Category1"

def test_call_ollama_api_success(monkeypatch):
    """Prueba para llamar a la API de Ollama con éxito"""
    # Mock para requests.post
    class MockResponse:
        def __init__(self, status_code, json_data):
            self.status_code = status_code
            self._json_data = json_data
        
        def json(self):
            return self._json_data
    
    def mock_post(*args, **kwargs):
        return MockResponse(200, {"response": "Test response"})
    
    # Aplicar mock
    import requests
    monkeypatch.setattr(requests, "post", mock_post)
    
    # Ejecutar prueba
    llm_service = LLMService()
    result = llm_service._call_ollama_api("Test prompt")
    
    assert result == "Test response"

def test_call_ollama_api_error(monkeypatch):
    """Prueba para llamar a la API de Ollama con error"""
    # Mock para requests.post
    class MockResponse:
        def __init__(self, status_code, text):
            self.status_code = status_code
            self.text = text
    
    def mock_post(*args, **kwargs):
        return MockResponse(500, "Internal server error")
    
    # Aplicar mock
    import requests
    monkeypatch.setattr(requests, "post", mock_post)
    
    # Ejecutar prueba
    llm_service = LLMService()
    result = llm_service._call_ollama_api("Test prompt")
    
    assert "Error" in result
    assert "500" in result