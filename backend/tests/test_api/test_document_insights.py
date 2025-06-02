# tests/test_api/test_document_insights.py

import pytest
from datetime import datetime, timedelta
from app.services.document_insights_service import DocumentInsightsService
from app.db.models import Document, DocumentMetrics, DocumentView


def test_get_trending_documents(db_session, test_tenant, test_user, test_documents):
    """Test para get_trending_documents con datos reales"""
    
    # Crear métricas para los documentos de test
    for i, doc in enumerate(test_documents[:2]):  # Solo usar 2 documentos
        metrics = DocumentMetrics(
            document_id=doc.id,
            tenant_id=test_tenant.id,
            view_count=10 - i * 2,  # 10, 8
            download_count=5 - i,   # 5, 4
            share_count=2 - i,      # 2, 1
            query_count=3 - i,      # 3, 2
            relevance_score=25.5 - i * 7.2,  # 25.5, 18.3
            last_viewed_at=datetime.now() - timedelta(hours=i)
        )
        db_session.add(metrics)
    
    db_session.commit()
    
    # Crear el service y ejecutar
    insights_service = DocumentInsightsService(
        tenant_id=str(test_tenant.id), 
        user_id=str(test_user.id)
    )
    
    result = insights_service.get_trending_documents(limit=2, time_period_days=30)
    
    # Verificaciones
    assert len(result) == 2
    assert result[0]["title"] == "Test Document 1"
    assert result[0]["metrics"]["view_count"] == 10
    assert result[0]["metrics"]["relevance_score"] == 25.5
    assert result[1]["title"] == "Test Document 2"
    assert result[1]["metrics"]["view_count"] == 8


def test_get_recently_viewed_documents(db_session, test_tenant, test_user, test_documents):
    """Test para get_recently_viewed_documents con datos reales"""
    
    # Crear vistas de documentos para el usuario
    for i, doc in enumerate(test_documents[:2]):
        # Crear métricas primero
        metrics = DocumentMetrics(
            document_id=doc.id,
            tenant_id=test_tenant.id,
            view_count=1,
            download_count=0,
            share_count=0,
            query_count=0,
            relevance_score=10.0,
            last_viewed_at=datetime.now() - timedelta(hours=i * 2)
        )
        db_session.add(metrics)
        
        # Crear vista del documento
        view = DocumentView(
            document_id=doc.id,
            user_id=test_user.id,
            tenant_id=test_tenant.id,
            viewed_at=datetime.now() - timedelta(hours=i * 2)
        )
        db_session.add(view)
    
    db_session.commit()
    
    # Crear el service y ejecutar
    insights_service = DocumentInsightsService(
        tenant_id=str(test_tenant.id), 
        user_id=str(test_user.id)
    )
    
    result = insights_service.get_recently_viewed_documents(limit=2, user_specific=True)
    
    # Verificaciones
    assert len(result) == 2
    assert result[0]["title"] == "Test Document 1"  # Más reciente
    assert result[1]["title"] == "Test Document 2"
    assert "last_viewed_at" in result[0]
    assert "last_viewed_at" in result[1]


def test_get_document_recommendations(db_session, test_tenant, test_user, test_documents):
    """Test para get_document_recommendations con datos reales"""
    
    # Crear métricas para todos los documentos
    for i, doc in enumerate(test_documents):
        metrics = DocumentMetrics(
            document_id=doc.id,
            tenant_id=test_tenant.id,
            view_count=10 - i,
            download_count=5 - i,
            share_count=2,
            query_count=3,
            relevance_score=25.0 - i * 5,
            last_viewed_at=datetime.now() - timedelta(days=i + 1)
        )
        db_session.add(metrics)
    
    # Crear vista solo para el primer documento (el usuario ya lo vio)
    view = DocumentView(
        document_id=test_documents[0].id,
        user_id=test_user.id,
        tenant_id=test_tenant.id,
        viewed_at=datetime.now() - timedelta(hours=1)
    )
    db_session.add(view)
    
    db_session.commit()
    
    # Crear el service y ejecutar
    insights_service = DocumentInsightsService(
        tenant_id=str(test_tenant.id), 
        user_id=str(test_user.id)
    )
    
    result = insights_service.get_document_recommendations(limit=2)
    
    # Verificaciones - debería recomendar documentos que no ha visto
    assert len(result) <= 2
    # No debería incluir el primer documento que ya vio
    document_ids = [doc["id"] for doc in result]
    assert str(test_documents[0].id) not in document_ids
    
    if len(result) > 0:
        assert "reason" in result[0]
        assert result[0]["title"] in ["Test Document 2", "Test Document 3"]


def test_get_trending_documents_empty(db_session, test_tenant, test_user):
    """Test para get_trending_documents sin documentos"""
    
    insights_service = DocumentInsightsService(
        tenant_id=str(test_tenant.id), 
        user_id=str(test_user.id)
    )
    
    result = insights_service.get_trending_documents(limit=10, time_period_days=30)
    
    # Debería retornar lista vacía
    assert isinstance(result, list)
    assert len(result) == 0


def test_get_recently_viewed_documents_empty(db_session, test_tenant, test_user):
    """Test para get_recently_viewed_documents sin vistas"""
    
    insights_service = DocumentInsightsService(
        tenant_id=str(test_tenant.id), 
        user_id=str(test_user.id)
    )
    
    result = insights_service.get_recently_viewed_documents(limit=10, user_specific=True)
    
    # Debería retornar lista vacía
    assert isinstance(result, list)
    assert len(result) == 0


def test_get_document_recommendations_empty(db_session, test_tenant, test_user):
    """Test para get_document_recommendations sin documentos"""
    
    insights_service = DocumentInsightsService(
        tenant_id=str(test_tenant.id), 
        user_id=str(test_user.id)
    )
    
    result = insights_service.get_document_recommendations(limit=5)
    
    # Debería retornar lista vacía
    assert isinstance(result, list)
    assert len(result) == 0