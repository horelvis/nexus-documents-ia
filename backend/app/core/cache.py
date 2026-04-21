# app/core/cache.py
"""
Advanced caching system with Redis, in-memory fallback, and intelligent invalidation
"""
import asyncio
import json
import logging
import pickle
import time
from abc import ABC, abstractmethod
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Union, Callable
from functools import wraps

import redis
from redis import Redis

from app.core.config import settings

logger = logging.getLogger(__name__)


class CacheBackend(ABC):
    """Abstract base class for cache backends"""

    @abstractmethod
    def get(self, key: str) -> Optional[Any]:
        """Get value from cache"""
        pass

    @abstractmethod
    def set(self, key: str, value: Any, ttl: Optional[int] = None) -> bool:
        """Set value in cache with optional TTL"""
        pass

    @abstractmethod
    def delete(self, key: str) -> bool:
        """Delete value from cache"""
        pass

    @abstractmethod
    def exists(self, key: str) -> bool:
        """Check if key exists in cache"""
        pass

    @abstractmethod
    def clear(self) -> bool:
        """Clear all cache entries"""
        pass

    @abstractmethod
    def get_stats(self) -> Dict[str, Any]:
        """Get cache statistics"""
        pass


class RedisCache(CacheBackend):
    """Redis-based cache backend with advanced features"""

    def __init__(self):
        self._redis_client: Optional[Redis] = None
        self._stats = defaultdict(int)
        self._connect()

    def _connect(self):
        """Connect to Redis with advanced configuration"""
        try:
            # Use REDIS_URL if available (for Cloud services), otherwise use individual settings
            if hasattr(settings, 'REDIS_URL') and settings.REDIS_URL:
                self._redis_client = redis.from_url(
                    settings.REDIS_URL,
                    decode_responses=False,  # Keep as bytes for pickle
                    socket_connect_timeout=5,
                    socket_timeout=5,
                    retry_on_timeout=True,
                    health_check_interval=30,
                    max_connections=20
                )
                logger.info(f"✅ Connected to Redis using URL: {settings.REDIS_URL}")
            else:
                self._redis_client = redis.Redis(
                    host=settings.REDIS_HOST,
                    port=settings.REDIS_PORT,
                    password=settings.REDIS_PASSWORD,
                    db=0,
                    decode_responses=False,  # Keep as bytes for pickle
                    socket_connect_timeout=5,
                    socket_timeout=5,
                    retry_on_timeout=True,
                    health_check_interval=30,
                    max_connections=20
                )
                logger.info(f"✅ Connected to Redis at {settings.REDIS_HOST}:{settings.REDIS_PORT}")

            # Test connection
            self._redis_client.ping()
            logger.info("✅ Redis connection test successful")
        except Exception as e:
            logger.error(f"❌ Failed to connect to Redis: {e}")
            self._redis_client = None
            raise

    def get(self, key: str) -> Optional[Any]:
        """Get value from cache with pickle deserialization"""
        if not self._redis_client:
            return None

        try:
            start_time = time.time()
            data = self._redis_client.get(key)
            if data:
                value = pickle.loads(data)
                self._stats['hits'] += 1
                self._stats['get_time'] += time.time() - start_time
                return value
            self._stats['misses'] += 1
            return None
        except Exception as e:
            logger.error(f"Redis GET error for key {key}: {e}")
            self._stats['errors'] += 1
            return None

    def set(self, key: str, value: Any, ttl: Optional[int] = None) -> bool:
        """Set value in cache with pickle serialization"""
        if not self._redis_client:
            return False

        try:
            start_time = time.time()
            data = pickle.dumps(value)
            if ttl:
                result = self._redis_client.setex(key, ttl, data)
            else:
                result = self._redis_client.set(key, data)

            self._stats['sets'] += 1
            self._stats['set_time'] += time.time() - start_time
            return bool(result)
        except Exception as e:
            logger.error(f"Redis SET error for key {key}: {e}")
            self._stats['errors'] += 1
            return False

    def delete(self, key: str) -> bool:
        """Delete key from cache"""
        if not self._redis_client:
            return False

        try:
            result = self._redis_client.delete(key)
            self._stats['deletes'] += 1
            return bool(result)
        except Exception as e:
            logger.error(f"Redis DELETE error for key {key}: {e}")
            self._stats['errors'] += 1
            return False

    def exists(self, key: str) -> bool:
        """Check if key exists"""
        if not self._redis_client:
            return False

        try:
            return bool(self._redis_client.exists(key))
        except Exception as e:
            logger.error(f"Redis EXISTS error for key {key}: {e}")
            self._stats['errors'] += 1
            return False

    def clear(self) -> bool:
        """Clear all cache entries"""
        if not self._redis_client:
            return False

        try:
            result = self._redis_client.flushdb()
            self._stats['clears'] += 1
            return bool(result)
        except Exception as e:
            logger.error(f"Redis CLEAR error: {e}")
            self._stats['errors'] += 1
            return False

    def get_json(self, key: str) -> Optional[Any]:
        """Get JSON value from cache (legacy method)"""
        value = self.get(key)
        if isinstance(value, str):
            try:
                return json.loads(value)
            except json.JSONDecodeError:
                logger.error(f"Failed to decode JSON for key {key}")
        return value

    def set_json(self, key: str, value: Any, ttl: Optional[int] = None) -> bool:
        """Set JSON value in cache (legacy method)"""
        return self.set(key, value, ttl)

    def clear_pattern(self, pattern: str) -> int:
        """Delete all keys matching pattern"""
        if not self._redis_client:
            return 0

        try:
            keys = self._redis_client.keys(pattern)
            if keys:
                result = self._redis_client.delete(*keys)
                self._stats['pattern_deletes'] += 1
                return result
            return 0
        except Exception as e:
            logger.error(f"Redis CLEAR pattern error for {pattern}: {e}")
            self._stats['errors'] += 1
            return 0

    def get_stats(self) -> Dict[str, Any]:
        """Get cache statistics"""
        total_requests = self._stats['hits'] + self._stats['misses']
        hit_rate = (self._stats['hits'] / total_requests * 100) if total_requests > 0 else 0

        return {
            'hits': self._stats['hits'],
            'misses': self._stats['misses'],
            'sets': self._stats['sets'],
            'deletes': self._stats['deletes'],
            'clears': self._stats['clears'],
            'pattern_deletes': self._stats['pattern_deletes'],
            'errors': self._stats['errors'],
            'hit_rate': round(hit_rate, 2),
            'avg_get_time': round(self._stats['get_time'] / max(self._stats['hits'], 1), 4),
            'avg_set_time': round(self._stats['set_time'] / max(self._stats['sets'], 1), 4),
            'connected': self.is_connected
        }

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


