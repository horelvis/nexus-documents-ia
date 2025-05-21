# tests/services/test_document_insights.py

import pytest
from unittest.mock import patch, MagicMock
from app.services.document_insights_service import DocumentInsightsService
from app.db.models import Document, DocumentMetrics, User, Tenant
from datetime import datetime, timedelta
from sqlalchemy.sql import func, desc  # Añadir importaciones necesarias
# Fixtures
@pytest.fixture
def mock_db_session():
    """Crea un mock de sesión de DB para tests"""
    session = MagicMock()
    
    # Configurar tenant mock
    tenant = MagicMock(spec=Tenant)
    tenant.id = "tenant-123"
    
    # Configurar user mock
    user = MagicMock(spec=User)
    user.id = "user-123"
    user.tenant_id = "tenant-123"
    
    # Configurar consulta para tenant
    tenant_query = MagicMock()
    tenant_query.filter.return_value.first.return_value = tenant
    session.query.return_value = tenant_query
    
    # Configurar consulta para user
    def query_side_effect(model):
        if model == Tenant:
            tenant_query = MagicMock()
            tenant_query.filter.return_value.first.return_value = tenant
            return tenant_query
        elif model == User:
            user_query = MagicMock()
            user_query.filter.return_value.first.return_value = user
            return user_query
        else:
            return MagicMock()
    
    session.query.side_effect = query_side_effect
    
    return session

@pytest.fixture
def insights_service(mock_db_session):
    """Crea un insights service con DB mock para tests"""
    with patch('app.services.document_insights_service.SessionLocal', return_value=mock_db_session):
        service = DocumentInsightsService(tenant_id="tenant-123", user_id="user-123")
        yield service

# Tests
def test_get_trending_documents(insights_service, mock_db_session):
    """Test para get_trending_documents"""
    # Configurar mocks para documentos y métricas
    doc1 = MagicMock(spec=Document)
    doc1.id = "doc-1"
    doc1.title = "Document 1"
    doc1.description = "Description 1"
    doc1.created_at = datetime.now()
    doc1.updated_at = datetime.now()
    doc1.format = "pdf"
    doc1.size = 1024
    
    metrics1 = MagicMock(spec=DocumentMetrics)
    metrics1.view_count = 10
    metrics1.download_count = 5
    metrics1.share_count = 2
    metrics1.query_count = 3
    metrics1.relevance_score = 25.5
    metrics1.last_viewed_at = datetime.now()
    
    doc2 = MagicMock(spec=Document)
    doc2.id = "doc-2"
    doc2.title = "Document 2"
    doc2.description = "Description 2"
    doc2.created_at = datetime.now() - timedelta(days=5)
    doc2.updated_at = datetime.now() - timedelta(days=2)
    doc2.format = "docx"
    doc2.size = 2048
    
    metrics2 = MagicMock(spec=DocumentMetrics)
    metrics2.view_count = 8
    metrics2.download_count = 3
    metrics2.share_count = 1
    metrics2.query_count = 2
    metrics2.relevance_score = 18.3
    metrics2.last_viewed_at = datetime.now() - timedelta(days=1)
    
    # Mock para la consulta join
    join_query = MagicMock()
    filter_query = MagicMock()
    order_query = MagicMock()
    limit_query = MagicMock()
    
    join_query.filter.return_value = filter_query
    filter_query.order_by.return_value = order_query
    order_query.limit.return_value = limit_query
    limit_query.all.return_value = [(doc1, metrics1), (doc2, metrics2)]
    
    query = MagicMock()
    query.join.return_value = join_query
    
    mock_db_session.query.return_value = query
    
    # Ejecutar método a probar
    result = insights_service.get_trending_documents(limit=2, time_period_days=30)
    
    # Verificaciones
    assert len(result) == 2
    assert result[0]["id"] == "doc-1"
    assert result[0]["title"] == "Document 1"
    assert result[0]["metrics"]["view_count"] == 10
    assert result[0]["metrics"]["relevance_score"] == 25.5
    assert result[1]["id"] == "doc-2"
    assert result[1]["metrics"]["view_count"] == 8

