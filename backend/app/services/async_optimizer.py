"""
Async optimization service for converting blocking operations to async
"""
import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable, Optional, Dict, List
import aiofiles
import aiohttp
from pathlib import Path

logger = logging.getLogger(__name__)


class AsyncOptimizer:
    """Service for optimizing blocking operations with async patterns"""

    def __init__(self, max_workers: int = 4):
        self.executor = ThreadPoolExecutor(max_workers=max_workers)
        self.session: Optional[aiohttp.ClientSession] = None

    async def __aenter__(self):
        """Async context manager entry"""
        self.session = aiohttp.ClientSession()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit"""
        if self.session:
            await self.session.close()
        self.executor.shutdown(wait=True)

    async def run_in_thread(self, func: Callable, *args, **kwargs) -> Any:
        """
        Run a blocking function in a thread pool to make it async.
        Useful for CPU-bound operations or blocking I/O.
        """
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(self.executor, func, *args, **kwargs)

    async def http_get(self, url: str, headers: Optional[Dict[str, str]] = None,
                      timeout: int = 30) -> Dict[str, Any]:
        """
        Async HTTP GET request with proper error handling.
        """
        if not self.session:
            raise RuntimeError("AsyncOptimizer must be used as async context manager")

        try:
            async with self.session.get(url, headers=headers, timeout=timeout) as response:
                response.raise_for_status()
                if response.content_type == 'application/json':
                    return await response.json()
                else:
                    return {'content': await response.text(), 'status': response.status}
        except aiohttp.ClientError as e:
            logger.error(f"HTTP GET failed for {url}: {str(e)}")
            raise

    async def http_post(self, url: str, data: Optional[Dict[str, Any]] = None,
                       headers: Optional[Dict[str, str]] = None, timeout: int = 30) -> Dict[str, Any]:
        """
        Async HTTP POST request with proper error handling.
        """
        if not self.session:
            raise RuntimeError("AsyncOptimizer must be used as async context manager")

        try:
            async with self.session.post(url, json=data, headers=headers, timeout=timeout) as response:
                response.raise_for_status()
                if response.content_type == 'application/json':
                    return await response.json()
                else:
                    return {'content': await response.text(), 'status': response.status}
        except aiohttp.ClientError as e:
            logger.error(f"HTTP POST failed for {url}: {str(e)}")
            raise

    async def read_file_async(self, file_path: str, encoding: str = 'utf-8') -> str:
        """
        Async file reading.
        """
        try:
            async with aiofiles.open(file_path, 'r', encoding=encoding) as f:
                return await f.read()
        except Exception as e:
            logger.error(f"Failed to read file {file_path}: {str(e)}")
            raise

    async def write_file_async(self, file_path: str, content: str, encoding: str = 'utf-8') -> None:
        """
        Async file writing.
        """
        try:
            async with aiofiles.open(file_path, 'w', encoding=encoding) as f:
                await f.write(content)
        except Exception as e:
            logger.error(f"Failed to write file {file_path}: {str(e)}")
            raise

    async def batch_process(self, items: List[Any], processor: Callable,
                           batch_size: int = 10) -> List[Any]:
        """
        Process items in batches asynchronously to improve performance.
        """
        results = []

        for i in range(0, len(items), batch_size):
            batch = items[i:i + batch_size]

            # Process batch concurrently
            tasks = [self.run_in_thread(processor, item) for item in batch]
            batch_results = await asyncio.gather(*tasks, return_exceptions=True)

            # Handle results and exceptions
            for j, result in enumerate(batch_results):
                if isinstance(result, Exception):
                    logger.error(f"Error processing item {i + j}: {str(result)}")
                    results.append(None)  # Or handle error appropriately
                else:
                    results.append(result)

        return results

    async def parallel_http_requests(self, urls: List[str],
                                    headers: Optional[Dict[str, str]] = None,
                                    timeout: int = 30) -> List[Dict[str, Any]]:
        """
        Make multiple HTTP requests in parallel.
        """
        if not self.session:
            raise RuntimeError("AsyncOptimizer must be used as async context manager")

        async def fetch_url(url: str) -> Dict[str, Any]:
            try:
                async with self.session.get(url, headers=headers, timeout=timeout) as response:
                    response.raise_for_status()
                    if response.content_type == 'application/json':
                        return await response.json()
                    else:
                        return {'content': await response.text(), 'status': response.status, 'url': url}
            except Exception as e:
                logger.error(f"Failed to fetch {url}: {str(e)}")
                return {'error': str(e), 'url': url}

        tasks = [fetch_url(url) for url in urls]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Handle exceptions in results
        processed_results = []
        for result in results:
            if isinstance(result, Exception):
                processed_results.append({'error': str(result)})
            else:
                processed_results.append(result)

        return processed_results


class AsyncFileProcessor:
    """Async file processing utilities"""

    @staticmethod
    async def process_large_file(file_path: str, chunk_size: int = 8192) -> str:
        """
        Process large files asynchronously in chunks.
        """
        content = []
        try:
            async with aiofiles.open(file_path, 'r') as f:
                while True:
                    chunk = await f.read(chunk_size)
                    if not chunk:
                        break
                    content.append(chunk)
        except Exception as e:
            logger.error(f"Failed to process large file {file_path}: {str(e)}")
            raise

        return ''.join(content)

    @staticmethod
    async def get_file_info_async(file_path: str) -> Dict[str, Any]:
        """
        Get file information asynchronously.
        """
        try:
            path = Path(file_path)
            if not path.exists():
                raise FileNotFoundError(f"File {file_path} not found")

            # Run stat in thread pool since it's blocking
            loop = asyncio.get_event_loop()
            stat = await loop.run_in_executor(None, path.stat)

            return {
                'path': str(path),
                'size': stat.st_size,
                'modified': stat.st_mtime,
                'created': stat.st_ctime,
                'is_file': path.is_file(),
                'is_dir': path.is_dir(),
                'exists': True
            }
        except Exception as e:
            logger.error(f"Failed to get file info for {file_path}: {str(e)}")
            return {'error': str(e), 'exists': False}


class AsyncDatabaseOptimizer:
    """Async database operation optimizer"""

    def __init__(self, db_session):
        self.db = db_session

    async def bulk_insert_async(self, items: List[Dict[str, Any]], table_name: str) -> int:
        """
        Perform bulk insert asynchronously.
        """
        if not items:
            return 0

        # Run bulk insert in thread pool to avoid blocking
        async_optimizer = AsyncOptimizer()

        def _bulk_insert():
            # This would be the actual bulk insert logic
            # For now, just simulate the operation
            logger.info(f"Bulk inserting {len(items)} items into {table_name}")
            return len(items)

        return await async_optimizer.run_in_thread(_bulk_insert)

    async def execute_query_async(self, query_func: Callable) -> Any:
        """
        Execute database query asynchronously.
        """
        async_optimizer = AsyncOptimizer()
        return await async_optimizer.run_in_thread(query_func)


# Global async optimizer instance
async_optimizer = AsyncOptimizer()


# Convenience functions
async def run_blocking_operation(func: Callable, *args, **kwargs) -> Any:
    """Run a blocking operation asynchronously"""
    return await async_optimizer.run_in_thread(func, *args, **kwargs)


async def http_get_async(url: str, headers: Optional[Dict[str, str]] = None,
                        timeout: int = 30) -> Dict[str, Any]:
    """Async HTTP GET with session reuse"""
    async with AsyncOptimizer() as optimizer:
        return await optimizer.http_get(url, headers, timeout)


async def http_post_async(url: str, data: Optional[Dict[str, Any]] = None,
                         headers: Optional[Dict[str, str]] = None,
                         timeout: int = 30) -> Dict[str, Any]:
    """Async HTTP POST with session reuse"""
    async with AsyncOptimizer() as optimizer:
        return await optimizer.http_post(url, data, headers, timeout)


async def read_file_async(file_path: str, encoding: str = 'utf-8') -> str:
    """Async file reading"""
    return await AsyncFileProcessor.read_file_async(file_path, encoding)


async def write_file_async(file_path: str, content: str, encoding: str = 'utf-8') -> None:
    """Async file writing"""
    async with aiofiles.open(file_path, 'w', encoding=encoding) as f:
        await f.write(content)


async def batch_process_async(items: List[Any], processor: Callable,
                             batch_size: int = 10) -> List[Any]:
    """Process items in batches asynchronously"""
    async with AsyncOptimizer() as optimizer:
        return await optimizer.batch_process(items, processor, batch_size)