class MemoryCache(CacheBackend):
    """In-memory cache backend (fallback)"""

    def __init__(self):
        self._cache: Dict[str, Dict[str, Any]] = {}
        self._stats = defaultdict(int)

    def get(self, key: str) -> Optional[Any]:
        """Get value from memory cache"""
        if key in self._cache:
            entry = self._cache[key]
            if entry.get('expires_at') and datetime.now() > entry['expires_at']:
                # Expired, remove it
                del self._cache[key]
                self._stats['misses'] += 1
                return None
            self._stats['hits'] += 1
            return entry['value']
        self._stats['misses'] += 1
        return None

    def set(self, key: str, value: Any, ttl: Optional[int] = None) -> bool:
        """Set value in memory cache"""
        expires_at = None
        if ttl:
            expires_at = datetime.now() + timedelta(seconds=ttl)

        self._cache[key] = {
            'value': value,
            'expires_at': expires_at,
            'created_at': datetime.now()
        }
        self._stats['sets'] += 1
        return True

    def delete(self, key: str) -> bool:
        """Delete value from memory cache"""
        if key in self._cache:
            del self._cache[key]
            self._stats['deletes'] += 1
            return True
        return False

    def exists(self, key: str) -> bool:
        """Check if key exists in memory cache"""
        if key in self._cache:
            entry = self._cache[key]
            if entry.get('expires_at') and datetime.now() > entry['expires_at']:
                del self._cache[key]
                return False
            return True
        return False

    def clear(self) -> bool:
        """Clear all memory cache entries"""
        self._cache.clear()
        self._stats['clears'] += 1
        return True

    def get_stats(self) -> Dict[str, Any]:
        """Get cache statistics"""
        total_requests = self._stats['hits'] + self._stats['misses']
        hit_rate = (self._stats['hits'] / total_requests * 100) if total_requests > 0 else 0

        return {
            'hits': self._stats['hits'],
            'misses': self._stats['misses'],
            'sets': self._stats['sets'],
            'deletes': self._stats['deletes'],
            'clears': self._stats['clears'],
            'errors': 0,
            'hit_rate': round(hit_rate, 2),
            'cache_size': len(self._cache),
            'connected': True
        }


