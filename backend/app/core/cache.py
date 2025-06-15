# app/core/cache.py
"""
Redis cache service for the application
"""
import redis
import json
import logging
from typing import Optional, Any
from app.core.config import settings

logger = logging.getLogger(__name__)


class RedisCache:
    """Redis cache implementation"""
    
    def __init__(self):
        self._redis_client = None
        self._connect()
    
    def _connect(self):
        """Connect to Redis"""
        try:
            self._redis_client = redis.Redis(
                host=settings.REDIS_HOST,
                port=settings.REDIS_PORT,
                password=settings.REDIS_PASSWORD,
                decode_responses=True,
                socket_connect_timeout=5,
                socket_timeout=5,
                retry_on_timeout=True,
                health_check_interval=30
            )
            # Test connection
            self._redis_client.ping()
            logger.info(f"✅ Connected to Redis at {settings.REDIS_HOST}:{settings.REDIS_PORT}")
        except Exception as e:
            logger.error(f"❌ Failed to connect to Redis: {e}")
            self._redis_client = None
    
    def get(self, key: str) -> Optional[str]:
        """Get value from cache"""
        if not self._redis_client:
            return None
        
        try:
            return self._redis_client.get(key)
        except Exception as e:
            logger.error(f"Redis GET error for key {key}: {e}")
            return None
    
    def set(self, key: str, value: str, ttl: int = 300):
        """Set value in cache with TTL in seconds"""
        if not self._redis_client:
            return False
        
        try:
            return self._redis_client.setex(key, ttl, value)
        except Exception as e:
            logger.error(f"Redis SET error for key {key}: {e}")
            return False
    
    def delete(self, key: str) -> bool:
        """Delete key from cache"""
        if not self._redis_client:
            return False
        
        try:
            return bool(self._redis_client.delete(key))
        except Exception as e:
            logger.error(f"Redis DELETE error for key {key}: {e}")
            return False
    
    def exists(self, key: str) -> bool:
        """Check if key exists"""
        if not self._redis_client:
            return False
        
        try:
            return bool(self._redis_client.exists(key))
        except Exception as e:
            logger.error(f"Redis EXISTS error for key {key}: {e}")
            return False
    
    def get_json(self, key: str) -> Optional[Any]:
        """Get JSON value from cache"""
        value = self.get(key)
        if value:
            try:
                return json.loads(value)
            except json.JSONDecodeError:
                logger.error(f"Failed to decode JSON for key {key}")
        return None
    
    def set_json(self, key: str, value: Any, ttl: int = 300) -> bool:
        """Set JSON value in cache"""
        try:
            json_value = json.dumps(value)
            return self.set(key, json_value, ttl)
        except Exception as e:
            logger.error(f"Failed to encode JSON for key {key}: {e}")
            return False
    
    def clear_pattern(self, pattern: str) -> int:
        """Delete all keys matching pattern"""
        if not self._redis_client:
            return 0
        
        try:
            keys = self._redis_client.keys(pattern)
            if keys:
                return self._redis_client.delete(*keys)
            return 0
        except Exception as e:
            logger.error(f"Redis CLEAR pattern error for {pattern}: {e}")
            return 0
    
    @property
    def is_connected(self) -> bool:
        """Check if Redis is connected"""
        if not self._redis_client:
            return False
        
        try:
            self._redis_client.ping()
            return True
        except:
            return False


# Singleton instance
cache = RedisCache()


# Helper functions for common operations
def cache_key(prefix: str, *args) -> str:
    """Generate a cache key with prefix"""
    parts = [prefix] + [str(arg) for arg in args]
    return ":".join(parts)


def user_cache_key(user_id: str, suffix: str) -> str:
    """Generate a user-specific cache key"""
    return cache_key("user", user_id, suffix)


def tenant_cache_key(tenant_id: str, suffix: str) -> str:
    """Generate a tenant-specific cache key"""
    return cache_key("tenant", tenant_id, suffix)