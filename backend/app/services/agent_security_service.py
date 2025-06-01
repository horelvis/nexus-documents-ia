"""
Agent Security and Audit Service
"""
import logging
import hashlib
import json
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
from uuid import UUID
from sqlalchemy.orm import Session
from sqlalchemy import and_, func, desc

from app.db.models import (
    Agent, AgentExecution, AgentConversation, AgentMessage,
    User, Tenant
)
from app.core.config import settings

logger = logging.getLogger(__name__)


class AgentSecurityService:
    """Servicio de seguridad y auditoría para agentes"""
    
    def __init__(self, db: Session):
        self.db = db
    
    # =====================================
    # CONTROL DE ACCESO
    # =====================================
    
    def check_agent_access(
        self, 
        agent_id: UUID, 
        user_id: UUID, 
        tenant_id: UUID,
        operation: str = "read"
    ) -> Dict[str, Any]:
        """Verificar acceso de usuario a un agente"""
        
        try:
            agent = self.db.query(Agent).filter(
                and_(
                    Agent.id == agent_id,
                    Agent.tenant_id == tenant_id
                )
            ).first()
            
            if not agent:
                return {
                    "allowed": False,
                    "reason": "Agent not found",
                    "code": "AGENT_NOT_FOUND"
                }
            
            user = self.db.query(User).filter(User.id == user_id).first()
            if not user:
                return {
                    "allowed": False,
                    "reason": "User not found",
                    "code": "USER_NOT_FOUND"
                }
            
            # Verificar si el usuario pertenece al tenant
            if user.tenant_id != tenant_id:
                return {
                    "allowed": False,
                    "reason": "User does not belong to tenant",
                    "code": "TENANT_MISMATCH"
                }
            
            # Verificar estado del agente
            if not agent.is_active:
                return {
                    "allowed": False,
                    "reason": "Agent is inactive",
                    "code": "AGENT_INACTIVE"
                }
            
            # Verificar permisos específicos
            if operation in ["update", "delete", "configure"]:
                # Solo el creador o admin puede modificar
                if agent.created_by != user_id and not user.is_superuser:
                    return {
                        "allowed": False,
                        "reason": "Insufficient permissions for write operation",
                        "code": "INSUFFICIENT_PERMISSIONS"
                    }
            
            elif operation in ["read", "execute", "chat"]:
                # Agentes públicos o creados por el usuario
                if not agent.is_public and agent.created_by != user_id and not user.is_superuser:
                    return {
                        "allowed": False,
                        "reason": "Agent is private",
                        "code": "AGENT_PRIVATE"
                    }
            
            return {
                "allowed": True,
                "agent": {
                    "id": str(agent.id),
                    "name": agent.name,
                    "type": agent.type,
                    "is_public": agent.is_public,
                    "created_by": str(agent.created_by)
                },
                "user": {
                    "id": str(user.id),
                    "is_superuser": user.is_superuser
                }
            }
            
        except Exception as e:
            logger.error(f"Error checking agent access: {str(e)}")
            return {
                "allowed": False,
                "reason": "Internal error",
                "code": "INTERNAL_ERROR",
                "error": str(e)
            }
    
    def check_rate_limits(
        self, 
        user_id: UUID, 
        tenant_id: UUID,
        operation: str = "execution"
    ) -> Dict[str, Any]:
        """Verificar límites de uso"""
        
        try:
            now = datetime.now()
            hour_ago = now - timedelta(hours=1)
            day_ago = now - timedelta(days=1)
            
            # Límites por defecto (deberían venir de configuración del tenant)
            limits = {
                "executions_per_hour": 100,
                "executions_per_day": 1000,
                "conversations_per_hour": 50,
                "conversations_per_day": 200,
                "messages_per_hour": 500,
                "messages_per_day": 2000
            }
            
            if operation == "execution":
                # Verificar ejecuciones por hora
                hourly_executions = self.db.query(func.count(AgentExecution.id)).filter(
                    and_(
                        AgentExecution.user_id == user_id,
                        AgentExecution.tenant_id == tenant_id,
                        AgentExecution.started_at >= hour_ago
                    )
                ).scalar() or 0
                
                if hourly_executions >= limits["executions_per_hour"]:
                    return {
                        "allowed": False,
                        "reason": "Hourly execution limit exceeded",
                        "limit": limits["executions_per_hour"],
                        "current": hourly_executions,
                        "reset_time": (now + timedelta(hours=1)).isoformat()
                    }
                
                # Verificar ejecuciones por día
                daily_executions = self.db.query(func.count(AgentExecution.id)).filter(
                    and_(
                        AgentExecution.user_id == user_id,
                        AgentExecution.tenant_id == tenant_id,
                        AgentExecution.started_at >= day_ago
                    )
                ).scalar() or 0
                
                if daily_executions >= limits["executions_per_day"]:
                    return {
                        "allowed": False,
                        "reason": "Daily execution limit exceeded",
                        "limit": limits["executions_per_day"],
                        "current": daily_executions,
                        "reset_time": (now + timedelta(days=1)).isoformat()
                    }
            
            elif operation == "conversation":
                # Verificar conversaciones por hora
                hourly_conversations = self.db.query(func.count(AgentConversation.id)).filter(
                    and_(
                        AgentConversation.user_id == user_id,
                        AgentConversation.tenant_id == tenant_id,
                        AgentConversation.created_at >= hour_ago
                    )
                ).scalar() or 0
                
                if hourly_conversations >= limits["conversations_per_hour"]:
                    return {
                        "allowed": False,
                        "reason": "Hourly conversation limit exceeded",
                        "limit": limits["conversations_per_hour"],
                        "current": hourly_conversations
                    }
            
            elif operation == "message":
                # Verificar mensajes por hora
                hourly_messages = self.db.query(func.count(AgentMessage.id)).join(
                    AgentConversation
                ).filter(
                    and_(
                        AgentConversation.user_id == user_id,
                        AgentConversation.tenant_id == tenant_id,
                        AgentMessage.created_at >= hour_ago
                    )
                ).scalar() or 0
                
                if hourly_messages >= limits["messages_per_hour"]:
                    return {
                        "allowed": False,
                        "reason": "Hourly message limit exceeded",
                        "limit": limits["messages_per_hour"],
                        "current": hourly_messages
                    }
            
            return {
                "allowed": True,
                "limits": limits,
                "current_usage": {
                    "executions_hour": hourly_executions if operation == "execution" else None,
                    "executions_day": daily_executions if operation == "execution" else None
                }
            }
            
        except Exception as e:
            logger.error(f"Error checking rate limits: {str(e)}")
            return {
                "allowed": True,  # En caso de error, permitir la operación
                "reason": "Rate limit check failed",
                "error": str(e)
            }
    
    # =====================================
    # AUDITORÍA Y LOGS
    # =====================================
    
    def log_agent_activity(
        self,
        agent_id: UUID,
        user_id: UUID,
        tenant_id: UUID,
        activity_type: str,
        details: Dict[str, Any],
        ip_address: str = None,
        user_agent: str = None
    ):
        """Registrar actividad de agente para auditoría"""
        
        try:
            # En una implementación completa, esto iría a una tabla de logs específica
            logger.info(
                f"AGENT_ACTIVITY: {activity_type}",
                extra={
                    "agent_id": str(agent_id),
                    "user_id": str(user_id),
                    "tenant_id": str(tenant_id),
                    "activity_type": activity_type,
                    "details": details,
                    "ip_address": ip_address,
                    "user_agent": user_agent,
                    "timestamp": datetime.now().isoformat()
                }
            )
            
        except Exception as e:
            logger.error(f"Error logging agent activity: {str(e)}")
    
    def get_security_metrics(
        self, 
        tenant_id: UUID,
        days: int = 30
    ) -> Dict[str, Any]:
        """Obtener métricas de seguridad"""
        
        try:
            start_date = datetime.now() - timedelta(days=days)
            
            # Métricas de uso
            total_executions = self.db.query(func.count(AgentExecution.id)).filter(
                and_(
                    AgentExecution.tenant_id == tenant_id,
                    AgentExecution.started_at >= start_date
                )
            ).scalar() or 0
            
            failed_executions = self.db.query(func.count(AgentExecution.id)).filter(
                and_(
                    AgentExecution.tenant_id == tenant_id,
                    AgentExecution.started_at >= start_date,
                    AgentExecution.status == 'failed'
                )
            ).scalar() or 0
            
            # Usuarios únicos
            unique_users = self.db.query(func.count(func.distinct(AgentExecution.user_id))).filter(
                and_(
                    AgentExecution.tenant_id == tenant_id,
                    AgentExecution.started_at >= start_date
                )
            ).scalar() or 0
            
            # Agentes más utilizados
            top_agents = self.db.query(
                AgentExecution.agent_id,
                func.count(AgentExecution.id).label('usage_count')
            ).filter(
                and_(
                    AgentExecution.tenant_id == tenant_id,
                    AgentExecution.started_at >= start_date
                )
            ).group_by(AgentExecution.agent_id).order_by(desc('usage_count')).limit(5).all()
            
            # Tasa de error
            error_rate = (failed_executions / total_executions * 100) if total_executions > 0 else 0
            
            return {
                "period_days": days,
                "total_executions": total_executions,
                "failed_executions": failed_executions,
                "error_rate": round(error_rate, 2),
                "unique_users": unique_users,
                "top_agents": [
                    {
                        "agent_id": str(agent_id),
                        "usage_count": usage_count
                    }
                    for agent_id, usage_count in top_agents
                ],
                "generated_at": datetime.now().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Error getting security metrics: {str(e)}")
            return {
                "error": "Failed to generate security metrics",
                "details": str(e)
            }
    
    # =====================================
    # VALIDACIÓN DE DATOS
    # =====================================
    
    def validate_agent_configuration(
        self, 
        agent_type: str, 
        configuration: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Validar configuración de agente"""
        
        try:
            validation_rules = {
                "digital_signature": {
                    "required_fields": ["default_provider"],
                    "optional_fields": ["notification_settings", "security_level"],
                    "max_config_size": 10000  # bytes
                },
                "document_analyzer": {
                    "required_fields": ["analysis_types"],
                    "optional_fields": ["language_settings", "confidence_threshold"],
                    "max_config_size": 5000
                },
                "generic": {
                    "required_fields": [],
                    "optional_fields": [],
                    "max_config_size": 2000
                }
            }
            
            rules = validation_rules.get(agent_type, validation_rules["generic"])
            
            # Verificar tamaño
            config_size = len(json.dumps(configuration))
            if config_size > rules["max_config_size"]:
                return {
                    "valid": False,
                    "reason": f"Configuration too large: {config_size} > {rules['max_config_size']} bytes"
                }
            
            # Verificar campos requeridos
            missing_fields = []
            for field in rules["required_fields"]:
                if field not in configuration:
                    missing_fields.append(field)
            
            if missing_fields:
                return {
                    "valid": False,
                    "reason": f"Missing required fields: {missing_fields}"
                }
            
            # Verificar campos no permitidos
            all_allowed = set(rules["required_fields"] + rules["optional_fields"])
            invalid_fields = set(configuration.keys()) - all_allowed
            
            if invalid_fields:
                return {
                    "valid": False,
                    "reason": f"Invalid fields: {list(invalid_fields)}"
                }
            
            return {
                "valid": True,
                "agent_type": agent_type,
                "config_size": config_size
            }
            
        except Exception as e:
            logger.error(f"Error validating agent configuration: {str(e)}")
            return {
                "valid": False,
                "reason": "Validation error",
                "error": str(e)
            }
    
    def sanitize_input_data(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Sanitizar datos de entrada"""
        
        try:
            sanitized = {}
            
            for key, value in data.items():
                # Sanitizar claves
                clean_key = str(key).strip()[:100]  # Limitar longitud
                
                if isinstance(value, str):
                    # Sanitizar strings
                    clean_value = value.strip()[:10000]  # Limitar longitud
                    # Remover caracteres potencialmente peligrosos
                    clean_value = clean_value.replace('<script>', '').replace('</script>', '')
                    clean_value = clean_value.replace('javascript:', '')
                    
                elif isinstance(value, dict):
                    # Recursivo para diccionarios
                    clean_value = self.sanitize_input_data(value)
                    
                elif isinstance(value, list):
                    # Sanitizar listas
                    clean_value = []
                    for item in value[:100]:  # Limitar elementos
                        if isinstance(item, str):
                            clean_item = item.strip()[:1000]
                            clean_value.append(clean_item)
                        elif isinstance(item, dict):
                            clean_value.append(self.sanitize_input_data(item))
                        else:
                            clean_value.append(item)
                            
                else:
                    clean_value = value
                
                sanitized[clean_key] = clean_value
            
            return sanitized
            
        except Exception as e:
            logger.error(f"Error sanitizing input data: {str(e)}")
            return data  # Devolver original en caso de error
    
    # =====================================
    # DETECCIÓN DE ANOMALÍAS
    # =====================================
    
    def detect_suspicious_activity(
        self, 
        user_id: UUID, 
        tenant_id: UUID,
        activity_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Detectar actividad sospechosa"""
        
        try:
            suspicion_score = 0
            flags = []
            
            # Verificar frecuencia de uso inusual
            recent_executions = self.db.query(func.count(AgentExecution.id)).filter(
                and_(
                    AgentExecution.user_id == user_id,
                    AgentExecution.started_at >= datetime.now() - timedelta(hours=1)
                )
            ).scalar() or 0
            
            if recent_executions > 50:  # Umbral configurable
                suspicion_score += 30
                flags.append("High frequency usage")
            
            # Verificar patrones de error
            recent_failures = self.db.query(func.count(AgentExecution.id)).filter(
                and_(
                    AgentExecution.user_id == user_id,
                    AgentExecution.started_at >= datetime.now() - timedelta(hours=1),
                    AgentExecution.status == 'failed'
                )
            ).scalar() or 0
            
            if recent_failures > 10:
                suspicion_score += 20
                flags.append("High failure rate")
            
            # Verificar uso de múltiples agentes
            recent_agent_count = self.db.query(
                func.count(func.distinct(AgentExecution.agent_id))
            ).filter(
                and_(
                    AgentExecution.user_id == user_id,
                    AgentExecution.started_at >= datetime.now() - timedelta(hours=1)
                )
            ).scalar() or 0
            
            if recent_agent_count > 20:
                suspicion_score += 15
                flags.append("Multiple agent usage")
            
            # Verificar datos de entrada sospechosos
            input_data = activity_data.get("input_data", {})
            input_size = len(json.dumps(input_data))
            
            if input_size > 50000:  # 50KB
                suspicion_score += 25
                flags.append("Large input data")
            
            # Determinar nivel de riesgo
            if suspicion_score >= 70:
                risk_level = "high"
            elif suspicion_score >= 40:
                risk_level = "medium"
            elif suspicion_score >= 20:
                risk_level = "low"
            else:
                risk_level = "normal"
            
            result = {
                "suspicious": suspicion_score > 20,
                "risk_level": risk_level,
                "suspicion_score": suspicion_score,
                "flags": flags,
                "recommended_action": self._get_recommended_action(risk_level),
                "timestamp": datetime.now().isoformat()
            }
            
            # Log si es sospechoso
            if result["suspicious"]:
                self.log_agent_activity(
                    agent_id=activity_data.get("agent_id"),
                    user_id=user_id,
                    tenant_id=tenant_id,
                    activity_type="SUSPICIOUS_ACTIVITY_DETECTED",
                    details=result
                )
            
            return result
            
        except Exception as e:
            logger.error(f"Error detecting suspicious activity: {str(e)}")
            return {
                "suspicious": False,
                "error": "Detection failed",
                "details": str(e)
            }
    
    def _get_recommended_action(self, risk_level: str) -> str:
        """Obtener acción recomendada según nivel de riesgo"""
        
        actions = {
            "high": "Block user and require administrator review",
            "medium": "Require additional authentication and monitoring",
            "low": "Increase monitoring frequency",
            "normal": "Continue normal monitoring"
        }
        
        return actions.get(risk_level, "Monitor activity")
    
    # =====================================
    # UTILIDADES DE HASH Y VERIFICACIÓN
    # =====================================
    
    def generate_execution_hash(self, execution_data: Dict[str, Any]) -> str:
        """Generar hash de verificación para ejecución"""
        
        try:
            # Crear string determinista de los datos
            hash_data = {
                "agent_id": execution_data.get("agent_id"),
                "user_id": execution_data.get("user_id"),
                "task_type": execution_data.get("task_type"),
                "timestamp": execution_data.get("timestamp"),
                "input_hash": hashlib.md5(
                    json.dumps(execution_data.get("input_data", {}), sort_keys=True).encode()
                ).hexdigest()
            }
            
            hash_string = json.dumps(hash_data, sort_keys=True)
            return hashlib.sha256(hash_string.encode()).hexdigest()
            
        except Exception as e:
            logger.error(f"Error generating execution hash: {str(e)}")
            return "hash_generation_failed"
    
    def verify_execution_integrity(
        self, 
        execution_id: UUID, 
        provided_hash: str
    ) -> bool:
        """Verificar integridad de ejecución"""
        
        try:
            execution = self.db.query(AgentExecution).filter(
                AgentExecution.id == execution_id
            ).first()
            
            if not execution:
                return False
            
            # Generar hash esperado
            execution_data = {
                "agent_id": str(execution.agent_id),
                "user_id": str(execution.user_id),
                "task_type": execution.task_type,
                "timestamp": execution.started_at.isoformat(),
                "input_data": execution.input_data
            }
            
            expected_hash = self.generate_execution_hash(execution_data)
            return expected_hash == provided_hash
            
        except Exception as e:
            logger.error(f"Error verifying execution integrity: {str(e)}")
            return False