class DistributedCache:
    """Main cache manager with Redis primary and memory fallback"""

    def __init__(self):
        self.redis_cache = RedisCache()
        self.memory_cache = MemoryCache()
        self.use_redis = True
        self._test_redis_connection()

    def _test_redis_connection(self):
        """Test Redis connection and fallback to memory if needed"""
        try:
            if self.redis_cache.is_connected:
                logger.info("✅ Redis cache connection successful")
            else:
                raise Exception("Redis not connected")
        except Exception as e:
            logger.warning(f"❌ Redis cache connection failed: {str(e)}")
            logger.warning("🔄 Falling back to in-memory cache")
            self.use_redis = False

    def get(self, key: str) -> Optional[Any]:
        """Get value from cache with fallback"""
        if self.use_redis:
            result = self.redis_cache.get(key)
            if result is not None:
                return result

        # Fallback to memory cache
        return self.memory_cache.get(key)

    def get_json(self, key: str) -> Optional[Any]:
        """Get JSON-deserialized value from cache"""
        value = self.get(key)
        if isinstance(value, str):
            try:
                return json.loads(value)
            except json.JSONDecodeError:
                logger.error(f"Failed to decode JSON for key {key}")
        return value

    def set(self, key: str, value: Any, ttl: Optional[int] = None) -> bool:
        """Set value in cache with fallback"""
        success = False

        if self.use_redis:
            success = self.redis_cache.set(key, value, ttl)

        # Always set in memory as backup
        memory_success = self.memory_cache.set(key, value, ttl)

        return success or memory_success

    def set_json(self, key: str, value: Any, ttl: Optional[int] = None) -> bool:
        """Serialize and set JSON value in cache"""
        serialized = value
        if not isinstance(value, (str, bytes)):
            try:
                serialized = json.dumps(value)
            except (TypeError, ValueError) as e:
                logger.error(f"Failed to serialize value for key {key}: {e}")
                return False
        return self.set(key, serialized, ttl)

    def delete(self, key: str) -> bool:
        """Delete value from cache"""
        redis_success = False
        if self.use_redis:
            redis_success = self.redis_cache.delete(key)

        memory_success = self.memory_cache.delete(key)

        return redis_success or memory_success

    def exists(self, key: str) -> bool:
        """Check if key exists in cache"""
        if self.use_redis:
            if self.redis_cache.exists(key):
                return True

        return self.memory_cache.exists(key)

    def clear(self) -> bool:
        """Clear all cache entries"""
        redis_success = False
        if self.use_redis:
            redis_success = self.redis_cache.clear()

        memory_success = self.memory_cache.clear()

        return redis_success or memory_success

    def get_or_set(self, key: str, func: Callable, ttl: Optional[int] = None):
        """Get from cache or compute and cache result"""
        # Try to get from cache first
        cached_value = self.get(key)
        if cached_value is not None:
            logger.debug(f"Cache hit for key: {key}")
            return cached_value

        # Compute value
        logger.debug(f"Cache miss for key: {key}")
        if asyncio.iscoroutinefunction(func):
            # Handle async functions
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    # We're in an async context
                    import concurrent.futures
                    with concurrent.futures.ThreadPoolExecutor() as executor:
                        future = executor.submit(asyncio.run, func())
                        value = future.result()
                else:
                    value = loop.run_until_complete(func())
            except RuntimeError:
                # No event loop, create one
                value = asyncio.run(func())
        else:
            value = func()

        # Cache the result
        self.set(key, value, ttl)

        return value

    def invalidate_pattern(self, pattern: str) -> int:
        """Invalidate all keys matching pattern"""
        deleted_count = 0

        if self.use_redis:
            deleted_count += self.redis_cache.clear_pattern(pattern)

        # For memory cache, we need to check each key
        # This is less efficient but necessary for pattern matching
        keys_to_delete = []
        # Note: Memory cache doesn't support pattern matching efficiently
        # In production, consider using a more sophisticated memory cache

        return deleted_count

    def get_stats(self) -> Dict[str, Any]:
        """Get combined cache statistics"""
        redis_stats = self.redis_cache.get_stats() if self.use_redis else {}
        memory_stats = self.memory_cache.get_stats()

        return {
            'redis': redis_stats,
            'memory': memory_stats,
            'using_redis': self.use_redis,
            'combined_hit_rate': memory_stats.get('hit_rate', 0)  # Simplified
        }


