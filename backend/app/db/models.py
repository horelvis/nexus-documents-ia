import uuid
from datetime import datetime
from typing import List, Optional

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, Text, Table, Float
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship

from sqlalchemy.sql import func
from app.db.base_class import Base

Base = declarative_base()

# Tabla de asociación para relaciones many-to-many
document_tags = Table(
    "document_tags",
    Base.metadata,
    Column("document_id", UUID(as_uuid=True), ForeignKey("documents.id")),
    Column("tag_id", Integer, ForeignKey("tags.id"))
)


class User(Base):
    __tablename__ = "users"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    full_name = Column(String, nullable=True)
    is_active = Column(Boolean(), default=True)
    is_superuser = Column(Boolean(), default=False)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relaciones
    tenant = relationship("Tenant", back_populates="users")


class Tenant(Base):
    __tablename__ = "tenants"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String, unique=True, nullable=False)
    description = Column(String, nullable=True)
    bucket_name = Column(String, nullable=False)
    is_active = Column(Boolean(), default=True)
    settings = Column(JSONB, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relaciones
    users = relationship("User", back_populates="tenant")
    documents = relationship("Document", back_populates="tenant")


class Document(Base):
    __tablename__ = "documents"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    title = Column(String, nullable=False)
    description = Column(Text, nullable=True)
    filename = Column(String, nullable=False)
    file_path = Column(String, nullable=False)
    file_type = Column(String, nullable=False)
    file_size = Column(Integer, nullable=False)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False)
    created_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    indexed = Column(Integer, default=0)  # 0: no indexado, 1: indexado, 2: error
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    
    # Relaciones
    tenant = relationship("Tenant", back_populates="documents")
    creator = relationship("User")
    tags = relationship("Tag", secondary=document_tags, back_populates="documents")
    chunks = relationship("DocumentChunk", back_populates="document", cascade="all, delete-orphan")

    # Nuevas relaciones
    metrics = relationship("DocumentMetrics", back_populates="document", uselist=False, cascade="all, delete-orphan")
    views = relationship("User", secondary=document_views, backref="viewed_documents")
    
    # Método de ayuda para incrementar métricas
    def increment_metric(self, metric_name, session, amount=1):
        if not self.metrics:
            self.metrics = DocumentMetrics(document_id=self.id, tenant_id=self.tenant_id)
            session.add(self.metrics)
        
        current_value = getattr(self.metrics, metric_name, 0)
        setattr(self.metrics, metric_name, current_value + amount)
        
        if metric_name == "view_count":
            self.metrics.last_viewed_at = func.now()
        
        # Actualizar relevance_score basado en todas las métricas
        self._update_relevance_score()
        
    def _update_relevance_score(self):
        # Fórmula simple para calcular relevancia: se puede ajustar según necesidades
        view_weight = 1.0
        download_weight = 3.0
        share_weight = 2.0
        query_weight = 1.5
        recency_weight = 2.0  # Para favorecer documentos vistos recientemente
        
        base_score = (
            self.metrics.view_count * view_weight +
            self.metrics.download_count * download_weight +
            self.metrics.share_count * share_weight +
            self.metrics.query_count * query_weight
        )
        
        # Factor de recencia: favorece documentos vistos recientemente
        recency_factor = 1.0
        if self.metrics.last_viewed_at:
            days_since_view = (datetime.now() - self.metrics.last_viewed_at).days
            if days_since_view < 30:  # Documentos vistos en el último mes
                recency_factor = 1 + ((30 - days_since_view) / 30) * recency_weight
        
        self.metrics.relevance_score = base_score * recency_factor


class DocumentChunk(Base):
    __tablename__ = "document_chunks"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    document_id = Column(UUID(as_uuid=True), ForeignKey("documents.id"), nullable=False)
    chunk_index = Column(Integer, nullable=False)
    content = Column(Text, nullable=False)
    embedding_id = Column(String, nullable=True)  # ID en la base de datos vectorial
    
    # Relaciones
    document = relationship("Document", back_populates="chunks")


class Tag(Base):
    __tablename__ = "tags"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String, nullable=False, unique=True)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relaciones
    tenant = relationship("Tenant")
    documents = relationship("Document", secondary=document_tags, back_populates="tags")

# Tabla de asociación para las lecturas de documentos
document_views = Table(
    "document_views",
    Base.metadata,
    Column("id", String, primary_key=True, default=lambda: str(uuid.uuid4())),
    Column("user_id", String, ForeignKey("users.id"), nullable=False),
    Column("document_id", String, ForeignKey("documents.id"), nullable=False),
    Column("viewed_at", DateTime, default=func.now(), nullable=False),
    Column("view_duration_seconds", Integer, nullable=True),
    Column("is_complete_view", Boolean, default=False),
    Column("tenant_id", String, ForeignKey("tenants.id"), nullable=False),
)


# Tabla para métricas de documentos
class DocumentMetrics(Base):
    __tablename__ = "document_metrics"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    document_id = Column(UUID(as_uuid=True), ForeignKey("documents.id"), nullable=False)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False)
    
    view_count = Column(Integer, default=0)
    download_count = Column(Integer, default=0)
    share_count = Column(Integer, default=0)
    query_count = Column(Integer, default=0)  # Número de consultas sobre este documento
    
    relevance_score = Column(Float, default=0.0)  # Puntuación calculada de relevancia
    last_viewed_at = Column(DateTime, nullable=True)
    
    created_at = Column(DateTime, default=func.now(), nullable=False)
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now(), nullable=False)
    
    # Relaciones
    document = relationship("Document", back_populates="metrics")
    tenant = relationship("Tenant")