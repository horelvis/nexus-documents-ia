"""Service for managing gradual migration from Qdrant/CrewAI to Weaviate/Elysia"""
import logging
import os
from typing import Dict, Any, List, Optional, Union
from datetime import datetime
from enum import Enum

from app.core.config import settings
from app.services.weaviate_client import weaviate_client
from app.services.cag_client import cag_client

logger = logging.getLogger(__name__)


class MigrationMode(str, Enum):
    """Migration modes for gradual transition"""
    QDRANT_ONLY = "qdrant_only"  # Use only Qdrant/CrewAI (legacy)
    PARALLEL = "parallel"        # Use both systems (migration phase)
    WEAVIATE_ONLY = "weaviate_only"  # Use only Weaviate/Elysia (target)


class MigrationService:
    """Service for managing gradual migration between vector databases"""
    
    def __init__(self):
        self.migration_mode = self._get_migration_mode()
        self.enable_weaviate = self._get_weaviate_enabled()
        
    def _get_migration_mode(self) -> MigrationMode:
        """Get current migration mode from environment"""
        mode = os.getenv("MIGRATION_MODE", "parallel")
        try:
            return MigrationMode(mode)
        except ValueError:
            logger.warning(f"⚠️ Invalid migration mode: {mode}, using parallel")
            return MigrationMode.PARALLEL
    
    def _get_weaviate_enabled(self) -> bool:
        """Check if Weaviate is enabled"""
        return os.getenv("ENABLE_WEAVIATE", "true").lower() == "true"
    
    async def health_check(self) -> Dict[str, Any]:
        """Check health of migration service and underlying systems"""
        status = {
            "migration_mode": self.migration_mode.value,
            "weaviate_enabled": self.enable_weaviate,
            "systems": {}
        }
        
        # Check Qdrant/CrewAI system
        try:
            cag_health = await cag_client.health_check()
            status["systems"]["qdrant_crewai"] = {
                "status": "healthy" if cag_health.get("status") == "healthy" else "unhealthy",
                "details": cag_health
            }
        except Exception as e:
            status["systems"]["qdrant_crewai"] = {
                "status": "unhealthy", 
                "error": str(e)
            }
        
        # Check Weaviate/Elysia system
        if self.enable_weaviate:
            try:
                weaviate_health = await weaviate_client.health_check()
                status["systems"]["weaviate_elysia"] = {
                    "status": "healthy" if weaviate_health.get("status") == "healthy" else "unhealthy",
                    "details": weaviate_health
                }
            except Exception as e:
                status["systems"]["weaviate_elysia"] = {
                    "status": "unhealthy",
                    "error": str(e)
                }
        
        return status
    
    async def search_documents(self, query: str, tenant_id: str, **kwargs) -> Dict[str, Any]:
        """Search documents using current migration strategy"""
        
        if self.migration_mode == MigrationMode.QDRANT_ONLY:
            # Use only Qdrant/CrewAI
            return await self._search_qdrant_only(query, tenant_id, **kwargs)
        
        elif self.migration_mode == MigrationMode.WEAVIATE_ONLY:
            # Use only Weaviate/Elysia
            return await self._search_weaviate_only(query, tenant_id, **kwargs)
        
        else:  # PARALLEL mode
            # Use both systems and compare/merge results
            return await self._search_parallel(query, tenant_id, **kwargs)
    
    async def _search_qdrant_only(self, query: str, tenant_id: str, **kwargs) -> Dict[str, Any]:
        """Search using only Qdrant/CrewAI system"""
        try:
            logger.info("🔍 [QDRANT-ONLY] Executing search via CAG service")
            
            # Call CAG service (Qdrant + CrewAI)
            search_request = {
                "query": query,
                "tenant_id": tenant_id,
                "max_results": kwargs.get("limit", 10),
                **kwargs
            }
            
            result = await cag_client.search_documents(search_request)
            
            return {
                "source": "qdrant_crewai",
                "mode": "qdrant_only",
                "results": result,
                "timestamp": datetime.now().isoformat()
            }
            
        except Exception as e:
            logger.error(f"❌ Qdrant-only search failed: {e}")
            raise
    
    async def _search_weaviate_only(self, query: str, tenant_id: str, **kwargs) -> Dict[str, Any]:
        """Search using only Weaviate/Elysia system"""
        try:
            logger.info("🔍 [WEAVIATE-ONLY] Executing search via Elysia")
            
            # Call Weaviate service with Elysia
            elysia_query = {
                "query": query,
                "tenant_id": tenant_id,
                "query_type": kwargs.get("query_type", "search"),
                "collections": kwargs.get("collections", []),
                "max_iterations": kwargs.get("max_iterations", 3),
                "enable_learning": kwargs.get("enable_learning", True)
            }
            
            result = await weaviate_client.elysia_query(elysia_query)
            
            return {
                "source": "weaviate_elysia",
                "mode": "weaviate_only", 
                "results": result,
                "timestamp": datetime.now().isoformat()
            }
            
        except Exception as e:
            logger.error(f"❌ Weaviate-only search failed: {e}")
            raise
    
    async def _search_parallel(self, query: str, tenant_id: str, **kwargs) -> Dict[str, Any]:
        """Search using both systems in parallel and merge results"""
        try:
            logger.info("🔍 [PARALLEL] Executing search on both systems")
            
            # Execute both searches concurrently
            import asyncio
            
            qdrant_task = asyncio.create_task(
                self._search_qdrant_safe(query, tenant_id, **kwargs)
            )
            
            weaviate_task = asyncio.create_task(
                self._search_weaviate_safe(query, tenant_id, **kwargs)
            )
            
            # Wait for both to complete
            qdrant_result, weaviate_result = await asyncio.gather(
                qdrant_task, weaviate_task, return_exceptions=True
            )
            
            # Process results
            response = {
                "source": "parallel",
                "mode": "parallel",
                "timestamp": datetime.now().isoformat(),
                "systems": {}
            }
            
            # Handle Qdrant results
            if isinstance(qdrant_result, Exception):
                logger.error(f"❌ Qdrant search failed: {qdrant_result}")
                response["systems"]["qdrant"] = {
                    "status": "error",
                    "error": str(qdrant_result)
                }
            else:
                response["systems"]["qdrant"] = {
                    "status": "success",
                    "results": qdrant_result
                }
            
            # Handle Weaviate results
            if isinstance(weaviate_result, Exception):
                logger.error(f"❌ Weaviate search failed: {weaviate_result}")
                response["systems"]["weaviate"] = {
                    "status": "error", 
                    "error": str(weaviate_result)
                }
            else:
                response["systems"]["weaviate"] = {
                    "status": "success",
                    "results": weaviate_result
                }
            
            # Merge results intelligently
            primary_result = self._merge_parallel_results(
                response["systems"].get("qdrant", {}).get("results"),
                response["systems"].get("weaviate", {}).get("results")
            )
            
            response["results"] = primary_result
            return response
            
        except Exception as e:
            logger.error(f"❌ Parallel search failed: {e}")
            raise
    
    async def _search_qdrant_safe(self, query: str, tenant_id: str, **kwargs) -> Dict[str, Any]:
        """Safe wrapper for Qdrant search"""
        search_request = {
            "query": query,
            "tenant_id": tenant_id,
            "max_results": kwargs.get("limit", 10),
            **kwargs
        }
        
        return await cag_client.search_documents(search_request)
    
    async def _search_weaviate_safe(self, query: str, tenant_id: str, **kwargs) -> Dict[str, Any]:
        """Safe wrapper for Weaviate search"""
        elysia_query = {
            "query": query,
            "tenant_id": tenant_id,
            "query_type": kwargs.get("query_type", "search"),
            "collections": kwargs.get("collections", []),
            "max_iterations": kwargs.get("max_iterations", 3)
        }
        
        return await weaviate_client.elysia_query(elysia_query)
    
    def _merge_parallel_results(self, qdrant_result: Optional[Dict[str, Any]], weaviate_result: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        """Merge results from both systems intelligently"""
        
        # If only one system worked, use that
        if weaviate_result and not qdrant_result:
            logger.info("✅ Using Weaviate results (Qdrant failed)")
            return weaviate_result
        
        if qdrant_result and not weaviate_result:
            logger.info("✅ Using Qdrant results (Weaviate failed)")
            return qdrant_result
        
        # If both failed
        if not qdrant_result and not weaviate_result:
            return {
                "error": "Both search systems failed",
                "results": [],
                "total_results": 0
            }
        
        # Both systems worked - prefer Weaviate (newer system)
        logger.info("✅ Both systems worked - preferring Weaviate results")
        
        # Add comparison metadata
        weaviate_result["comparison"] = {
            "qdrant_result_count": len(qdrant_result.get("results", [])) if qdrant_result else 0,
            "weaviate_result_count": len(weaviate_result.get("results", [])) if weaviate_result else 0,
            "systems_compared": True
        }
        
        return weaviate_result
    
    async def add_document(self, document_data: Dict[str, Any]) -> Dict[str, Any]:
        """Add document using current migration strategy"""
        
        if self.migration_mode == MigrationMode.QDRANT_ONLY:
            # Add only to Qdrant
            return await self._add_document_qdrant_only(document_data)
        
        elif self.migration_mode == MigrationMode.WEAVIATE_ONLY:
            # Add only to Weaviate
            return await self._add_document_weaviate_only(document_data)
        
        else:  # PARALLEL mode
            # Add to both systems
            return await self._add_document_parallel(document_data)
    
    async def _add_document_qdrant_only(self, document_data: Dict[str, Any]) -> Dict[str, Any]:
        """Add document to Qdrant only"""
        try:
            result = await cag_client.add_document(document_data)
            return {
                "source": "qdrant_only",
                "result": result,
                "timestamp": datetime.now().isoformat()
            }
        except Exception as e:
            logger.error(f"❌ Qdrant document add failed: {e}")
            raise
    
    async def _add_document_weaviate_only(self, document_data: Dict[str, Any]) -> Dict[str, Any]:
        """Add document to Weaviate only"""
        try:
            # Determine collection name
            tenant_id = document_data.get("tenant_id")
            collection_name = f"nexus_{tenant_id}_documents".lower().replace("-", "_")
            
            result = await weaviate_client.add_document(collection_name, document_data)
            return {
                "source": "weaviate_only",
                "result": result,
                "timestamp": datetime.now().isoformat()
            }
        except Exception as e:
            logger.error(f"❌ Weaviate document add failed: {e}")
            raise
    
    async def _add_document_parallel(self, document_data: Dict[str, Any]) -> Dict[str, Any]:
        """Add document to both systems"""
        try:
            import asyncio
            
            # Add to both systems concurrently
            qdrant_task = asyncio.create_task(
                self._add_document_qdrant_only(document_data)
            )
            
            weaviate_task = asyncio.create_task(
                self._add_document_weaviate_only(document_data)
            )
            
            qdrant_result, weaviate_result = await asyncio.gather(
                qdrant_task, weaviate_task, return_exceptions=True
            )
            
            response = {
                "source": "parallel",
                "timestamp": datetime.now().isoformat(),
                "systems": {}
            }
            
            # Process results
            if isinstance(qdrant_result, Exception):
                response["systems"]["qdrant"] = {"status": "error", "error": str(qdrant_result)}
            else:
                response["systems"]["qdrant"] = {"status": "success", "result": qdrant_result}
            
            if isinstance(weaviate_result, Exception):
                response["systems"]["weaviate"] = {"status": "error", "error": str(weaviate_result)}
            else:
                response["systems"]["weaviate"] = {"status": "success", "result": weaviate_result}
            
            # Use Weaviate result as primary if available
            if not isinstance(weaviate_result, Exception):
                response["result"] = weaviate_result["result"]
            elif not isinstance(qdrant_result, Exception):
                response["result"] = qdrant_result["result"]
            else:
                raise Exception("Both systems failed to add document")
            
            return response
            
        except Exception as e:
            logger.error(f"❌ Parallel document add failed: {e}")
            raise
    
    async def start_migration(self, source_collection: str, target_collection: str, tenant_id: str) -> Dict[str, Any]:
        """Start migration from Qdrant to Weaviate"""
        try:
            logger.info(f"🚀 Starting migration: {source_collection} -> {target_collection}")
            
            migration_data = {
                "source_collection": source_collection,
                "target_collection": target_collection, 
                "tenant_id": tenant_id,
                "batch_size": 100
            }
            
            result = await weaviate_client.migrate_from_qdrant(migration_data)
            
            return {
                "status": "migration_started",
                "migration_id": result.get("migration_id"),
                "details": result,
                "timestamp": datetime.now().isoformat()
            }
            
        except Exception as e:
            logger.error(f"❌ Migration start failed: {e}")
            raise
    
    def get_migration_status(self) -> Dict[str, Any]:
        """Get current migration status and configuration"""
        return {
            "migration_mode": self.migration_mode.value,
            "weaviate_enabled": self.enable_weaviate,
            "available_modes": [mode.value for mode in MigrationMode],
            "description": {
                "qdrant_only": "Using legacy Qdrant/CrewAI system only",
                "parallel": "Using both systems - migration in progress", 
                "weaviate_only": "Using new Weaviate/Elysia system only"
            },
            "next_steps": self._get_next_steps()
        }
    
    def _get_next_steps(self) -> List[str]:
        """Get recommended next steps based on current mode"""
        if self.migration_mode == MigrationMode.QDRANT_ONLY:
            return [
                "Set ENABLE_WEAVIATE=true to enable Weaviate system",
                "Set MIGRATION_MODE=parallel to start parallel testing",
                "Test both systems side by side"
            ]
        elif self.migration_mode == MigrationMode.PARALLEL:
            return [
                "Monitor both systems for stability",
                "Compare result quality between systems",
                "When ready, set MIGRATION_MODE=weaviate_only",
                "After verification, deprecate Qdrant completely"
            ]
        else:  # WEAVIATE_ONLY
            return [
                "Migration complete - using Weaviate/Elysia only",
                "Monitor system performance",
                "Consider removing Qdrant containers to save resources"
            ]


# Global service instance
migration_service = MigrationService()