# Global cache instance
cache = DistributedCache()


# Helper functions for common operations
def cache_key(prefix: str, *args) -> str:
    """Generate a cache key with prefix"""
    parts = [prefix] + [str(arg) for arg in args]
    return ":".join(parts)


def user_cache_key(user_id: str, suffix: str) -> str:
    """Generate a user-specific cache key"""
    return cache_key("user", user_id, suffix)


def document_cache_key(document_id: str, suffix: str) -> str:
    """Generate a document-specific cache key"""
    return cache_key("document", document_id, suffix)


# Cache decorators
def cached(ttl: Optional[int] = None, key_prefix: str = ""):
    """Decorator to cache function results"""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            # Generate cache key from function name and arguments
            key_parts = [key_prefix or func.__name__]
            key_parts.extend([str(arg) for arg in args])
            if kwargs:
                key_parts.extend([f"{k}:{v}" for k, v in sorted(kwargs.items())])

            cache_key = ":".join(key_parts)

            # Try to get from cache
            result = cache.get(cache_key)
            if result is not None:
                logger.debug(f"Cache hit for {func.__name__}")
                return result

            # Compute result
            logger.debug(f"Cache miss for {func.__name__}")
            result = func(*args, **kwargs)

            # Cache the result
            cache.set(cache_key, result, ttl)

            return result
        return wrapper
    return decorator


def async_cached(ttl: Optional[int] = None, key_prefix: str = ""):
    """Decorator to cache async function results"""
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            # Generate cache key from function name and arguments
            key_parts = [key_prefix or func.__name__]
            key_parts.extend([str(arg) for arg in args])
            if kwargs:
                key_parts.extend([f"{k}:{v}" for k, v in sorted(kwargs.items())])

            cache_key = ":".join(key_parts)

            # Try to get from cache
            result = cache.get(cache_key)
            if result is not None:
                logger.debug(f"Cache hit for {func.__name__}")
                return result

            # Compute result
            logger.debug(f"Cache miss for {func.__name__}")
            result = await func(*args, **kwargs)

            # Cache the result
            cache.set(cache_key, result, ttl)

            return result
        return wrapper
    return decorator


# Cache invalidation helpers
def invalidate_user_cache(user_id: str):
    """Invalidate all cache entries for a user"""
    pattern = f"user:{user_id}:*"
    cache.invalidate_pattern(pattern)
    logger.info(f"Invalidated cache for user {user_id}")