def test_get_recently_viewed_documents(insights_service, mock_db_session):
    """Test para get_recently_viewed_documents"""
    # Configurar mocks para documentos y fechas de visualización
    doc1 = MagicMock(spec=Document)
    doc1.id = "doc-1"
    doc1.title = "Document 1"
    doc1.description = "Description 1"
    doc1.created_at = datetime.now() - timedelta(days=10)
    doc1.updated_at = datetime.now() - timedelta(days=5)
    doc1.format = "pdf"
    doc1.size = 1024
    
    last_viewed1 = datetime.now() - timedelta(hours=2)
    
    doc2 = MagicMock(spec=Document)
    doc2.id = "doc-2"
    doc2.title = "Document 2"
    doc2.description = "Description 2"
    doc2.created_at = datetime.now() - timedelta(days=15)
    doc2.updated_at = datetime.now() - timedelta(days=7)
    doc2.format = "docx"
    doc2.size = 2048
    
    last_viewed2 = datetime.now() - timedelta(days=1)
    
    # Mock para la consulta
    join_query = MagicMock()
    filter_query = MagicMock()
    group_query = MagicMock()
    order_query = MagicMock()
    limit_query = MagicMock()
    
    join_query.filter.return_value = filter_query
    filter_query.group_by.return_value = group_query
    group_query.order_by.return_value = order_query
    order_query.limit.return_value = limit_query
    limit_query.all.return_value = [(doc1, last_viewed1), (doc2, last_viewed2)]
    
    query = MagicMock()
    query.join.return_value = join_query
    
    mock_db_session.query.return_value = query
    
    # Ejecutar método a probar
    result = insights_service.get_recently_viewed_documents(limit=2, user_specific=True)
    
    # Verificaciones
    assert len(result) == 2
    assert result[0]["id"] == "doc-1"
    assert result[0]["title"] == "Document 1"
    assert result[0]["last_viewed_at"] == last_viewed1
    assert result[1]["id"] == "doc-2"
    assert result[1]["last_viewed_at"] == last_viewed2

def test_get_document_recommendations(insights_service, mock_db_session):
    """Test para get_document_recommendations"""
    # Configurar mocks para la consulta de documentos vistos por el usuario
    user_viewed_docs_query = MagicMock()
    user_viewed_docs_subquery = MagicMock()
    user_viewed_docs_query.subquery.return_value = user_viewed_docs_subquery
    
    # Documentos recomendados
    doc1 = MagicMock(spec=Document)
    doc1.id = "doc-1"
    doc1.title = "Document 1"
    doc1.description = "Description 1"
    doc1.created_at = datetime.now() - timedelta(days=10)
    doc1.updated_at = datetime.now() - timedelta(days=5)
    doc1.format = "pdf"
    doc1.size = 1024
    
    metrics1 = MagicMock(spec=DocumentMetrics)
    metrics1.relevance_score = 25.5
    
    doc2 = MagicMock(spec=Document)
    doc2.id = "doc-2"
    doc2.title = "Document 2"
    doc2.description = "Description 2"
    doc2.created_at = datetime.now() - timedelta(days=15)
    doc2.updated_at = datetime.now() - timedelta(days=7)
    doc2.format = "docx"
    doc2.size = 2048
    
    metrics2 = MagicMock(spec=DocumentMetrics)
    metrics2.relevance_score = 18.3
    
    # Mock para la consulta de documentos vistos por el usuario
    mock_db_session.query.side_effect = None
    mock_db_session.query.return_value = user_viewed_docs_query
    
    # Mock para la consulta de documentos populares no vistos
    join_query = MagicMock()
    filter_query = MagicMock()
    order_query = MagicMock()
    limit_query = MagicMock()
    
    join_query.filter.return_value = filter_query
    filter_query.order_by.return_value = order_query
    order_query.limit.return_value = limit_query
    limit_query.all.return_value = [(doc1, metrics1), (doc2, metrics2)]
    
    # Restaurar side_effect y configurar secuencia de retornos
    mock_db_session.query.side_effect = [
        user_viewed_docs_query,  # Primera llamada para documentos vistos
        MagicMock(join=lambda *args, **kwargs: join_query)  # Segunda llamada para documentos populares
    ]
    
    # Ejecutar método a probar
    result = insights_service.get_document_recommendations(limit=2)
    
    # Verificaciones
    assert len(result) == 2
    assert result[0]["id"] == "doc-1"
    assert result[0]["title"] == "Document 1"
    assert "reason" in result[0]
    assert result[1]["id"] == "doc-2"