import redis
import hashlib
import logging
from typing import Optional, Tuple
from datetime import datetime, timedelta
from app.core.config import settings

logger = logging.getLogger(__name__)

class RedisCache:
    """
    Redis cache service for document caching with size-based TTL strategy.
    """
    
    def __init__(self):
        self.redis_client = redis.Redis(
            host=settings.REDIS_HOST,
            port=settings.REDIS_PORT,
            password=settings.REDIS_PASSWORD,
            decode_responses=False,  # Keep binary for file content
            socket_connect_timeout=5,
            socket_timeout=5,
            retry_on_timeout=True
        )
        
        # Cache TTL strategy based on file size
        self.TTL_SMALL_FILES = 3600   # 1 hour for files < 10MB
        self.TTL_MEDIUM_FILES = 1800  # 30 minutes for files 10-50MB  
        self.TTL_LARGE_FILES = 0      # No cache for files > 50MB
        
        # Size thresholds in bytes
        self.SMALL_FILE_LIMIT = 10 * 1024 * 1024   # 10MB
        self.MEDIUM_FILE_LIMIT = 50 * 1024 * 1024  # 50MB
        
    def _get_cache_key(self, tenant_id: str, object_name: str) -> str:
        """Generate cache key for a document."""
        key_data = f"doc:{tenant_id}:{object_name}"
        return hashlib.sha256(key_data.encode()).hexdigest()[:32]
    
    def _get_metadata_key(self, cache_key: str) -> str:
        """Generate metadata key for a cached document."""
        return f"meta:{cache_key}"
    
    def _get_ttl_for_size(self, file_size: int) -> int:
        """Determine TTL based on file size."""
        if file_size <= self.SMALL_FILE_LIMIT:
            return self.TTL_SMALL_FILES
        elif file_size <= self.MEDIUM_FILE_LIMIT:
            return self.TTL_MEDIUM_FILES
        else:
            return self.TTL_LARGE_FILES
    
    def should_cache(self, file_size: int) -> bool:
        """Determine if file should be cached based on size."""
        return file_size <= self.MEDIUM_FILE_LIMIT
    
    def get(self, tenant_id: str, object_name: str) -> Optional[Tuple[bytes, dict]]:
        """
        Get cached document content and metadata.
        
        Returns:
            Tuple of (file_content, metadata) or None if not found
        """
        try:
            cache_key = self._get_cache_key(tenant_id, object_name)
            metadata_key = self._get_metadata_key(cache_key)
            
            # Get content and metadata in pipeline for efficiency
            pipe = self.redis_client.pipeline()
            pipe.get(cache_key)
            pipe.hgetall(metadata_key)
            results = pipe.execute()
            
            content, metadata = results[0], results[1]
            
            if content is None:
                logger.debug(f"Cache miss for {object_name}")
                return None
            
            # Convert metadata bytes to strings
            if metadata:
                metadata = {k.decode() if isinstance(k, bytes) else k: 
                           v.decode() if isinstance(v, bytes) else v 
                           for k, v in metadata.items()}
            
            logger.debug(f"Cache hit for {object_name}, size: {len(content)} bytes")
            return content, metadata
            
        except Exception as e:
            logger.error(f"Redis cache get error for {object_name}: {e}")
            return None
    
    def set(self, tenant_id: str, object_name: str, content: bytes, 
            metadata: dict, file_size: int) -> bool:
        """
        Cache document content and metadata.
        
        Args:
            tenant_id: Tenant identifier
            object_name: GCS object name
            content: File content as bytes
            metadata: File metadata dict
            file_size: File size in bytes
            
        Returns:
            True if cached successfully, False otherwise
        """
        try:
            # Check if file should be cached
            if not self.should_cache(file_size):
                logger.debug(f"File {object_name} too large to cache ({file_size} bytes)")
                return False
            
            cache_key = self._get_cache_key(tenant_id, object_name)
            metadata_key = self._get_metadata_key(cache_key)
            ttl = self._get_ttl_for_size(file_size)
            
            # Add cache metadata
            cache_metadata = metadata.copy() if metadata else {}
            cache_metadata.update({
                'cached_at': datetime.utcnow().isoformat(),
                'file_size': str(file_size),
                'cache_key': cache_key
            })
            
            # Store content and metadata in pipeline
            pipe = self.redis_client.pipeline()
            pipe.setex(cache_key, ttl, content)
            pipe.hset(metadata_key, mapping=cache_metadata)
            pipe.expire(metadata_key, ttl)
            pipe.execute()
            
            logger.info(f"Cached {object_name} ({file_size} bytes, TTL: {ttl}s)")
            return True
            
        except Exception as e:
            logger.error(f"Redis cache set error for {object_name}: {e}")
            return False
    
    def delete(self, tenant_id: str, object_name: str) -> bool:
        """Delete cached document."""
        try:
            cache_key = self._get_cache_key(tenant_id, object_name)
            metadata_key = self._get_metadata_key(cache_key)
            
            pipe = self.redis_client.pipeline()
            pipe.delete(cache_key)
            pipe.delete(metadata_key)
            results = pipe.execute()
            
            deleted = any(results)
            if deleted:
                logger.info(f"Deleted cached document: {object_name}")
            
            return deleted
            
        except Exception as e:
            logger.error(f"Redis cache delete error for {object_name}: {e}")
            return False
    
    def get_cache_stats(self) -> dict:
        """Get cache statistics."""
        try:
            info = self.redis_client.info('memory')
            keyspace = self.redis_client.info('keyspace')
            
            return {
                'memory_used': info.get('used_memory_human', 'unknown'),
                'memory_peak': info.get('used_memory_peak_human', 'unknown'),
                'total_keys': sum(db.get('keys', 0) for db in keyspace.values()),
                'connected': True
            }
        except Exception as e:
            logger.error(f"Redis stats error: {e}")
            return {'connected': False, 'error': str(e)}
    
    def clear_tenant_cache(self, tenant_id: str) -> int:
        """Clear all cached documents for a tenant."""
        try:
            # Find all keys for this tenant (this is expensive, use carefully)
            pattern = f"*{tenant_id}*"
            keys = self.redis_client.keys(pattern)
            
            if keys:
                deleted = self.redis_client.delete(*keys)
                logger.info(f"Cleared {deleted} cached documents for tenant {tenant_id}")
                return deleted
            
            return 0
            
        except Exception as e:
            logger.error(f"Redis clear tenant cache error for {tenant_id}: {e}")
            return 0
    
    def health_check(self) -> bool:
        """Check if Redis is healthy."""
        try:
            return self.redis_client.ping()
        except Exception:
            return False

# Global instance
redis_cache = RedisCache()