def invalidate_document_cache(document_id: str):
    """Invalidate all cache entries for a document"""
    pattern = f"document:{document_id}:*"
    cache.invalidate_pattern(pattern)
    logger.info(f"Invalidated cache for document {document_id}")


# Database query result caching decorators
def cached_query(ttl: Optional[int] = None):
    """Decorator for caching database query results"""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            # Create cache key from function name and arguments
            cache_key = f"query:{func.__name__}:{hash(str(args) + str(sorted(kwargs.items())))}"

            # Try to get from cache first
            cached_result = cache.get(cache_key)
            if cached_result is not None:
                logger.debug(f"Query cache hit for {func.__name__}")
                return cached_result

            # Execute query
            logger.debug(f"Query cache miss for {func.__name__}")
            result = func(*args, **kwargs)

            # Cache the result
            cache.set(cache_key, result, ttl or 300)  # Default 5 minutes

            return result
        return wrapper
    return decorator


def async_cached_query(ttl: Optional[int] = None):
    """Decorator for caching async database query results"""
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            # Create cache key from function name and arguments
            cache_key = f"async_query:{func.__name__}:{hash(str(args) + str(sorted(kwargs.items())))}"

            # Try to get from cache first
            cached_result = cache.get(cache_key)
            if cached_result is not None:
                logger.debug(f"Async query cache hit for {func.__name__}")
                return cached_result

            # Execute query
            logger.debug(f"Async query cache miss for {func.__name__}")
            result = await func(*args, **kwargs)

            # Cache the result
            cache.set(cache_key, result, ttl or 300)  # Default 5 minutes

            return result
        return wrapper
    return decorator


# Cache invalidation helpers for common patterns
def invalidate_user_related_cache(user_id: str):
    """Invalidate all user-related cache entries"""
    patterns = [
        f"user:{user_id}:*",
        f"query:*:*{user_id}*",  # Queries that might involve this user
    ]
    for pattern in patterns:
        cache.invalidate_pattern(pattern)
    logger.info(f"Invalidated user-related cache for user {user_id}")


def invalidate_document_related_cache(document_id: str):
    """Invalidate all document-related cache entries"""
    patterns = [
        f"document:{document_id}:*",
        f"query:*:*{document_id}*",  # Queries that might involve this document
    ]
    for pattern in patterns:
        cache.invalidate_pattern(pattern)
    logger.info(f"Invalidated document-related cache for document {document_id}")


# Cache warming utilities
async def warm_cache_for_user(user_id: str, user_service):
    """Pre-populate cache with commonly accessed user data"""
    try:
        # Cache user profile
        user_data = await user_service.get_user_profile(user_id)
        cache.set(f"user:{user_id}:profile", user_data, ttl=600)  # 10 minutes

        # Cache user's recent documents
        recent_docs = await user_service.get_recent_documents(user_id, limit=10)
        cache.set(f"user:{user_id}:recent_docs", recent_docs, ttl=300)  # 5 minutes

        logger.info(f"Warmed cache for user {user_id}")
    except Exception as e:
        logger.warning(f"Failed to warm cache for user {user_id}: {str(e)}")


# Cache statistics and monitoring
def get_cache_stats() -> Dict[str, Any]:
    """Get comprehensive cache statistics"""
    return cache.get_stats()


def log_cache_performance():
    """Log cache performance metrics"""
    stats = get_cache_stats()
    logger.info("Cache Performance Report:")
    logger.info(f"  - Redis Connected: {stats.get('redis', {}).get('connected', False)}")
    logger.info(f"  - Memory Cache Size: {stats.get('memory', {}).get('cache_size', 0)} items")
    logger.info(f"  - Hit Rate: {stats.get('combined_hit_rate', 0):.1f}%")

    redis_stats = stats.get('redis', {})
    if redis_stats:
        logger.info(f"  - Redis Hits: {redis_stats.get('hits', 0)}")
        logger.info(f"  - Redis Misses: {redis_stats.get('misses', 0)}")
        logger.info(f"  - Redis Errors: {redis_stats.get('errors', 0)}")
